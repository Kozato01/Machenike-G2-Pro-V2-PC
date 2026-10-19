"""KeyLinker BLE protocol (Machenike G2 Pro V2, firmware anuncia "G5Pro_V2"), reconstruído do app
Android com.pulsenet.inputset 3.73 e confirmado no controle real. Mapa completo em docs/PROTOCOLO.md.

Pacote claro: [cmd, b1, b2, rand, *payload, crc8]  ->  scramble() e escrito em WRITE_CHAR.
  b1 = len(payload)+5 (escritas de config: contador de 3 bits | len+5)
  b2 = seq (escritas de config: paridade | índice de página | contador)
Toda resposta chega em NOTIFY_CHAR como cmd 25 (0x19) ecoando o b2 do pedido.

uso:  python keylinker.py              -> autoteste
      python keylinker.py scan         -> lista dispositivos BLE
      python keylinker.py dump [ADDR]  -> lê toda a configuração do controle (só leitura) e imprime JSON
"""
import asyncio
import json
import random
import sys

SERVICE = "d7f010e0-660d-46e9-96c3-19c4148bdab5"
WRITE_CHAR = "d7f010e1-660d-46e9-96c3-19c4148bdab5"
NOTIFY_CHAR = "d7f010e2-660d-46e9-96c3-19c4148bdab5"
ADDR_PREFIXES = ("98:B6:ED:", "98:B6:E9:")  # lado BLE de configuração (o clássico é 98:B6:EC:)

CRC_TABLE = [
    0, 121, 242, 139, 51, 74, 193, 184, 102, 31, 148, 237, 85, 44, 167, 222, 204, 181, 62, 71, 255, 134, 13, 116, 170, 211,
    88, 33, 153, 224, 107, 18, 79, 54, 189, 196, 124, 5, 142, 247, 41, 80, 219, 162, 26, 99, 232, 145, 131, 250, 113, 8,
    176, 201, 66, 59, 229, 156, 23, 110, 214, 175, 36, 93, 158, 231, 108, 21, 173, 212, 95, 38, 248, 129, 10, 115, 203,
    178, 57, 64, 82, 43, 160, 217, 97, 24, 147, 234, 52, 77, 198, 191, 7, 126, 245, 140, 209, 168, 35, 90, 226, 155, 16,
    105, 183, 206, 69, 60, 132, 253, 118, 15, 29, 100, 239, 150, 46, 87, 220, 165, 123, 2, 137, 240, 72, 49, 186, 195,
    235, 146, 25, 96, 216, 161, 42, 83, 141, 244, 127, 6, 190, 199, 76, 53, 39, 94, 213, 172, 20, 109, 230, 159, 65, 56,
    179, 202, 114, 11, 128, 249, 164, 221, 86, 47, 151, 238, 101, 28, 194, 187, 48, 73, 241, 136, 3, 122, 104, 17, 154,
    227, 91, 34, 169, 208, 14, 119, 252, 133, 61, 68, 207, 182, 117, 12, 135, 254, 70, 63, 180, 205, 19, 106, 225, 152,
    32, 89, 210, 171, 185, 192, 75, 50, 138, 243, 120, 1, 223, 166, 45, 84, 236, 149, 30, 103, 58, 67, 200, 177, 9, 112,
    251, 130, 92, 37, 174, 215, 111, 22, 157, 228, 246, 143, 4, 125, 197, 188, 55, 78, 144, 233, 98, 27, 163, 218, 81, 40]
G = [51, 99, 157, 121, 242, 219, 162, 26, 170, 33, 139, 232, 116, 211, 88]
H = [161, 82, 213, 163, 245, 137, 246, 143, 240, 157, 72, 147, 234, 52, 49, 186, 195, 77, 198, 235,
     73, 96, 216, 163, 218, 42, 83, 141, 244, 97, 24, 191, 174, 215, 111, 81, 228, 160, 217, 146]

# util/c.java: códigos de tecla (2048 = tecla vazia, só na UI)
KEYS = {1: "A", 2: "B", 3: "X", 4: "Y", 5: "L1", 6: "R1", 7: "L2", 8: "R2", 9: "Select", 10: "Start", 11: "L3",
        12: "R3", 13: "Baixo", 14: "Cima", 15: "Direita", 16: "Esquerda", 17: "Home", 18: "Stick E", 19: "Stick D",
        20: "L4", 21: "R4", 22: "L5", 23: "R5", 24: "ML", 25: "MR", 26: "MC", 27: "M", 95: "Captura", 96: "Turbo",
        93: "−", 94: "+", 97: "ML", 98: "MR", 99: "Modo", 100: "Fn", 101: "SL", 102: "SR",
        103: "M1", 104: "M2", 105: "M3", 106: "M4", 107: "M5", 108: "M6", 2048: "(vazia)"}
NO_SHUTDOWN = 357913  # minutos; FF FF FF FF no fio ("∞" no app)


def crc8(data):
    c = 0
    for b in data:
        c = CRC_TABLE[c ^ b]
    return c


def scramble(p):  # e.h()
    b2, b3 = p[2], p[3]
    o = list(p)
    o[0] = (p[0] ^ (b2 + b3 - 154)) & 0xFF
    o[1] = (p[1] ^ (b2 + b3 + 155)) & 0xFF
    o[2] = ((b2 - 173) ^ b3) & 0xFF
    o[3] = ((b3 + 191) ^ 219) & 0xFF
    for i in range(4, len(p) - 1):
        o[i] = (p[i] ^ (b2 + b3 - G[i - 4])) & 0xFF
    k = (o[3] & 2) * 10
    return bytes(x ^ H[k + i] for i, x in enumerate(o))


def unscramble(p):  # e.g()
    k = 20 if (p[3] ^ H[3]) & 2 else 0
    o = [x ^ H[k + i] for i, x in enumerate(p)]
    o[3] = ((o[3] ^ 219) - 191) & 0xFF
    o[2] = ((o[2] ^ o[3]) + 173) & 0xFF
    o[1] = (o[1] ^ (o[2] + o[3] + 155)) & 0xFF
    o[0] = (o[0] ^ (o[2] + o[3] - 154)) & 0xFF
    for i in range(4, len(p) - 1):
        o[i] = (o[i] ^ (o[2] + o[3] - G[i - 4])) & 0xFF
    return bytes(o)


class Codec:
    """Contadores dos cabeçalhos (e.java K/I/p)."""

    def __init__(self):
        self.n = self.c = self.d = 0

    def seq(self):  # K(): b2 de leituras; bit alto alterna a cada pacote
        self.n += 1
        return self.n % 128 + (128 if self.n % 2 == 0 else 0)

    def page(self, i):  # I(): b2 de escritas de config = paridade | página (4 bits) | contador%8
        self.c += 1
        return (self.c % 2) << 7 | (i & 15) << 3 | self.c % 8

    def count(self, n):  # p(): b1 de escritas de config = contador 7..0 (3 bits) | len+5
        self.d = (self.d - 1) % 8
        return self.d << 5 | (n + 5)

    def frame(self, cmd, payload=(), b1=None, b2=None):
        b1 = len(payload) + 5 if b1 is None else b1
        b2 = self.seq() if b2 is None else b2
        p = [cmd, b1, b2, random.randrange(256), *payload]
        return scramble(bytes(p + [crc8(p)])), b2

    def build(self, cmd, payload=()):
        return self.frame(cmd, payload)[0]


def parse(raw):
    """-> (cmd, b2, payload) ou None se o CRC não bate."""
    p = unscramble(raw)
    if crc8(p[:-1]) != p[-1]:
        return None
    return p[0], p[2], p[4:-1]


# ---------- decodificadores (payload da resposta 0x19, sem o cabeçalho) ----------

def le32(b):
    return b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24


def keys_rle(seq):  # z1.i.w: byte > 128 estende o código anterior em (v-129) códigos seguidos
    out = []
    for v in seq:
        if v > 128 and out:
            out += range(out[-1] + 1, out[-1] + v - 128)
        else:
            out.append(v)
    return out


def bits(mask_bytes, keys):  # máscara LSB-first sobre a lista de teclas
    m = int.from_bytes(bytes(mask_bytes), "little")
    return [k for i, k in enumerate(keys) if m >> i & 1]


def decode_identity(p):  # 145 -> b1.S0()
    c = p[1:1 + p[0]]
    out = {"vid": f"{c[0]:02x}{c[1]:02x}", "pid": f"{c[2]:02x}{c[3]:02x}", "device_id": c[2] >> 4,
           "firmware": f"{c[4]:x}.{c[5]:02x}"}
    if len(c) == 7:
        gen, model = c[6] >> 5, c[6] & 15
        out |= {"model": model, "sensor_bit": c[6] >> 4 & 1,
                "family": (1 if model in (0, 7, 8) else 2) if gen == 2 else gen}  # 2 = "host" (telas CK)
    return out


def decode_features(p):  # 176 [0,1] -> CKAdvancedActivity.p2 / z1.i.A..E,x,y,z
    f = p[1:]
    return {"sticks": {"left": bool(f[0] & 2), "right": bool(f[0] & 1)},
            "triggers": {"left": bool(f[1] & 2), "right": bool(f[1] & 1)},
            "motors": [i + 1 for i in range(4) if f[2] >> i & 1],
            "turbo": f[3] > 0,
            "macros": [n for i, n in enumerate(("M1", "M2", "M3", "M4", "M5", "M6", "ML", "MR")) if f[4] >> i & 1],
            "remap": f[5] > 0, "remap_extra_list": bool(f[5] & 2),
            "lights": [i + 1 for i in range(4) if f[6] >> i & 1],
            "macro_new_format": f[4] > 0 and bool(f[7] & 2),  # j0.f2767j (ConnectionActivity.r)
            "sensor": f[9] > 0, "raw": p.hex()}


def decode_stick(s):  # z1.i.c/i (7 bytes por lado)
    return {"deadzone": s[0], "max": 100 - s[1], "curve": list(s[2:6]),
            "invert_x": bool(s[6] & 1), "invert_y": bool(s[6] & 2), "swap": bool(s[6] & 4)}


def decode_trigger(s):  # z1.i.d/j: curso 0..200
    return {"start": s[0], "end": 200 - s[1], "curve": list(s[2:6]), "swap": bool(s[6] & 4)}


def decode_pair(p, one):  # 177/178: [14, E(7), D(7)]
    d = p[1:]
    return {"left": one(d[0:7]), "right": one(d[7:14])}


def decode_motor(p):  # 179 -> z1.i.h
    d = p[1:]
    t = le32(d[4:8])
    return {"motors": list(d[0:4]), "shutdown_min": NO_SHUTDOWN if t == 0xFFFFFFFF else t * 5 // 60000}


def decode_light(d):  # 183 -> z1.i.b, 6 bytes por zona
    return [{"rgb": list(d[i:i + 3]), "speed": (d[i + 4] & 15) << 8 | d[i + 3], "breath": bool(d[i + 4] & 128),
             "brightness": d[i + 5]} for i in range(0, len(d) - 5, 6)]


def decode_turbo(keys_data, p):  # 176·4 + 180 -> z1.i.s/r/q/u/t/p
    n = keys_data[0]
    manual = keys_rle(keys_data[1:])[:n]
    rest, got, i = keys_data[1:], 0, 0
    while i < len(rest) and got < n:  # pula a primeira lista para achar a de "auto"
        got += rest[i] - 129 if rest[i] > 128 else 1
        i += 1
    auto = keys_rle(rest[i + 1:])
    d = p[1:]
    return {"keys": manual, "auto_capable": auto, "speed": d[0] * 10, "manual_on": bits(d[3:6], manual),
            "auto_on": bits(d[6:9], auto), "extra": [d[1], d[2], *d[9:13]]}


def decode_remap(keys_data, map_data):  # 176·3 + 182 -> z1.i.v: 0 = padrão, própria tecla = vazia
    keys = keys_rle(keys_data[1:])
    out = {}
    for i, k in enumerate(keys):
        t = map_data[i] if i < len(map_data) else 0
        out[k] = k if t == 0 else (2048 if t == k else t)
    return out


def decode_macro(idx, d, keys):  # 181 -> z1.i.f/e (formato antigo)
    """Passo = máscara de 24 bits LSB-first sobre a lista de teclas de macro (1 bit por tecla,
    4 bits por stick: 0..7 = direção-1, >=8 = parado) + duração em unidades de 5 ms."""
    head = {"index": idx, "loop_ms": ((d[1] & 15) << 8 | d[0]) * 5, "loop": bool(d[1] & 128)}
    steps = []
    for i in range(2, len(d) - 4, 5):
        m, pos = int.from_bytes(d[i:i + 3], "little"), 0
        step = {"ms": ((d[i + 4] << 8) | d[i + 3]) * 5, "keys": []}
        for k in keys:
            if k in (18, 19):
                v = m >> pos & 15
                pos += 4
                if v < 8:
                    step["stick_left" if k == 18 else "stick_right"] = v + 1
            else:
                if m >> pos & 1:
                    step["keys"].append(k)
                pos += 1
        steps.append(step)
    full = 2 + 5 * len(steps)
    tail = {"tail": list(d[full:])} if len(d) > full else {}  # M3/M4 de fábrica terminam com 4 bytes soltos
    return head | {"steps": steps} | tail


def decode_status(p):  # resposta ao keepalive 29 -> ButtonTestActivity.q0 / b1.s0
    c = p[1:]
    b = c[3]
    level = 2 if b & 0x20 else 3 if b & 0x40 else 4 if b & 0x80 else 1  # 1 = quase vazia ... 4 = cheia
    return {"battery": level, "charging": bool(b & 0x10), "confirm_key": c[8] if len(c) > 8 else None}


def decode_events(p):  # 0x1F: [tamanho, eventos...]; sticks e gatilhos trazem valor corrigido e bruto
    d, out, i = p[1:], [], 0
    while i + 1 < len(d):
        down, code = d[i], d[i + 1]
        if code in (18, 19) and i + 5 < len(d):
            out.append({"code": code, "x": d[i + 2], "y": d[i + 3], "raw_x": d[i + 4], "raw_y": d[i + 5]})
            i += 6
        elif code in (7, 8) and i + 3 < len(d):
            out.append({"code": code, "value": d[i + 2], "raw": d[i + 3]})
            i += 4
        else:
            out.append({"code": code, "down": bool(down)})
            i += 2
    return out


# keepalive 29 [5,223,171,0,X,Y] (e.c0): o app o envia a cada 750 ms; o modo escolhe o que o controle transmite
MODES = {"normal": (10, 2), "teste": (6, 5), "analogicos": (6, 2), "motor": (10, 3), "leitura": (2, 12)}
CALIBRATE = (29, [3, 223, 171, 16])  # e.d0(): LED pisca; controle parado na mesa; apertar a tecla de confirmação


# ---------- codificadores de escrita ----------

def encode_sticks(left, right):  # cmd 49 -> z1.i.k
    def one(s):
        return [s["deadzone"], 100 - s["max"], *s["curve"], s["invert_x"] | s["invert_y"] << 1 | s["swap"] << 2]
    return [14, *one(left), *one(right)]


def encode_triggers(left, right):  # cmd 50 -> z1.i.o
    def one(s):
        return [s["start"], 200 - s["end"], *s["curve"], s["swap"] << 2]
    return [14, *one(left), *one(right)]


def encode_motor(motors, shutdown_min):  # cmd 51 -> z1.i.g
    t = 0xFFFFFFFF if shutdown_min >= NO_SHUTDOWN else shutdown_min * 60000 // 5
    return [8, *motors, *t.to_bytes(4, "little")]


def encode_lights(zones):  # cmd 55 -> b1.z1 (antes de paginar)
    d = []
    for z in zones:
        d += [*z["rgb"], z["speed"] & 255, z["breath"] << 7 | z["speed"] >> 8 & 15, z["brightness"]]
    return [len(d), *d]


def encode_turbo(t):  # cmd 52 -> b1.F1; as duas máscaras são montadas sobre a lista "keys", como no app
    def mask(on):
        return list(sum(1 << i for i, k in enumerate(t["keys"]) if k in on).to_bytes(3, "little"))
    return [13, t["speed"] // 10, *t["extra"][:2], *mask(t["manual_on"]), *mask(t["auto_on"]), *t["extra"][2:6]]


def encode_remap(remap):  # cmd 54 -> b1.w1 (antes de paginar)
    if all(t == k for k, t in remap.items()):
        return [0]
    return [len(remap), *(0 if t == k else (k if t == 2048 else t) for k, t in remap.items())]


def encode_macro(m, keys):  # cmd 53 -> b1.B1 (formato antigo); inverso de decode_macro, com o byte de total
    """Macro vazia = [0] (o app apaga assim). Passo: máscara de 24 bits LSB-first + duração em 5 ms."""
    steps = m.get("steps") or []
    if m.get("empty") or not steps:
        return [0]
    loop = m.get("loop_ms", 0) // 5
    out = [len(steps) * 5 + 2, loop & 255, int(bool(m.get("loop"))) << 7 | loop >> 8 & 15]
    for st in steps:
        mask, pos = 0, 0
        for k in keys:
            if k in (18, 19):
                v = st.get("stick_left" if k == 18 else "stick_right")
                mask |= (v - 1 if v else 8) << pos
                pos += 4
            else:
                mask |= int(k in st["keys"]) << pos
                pos += 1
        d = st["ms"] // 5
        out += [*mask.to_bytes(3, "little"), d & 255, d >> 8 & 255]
    out += m.get("tail", [])  # devolvido intacto: a regravação fica idêntica
    out[0] = len(out) - 1
    return out


def pages(data, size=15):
    return [data[i:i + size] for i in range(0, len(data), size)] or [[]]


MACRO_SLOTS = ("M1", "M2", "M3", "M4", "M5", "M6", "ML", "MR")
# seções graváveis, todas validadas no hardware com regravação idêntica (ACK 02 DF AA + releitura igual)
WRITERS = {
    "sticks": (49, lambda v: encode_sticks(v["left"], v["right"])),
    "triggers": (50, lambda v: encode_triggers(v["left"], v["right"])),
    "motor": (51, lambda v: encode_motor(v["motors"], v["shutdown_min"])),
    "turbo": (52, lambda v: encode_turbo(v)),
    "remap": (54, lambda v: encode_remap(v)),
    "lights": (55, lambda v: encode_lights(v)),
}


# ---------- sessão BLE ----------

class Session:
    def __init__(self, client):
        self.client = client
        self.codec = Codec()
        self.waiting = {}
        self.events = []  # notificações que não são resposta (0x1F fluxo, 0x20/0x23 estado, 0x28)
        self.on_event = None  # se definido, recebe essas notificações em vez da lista (sessões longas)

    async def start(self):
        await self.client.start_notify(NOTIFY_CHAR, self._on)

    def _on(self, _, data):
        p = unscramble(bytes(data))
        if crc8(p[:-1]) != p[-1]:
            return
        fut = self.waiting.pop(p[2], None) if p[0] == 0x19 else None
        if fut and not fut.done():
            fut.set_result(bytes(p[4:-1]))
        elif self.on_event:
            self.on_event(bytes(p))
        else:
            self.events.append(bytes(p))

    async def send(self, cmd, payload=(), b1=None, b2=None, timeout=2.0):
        pkt, b2 = self.codec.frame(cmd, payload, b1, b2)
        fut = asyncio.get_running_loop().create_future()
        self.waiting[b2] = fut
        await self.client.write_gatt_char(WRITE_CHAR, pkt, response=True)
        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.waiting.pop(b2, None)
            raise TimeoutError(f"sem resposta ao cmd {cmd} {list(payload)}")

    async def fire(self, cmd, payload=()):  # comandos que não respondem (27, calibração)
        await self.client.write_gatt_char(WRITE_CHAR, self.codec.frame(cmd, payload)[0], response=True)

    async def keepalive(self, mode="normal"):
        return decode_status(await self.send(29, [5, 223, 171, 0, *MODES[mode]]))

    async def write(self, cmd, data, slot=None):
        """Escrita de config paginada em blocos de 15 bytes, um ACK (0x19) por página.
        b1 = contador 7..0 | len+5 (cmd 53: nº da macro | len+5); b2 = paridade | página | contador."""
        acks = []
        for i, chunk in enumerate(pages(list(data))):
            b1 = self.codec.count(len(chunk)) if slot is None else slot << 5 | len(chunk) + 5
            acks.append(await self.send(cmd, chunk, b1=b1, b2=self.codec.page(i)))
        return acks

    async def read_paged(self, cmd, payload_for_page, max_pages=32):
        """Primeira página: [total, dados...]; seguintes: [dados...]. Pede página+1 até completar."""
        data, total = [], None
        for page in range(max_pages):
            r = await self.send(cmd, payload_for_page(page))
            if total is None:
                total, r = r[0], r[1:]
            data += r
            if len(data) >= total or not r:
                return bytes(data[:total])
        raise RuntimeError(f"cmd {cmd}: mais de {max_pages} páginas")

    # leituras por seção (valores crus: códigos de tecla como int)
    async def read_identity(self):
        return decode_identity(await self.send(145))

    async def read_features(self):
        return decode_features(await self.send(176, [0, 1]))

    async def read_sticks(self):
        return decode_pair(await self.send(177, [0]), decode_stick)

    async def read_triggers(self):
        return decode_pair(await self.send(178, [0]), decode_trigger)

    async def read_motor(self):
        return decode_motor(await self.send(179, [0]))

    async def read_turbo(self):
        return decode_turbo(await self.read_paged(176, lambda p: [p, 4]), await self.send(180, [0]))

    async def read_remap(self):
        keys = await self.read_paged(176, lambda p: [p, 3])
        return decode_remap(keys, await self.read_paged(182, lambda p: [p]))

    async def read_lights(self):
        return decode_light(await self.read_paged(183, lambda p: [p]))

    async def apply_macro(self, index, macro, keys):
        """Grava uma macro (slot 0 = M1) e devolve todas as macros relidas."""
        await self.write(53, encode_macro(macro, keys), slot=index)
        return await self.read_macros(self.macro_slots)

    async def read_macros(self, slots):
        self.macro_slots = slots
        keys = keys_rle((await self.read_paged(176, lambda p: [p, 5]))[1:])
        out = {"keys": keys, "slots": []}
        for i, name in enumerate(MACRO_SLOTS):
            if name in slots:
                d = await self.read_paged(181, lambda p, i=i: [p, i])
                out["slots"].append({"name": name} | (decode_macro(i, d, keys) if d else {"empty": True}))
        return out

    async def read_all(self):
        """Handshake + todas as seções que o controle declara ter."""
        ident = await self.read_identity()
        feat = await self.read_features()
        out = {"identity": ident, "features": feat}
        if feat["remap"]:
            out["remap"] = await self.read_remap()
        if feat["sticks"]["left"] or feat["sticks"]["right"]:
            out["sticks"] = await self.read_sticks()
        if feat["triggers"]["left"] or feat["triggers"]["right"]:
            out["triggers"] = await self.read_triggers()
        out["motor"] = await self.read_motor()
        if feat["turbo"]:
            out["turbo"] = await self.read_turbo()
        if feat["lights"]:
            out["lights"] = await self.read_lights()
        if feat["macros"]:
            out["macros"] = await self.read_macros(feat["macros"])
        return out

    async def apply(self, section, value):
        """Grava uma seção e devolve o que o controle guardou (releitura)."""
        cmd, enc = WRITERS[section]
        await self.write(cmd, enc(value))
        return await getattr(self, "read_" + section)()

    async def dump(self):  # versão legível para o CLI
        out = await self.read_all()
        if "remap" in out:
            out["remap"] = {KEYS.get(k, k): KEYS.get(t, t) for k, t in out["remap"].items()}
        if "turbo" in out:
            out["turbo"] = {k: [KEYS.get(x, x) for x in v] if k in ("keys", "auto_capable", "manual_on", "auto_on")
                            else v for k, v in out["turbo"].items()}
        if "macros" in out:
            out["macros"]["keys"] = [KEYS.get(k, k) for k in out["macros"]["keys"]]
        out["events"] = [e.hex() for e in self.events]
        return out


async def find(timeout=8):
    from bleak import BleakScanner
    for d, adv in (await BleakScanner.discover(timeout=timeout, return_adv=True)).values():
        if d.address.upper().startswith(ADDR_PREFIXES) or SERVICE in [u.lower() for u in adv.service_uuids]:
            return d.address
    return None


async def scan():
    from bleak import BleakScanner
    for d, adv in (await BleakScanner.discover(timeout=8, return_adv=True)).values():
        mark = " <== KeyLinker" if d.address.upper().startswith(ADDR_PREFIXES) else ""
        print(f"{d.address}  rssi={adv.rssi:4}  {d.name or '?'}{mark}")


async def dump(addr=None):
    from bleak import BleakClient
    addr = addr or await find()
    if not addr:
        sys.exit("controle não encontrado (Bluetooth ligado? controle ligado?)")
    async with BleakClient(addr, timeout=20) as c:
        s = Session(c)
        await s.start()
        print(json.dumps({"address": addr} | await s.dump(), ensure_ascii=False, indent=1))


def selftest():
    c = Codec()
    for cmd, pl in ((145, []), (176, [0, 1]), (49, list(range(15)))):
        pkt = c.build(cmd, pl)
        assert parse(pkt) is not None and parse(pkt)[0] == cmd and list(parse(pkt)[2]) == pl, (cmd, pkt.hex())
    assert [c.seq() for _ in range(4)] == [132, 5, 134, 7]
    cc = Codec()
    assert [cc.count(15) >> 5 for _ in range(9)] == [7, 6, 5, 4, 3, 2, 1, 0, 7]
    cc = Codec()
    assert [cc.page(0) for _ in range(3)] == [0b10000001, 0b00000010, 0b10000011] and cc.page(2) & 0x78 == 2 << 3
    # pacotes reais do controle (2026-10-18): resposta ao 145 e ao 176 [0,1]
    cmd, b2, pl = parse(bytes.fromhex("20c885b00a9d383ce04f341d6d"))
    assert (cmd, b2) == (25, 1) and decode_identity(pl) == {
        "vid": "1006", "pid": "200c", "device_id": 2, "firmware": "1.44", "model": 2, "sensor_bit": 1, "family": 2}
    cmd, b2, pl = parse(bytes.fromhex("691e5c68705966d41496280787a527a8"))
    f = decode_features(pl)
    assert (cmd, b2) == (25, 130) and f["macros"] == ["M1", "M2", "M3", "M4"] and f["motors"] == [1, 2]
    assert f["lights"] == [1] and f["remap"] and f["turbo"] and not f["sensor"] and not f["macro_new_format"]
    # ida e volta dos codificadores
    st = {"deadzone": 5, "max": 97, "curve": [85, 85, 170, 170], "invert_x": False, "invert_y": True, "swap": False}
    assert decode_pair(bytes(encode_sticks(st, st)), decode_stick) == {"left": st, "right": st}
    tr = {"start": 10, "end": 190, "curve": [35, 35, 136, 204], "swap": True}
    assert decode_pair(bytes(encode_triggers(tr, tr)), decode_trigger) == {"left": tr, "right": tr}
    assert decode_motor(bytes(encode_motor([200, 150, 0, 0], 10))) == {"motors": [200, 150, 0, 0], "shutdown_min": 10}
    assert decode_motor(bytes(encode_motor([1, 2, 3, 4], NO_SHUTDOWN)))["shutdown_min"] == NO_SHUTDOWN
    z = [{"rgb": [255, 0, 64], "speed": 300, "breath": True, "brightness": 80}]
    assert decode_light(bytes(encode_lights(z)[1:])) == z
    keys = [1, 2, 3, 4, 103, 104]
    rm = {1: 1, 2: 3, 3: 2048, 4: 4, 103: 1, 104: 104}
    assert decode_remap(bytes([6, 1, 132, 103, 130]), bytes(encode_remap(rm)[1:])) == rm and encode_remap(
        dict(zip(keys, keys))) == [0]
    assert keys_rle([1, 132, 103, 130]) == [1, 2, 3, 4, 103, 104]
    td = bytes([2, 1, 2, 1, 2])  # 2 teclas manuais (A,B), 1 auto (B)
    t = decode_turbo(td, bytes([13, 5, 0, 0, 3, 0, 0, 1, 0, 0, 0, 0, 0, 0]))
    assert t["keys"] == [1, 2] and t["auto_capable"] == [2] and t["manual_on"] == [1, 2] and t["auto_on"] == [2]
    t2 = decode_turbo(bytes([2, 1, 130, 2, 1, 130]), bytes(encode_turbo(
        {"keys": [1, 2], "speed": 80, "manual_on": [2], "auto_on": [1], "extra": [0, 0, 88, 2, 88, 2]})))
    assert (t2["speed"], t2["manual_on"], t2["auto_on"], t2["extra"]) == (80, [2], [1], [0, 0, 88, 2, 88, 2])
    assert pages(list(range(31))) == [list(range(15)), list(range(15, 30)), [30]]
    # pacotes reais (2026-10-18): resposta ao keepalive e eventos 0x1F do modo de teste
    assert decode_status(bytes.fromhex("09dfaa00801d0100005e")) == {"battery": 4, "charging": False, "confirm_key": 94}
    assert decode_events(bytes.fromhex("0a0008000300128080" "7f70")) == [
        {"code": 8, "value": 0, "raw": 3}, {"code": 18, "x": 128, "y": 128, "raw_x": 127, "raw_y": 112}]
    assert decode_events(bytes([4, 1, 1, 0, 2])) == [{"code": 1, "down": True}, {"code": 2, "down": False}]
    mac = decode_macro(0, bytes([20, 0x80, 0b00000101, 0b0011_0000, 0, 10, 0]), [1, 2, 3, 18, 4])
    assert encode_macro(mac, [1, 2, 3, 18, 4]) == [7, 20, 0x80, 0b00000101, 0, 0, 10, 0]  # bits além da lista não voltam
    assert encode_macro({"empty": True}, [1]) == [0]
    m3 = bytes([0, 0, 136, 0, 1, 70, 0, 136, 0, 0, 15])  # M3 real (2026-10-19): X 350 ms + 4 bytes de fábrica
    keys = [18, 19, 11, 12, 13, 14, 15, 16, 1, 2, 3, 4, 5, 6, 7, 8, 93, 94]
    dm3 = decode_macro(2, m3, keys)
    assert dm3["steps"] == [{"ms": 350, "keys": [3]}] and encode_macro(dm3, keys) == [11, *m3]
    assert mac["loop_ms"] == 100 and mac["loop"] and mac["steps"] == [{"ms": 50, "keys": [1, 3], "stick_left": 1}]
    print("selftest ok")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console cp1252 não imprime "−"
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "scan":
        asyncio.run(scan())
    elif cmd == "dump":
        asyncio.run(dump(sys.argv[2] if len(sys.argv) > 2 else None))
    else:
        selftest()
