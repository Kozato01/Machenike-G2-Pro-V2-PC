"""Configurador do Machenike G2 Pro V2 (PySide6).

A Ficha de acerto mostra o que está gravado no controle; ao mudar algo (− / + ou digitando), a célula ganha a coluna
"novo" em laranja. "Aplicar" grava cada seção pelo BLE e relê: só depois da releitura a ficha diz "salvo no controle".
Protocolo em keylinker.py.  uso:  python app.py
"""
import asyncio
import atexit
import subprocess
import copy
import ctypes
import html
import math
import os
import re
import shutil
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

from bleak import BleakClient
from bleak.exc import BleakBluetoothNotAvailableError
from PySide6.QtCore import (QProcess, QSettings, QByteArray, QEasingCurve, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QIcon, QKeySequence, QPainter, QPainterPath,
                           QPainterPathStroker, QPalette, QPen, QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QBoxLayout, QButtonGroup, QColorDialog, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QKeySequenceEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QPushButton,
                               QSizePolicy,
                               QStackedWidget, QStyle, QStyleOptionComboBox, QToolButton, QVBoxLayout, QWidget)

import i18n
import keylinker as kl


def _lang():  # G2_LANG força a língua (capturas); senão, a escolha salva no app
    return os.environ.get("G2_LANG") or QSettings("Controle", "G2ProV2").value("lang", "pt")


LANG = _lang()


def tr(text):
    """Texto na língua escolhida. O português é a fonte, e é ele que aparece se faltar tradução."""
    return i18n.EN.get(text, text) if LANG == "en" else text

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))  # no .exe, os arquivos vêm do pacote

# ---------------------------------------------------------------- mundo: Ficha de acerto
C = dict(ground="#16181B", grid="#202328", cell="#1F2226", cell_hi="#262A30", rule="#2E3238", rule_hi="#454B53",
         rail="#0F1113", ink="#ECE7DD", chalk="#C9CDD3", pencil="#9A9EA6", blue="#8FC3E6", orange="#F2702A",
         green="#6CC08B", red="#F06A6E", off="#5F636A", body="#1B1E22")
LABELS = {"sticks": tr("analógicos"), "triggers": "gatilhos", "motor": "motores", "turbo": "turbo", "remap": tr("botões"),
          "lights": "luz", "macros": "macros"}
SECTIONS = [*kl.WRITERS, "macros"]  # o que a ficha deixa editar e aplicar
MACROS_WRITABLE = True  # cmd 53 validado em 2026-10-19: M3 regravada idêntica, M1 gravada e apagada
LINEAR = [85, 85, 170, 170]
PRESETS = [(tr("Padrão"), LINEAR), (tr("Rápido"), [35, 35, 136, 204]), (tr("Lento"), [35, 35, 219, 145]),
           (tr("Suave"), [142, 142, 220, 157]), (tr("Fino"), [67, 67, 72, 106])]
YES_NO = [(tr("Não"), False), (tr("Sim"), True)]
TURBO_PERIODS = [1000, 500, 330, 250, 200, 160, 140, 120, 110, 100, 90, 80, 70, 60, 50, 40, 30]  # ms (z1.r)
DIRECTIONS = {1: "cima", 2: "cima-direita", 3: "direita", 4: "baixo-direita", 5: "baixo", 6: "baixo-esquerda",
              7: "esquerda", 8: "cima-esquerda"}
LEFT_KEYS = {5, 7, 11, 13, 14, 15, 16, 93}  # L1 L2 L3 direcional −
CAL_PRESETS = [(tr("Competitivo"), 1, 1, tr("resposta máxima; só cobre o drift medido")),
               (tr("Equilibrado"), 3, 3, tr("folga para o stick envelhecer")),
               (tr("Anti-drift"), 6, 5, tr("para sticks gastos ou que voltam tortos"))]  # (nome, + zona morta, − máximo)


def F(px, weight=400, wdth=100, caps=False, tnum=False, track=0.0):
    f = QFont("Archivo")
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    if wdth != 100:
        f.setVariableAxis(QFont.Tag("wdth"), wdth)
    if caps:
        f.setCapitalization(QFont.AllUppercase)
    if track:
        f.setLetterSpacing(QFont.AbsoluteSpacing, track)  # px; o modo percentual come o espaço entre palavras
    if tnum:
        f.setFeature(QFont.Tag("tnum"), 1)
    return f


def label(text="", font=None, color=None, align=None):
    w = QLabel(text)
    if font:
        w.setFont(font)
    if color:
        w.setStyleSheet(f"color: {color};")
    if align is not None:
        w.setAlignment(align)
    return w


class Para(QLabel):
    """Texto corrido com entrelinha de 140% (o QLabel padrão fica apertado em várias linhas)."""

    def __init__(self, text="", font=None, color=None):
        super().__init__()
        self.color = color
        self.setWordWrap(True)
        self.setTextFormat(Qt.RichText)
        self.setFont(font or F(14))
        self.setText(text)

    def setText(self, text, color=None):
        self.color = color or self.color
        style = tr("line-height:140%;margin:0;") + (tr("color:{0};").format(self.color) if self.color else "")
        super().setText(tr("<p style=\"{0}\">{1}</p>").format(style, html.escape(text).replace(chr(10), '<br>')))


SVG = {
    "sheet": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9z M8.5 11h7 M8.5 14.5h7 M8.5 18h4"/>',
    "stick": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    "trigger": '<path d="M6 20v-9a6 6 0 0 1 12 0v9"/><path d="M6 14.5h12"/>',
    "buttons": '<circle cx="12" cy="6.5" r="2.5"/><circle cx="6.5" cy="12" r="2.5"/><circle cx="17.5" cy="12" r="2.5"/>'
               '<circle cx="12" cy="17.5" r="2.5"/>',
    "turbo": '<path d="M13 3 6 13.5h5.5L10 21l7.5-10.5H12z"/>',
    "macro": '<path d="M4 7h9 M4 12h6 M4 17h9"/><path d="M15.5 10l5 3-5 3z"/>',
    "checkup": '<path d="M3 12.5h4l2.5-6 3.5 11 2.5-5H21"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "alert": '<path d="M12 4 2.8 19.5h18.4z"/><path d="M12 10v4.2 M12 17v.01"/>',
    "next": '<path d="M9.5 6l6 6-6 6"/>',
    "minus": '<path d="M7 12h10"/>',
    "plus": '<path d="M12 7v10 M7 12h10"/>',
    "close": '<path d="M7.5 7.5l9 9 M16.5 7.5l-9 9"/>',
}
APP_ICON = (ROOT / "assets" / "icon.svg").read_text(encoding="utf-8")


def render_svg(svg, size):
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


def pixmap(name, color, size=20):
    return render_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" '
                      'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
                      % (color, SVG[name]), size)


def icon(name, off=None, on=None):
    ic = QIcon()
    ic.addPixmap(pixmap(name, off or C["pencil"]), QIcon.Normal, QIcon.Off)
    for mode, state in ((QIcon.Normal, QIcon.On), (QIcon.Active, QIcon.Off), (QIcon.Active, QIcon.On)):
        ic.addPixmap(pixmap(name, on or C["ink"]), mode, state)
    ic.addPixmap(pixmap(name, C["off"]), QIcon.Disabled, QIcon.Off)
    return ic


def qss():
    chev, chev_on = ((ROOT / "assets" / "icons" / n).as_posix() for n in ("chevron.svg", "chevron-on.svg"))
    c = C
    return f"""
QMainWindow, QStackedWidget {{ background: {c['ground']}; }}
QToolTip {{ background: {c['cell']}; color: {c['ink']}; border: 1px solid {c['rule_hi']}; padding: 6px 8px; }}
QFrame#cell {{ background: {c['cell']}; border: 1px solid {c['rule']}; border-radius: 6px; }}
QFrame#chip {{ background: {c['cell']}; border: 1px solid {c['rule']}; border-radius: 15px; }}
QFrame#bar {{ background: {c['ground']}; border: 0; border-bottom: 1px solid {c['rule']}; }}
QFrame#foot {{ background: {c['ground']}; border: 0; border-top: 1px solid {c['rule']}; }}
QPushButton {{ background: {c['cell']}; color: {c['ink']}; border: 1px solid {c['rule_hi']}; border-radius: 8px;
  padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {c['cell_hi']}; border-color: #5C636D; }}
QPushButton:pressed {{ background: #2C3138; }}
QPushButton:focus {{ border-color: {c['blue']}; }}
QPushButton:disabled {{ color: #767A81; border-color: {c['rule']}; background: transparent; }}
QPushButton#primary {{ background: {c['orange']}; color: {c['ground']}; border-color: {c['orange']}; }}
QPushButton#primary:hover {{ background: #FF8344; border-color: #FF8344; }}
QPushButton#primary:focus {{ border: 2px solid {c['ink']}; }}
QPushButton#primary:disabled {{ background: #2B2520; color: #8C7C6E; border-color: #3B3028; }}
QPushButton#step {{ background: transparent; border: 1px solid {c['rule_hi']}; border-radius: 6px; padding: 0; }}
QPushButton#step:hover {{ background: {c['cell_hi']}; border-color: #5C636D; }}
QPushButton#step:pressed {{ background: #2C3138; }}
QPushButton#step:focus {{ border-color: {c['blue']}; }}
QPushButton#step:disabled {{ border-color: {c['rule']}; }}
QPushButton#seg {{ background: transparent; border: 1px solid {c['rule_hi']}; border-radius: 0; padding: 5px 10px;
  color: {c['chalk']}; }}
QPushButton#seg[edge="first"] {{ border-top-left-radius: 6px; border-bottom-left-radius: 6px; }}
QPushButton#seg[edge="last"] {{ border-top-right-radius: 6px; border-bottom-right-radius: 6px; }}
QPushButton#seg:hover {{ background: {c['cell_hi']}; }}
QPushButton#seg:checked {{ background: #263440; border-color: {c['blue']}; color: {c['ink']}; }}
QPushButton#seg[pending="true"] {{ background: #33251C; border-color: {c['orange']}; color: {c['orange']}; }}
QKeySequenceEdit QLineEdit, QLineEdit#pc {{ background: {c['cell_hi']}; border: 1px solid {c['rule_hi']};
  border-radius: 6px; padding: 4px 10px; color: {c['ink']}; font-size: 15px; min-height: 22px; }}
QKeySequenceEdit QLineEdit:focus, QLineEdit#pc:focus {{ border-color: {c['blue']}; }}
QToolButton#rail {{ background: transparent; border: 1px solid transparent; border-radius: 10px; color: {c['pencil']};
  padding-top: 6px; }}
QToolButton#rail:hover {{ background: #191C20; color: {c['ink']}; }}
QToolButton#rail:checked {{ background: #23272C; border-color: #353A41; color: {c['ink']}; }}
QToolButton#rail:focus {{ border-color: {c['blue']}; }}
QLineEdit#value {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 1px 6px;
  color: {c['ink']}; selection-background-color: #34495A; selection-color: {c['ink']}; }}
QLineEdit#value:hover {{ background: {c['cell_hi']}; border-color: {c['rule_hi']}; }}
QLineEdit#value:focus {{ background: {c['cell_hi']}; border-color: {c['blue']}; }}
QLineEdit#value:disabled {{ color: {c['off']}; }}
QLineEdit#value[pending="true"] {{ color: {c['orange']}; }}
QComboBox {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 1px 33px 1px 6px;
  color: {c['ink']}; }}
QComboBox:hover {{ background: {c['cell_hi']}; border-color: {c['rule_hi']}; }}
QComboBox:focus, QComboBox:on {{ background: {c['cell_hi']}; border-color: {c['blue']}; }}
QComboBox::drop-down {{ border: 0; width: 24px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({chev}); width: 10px; height: 10px; }}
QComboBox::down-arrow:hover, QComboBox::down-arrow:on {{ image: url({chev_on}); }}
QComboBox QAbstractItemView {{ background: {c['cell']}; color: {c['ink']}; border: 1px solid {c['rule_hi']};
  padding: 4px; outline: 0; selection-background-color: #2A3A48; selection-color: {c['ink']}; }}
QProgressBar {{ background: {c['rule']}; border: 0; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {c['blue']}; border-radius: 3px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3A3F46; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #4A5059; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{ background: none; height: 0; }}
"""


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def clear(layout):
    while layout.count():
        w = layout.takeAt(0).widget()
        if w:
            w.hide()  # sai da tela já; deleteLater só roda no próximo ciclo do laço
            w.setParent(None)
            w.deleteLater()


# ---------------------------------------------------------------- valores para a tela
def pct(raw, full):
    return round(raw * 100 / full)


def curve_name(c):
    return next((n for n, v in PRESETS if v == list(c)), tr("Personalizada"))


def hz(ms):
    v = 1000 / ms
    return (f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}".replace(".", ",")) + tr(" Hz")


def num(v, digits=1):
    return f"{v:.{digits}f}".replace(".", ",")


def key_name(code):
    return tr(kl.KEYS[code]) if code in kl.KEYS else tr("Tecla {0}").format(code)


def remap_name(k, t):
    return tr("Padrão") if t == k else tr("Desativada") if t == 2048 else key_name(t)


def color_name(rgb):
    col = QColor(*rgb)
    if col.valueF() < 0.08:
        return tr("Apagada")
    if col.saturationF() < 0.15:
        return tr("Branca") if col.valueF() > 0.7 else tr("Cinza")
    h = col.hueF() * 360
    for limit, name in ((15, tr("Vermelha")), (40, tr("Laranja")), (68, tr("Amarela")), (160, tr("Verde")), (200, tr("Ciano")),
                        (255, tr("Azul")), (290, tr("Roxa")), (335, tr("Rosa")), (361, tr("Vermelha"))):
        if h < limit:
            return name


def turbo_mode(t, k):
    return "manual" if k in t["manual_on"] else "auto" if k in t["auto_on"] else "off"


def turbo_with(t, k, mode):
    t = copy.deepcopy(t)
    man, aut = set(t["manual_on"]) - {k}, set(t["auto_on"]) - {k}
    (man if mode == "manual" else aut if mode == "auto" else set()).add(k)
    t["manual_on"] = [x for x in t["keys"] if x in man]
    t["auto_on"] = [x for x in t["auto_capable"] if x in aut]
    return t


def diff_count(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return sum(diff_count(v, b.get(k)) for k, v in a.items())
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and a and isinstance(a[0], dict):
        return sum(diff_count(x, y) for x, y in zip(a, b))
    return int(a != b)


def pctile(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))] if v else 0.0


def rest_drift(samples):
    """Drift parado = percentil 95 do módulo (ignora picos). Se a faixa entre os percentis 5 e 95 passa de 8%,
    o stick se mexeu durante a medição: devolve (drift, True) para pedir que meça de novo."""
    return pctile(samples, 0.95), pctile(samples, 0.95) - pctile(samples, 0.05) > 0.08


def calibrated(sticks, drift, reach, dz_margin, max_margin):
    """Zona morta = drift medido + margem; máximo = alcance medido − margem (só se o alcance foi medido)."""
    out = copy.deepcopy(sticks)
    for side in ("left", "right"):
        out[side]["deadzone"] = max(0, min(50, math.ceil(drift[side] * 100 + dz_margin)))
        if reach[side] >= 0.6:
            out[side]["max"] = max(50, min(100, math.floor(reach[side] * 100 - max_margin)))
    return out


# ---------------------------------------------------------------- estado: controle × rascunho
class Store(QObject):
    changed = Signal()
    confirmed = Signal(str)

    def __init__(self):
        super().__init__()
        self.device, self.draft, self.saved_at, self.problems = {}, {}, {}, {}
        self.read_at = None

    def ready(self):
        return bool(self.device)

    def load(self, cfg):
        keep = {s: self.draft[s] for s in self.pending() if cfg.get(s) == self.device.get(s)}  # releitura não apaga
        self.device, self.draft = copy.deepcopy(cfg), copy.deepcopy(cfg) | copy.deepcopy(keep)
        self.problems.clear()
        self.read_at = time.strftime(tr("%H:%M"))
        self.changed.emit()

    def get(self, path, src=None):
        node = self.draft if src is None else src
        for k in path:
            node = node[k]
        return node

    def set(self, path, value):
        if len(path) == 1:
            self.draft[path[0]] = value
        else:
            sec = copy.deepcopy(self.draft[path[0]])
            node = sec
            for k in path[1:-1]:
                node = node[k]
            node[path[-1]] = value
            self.draft[path[0]] = sec
        self.problems.pop(path[0], None)
        self.changed.emit()

    def pending(self):
        return [s for s in SECTIONS if s in self.device and self.draft.get(s) != self.device[s]]

    def count(self):
        return sum(diff_count(self.draft[s], self.device[s]) for s in self.pending())

    def discard(self):
        self.draft = copy.deepcopy(self.device)
        self.problems.clear()
        self.changed.emit()

    def stored(self, section, value):
        wanted = self.draft.get(section)
        self.device[section], self.draft[section] = copy.deepcopy(value), copy.deepcopy(value)
        self.read_at = time.strftime(tr("%H:%M"))  # o valor veio da releitura
        if value == wanted:
            self.saved_at[section] = time.strftime(tr("%H:%M"))
            self.problems.pop(section, None)
            self.confirmed.emit(section)
        else:
            self.problems[section] = tr("O controle guardou outro valor. A ficha mostra o que ficou gravado.")
        self.changed.emit()

    def fail(self, section, message):
        if section:
            self.problems[section] = message
        self.changed.emit()


# ---------------------------------------------------------------- BLE numa thread asyncio
class Link(QObject):
    status = Signal(str, str)      # search | busy | ok | off | error, texto
    loaded = Signal(object)
    stored = Signal(str, object)
    failed = Signal(str, str)
    vitals = Signal(object)        # bateria e tecla de confirmação (keepalive 29)
    rawdone = Signal(str, object, bool)  # gravação fora da ficha (calibragem): seção, valor relido, confere?

    def __init__(self):
        super().__init__()
        self.session, self.mode, self.lock, self.firmware, self.address = None, "normal", None, "?", None
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(self._main(), self.loop)

    def reread(self):
        self._do(self._read)

    def apply(self, changes):
        self._do(self._apply, changes)

    def calibrate(self):
        self._do(self._fire, kl.CALIBRATE)

    def set_mode(self, mode):
        self.mode = mode

    def raw_apply(self, section, value):
        """Grava sem passar pela ficha e relê; usado pela calibragem para zerar e restaurar os sticks."""
        async def run():
            stored, ok = None, False
            if self.session:
                try:
                    async with self.lock:
                        stored = await self.session.apply(section, value)
                    ok = stored == value
                except Exception:  # sem resposta: a calibragem mostra o erro
                    pass
            self.rawdone.emit(section, stored, ok)
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    def _do(self, fn, *args):
        async def run():
            if not self.session:
                self.failed.emit("", tr("O controle não está conectado. Espere ele aparecer e tente de novo."))
                return
            try:
                async with self.lock:
                    await fn(*args)
            except Exception as e:  # erro de comunicação vira estado na tela
                self.failed.emit("", self._msg(e))
        asyncio.run_coroutine_threadsafe(run(), self.loop)

    @staticmethod
    def _msg(e):
        if isinstance(e, TimeoutError):
            return tr("O controle não respondeu. Confira se está ligado e perto do PC e tente de novo.")
        return tr("Falha na comunicação ({0}). Tente de novo.").format(e.__class__.__name__)

    async def _fire(self, cmd_payload):
        await self.session.fire(*cmd_payload)

    async def _main(self):
        self.lock = asyncio.Lock()
        while True:
            try:
                await self._connect()
            except BleakBluetoothNotAvailableError:
                self.status.emit("off", tr("Bluetooth do Windows desligado — ligue em Configurações › Bluetooth"))
            except Exception:  # queda de conexão: tenta de novo
                self.status.emit("error", tr("Conexão perdida — reconectando"))
            self.session = None
            await asyncio.sleep(3)

    async def _connect(self):
        self.status.emit("search", tr("Procurando o controle…"))
        saved = QSettings("Controle", "G2ProV2")
        addr = await kl.find(timeout=6) or saved.value("address")  # às vezes o anúncio some, mas o endereço conecta
        if not addr:
            self.status.emit("search", tr("Controle não encontrado — ligue-o; ele aparece sozinho"))
            return
        self.status.emit("busy", tr("Conectando…"))
        gone = asyncio.Event()
        async with BleakClient(addr, timeout=20,
                               disconnected_callback=lambda _: self.loop.call_soon_threadsafe(gone.set)) as client:
            s = kl.Session(client)
            s.on_event = lambda p: None  # fluxo 0x1F ignorado aqui (entradas ao vivo vêm do XInput)
            await s.start()
            self.session, self.address = s, addr
            saved.setValue("address", addr)
            async with self.lock:
                await self._read()
            misses = 0
            while not gone.is_set():
                try:
                    await asyncio.wait_for(gone.wait(), 0.75)
                except asyncio.TimeoutError:
                    try:
                        async with self.lock:
                            st = await s.keepalive(self.mode)
                        misses = 0
                        self.vitals.emit(st)
                    except TimeoutError:
                        misses += 1
                        if misses >= 3:
                            break
        self.status.emit("error", tr("O controle saiu do alcance — reconectando"))

    async def _read(self):
        self.status.emit("busy", tr("Lendo a configuração do controle…"))
        cfg = await self.session.read_all()
        cfg["address"] = self.address
        self.firmware = cfg["identity"]["firmware"]
        self.macros = cfg.get("macros")
        self.loaded.emit(cfg)
        self.status.emit("ok", tr("Conectado · firmware {0}").format(self.firmware))

    async def _apply_macros(self, value):
        """Grava só as macros que mudaram (cmd 53, uma por slot) e relê todas uma vez."""
        old = {m["name"]: m for m in self.macros["slots"]}
        for slot in value["slots"]:
            if slot != old.get(slot["name"]):
                await self.session.write(53, kl.encode_macro(slot, value["keys"]),
                                         slot=kl.MACRO_SLOTS.index(slot["name"]))
        self.macros = await self.session.read_macros([m["name"] for m in value["slots"]])
        return self.macros

    async def _apply(self, changes):
        try:
            for i, (section, value) in enumerate(changes, 1):
                self.status.emit("busy", tr("Gravando {0} ({1} de {2})…").format(tr(LABELS[section]), i, len(changes)))
                try:
                    stored = await (self._apply_macros(value) if section == "macros" else
                                    self.session.apply(section, value))
                except Exception as e:
                    self.failed.emit(section, self._msg(e))
                    return
                self.stored.emit(section, stored)
        finally:
            self.status.emit("ok", tr("Conectado · firmware {0}").format(self.firmware))


# ---------------------------------------------------------------- XInput: o que os jogos recebem
class _Pad(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", _Pad)]


class _Vib(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wintypes.WORD), ("wRightMotorSpeed", wintypes.WORD)]


class XInput:
    BUTTONS = {0x1000: 1, 0x2000: 2, 0x4000: 3, 0x8000: 4, 0x0100: 5, 0x0200: 6, 0x0040: 11, 0x0080: 12,
               0x0002: 13, 0x0001: 14, 0x0008: 15, 0x0004: 16, 0x0020: 93, 0x0010: 94}  # -> códigos KeyLinker

    def __init__(self):
        try:
            self.dll = ctypes.WinDLL("xinput1_4")
        except OSError:
            self.dll = None
        self.user, self.pinned = 0, False

    def read(self):
        if not self.dll:
            return None
        for u in ((self.user,) if self.pinned else dict.fromkeys((self.user, 0, 1, 2, 3))):
            st = _State()
            if self.dll.XInputGetState(u, ctypes.byref(st)) == 0:
                self.user, g = u, st.Gamepad
                return {"down": {code for bit, code in self.BUTTONS.items() if g.wButtons & bit},
                        "lt": g.bLeftTrigger, "rt": g.bRightTrigger,
                        "l": (g.sThumbLX / 32768, g.sThumbLY / 32768), "r": (g.sThumbRX / 32768, g.sThumbRY / 32768)}
        return None

    def vibrate(self, left, right):
        if self.dll:
            self.dll.XInputSetState(self.user, ctypes.byref(_Vib(left, right)))


# ---------------------------------------------------------------- ações no PC (traseiras → teclado)
# M1–M4 no PC: a macro aperta L1 e R1 juntos por 40 ms, mais uma marca que diz qual M é (M3: nenhuma, M4: X,
# M1: A, M2: B). O app reconhece no instante em que o sinal aparece e manda a tecla na hora. Testado: o controle não
# toca L3/R3 em macro; − e + vira o botão Guia (Big Picture do Steam). Com o Virtual, o jogo não vê nada disso.
PC_BASE = [5, 6]  # L1 e R1
PC_MARK = {"M3": [], "M4": [3], "M1": [1], "M2": [2]}  # X, A, B (o controle toca esses em macro: as de fábrica)
PC_HOLD_MS = 40


def pc_steps(name):
    return [{"ms": PC_HOLD_MS, "keys": PC_MARK[name] + PC_BASE}]  # na ordem da lista de teclas do controle
FACTORY_MACROS = {  # como vieram (lidas em 2026-10-19), com os 4 bytes finais de fábrica
    "M3": {"loop_ms": 0, "loop": False, "steps": [{"ms": 350, "keys": [3]}], "tail": [136, 0, 0, 15]},
    "M4": {"loop_ms": 0, "loop": False, "steps": [{"ms": 315, "keys": [4]}], "tail": [136, 0, 0, 33]}}
_VK = {Qt.Key_Escape: 0x1B, Qt.Key_Tab: 0x09, Qt.Key_Backspace: 0x08, Qt.Key_Return: 0x0D, Qt.Key_Enter: 0x0D,
       Qt.Key_Space: 0x20, Qt.Key_Insert: 0x2D, Qt.Key_Delete: 0x2E, Qt.Key_Home: 0x24, Qt.Key_End: 0x23,
       Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22, Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27,
       Qt.Key_Down: 0x28, Qt.Key_Print: 0x2C, Qt.Key_Pause: 0x13, Qt.Key_CapsLock: 0x14,
       Qt.Key_VolumeUp: 0xAF, Qt.Key_VolumeDown: 0xAE, Qt.Key_VolumeMute: 0xAD, Qt.Key_MediaPlay: 0xB3,
       Qt.Key_MediaTogglePlayPause: 0xB3, Qt.Key_MediaNext: 0xB0, Qt.Key_MediaPrevious: 0xB1,
       Qt.Key_MediaStop: 0xB2}
_EXTENDED = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x2C}


def shortcut_vks(text):
    """"Ctrl+Shift+S" → teclas virtuais do Windows (modificadores primeiro). None se a tecla não tem tradução."""
    seq = QKeySequence(text)
    if seq.isEmpty():
        return None
    combo = seq[0]
    key, mods = combo.key(), combo.keyboardModifiers()
    vks = [vk for flag, vk in ((Qt.ControlModifier, 0x11), (Qt.ShiftModifier, 0x10), (Qt.AltModifier, 0x12),
                               (Qt.MetaModifier, 0x5B)) if mods & flag]
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        vk = int(key)
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        vk = 0x70 + int(key) - int(Qt.Key_F1)
    elif key in _VK:
        vk = _VK[key]
    elif 32 <= int(key) < 0x110000:  # pontuação: o layout do teclado diz qual tecla é
        scan = ctypes.windll.user32.VkKeyScanW(int(key)) if hasattr(ctypes, "windll") else -1
        vk = scan & 0xFF if scan != -1 else None
    else:
        vk = None
    return vks + [vk] if vk else None


class _KeyIn(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MouseIn(ctypes.Structure):  # só para o union ter o tamanho certo
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _In(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KeyIn), ("mi", _MouseIn)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(events):  # events: (vk, scan, flags)
    arr = (_In * len(events))(*[_In(1, _In._U(ki=_KeyIn(vk, scan, flags, 0, 0))) for vk, scan, flags in events])
    ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(_In))


def send_keys(text, down=True, up=True):
    """Aperta (down) e/ou solta (up) o atalho; segurar = down agora, up quando o botão for solto."""
    vks = shortcut_vks(text)
    if vks:
        ext = [(vk, 1 if vk in _EXTENDED else 0) for vk in vks]
        _send(([(vk, 0, e) for vk, e in ext] if down else []) + ([(vk, 0, e | 2) for vk, e in reversed(ext)] if up else []))


def send_shortcut(text):
    send_keys(text)


def send_text(text):
    units = text.encode("utf-16-le")
    codes = [int.from_bytes(units[i:i + 2], "little") for i in range(0, len(units), 2)]
    _send([ev for c in codes for ev in ((0, c, 4), (0, c, 4 | 2))])  # KEYEVENTF_UNICODE (+ KEYUP)


_CLICKS = {"clique": (0x2, 0x4), "clique esquerdo": (0x2, 0x4), "clique direito": (0x8, 0x10),
           "clique do meio": (0x20, 0x40), "click": (0x2, 0x4), "left click": (0x2, 0x4),
           "right click": (0x8, 0x10), "middle click": (0x20, 0x40)}  # MOUSEEVENTF_*DOWN, *UP (PT e EN)


def sequence_steps(text):
    """"Ctrl+C, 100 ms, Ctrl+V, \"gg\", clique" → passos; devolve (passos, partes que não entendi)."""
    steps, bad = [], []
    for part in (t.strip() for t in re.findall(r'\s*"[^"]*"\s*|[^,]+', text)):  # vírgula entre aspas é texto
        low = part.lower()
        wait = re.fullmatch(r"(?:(?:espera|wait)\s*)?(\d+)\s*ms", low)
        if not part:
            continue
        if wait:
            steps.append(("wait", min(int(wait.group(1)), 10000)))
        elif low in _CLICKS:
            steps.append(("click", _CLICKS[low]))
        elif len(part) >= 2 and part[0] == part[-1] == '"':
            steps.append(("text", part[1:-1]))
        elif shortcut_vks(part):
            steps.append(("keys", part))
        else:
            bad.append(part)
    return steps, bad


def run_sequence(text):
    for kind, arg in sequence_steps(text)[0]:
        if kind == "wait":
            time.sleep(arg / 1000)
        elif kind == "text":
            send_text(arg)
        elif kind == "keys":
            send_shortcut(arg)
        else:
            for flag in arg:
                ins = _In(0, _In._U(mi=_MouseIn(0, 0, 0, flag, 0, 0)))
                ctypes.windll.user32.SendInput(1, ctypes.byref(ins), ctypes.sizeof(_In))
        time.sleep(0.02)  # um respiro entre passos: alguns jogos perdem teclas coladas


class PcActions:
    """O que cada M faz no PC (salvo neste PC). Reconhece a M pela marca que vem junto do L1 e R1. Só conta se L1 e
    R1 apareceram na mesma leitura: a macro aperta tudo no mesmo instante, um dedo sempre aperta um antes."""

    def __init__(self):
        self.settings = QSettings("Controle", "G2ProV2")
        self.saved, self.prev = {}, set()

    def get(self, name):
        return self.settings.value(f"pc/{name}/kind", "none"), self.settings.value(f"pc/{name}/value", "")

    def put(self, name, kind, value):
        if (kind, value) != self.get(name):
            self.saved[name] = time.strftime("%H:%M")  # a célula mostra a confirmação
        self.settings.setValue(f"pc/{name}/kind", kind)
        self.settings.setValue(f"pc/{name}/value", value)

    def tick(self, pad, now=None):
        now = time.monotonic() if now is None else now
        down = pad["down"] if pad else set()
        hit, together = set(PC_BASE) <= down, not set(PC_BASE) & self.prev  # nenhum dos dois estava apertado antes
        self.prev = down
        if hit and together:
            marks = down & {k for m in PC_MARK.values() for k in m}
            name = next((m for m, mk in PC_MARK.items() if set(mk) == marks), None)
            if name and self.get(name)[0] != "none":
                self.fire(name)

    def watch(self, pad):
        """Lê o controle a cada 2 ms numa thread: o temporizador do Qt no Windows só dispara a cada ~15 ms."""
        def loop():
            while True:
                self.tick(pad.read())
                time.sleep(0.002)
        threading.Thread(target=loop, daemon=True).start()

    def fire(self, name):
        kind, value = self.get(name)
        if kind in ("shortcut", "special") and value:
            send_shortcut(value)
        elif kind == "text" and value:
            send_text(value)
        elif kind == "sequence" and value:  # numa thread: as esperas não travam o app
            threading.Thread(target=run_sequence, args=(value,), daemon=True).start()


PC = PcActions()
VIRTUAL = None  # VirtualPad, criado pela janela


# ---------------------------------------------------------------- controle virtual (ViGEmBus + HidHide)
HIDHIDE = Path(r"C:\Program Files\Nefarius Software Solutions\HidHide\x64\HidHideCLI.exe")
SIGNAL = 0x0100 | 0x0200  # bits XInput de L1 e R1: o sinal das M; o jogo nunca vê os dois juntos


def hidhide(*args):
    """Roda o HidHideCLI; devolve a saída ou None se o HidHide não está instalado."""
    if not HIDHIDE.exists():
        return None
    try:  # stdin vazio: sem ele o CLI fica esperando comandos e trava
        r = subprocess.run([str(HIDHIDE), *args], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout


MARK_BITS = 0x1000 | 0x2000 | 0x4000  # A, B, X: as marcas das M


def strip_signal(buttons, mask=0, prev=0):
    """Tira o sinal das M: L1 e R1 aparecendo juntos na mesma leitura (a macro), com a marca que veio junto; um dedo
    aperta um antes e passa normal. Do começo do sinal até tudo soltar, nada disso passa (na soltura um botão sai
    antes e escaparia sozinho). Devolve (botões para o jogo, bits ainda segurados)."""
    if not mask and buttons & SIGNAL == SIGNAL and not prev & SIGNAL:
        mask = SIGNAL | buttons & MARK_BITS
    elif mask and not buttons & mask:
        mask = 0
    return buttons & ~mask, mask


DRIVERS = {"ViGEmBus": "ViGEmBusSetup_x64.msi", "HidHide": "HidHide_1.5.230_x64.exe"}  # em assets/drivers


def install_drivers(names):
    """Abre os instaladores dos drivers que faltam, como administrador, um depois do outro. Copia antes para uma
    pasta fixa: no .exe, a pasta interna some quando o app fecha, e o instalador pode ainda estar rodando."""
    dest = Path(os.environ.get("TEMP", str(ROOT))) / "G2ProV2-drivers"
    dest.mkdir(exist_ok=True)
    steps = []
    for name in names:
        f = Path(shutil.copy(ROOT / "assets" / "drivers" / DRIVERS[name], dest))
        if f.suffix == ".msi":
            steps.append(f"Start-Process msiexec.exe -Verb RunAs -Wait -ArgumentList '/i \"{f}\" /passive /norestart'")
        else:
            steps.append(f"Start-Process '{f}' -Verb RunAs -Wait -ArgumentList '/passive /norestart'")
    return QProcess.startDetached("powershell.exe", ["-NoProfile", "-WindowStyle", "Hidden", "-Command",
                                                     "; ".join(steps)])


class VirtualPad:
    """Liga: libera este Python no HidHide, esconde o controle real, cria o Xbox 360 virtual e repassa tudo em
    ~500 Hz numa thread. Desliga (ou fecha o app): para o repasse, remove o virtual e mostra o real de novo."""

    def __init__(self, pad):
        self.pad, self.vpad, self.thread, self.running, self.error = pad, None, None, False, None
        atexit.register(self.stop)  # nunca deixar o controle real escondido com o app fechado

    @staticmethod
    def missing():
        """Drivers do Windows que faltam para o modo virtual (o app traz os instaladores)."""
        out = []
        try:
            import vgamepad  # noqa: F401  (falha ao importar se o ViGEmBus não está instalado)
        except Exception:
            out.append("ViGEmBus")
        return out + ([] if HIDHIDE.exists() else ["HidHide"])

    def available(self):
        miss = self.missing()
        return tr("Faltam os drivers do controle virtual: {0}.").format(", ".join(miss)) if miss else None

    def start(self):
        self.error = self.available()
        if self.error or self.running:
            return not self.error
        real = self.pad.read()
        if real is None:
            self.error = tr("O Windows não está vendo o controle (XInput): conecte pelo cabo ou dongle.")
            return False
        try:
            import vgamepad as vg
            # ponytail: esconde todo controle Xbox 360 ligado (o real aparece assim); um 2º controle também some
            ids = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-PnpDevice -PresentOnly | Where-Object "
                                  "InstanceId -match 'VID_045E&PID_028E' | ForEach-Object InstanceId"],
                                 stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.split()
            hide = [arg for i in ids for arg in ("--dev-hide", i)]
            # o virtual tem o mesmo 045E:028E: se um dia entrou na lista (salva pelo HidHide), o jogo não vê nada.
            # Começa do zero e esconde só o que estava ligado antes do virtual existir.
            old = re.findall(r'--dev-hide "([^"]+)"', hidhide("--dev-list") or "")
            unhide = [arg for i in old for arg in ("--dev-unhide", i)]
            if hidhide(*unhide, "--app-reg", sys.executable, *hide, "--cloak-on") is None:
                raise RuntimeError(tr("o HidHide não respondeu"))
            self.pad.pinned = True  # daqui em diante só lê o slot do controle real
            self.vpad = vg.VX360Gamepad()

            def rumble(client, target, large_motor, small_motor, led_number, user_data):
                self.pad.vibrate(large_motor * 257, small_motor * 257)
            self.vpad.register_notification(rumble)
        except Exception as e:
            self.error = tr("Não consegui criar o controle virtual ({0}: {1}).").format(e.__class__.__name__, e)
            self.stop()
            return False
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def _loop(self):
        try:  # repasse dos botões na frente de tudo: desenhar a tela e o Bluetooth esperam
            ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), 15)
        except (AttributeError, OSError):
            pass
        last, latched, prev = None, 0, 0
        while self.running:
            st = _State()
            if self.pad.dll.XInputGetState(self.pad.user, ctypes.byref(st)) == 0 and st.dwPacketNumber != last:
                last, g, r = st.dwPacketNumber, st.Gamepad, self.vpad.report
                r.wButtons, latched = strip_signal(g.wButtons, latched, prev)
                prev = g.wButtons
                r.bLeftTrigger, r.bRightTrigger = g.bLeftTrigger, g.bRightTrigger
                r.sThumbLX, r.sThumbLY, r.sThumbRX, r.sThumbRY = g.sThumbLX, g.sThumbLY, g.sThumbRX, g.sThumbRY
                self.vpad.update()
            time.sleep(0.001)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(0.5)
            self.thread = None
        if self.vpad:
            try:
                self.vpad.unregister_notification()
            except Exception:  # driver já fora: nada a soltar
                pass
            self.vpad = None
        self.pad.pinned = False
        hidhide("--cloak-off")


# ---------------------------------------------------------------- campos editáveis (o valor fica no lugar)
def field_frame(p, w, r):
    if w.hasFocus() or w.underMouse():
        p.setPen(QPen(QColor(C["blue"] if w.hasFocus() else C["rule_hi"]), 1))
        p.setBrush(QColor(C["cell_hi"]))
        p.drawRoundedRect(r, 6, 6)


class ValueField(QLineEdit):
    """Número editável no lugar: tinta normal; laranja quando difere do controle.
    ↑/↓ ajustam, Enter confirma, Esc volta ao valor do controle."""
    valueChanged = Signal(int)

    def __init__(self, lo, hi, unit="%", special=None, width=64, inc=1):
        super().__init__(objectName="value")
        self.lo, self.hi, self.unit, self.special, self.inc = lo, hi, unit, special or {}, inc
        self.ref = self.val = None
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setFont(F(18, 600, 85, tnum=True))
        self.setFixedSize(width, 32)
        self.setToolTip(tr("Digite o valor ou use ↑/↓; Enter confirma, Esc volta ao valor do controle"))
        self.editingFinished.connect(self._commit)
        self.setText("—")

    def _text(self, v):
        return self.special.get(v, f"{v}{self.unit}")

    def _redraw(self):
        self.setText("—" if self.val is None else self._text(self.val))

    def _parse(self, text):
        t = text.strip()
        for k, s in self.special.items():
            if t.lower() == s.lower():
                return k
        d = re.sub(r"\D", "", t)
        return int(d) if d else None

    def step(self, n):
        if self.val is not None:
            self._set(self.val + n * self.inc)

    def _set(self, v):
        if self.val is None:
            return
        v = max(self.lo, min(self.hi, v))
        if v != self.val:
            self.val = v
            self.valueChanged.emit(v)
        self._redraw()

    def _commit(self):
        v = self._parse(self.text())
        self._set(self.val if v is None else v)

    def keyPressEvent(self, e):
        steps = {Qt.Key_Up: 1, Qt.Key_Down: -1, Qt.Key_PageUp: 5, Qt.Key_PageDown: -5}
        if e.key() == Qt.Key_Escape and self.ref is not None:
            self._set(self.ref)
            self.clearFocus()
        elif e.key() in steps and self.val is not None:
            base = self._parse(self.text())
            self._set((self.val if base is None else base) + steps[e.key()] * self.inc)
            self.selectAll()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        if not self.hasFocus() or self.val is None:
            e.ignore()
            return
        self._set(self.val + (1 if e.angleDelta().y() > 0 else -1))
        self.selectAll()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, e):
        self._commit()
        super().focusOutEvent(e)

    def show_state(self, ref, value):
        self.ref, self.val = ref, value
        if not self.hasFocus():
            self._redraw()
        self.setProperty("pending", value is not None and value != ref)
        repolish(self)


class Stepper(QWidget):
    """[−] valor [+]: o jeito direto de mudar um número (segure para repetir); ainda dá para digitar."""
    valueChanged = Signal(int)

    def __init__(self, lo, hi, unit="%", special=None, inc=1, width=64):
        super().__init__()
        self.field = ValueField(lo, hi, unit, special, width, inc)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.minus, self.plus = (QPushButton(objectName="step") for _ in range(2))
        for b, name, n in ((self.minus, "minus", -1), (self.plus, "plus", 1)):
            b.setIcon(icon(name, C["chalk"], C["ink"]))
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(24, 28)
            b.setAutoRepeat(True)
            b.setAutoRepeatDelay(350)
            b.setAutoRepeatInterval(70)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tr("Diminuir (segure para repetir)") if n < 0 else tr("Aumentar (segure para repetir)"))
            b.clicked.connect(lambda _=False, n=n: self.field.step(n))
        lay.addWidget(self.minus)
        lay.addWidget(self.field)
        lay.addWidget(self.plus)
        self.field.valueChanged.connect(self.valueChanged)
        self.setFixedSize(24 + 3 + width + 3 + 24, 32)

    def show_state(self, ref, value):
        self.field.show_state(ref, value)
        self.minus.setEnabled(value is not None and value > self.field.lo)
        self.plus.setEnabled(value is not None and value < self.field.hi)

    def setEnabled(self, on):
        super().setEnabled(on)
        self.field.setEnabled(on)


class ChoiceField(QComboBox):
    """Opção editável no lugar; o texto fica alinhado à direita na mesma linha dos números."""
    picked = Signal(object)

    def __init__(self, options, width=112):
        super().__init__()
        self.options, self.ref, self.pending = list(options), None, False
        for name, _ in self.options:
            self.addItem(name)
        self.setFixedSize(width, 32)
        self.setFont(F(16, 600, 80))
        self.setCursor(Qt.PointingHandCursor)
        self.setCurrentIndex(-1)
        self.setPlaceholderText("—")
        self.activated.connect(lambda i: self.picked.emit(self.options[i][1]))
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):  # a roda rola a página: trocar a opção sem querer apagava o atalho de uma traseira
        e.ignore()

    def show_state(self, ref, value):
        self.ref = ref
        for i, (name, v) in enumerate(self.options):
            self.setItemText(i, tr("{0}  · no controle").format(name) if v == ref else name)
        idx = next((i for i, (_, v) in enumerate(self.options) if v == value), -1)
        self.setPlaceholderText("—" if value is None else tr("Personalizada"))
        self.blockSignals(True)
        self.setCurrentIndex(idx)
        self.blockSignals(False)
        self.pending = value is not None and value != ref
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = ""
        self.style().drawComplexControl(QStyle.CC_ComboBox, opt, p, self)
        i = self.currentIndex()
        text = self.options[i][0] if i >= 0 else self.placeholderText()
        p.setPen(QColor(C["off"] if not self.isEnabled() else C["orange"] if self.pending else C["ink"]))
        p.setFont(self.font())
        p.drawText(QRectF(self.rect()).adjusted(6, 0, -33, 0), Qt.AlignRight | Qt.AlignVCenter, text)


class Segmented(QWidget):
    """Opções lado a lado (predefinições de curva): um clique escolhe; a pendente fica em laranja."""
    picked = Signal(object)

    def __init__(self, options):
        super().__init__()
        self.options, self.buttons = list(options), []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        group = QButtonGroup(self)
        for i, (name, v) in enumerate(self.options):
            b = QPushButton(name, objectName="seg")
            b.setCheckable(True)
            b.setFont(F(14, 600, 85))
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("edge", "first" if i == 0 else "last" if i == len(self.options) - 1 else "mid")
            b.clicked.connect(lambda _=False, v=v: self.picked.emit(v))
            group.addButton(b)
            lay.addWidget(b)
            self.buttons.append(b)
        group.setExclusive(False)
        self.setFixedHeight(32)

    def show_state(self, ref, value):
        for b, (name, v) in zip(self.buttons, self.options):
            b.setChecked(v == value)
            b.setProperty("pending", v == value and value != ref)
            b.setToolTip(tr("gravada no controle") if v == ref else "")
            repolish(b)


class SwatchField(QPushButton):
    picked = Signal(object)

    def __init__(self, width=124):
        super().__init__()
        self.ref = self.value = None
        self.setFixedSize(width, 32)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Escolher outra cor"))
        self.clicked.connect(self._pick)

    def show_state(self, ref, value):
        self.ref, self.value = ref, value
        self.update()

    def _pick(self):
        if self.value is None:
            return
        c = QColorDialog.getColor(QColor(*self.value), self.window(), tr("Cor da luz"))
        if c.isValid():
            self.picked.emit([c.red(), c.green(), c.blue()])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        field_frame(p, self, r)
        p.setFont(F(16, 600, 80))
        text_r = r.adjusted(6, 0, -33, 0)
        if self.value is None:
            p.setPen(QColor(C["off"]))
            p.drawText(text_r, Qt.AlignRight | Qt.AlignVCenter, "—")
            return
        name = color_name(self.value)
        p.setPen(QColor(C["orange"] if self.value != self.ref else C["ink"]))
        p.drawText(text_r, Qt.AlignRight | Qt.AlignVCenter, name)
        x = text_r.right() - p.fontMetrics().horizontalAdvance(name) - 22
        p.setPen(QPen(QColor(C["rule_hi"]), 1))
        p.setBrush(QColor(*self.value))
        p.drawRoundedRect(QRectF(x, r.center().y() - 8, 16, 16), 3, 3)


class LinkField(QPushButton):
    """Valor que leva a outra página (resumo + seta)."""

    def __init__(self, on_click, width=124):
        super().__init__()
        self.setFixedSize(width, 32)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(F(16, 600, 80, tnum=True))
        self.clicked.connect(on_click)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        field_frame(p, self, r)
        col = C["blue"] if self.isEnabled() else C["off"]
        p.setPen(QColor(col))
        p.setFont(self.font())
        p.drawText(r.adjusted(6, 0, -33, 0), Qt.AlignRight | Qt.AlignVCenter, self.text())
        p.drawPixmap(QPointF(r.right() - 20, r.center().y() - 8), pixmap("next", col, 16))


# ---------------------------------------------------------------- célula da ficha
class Bind:
    def __init__(self, section, get, put, show, field, before, to_ui, from_ui, row):
        self.section, self.get, self.put, self.show = section, get, put, show
        self.field, self.before, self.to_ui, self.from_ui, self.row = field, before, to_ui, from_ui, row


class Note(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        self.icon, self.text = QLabel(), Para(font=F(13))
        lay.addWidget(self.icon, 0, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        self.hide()

    def say(self, kind, color, text):
        self.icon.setPixmap(pixmap(kind, color, 16))
        self.text.setText(text, color)
        self.show()


class SetupCell(QFrame):
    """Célula da ficha. Limpa, lê como uma coluna (rótulo · valor editável); com mudança, ganha a coluna
    "no controle" (lápis) ao lado do "novo" (laranja)."""

    def __init__(self, store, title, side="", mirror=False, columns=True):
        super().__init__(objectName="cell")
        self.store, self.binds, self.links, self.sections = store, [], [], set()
        self.flash_t = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        head = QHBoxLayout()
        t = label(title, F(12, 700, 75, caps=True, track=1.0), C["pencil"])
        tag = label(side, F(12, 700, 75, caps=True, track=1.0), C["pencil"])
        for w in ((tag, None, t) if mirror else (t, None, tag)):
            head.addStretch(1) if w is None else head.addWidget(w)
        lay.addLayout(head)
        self.top = QVBoxLayout()
        self.top.setSpacing(8)
        lay.addLayout(self.top)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(0)
        self.grid.setColumnStretch(0, 1)
        self.heads = []
        if columns:
            was = label(tr("no controle"), F(11, 700, 75, caps=True, track=1.2), C["pencil"], Qt.AlignRight | Qt.AlignBottom)
            new = label(tr("novo"), F(11, 700, 75, caps=True, track=1.2), C["orange"], Qt.AlignRight | Qt.AlignBottom)
            new.setContentsMargins(0, 0, 33, 0)
            self.grid.addWidget(was, 0, 0, 1, 2)  # ocupa a coluna do rótulo: nunca corta
            self.grid.addWidget(new, 0, 2)
            self.heads = [was, new]
            for h in self.heads:
                h.hide()
        lay.addLayout(self.grid)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        lay.addLayout(self.body)
        self.note = Note()
        lay.addWidget(self.note)
        lay.addStretch(1)
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setDuration(1400)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(self._flash_step)

    def _row(self, text, before, widget, wide=False):
        r = self.grid.rowCount()
        lab = label(text, F(14), C["chalk"])
        lab.setMinimumHeight(40)
        self.grid.addWidget(lab, r, 0)
        if wide:
            self.grid.addWidget(widget, r, 1, 1, 2, Qt.AlignRight | Qt.AlignVCenter)
            return r
        if before is not None:
            self.grid.addWidget(before, r, 1)
        self.grid.addWidget(widget, r, 2, Qt.AlignRight | Qt.AlignVCenter)
        return r

    def add(self, text, field, get, put, show, section, to_ui=None, from_ui=None, wide=False):
        before = label("", F(16, 600, 85, tnum=True), C["pencil"], Qt.AlignRight | Qt.AlignVCenter)
        before.hide()
        r = self._row(text, before, field, wide)
        b = Bind(section, get, put, show, field, None if wide else before, to_ui or (lambda v: v),
                 from_ui or (lambda v: v), r)
        sig = field.valueChanged if isinstance(field, (ValueField, Stepper)) else field.picked
        sig.connect(lambda ui, b=b: self._edited(b, ui))
        self.binds.append(b)
        self.sections.add(section)
        return b

    def add_path(self, text, field, path, show, **kw):
        s = self.store
        return self.add(text, field, lambda src, p=path: s.get(p, src), lambda raw, p=path: s.set(p, raw),
                        show, path[0], **kw)

    def add_link(self, text, section, show, on_click):
        btn = LinkField(on_click)
        self._row(text, None, btn)
        self.links.append((section, show, btn))

    def _edited(self, b, ui):
        try:
            dev = b.get(self.store.device)
        except (KeyError, IndexError, TypeError):
            return
        raw = dev if ui == b.to_ui(dev) else b.from_ui(ui)
        if raw != b.get(self.store.draft):
            b.put(raw)

    def pending(self):
        s = self.store
        try:
            return any(b.get(s.draft) != b.get(s.device) for b in self.binds)
        except (KeyError, IndexError, TypeError):
            return False

    def refresh(self):
        s = self.store
        any_pending = False
        for b in self.binds:
            try:
                dev, cur = b.get(s.device), b.get(s.draft)
            except (KeyError, IndexError, TypeError):
                b.field.setEnabled(False)
                b.field.show_state(None, None)
                if b.before:
                    b.before.hide()
                continue
            b.field.setEnabled(True)
            b.field.show_state(b.to_ui(dev), b.to_ui(cur))
            changed = cur != dev
            if b.before:
                b.before.setText(b.show(dev))
                b.before.setVisible(changed)
                any_pending |= changed
        for h in self.heads:
            h.setVisible(any_pending)
        self.grid.setColumnMinimumWidth(1, 56 if any_pending else 0)
        for section, show, btn in self.links:
            ok = section in s.device
            btn.setEnabled(ok)
            btn.setText(show(s.device) if ok else "—")
        problem = next((s.problems[x] for x in self.sections if x in s.problems), None)
        saved = [s.saved_at[x] for x in self.sections if x in s.saved_at]
        if problem:
            self.note.say("alert", C["red"], problem)
        elif saved and not self.pending():
            self.note.say("check", C["green"], tr("Salvo no controle às {0}").format(max(saved)))
        else:
            self.note.hide()

    def flash(self):
        self.anim.stop()
        self.anim.start()

    def _flash_step(self, t):
        self.flash_t = t
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#2A2E33"), 1))
        for r in range(2, self.grid.rowCount()):
            y = self.grid.cellRect(r, 0).top()
            if y > 0:
                p.drawLine(14, y, self.width() - 14, y)
        if self.flash_t > 0.01:
            col = QColor(C["green"])
            col.setAlphaF(self.flash_t)
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)


# ---------------------------------------------------------------- desenhos
class Sheet(QWidget):
    """Fundo de prancheta com a grade de 24 px à mostra."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C["ground"]))
        p.setPen(QPen(QColor(C["grid"]), 1))
        for x in range(0, self.width(), 24):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 24):
            p.drawLine(0, y, self.width(), y)


def path_from(points):
    """M x y, depois trincas de pontos (c1, c2, fim) de cúbicas; tuplas soltas viram linhas."""
    path = QPainterPath()
    path.moveTo(*points[0])
    for seg in points[1:]:
        if len(seg) == 3:
            path.cubicTo(QPointF(*seg[0]), QPointF(*seg[1]), QPointF(*seg[2]))
        else:
            path.lineTo(*seg)
    path.closeSubpath()
    return path


BODY = path_from([(150, 62), ((196, 46), (364, 46), (410, 62)), ((466, 80), (516, 164), (538, 262)),
                  ((552, 330), (506, 368), (466, 334)), ((436, 304), (402, 268), (362, 262)), (198, 262),
                  ((158, 268), (124, 304), (94, 334)), ((54, 368), (8, 330), (22, 262)),
                  ((44, 164), (94, 80), (150, 62))])
PLATE = path_from([(172, 82), ((220, 68), (340, 68), (388, 82)), ((424, 94), (452, 138), (462, 186)),
                   ((436, 206), (404, 216), (374, 218)), (186, 218), ((156, 216), (124, 206), (98, 186)),
                   ((108, 138), (136, 94), (172, 82))])
PARTS = {"stick_l": (170, 130), "stick_r": (340, 200), "dpad": (239, 196), "abxy": (400, 128), "a": (400, 152),
         "b": (424, 128), "x": (376, 128), "y": (400, 104), "l1": (160, 52), "l2": (187, 26), "r1": (400, 52),
         "r2": (373, 26), "trig_l": (187, 30), "trig_r": (373, 30), "minus": (252, 110), "plus": (308, 110),
         "light": (280, 150), "motor_l": (66, 300), "motor_r": (494, 300),
         "m3": (108, 272), "m4": (452, 272)}  # m3/m4: na vista de trás (espelhada)
CODE_PART = {1: "a", 2: "b", 3: "x", 4: "y", 5: "l1", 7: "l2", 6: "r1", 8: "r2", 11: "stick_l", 12: "stick_r",
             13: "dpad", 14: "dpad", 15: "dpad", 16: "dpad", 93: "minus", 94: "plus"}
KEY_XY = {1: (400, 152), 2: (424, 128), 3: (376, 128), 4: (400, 104), 5: (160, 52), 7: (187, 24), 6: (400, 52),
          8: (373, 24), 11: (170, 130), 12: (340, 200), 13: (239, 224), 14: (239, 168), 15: (267, 196),
          16: (211, 196), 93: (252, 110), 94: (308, 110)}  # ponta da linha de chamada de cada tecla


class ControllerPlan(QWidget):
    """O G2 Pro V2 em traço técnico: pendente em laranja, confirmado em verde, apertado em azul; o anel do Home
    mostra a cor real da luz; as traseiras aparecem tracejadas (ficam atrás)."""

    def __init__(self, store=None, aspect=False, src="draft"):
        super().__init__()
        self.store, self.src, self.lit, self.lit_codes, self.live = store, src, set(), set(), None
        self.flash_parts, self.flash_t, self.aspect, self.view = set(), 0.0, aspect, "front"
        self.setMinimumSize(360, 260)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred if aspect else QSizePolicy.Expanding)
        sp.setHeightForWidth(aspect)  # com aspect, a altura segue a largura e o que vem abaixo fica colado
        self.setSizePolicy(sp)
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.setDuration(1400)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(lambda t: (setattr(self, "flash_t", t), self.update()))

    def hasHeightForWidth(self):
        return self.aspect

    def heightForWidth(self, w):
        return int(w * 410 / 600)

    def flash(self, parts):
        self.flash_parts = set(parts)
        self.anim.stop()
        self.anim.start()

    def _xf(self):
        s = min(self.width() / 600, self.height() / 410)
        return s, (self.width() - 560 * s) / 2, (self.height() - 380 * s) / 2

    def point(self, xy):
        s, ox, oy = self._xf()
        return QPointF(ox + xy[0] * s, oy + xy[1] * s)

    def anchor(self, part):
        return self.point(PARTS[part])

    def _led(self):
        try:
            z = getattr(self.store, self.src)["lights"][0]
            col = QColor(*z["rgb"])
            col.setAlphaF(0.35 + 0.65 * z["brightness"] / 255)
            return col
        except (AttributeError, KeyError, IndexError, TypeError):
            return QColor(C["blue"])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s, ox, oy = self._xf()
        p.translate(ox, oy)
        p.scale(s, s)

        def pen(color, width=1.0, style=Qt.SolidLine, alpha=1.0):
            c = QColor(color)
            c.setAlphaF(alpha)
            q = QPen(c, width, style)
            q.setCosmetic(True)
            q.setCapStyle(Qt.RoundCap)
            return q

        ink, fine = pen(C["ink"], 2), pen(C["pencil"], 1.1)
        on = set(self.lit) | {CODE_PART[c] for c in self.lit_codes if c in CODE_PART}
        on |= {"a", "b", "x", "y"} if "abxy" in on else set()
        on |= {"l2"} if "trig_l" in on else set()
        on |= {"r2"} if "trig_r" in on else set()
        flash = set(self.flash_parts)
        flash |= {"a", "b", "x", "y"} if "abxy" in flash else set()
        flash |= ({"l2"} if "trig_l" in flash else set()) | ({"r2"} if "trig_r" in flash else set())
        pressed = {CODE_PART[c] for c in self.live["down"] if c in CODE_PART} if self.live else set()

        def fill(part):
            if self.flash_t > 0.01 and part in flash:
                col = QColor(C["green"])
                col.setAlphaF(0.25 + 0.75 * self.flash_t)
                return col
            if part in pressed:
                return QColor(C["blue"])
            if part in on:
                return QColor(C["orange"])
            return None

        if self.view == "back":
            return self._paint_back(p, pen, ink, fill, on)

        # gatilhos (atrás do corpo) e ombros
        for part, rect in (("l2", QRectF(152, 14, 70, 34)), ("r2", QRectF(338, 14, 70, 34))):
            p.setPen(ink)
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawRoundedRect(rect, 12, 12)
            p.setPen(fine)
            p.drawLine(QPointF(rect.left() + 14, rect.top() + 10), QPointF(rect.right() - 14, rect.top() + 10))
        p.setPen(ink)
        p.setBrush(QColor(C["body"]))
        p.drawPath(BODY)
        for part, rect in (("l1", QRectF(136, 44, 92, 17)), ("r1", QRectF(332, 44, 92, 17))):
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawRoundedRect(rect, 8.5, 8.5)
        # placa frontal, textura das empunhaduras e motores
        p.setPen(pen(C["pencil"], 1, alpha=0.45))
        p.setBrush(Qt.NoBrush)
        p.drawPath(PLATE)
        for sign, x0 in ((1, 36), (-1, 524)):
            for i in range(4):
                grip = QPainterPath()
                grip.moveTo(x0 + sign * (2 + i * 7), 262 + i * 11)
                grip.cubicTo(QPointF(x0 + sign * (12 + i * 7), 284 + i * 11), QPointF(x0 + sign * (26 + i * 7),
                             300 + i * 9), QPointF(x0 + sign * (40 + i * 6), 306 + i * 8))
                p.drawPath(grip)
        for part in ("motor_l", "motor_r"):
            col = fill(part)
            if col:
                col.setAlphaF(min(col.alphaF(), 0.85))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPointF(*PARTS[part]), 18, 18)
        # traseiras: tracejadas porque ficam atrás
        p.setPen(pen(C["pencil"], 1.3, Qt.DashLine, 0.8))
        for sign, x in ((1, 122), (-1, 438)):
            back = QPainterPath()
            back.moveTo(x, 236)
            back.cubicTo(QPointF(x - sign * 14, 256), QPointF(x - sign * 24, 280), QPointF(x - sign * 28, 306))
            p.drawPath(back)
        # sticks: poço, capa e concavidade
        for part, axis in (("stick_l", "l"), ("stick_r", "r")):
            center = QPointF(*PARTS[part])
            p.setPen(fine)
            p.setBrush(QColor(C["ground"]))
            p.drawEllipse(center, 35, 35)
            off = QPointF(self.live[axis][0] * 14, -self.live[axis][1] * 14) if self.live else QPointF(0, 0)
            p.setPen(ink)
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawEllipse(center + off, 22, 22)
            p.setPen(pen(C["ground"] if fill(part) else C["pencil"], 1))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(center + off, 14, 14)
        # direcional com cantos arredondados
        h, v = QPainterPath(), QPainterPath()
        h.addRoundedRect(QRectF(205, 185, 68, 22), 6, 6)
        v.addRoundedRect(QRectF(228, 162, 22, 68), 6, 6)
        p.setPen(ink)
        p.setBrush(fill("dpad") or QColor(C["body"]))
        p.drawPath(h.united(v))
        p.setPen(fine)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(239, 196), 5, 5)
        # A B X Y com letras
        p.setFont(F(12, 700, 85))
        for part, letter in (("a", tr("A")), ("b", tr("B")), ("x", tr("X")), ("y", tr("Y"))):
            center = QPointF(*PARTS[part])
            col = fill(part)
            p.setPen(ink)
            p.setBrush(col or QColor(C["body"]))
            p.drawEllipse(center, 12, 12)
            p.setPen(QColor(C["ground"] if col else C["pencil"]))
            p.drawText(QRectF(center.x() - 12, center.y() - 12, 24, 24), Qt.AlignCenter, letter)
        # − e + como cápsulas com o símbolo desenhado
        for part in ("minus", "plus"):
            cx, cy = PARTS[part]
            col = fill(part)
            p.setPen(ink)
            p.setBrush(col or QColor(C["body"]))
            p.drawRoundedRect(QRectF(cx - 10, cy - 6.5, 20, 13), 6.5, 6.5)
            p.setPen(pen(C["ground"] if col else C["pencil"], 1.4))
            p.drawLine(QPointF(cx - 4, cy), QPointF(cx + 4, cy))
            if part == "plus":
                p.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))
        # Home com o anel na cor da luz
        led = self._led()
        col = fill("light")
        p.setPen(pen(led.name(), 3.2, alpha=led.alphaF()))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(*PARTS["light"]), 13, 13)
        p.setPen(pen(C["orange"], 1.6) if col else fine)
        p.setBrush(col or QColor(C["ground"]))
        p.drawEllipse(QPointF(*PARTS["light"]), 9, 9)
        if self.live:  # números ao vivo junto das partes
            p.setFont(F(13, 600, 85, tnum=True))
            for v, rect in ((self.live["lt"], QRectF(152, 14, 70, 34)), (self.live["rt"], QRectF(338, 14, 70, 34))):
                bar = QRectF(rect.left() + 6, rect.top() + 16, (rect.width() - 12) * v / 255, 8)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(C["blue"]))
                p.drawRoundedRect(bar, 4, 4)
                p.setPen(QColor(C["ink"]))
                p.drawText(QRectF(rect.left(), -6, rect.width(), 18), Qt.AlignCenter, f"{pct(v, 255)}%")
            for axis, (cx, cy) in (("l", PARTS["stick_l"]), ("r", PARTS["stick_r"])):
                x, y = self.live[axis]
                p.drawText(QRectF(cx - 60, cy + 38, 120, 18), Qt.AlignCenter,
                           tr("X {0:+d}  Y {1:+d}").format(round(x * 100), round(y * 100)))


    def _paint_back(self, p, pen, ink, fill, on):
        """Vista de trás, espelhada como quando se vira o controle: L2/R2 trocam de lado e as traseiras aparecem
        inteiras (M3 sob a mão direita, que fica à esquerda no desenho; M4 sob a esquerda: a confirmar)."""
        p.save()
        p.translate(560, 0)
        p.scale(-1, 1)
        for part, rect in (("l2", QRectF(152, 14, 70, 34)), ("r2", QRectF(338, 14, 70, 34))):
            p.setPen(ink)
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawRoundedRect(rect, 12, 12)
        p.setBrush(QColor(C["body"]))
        p.drawPath(BODY)
        for part, rect in (("l1", QRectF(136, 44, 92, 17)), ("r1", QRectF(332, 44, 92, 17))):
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawRoundedRect(rect, 8.5, 8.5)
        p.setPen(pen(C["pencil"], 1, alpha=0.45))  # junta da carcaça e plaqueta central
        p.setBrush(Qt.NoBrush)
        seam = QPainterPath()
        seam.moveTo(120, 78)
        seam.cubicTo(QPointF(220, 64), QPointF(340, 64), QPointF(440, 78))
        p.drawPath(seam)
        p.drawRoundedRect(QRectF(226, 120, 108, 64), 10, 10)
        for sign, x, part in ((1, 122, "m4"), (-1, 438, "m3")):
            curve = QPainterPath()
            curve.moveTo(x, 232)
            curve.cubicTo(QPointF(x - sign * 14, 254), QPointF(x - sign * 24, 280), QPointF(x - sign * 28, 308))
            stroke = QPainterPathStroker()
            stroke.setWidth(16)
            stroke.setCapStyle(Qt.RoundCap)
            p.setPen(pen(C["orange"], 2) if part in on else ink)
            p.setBrush(fill(part) or QColor(C["body"]))
            p.drawPath(stroke.createStroke(curve))
        p.restore()
        p.setFont(F(13, 700, 85))  # rótulos fora do espelho, para a letra não inverter
        for text, x, y, part in ((tr("M3"), 108, 212, "m3"), (tr("M4"), 452, 212, "m4"), (tr("L2"), 373, -8, None),
                                 (tr("R2"), 187, -8, None)):
            p.setPen(QColor(C["orange"] if part in on else C["chalk"] if part else C["pencil"]))
            p.drawText(QRectF(x - 30, y, 60, 18), Qt.AlignCenter, text)
        p.setFont(F(12, 700, 75, caps=True, track=1.0))
        p.setPen(QColor(C["pencil"]))
        p.drawText(QRectF(180, 352, 200, 18), Qt.AlignCenter, tr("vista de trás"))


class Radar(QWidget):
    """O stick visto de cima: zona morta (centro hachurado), máximo (anel), posição ao vivo e, depois da
    calibragem, o drift e o alcance medidos (tracejado azul)."""

    def __init__(self, store, side):
        super().__init__()
        self.store, self.side, self.live, self.drift, self.reach = store, side, None, None, None
        self.setMinimumSize(190, 190)
        sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return w

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 4
        c = QPointF(self.width() / 2, self.height() / 2)
        r = side / 2
        p.setPen(QPen(QColor(C["rule"]), 1))
        p.setBrush(QColor(C["ground"]))
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor("#2A2E33"), 1))
        p.setBrush(Qt.NoBrush)
        for f in (0.25, 0.5, 0.75):
            p.drawEllipse(c, r * f, r * f)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        if not self.store.ready() or "sticks" not in self.store.device:
            return
        dev = self.store.get(("sticks", self.side), self.store.device)
        cur = self.store.get(("sticks", self.side))
        # além do máximo: o stick já dá saída total
        beyond = QPainterPath()
        beyond.addEllipse(c, r, r)
        inner = QPainterPath()
        inner.addEllipse(c, r * cur["max"] / 100, r * cur["max"] / 100)
        shade = QColor(C["pencil"])
        shade.setAlphaF(0.10)
        p.fillPath(beyond.subtracted(inner), shade)
        hatch = QColor(C["pencil"])
        hatch.setAlphaF(0.55)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(hatch, Qt.BDiagPattern))
        p.drawEllipse(c, r * dev["deadzone"] / 100, r * dev["deadzone"] / 100)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(C["pencil"]), 1.2, Qt.DashLine))
        p.drawEllipse(c, r * dev["deadzone"] / 100, r * dev["deadzone"] / 100)
        p.drawEllipse(c, r * dev["max"] / 100, r * dev["max"] / 100)
        p.setPen(QPen(QColor(C["orange"]), 2))
        for key in ("deadzone", "max"):
            if cur[key] != dev[key]:
                p.drawEllipse(c, r * cur[key] / 100, r * cur[key] / 100)
        p.setPen(QPen(QColor(C["blue"]), 1.4, Qt.DashLine))
        for v in (self.drift, self.reach):
            if v:
                p.drawEllipse(c, r * min(v, 1), r * min(v, 1))
        if self.live is not None:
            x, y = self.live
            dot = QPointF(c.x() + x * r, c.y() - y * r)
            p.setPen(QPen(QColor(C["blue"]), 1))
            p.drawLine(c, dot)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["blue"]))
            p.drawEllipse(dot, 6, 6)


class CurvePlot(QWidget):
    """Curva (0,0)→P1→P2→(255,255) na grade, como a TableView do app. Geometria pendente em laranja,
    a gravada como fantasma; editável no modo grande."""

    def __init__(self, store, section, side, interactive=False, on_click=None):
        super().__init__()
        self.store, self.section, self.side, self.interactive = store, section, side, interactive
        self.on_click, self.drag, self.temp, self.live = on_click, None, None, None
        self.setMinimumHeight(190 if interactive else 84)
        if interactive:
            sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            sp.setHeightForWidth(True)
            self.setSizePolicy(sp)
        if on_click:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(tr("Abrir o editor de curva"))

    def hasHeightForWidth(self):
        return self.interactive

    def heightForWidth(self, w):
        return w

    def _data(self, src):
        return self.store.get((self.section, self.side), src)

    def _rect(self):
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.interactive:
            side = min(r.width(), r.height())
            r = QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side)
        return r

    def _pt(self, x, y):
        r = self._rect()
        return QPointF(r.left() + r.width() * x / 255, r.bottom() - r.height() * y / 255)

    def _poly(self, c):
        return [self._pt(0, 0), self._pt(c[0], c[1]), self._pt(c[2], c[3]), self._pt(255, 255)]

    def _band(self, d):
        return (d["deadzone"] / 100, d["max"] / 100) if self.section == "sticks" else (d["start"] / 200, d["end"] / 200)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._rect()
        p.fillRect(r, QColor(C["ground"]))
        p.setPen(QPen(QColor("#2A2E33"), 1))
        n = 8 if self.interactive else 6
        for i in range(1, n):
            p.drawLine(QPointF(r.left() + r.width() * i / n, r.top()), QPointF(r.left() + r.width() * i / n, r.bottom()))
            p.drawLine(QPointF(r.left(), r.top() + r.height() * i / n), QPointF(r.right(), r.top() + r.height() * i / n))
        p.setPen(QPen(QColor(C["rule"]), 1))
        p.drawRect(r)
        if not self.store.ready() or self.section not in self.store.device:
            return
        dev, cur = self._data(self.store.device), self._data(self.store.draft)
        (dlo, dhi), (clo, chi) = self._band(dev), self._band(cur)
        ghost = QColor(C["pencil"])
        ghost.setAlphaF(0.12)
        p.fillRect(QRectF(r.left(), r.top(), r.width() * dlo, r.height()), ghost)
        p.fillRect(QRectF(r.left() + r.width() * dhi, r.top(), r.width() * (1 - dhi), r.height()), ghost)
        orange = QColor(C["orange"])
        for d, c in ((dlo, clo), (dhi, chi)):
            if d != c:
                tint = QColor(C["orange"])
                tint.setAlphaF(0.18)
                lo, hi = sorted((d, c))
                p.fillRect(QRectF(r.left() + r.width() * lo, r.top(), r.width() * (hi - lo), r.height()), tint)
                p.setPen(QPen(orange, 1.5))
                x = r.left() + r.width() * c
                p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        p.setPen(QPen(QColor(C["pencil"]), 1.5, Qt.DashLine))
        p.drawPolyline(self._poly(dev["curve"]))
        curve = self.temp or cur["curve"]
        p.setPen(QPen(orange if curve != dev["curve"] else QColor(C["ink"]), 2.5 if self.interactive else 2))
        p.drawPolyline(self._poly(curve))
        if self.interactive:
            for i in (0, 1):
                pt = self._pt(curve[2 * i], curve[2 * i + 1])
                p.setPen(QPen(QColor(C["blue"] if self.drag == i else C["ink"]), 2))
                p.setBrush(QColor(C["ground"]))
                p.drawEllipse(pt, 7, 7)
            p.setPen(QColor(C["pencil"]))
            p.setFont(F(12, 600, 85, tnum=True))
            p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignLeft | Qt.AlignTop, tr("saída"))
            p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignRight | Qt.AlignBottom, tr("entrada"))
        if self.live is not None:
            y = r.bottom() - r.height() * self.live
            p.setPen(QPen(QColor(C["blue"]), 1.5, Qt.DashLine))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(C["blue"]))
            p.drawEllipse(QPointF(r.right() - 1, y), 5, 5)

    def _value(self, pos):
        r = self._rect()
        x = round(255 * (pos.x() - r.left()) / r.width())
        y = round(255 * (r.bottom() - pos.y()) / r.height())
        return max(0, min(255, x)), max(0, min(255, y))

    def mousePressEvent(self, e):
        if self.on_click and not self.interactive:
            self.on_click()
            return
        if not self.interactive or not self.store.ready():
            return
        curve = self._data(self.store.draft)["curve"]
        d = [(self._pt(curve[2 * i], curve[2 * i + 1]) - e.position()).manhattanLength() for i in (0, 1)]
        i = 0 if d[0] <= d[1] else 1
        if d[i] < 24:
            self.drag, self.temp = i, list(curve)
            self.update()

    def mouseMoveEvent(self, e):
        if self.drag is None:
            return
        x, y = self._value(e.position())
        self.temp[2 * self.drag], self.temp[2 * self.drag + 1] = x, y
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag is None:
            return
        curve, self.drag, self.temp = self.temp, None, None
        dev = self._data(self.store.device)["curve"]
        self.store.set((self.section, self.side, "curve"), dev if curve == dev else curve)


class Battery(QWidget):
    def __init__(self, big=False):
        super().__init__()
        self.level, self.charging = None, False
        self.setFixedSize(QSize(44, 22) if big else QSize(26, 14))

    def set(self, level, charging):
        self.level, self.charging = level, charging
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width() - 4, self.height()
        p.setPen(QPen(QColor(C["chalk"]), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 3, 3)
        p.fillRect(QRectF(w, h * 0.32, 3, h * 0.36), QColor(C["chalk"]))
        if self.level:
            col = QColor(C["red"] if self.level <= 1 else C["green"] if self.charging else C["ink"])
            p.fillRect(QRectF(3.5, 3.5, (w - 7) * self.level / 4, h - 7), col)


# ---------------------------------------------------------------- linhas reutilizáveis
def stick_rows(cell, side, extended=False):
    p = ("sticks", side)
    cell.add_path(tr("Zona morta"), Stepper(0, 50), p + ("deadzone",), lambda v: f"{v}%")
    cell.add_path(tr("Máximo"), Stepper(50, 100), p + ("max",), lambda v: f"{v}%")
    if extended:
        cell.add_path(tr("Curva"), Segmented(PRESETS), p + ("curve",), curve_name, wide=True)
        cell.add_path(tr("Inverter eixo X"), ChoiceField(YES_NO), p + ("invert_x",), lambda v: tr("Sim") if v else tr("Não"))
        cell.add_path(tr("Inverter eixo Y"), ChoiceField(YES_NO), p + ("invert_y",), lambda v: tr("Sim") if v else tr("Não"))
    else:
        cell.add_path(tr("Curva"), ChoiceField(PRESETS), p + ("curve",), curve_name)


def trigger_rows(cell, side, extended=False):
    p = ("triggers", side)
    half = {"to_ui": lambda r: round(r / 2), "from_ui": lambda u: u * 2}
    show = lambda r: f"{r / 2:g}%".replace(".", ",")
    cell.add_path(tr("Início"), Stepper(0, 50), p + ("start",), show, **half)
    cell.add_path(tr("Fim"), Stepper(50, 100), p + ("end",), show, **half)
    if extended:
        cell.add_path(tr("Curva"), Segmented(PRESETS), p + ("curve",), curve_name, wide=True)
    else:
        cell.add_path(tr("Curva"), ChoiceField(PRESETS), p + ("curve",), curve_name)


def swap_row(cell, section, text):
    store = cell.store

    def put(v):
        d = copy.deepcopy(store.draft[section])
        d["left"]["swap"] = d["right"]["swap"] = v
        store.set((section,), d)
    cell.add(text, ChoiceField(YES_NO), lambda src: src[section]["left"]["swap"], put,
             lambda v: tr("Sim") if v else tr("Não"), section)


def motor_row(cell, index, text=tr("Vibração")):
    cell.add_path(text, Stepper(0, 100), ("motor", "motors", index), lambda r: f"{pct(r, 255)}%",
                  to_ui=lambda r: pct(r, 255), from_ui=lambda u: round(u * 255 / 100))


def shutdown_row(cell):
    cell.add_path(tr("Desligar"), Stepper(1, 31, " min", {31: tr("Nunca")}), ("motor", "shutdown_min"),
                  lambda v: tr("Nunca") if v >= kl.NO_SHUTDOWN else f"{v} min",
                  to_ui=lambda v: 31 if v >= kl.NO_SHUTDOWN else max(1, min(v, 30)),
                  from_ui=lambda u: kl.NO_SHUTDOWN if u == 31 else u)


def light_rows(cell):
    p = ("lights", 0)
    cell.add_path(tr("Cor"), SwatchField(), p + ("rgb",), color_name)
    cell.add_path(tr("Brilho"), Stepper(0, 100), p + ("brightness",), lambda r: f"{pct(r, 255)}%",
                  to_ui=lambda r: pct(r, 255), from_ui=lambda u: round(u * 255 / 100))
    cell.add_path(tr("Efeito"), ChoiceField([(tr("Fixa"), False), (tr("Respirando"), True)], 118), p + ("breath",),
                  lambda v: tr("Respirando") if v else tr("Fixa"))
    cell.add_path(tr("Ritmo"), Stepper(0, 100), p + ("speed",), lambda r: f"{pct(r, 2048)}%",
                  to_ui=lambda r: pct(r, 2048), from_ui=lambda u: round(u * 2048 / 100))


def page_head(title, meta):
    head = QHBoxLayout()
    head.setSpacing(18)
    head.addWidget(label(title, F(34, 800, 68, caps=True, track=0.6)))
    m = label(meta, F(14), C["pencil"])
    head.addWidget(m, 0, Qt.AlignBottom)
    head.addStretch(1)
    return head, m


def column(cells, width=312):
    box = QWidget()
    box.setFixedWidth(width)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(16)
    for c in cells:
        lay.addWidget(c)
    lay.addStretch(1)
    return box


def leader_order(keys, x, top=62, pitch=41):
    """Ordem das linhas que liga cada tecla à sua peça sem cruzar: o casamento de menor comprimento total entre
    pontos numa reta (as linhas da célula) e alvos de um lado dela nunca se cruza. DP sobre subconjuntos (n ≤ 8).
    Geometria aproximada em coordenadas da planta: linhas a cada `pitch`, a partir de `top`, na borda `x`."""
    keys = [k for k in keys if k in KEY_XY] + [k for k in keys if k not in KEY_XY]
    n = len([k for k in keys if k in KEY_XY])
    best, pick = {0: 0.0}, {}
    for mask in range(1 << n):
        if mask not in best:
            continue
        row = bin(mask).count("1")
        for j in range(n):
            if mask & (1 << j):
                continue
            tx, ty = KEY_XY[keys[j]]
            cost = best[mask] + ((tx - x) ** 2 + (ty - (top + pitch * row)) ** 2) ** 0.5
            nxt = mask | (1 << j)
            if cost < best.get(nxt, float("inf")):
                best[nxt], pick[nxt] = cost, j
    order, mask = [], (1 << n) - 1
    while mask:
        order.append(keys[pick[mask]])
        mask &= ~(1 << pick[mask])
    return order[::-1] + keys[n:]


class LeadOverlay(QWidget):
    """Camada por cima da página só para as linhas de chamada: elas chegam até a tecla, por cima do desenho."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self.page.draw_leads(p)


def value_cols(w):
    """Bordas direitas das colunas da tabela de predefinições: zona morta E, D · máximo E, D."""
    r = w - 12
    return [r - 140, r - 96, r - 44, r]


class PresetHead(QWidget):
    """Cabeçalho da tabela de predefinições e a linha do que foi medido (drift parado e alcance girando)."""

    def __init__(self):
        super().__init__()
        self.values = ("",) * 4
        self.setFixedHeight(78)

    def set_values(self, values):
        self.values = values
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        xs = value_cols(self.width())
        p.setFont(F(11, 700, 75, caps=True, track=1.2))
        for text, a, b in ((tr("Zona morta"), xs[0], xs[1]), (tr("Máximo"), xs[2], xs[3])):
            p.setPen(QColor(C["pencil"]))
            p.drawText(QRectF(a - 40, 0, b - a + 40, 15), Qt.AlignHCenter | Qt.AlignTop, text)
            p.setPen(QPen(QColor(C["rule_hi"]), 1))
            p.drawLine(QPointF(a - 36, 19.5), QPointF(b, 19.5))
        p.setPen(QColor(C["pencil"]))
        for x, tag in zip(xs, tr("EDED")):
            p.drawText(QRectF(x - 40, 22, 40, 15), Qt.AlignRight | Qt.AlignTop, tag)
        p.setFont(F(14, 600, 85))
        p.setPen(QColor(C["chalk"]))
        p.drawText(QRectF(12, 42, xs[0] - 52, 20), Qt.AlignLeft | Qt.AlignVCenter, tr("Medido"))
        p.setFont(F(14, 600, 85, tnum=True))
        for x, v in zip(xs, self.values):
            p.drawText(QRectF(x - 44, 42, 44, 20), Qt.AlignRight | Qt.AlignVCenter, v)
        p.setFont(F(12))
        p.setPen(QColor(C["pencil"]))
        p.drawText(QRectF(12, 62, self.width() - 24, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   tr("drift parado · alcance girando"))


class PresetRow(QPushButton):
    """Uma predefinição da calibragem: nome, os quatro valores que ela grava e para quem serve. Escolhida e ainda
    não aplicada, fica laranja como toda mudança pendente."""

    def __init__(self, name, why):
        super().__init__()
        self.name, self.why, self.values, self.picked = name, why, ("",) * 4, False
        self.setFixedHeight(54)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(why)

    def set_values(self, values, picked):
        self.values, self.picked = values, picked
        self.setAccessibleName(tr("{0}: zona morta E {1}, D {2}; máximo E {3}, D {4}").format(self.name, values[0], values[1], values[2], values[3]))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse()
        edge = C["blue"] if self.hasFocus() else C["orange"] if self.picked else tr("#5C636D") if hover else C["rule_hi"]
        p.setPen(QPen(QColor(edge), 1))
        p.setBrush(QColor("#33251C" if self.picked else C["cell_hi"] if hover else C["cell"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        xs = value_cols(self.width())
        p.setFont(F(14, 700, 85))
        p.setPen(QColor(C["orange"] if self.picked else C["ink"]))
        p.drawText(QRectF(12, 8, xs[0] - 52, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.name, Qt.ElideRight, xs[0] - 52))
        p.setFont(F(14, 600, 85, tnum=True))
        p.setPen(QColor(C["orange"] if self.picked else C["chalk"]))
        for x, v in zip(xs, self.values):
            p.drawText(QRectF(x - 44, 8, 44, 20), Qt.AlignRight | Qt.AlignVCenter, v)
        p.setFont(F(12))
        p.setPen(QColor(C["pencil"]))
        p.drawText(QRectF(12, 30, self.width() - 24, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.why, Qt.ElideRight, self.width() - 24))


def draw_lead(p, start, end, pending):
    col = QColor(C["orange"] if pending else C["blue"])
    col.setAlphaF(0.9 if pending else 0.4)
    p.setPen(QPen(col, 1.2 if pending else 1))
    p.drawLine(start, end)
    p.setPen(Qt.NoPen)
    p.setBrush(col)
    p.drawEllipse(end, 3, 3)


# ---------------------------------------------------------------- páginas
class Page(Sheet):
    mode = "normal"
    leads = False  # True: a página desenha linhas de chamada na camada de cima (draw_leads)

    def __init__(self, store):
        super().__init__()
        self.store, self.cells = store, []
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(28, 20, 28, 20)
        self.outer.setSpacing(16)
        self.overlay = LeadOverlay(self) if self.leads else None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.overlay:
            self.overlay.setGeometry(self.rect())
            self.overlay.raise_()

    def refresh(self):
        for c in self.cells:
            c.refresh()
        if self.overlay:
            self.overlay.raise_()
            self.overlay.update()

    def draw_leads(self, p):
        pass

    def live(self, pad):
        pass

    def flash(self, section):
        for c in self.cells:
            if section in c.sections:
                c.flash()


class SheetPage(Page):
    """A ficha: planta ao centro, lado esquerdo do controle à esquerda, espelhado à direita."""
    leads = True

    def __init__(self, store, go):
        super().__init__(store)
        head, self.meta = page_head(tr("Ficha de acerto"), "")
        self.outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(24)
        # de cima para baixo como no controle (gatilho, stick, motor): as linhas de chamada não se cruzam
        L = [SetupCell(store, tr("Gatilho L2"), tr("E")), SetupCell(store, tr("Stick esquerdo"), tr("E")),
             SetupCell(store, tr("Motor esquerdo"), tr("E"))]
        R = [SetupCell(store, tr("Gatilho R2"), tr("D"), mirror=True), SetupCell(store, tr("Stick direito"), tr("D"), mirror=True),
             SetupCell(store, tr("Motor direito"), tr("D"), mirror=True)]
        for cells, side, idx in ((L, "left", 0), (R, "right", 1)):
            trigger_rows(cells[0], side)
            stick_rows(cells[1], side)
            cells[1].body.addWidget(CurvePlot(store, "sticks", side, on_click=lambda: go(1)))
            motor_row(cells[2], idx)
        self.light = SetupCell(store, tr("Luz"), tr("centro"))
        light_rows(self.light)
        self.general = SetupCell(store, tr("Geral"), tr("centro"))
        self.general.add_link(tr("Remapeadas"), "remap", lambda d: tr("%d de %d") % (
            sum(t != k for k, t in d["remap"].items()), len(d["remap"])), lambda: go(3, "front"))
        self.general.add_link(tr("Turbo"), "turbo", lambda d: (lambda n: tr("Desligado") if not n else f"{n} teclas")(
            len(d["turbo"]["manual_on"]) + len(d["turbo"]["auto_on"])), lambda: go(4))
        self.general.add_link(tr("Macros"), "macros", lambda d: ", ".join(
            m["name"] for m in d["macros"]["slots"] if not m.get("empty")) or tr("Nenhuma"), lambda: go(3, "macros"))
        shutdown_row(self.general)
        self.plan = ControllerPlan(store)
        self.center = QWidget()
        center = QVBoxLayout(self.center)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(16)
        center.addWidget(self.plan, 1)
        self.bottom = QBoxLayout(QBoxLayout.LeftToRight)
        self.bottom.setSpacing(16)
        self.bottom.addWidget(self.light)
        self.bottom.addWidget(self.general)
        center.addLayout(self.bottom)
        body.addWidget(column(L))
        body.addWidget(self.center, 1)
        body.addWidget(column(R))
        self.outer.addLayout(body, 1)
        self.cells = L + R + [self.light, self.general]
        # a Geral não tem uma peça só (remapeamento, turbo, macros): fica sem linha de chamada
        self.links = list(zip(self.cells, ("trig_l", "stick_l", "motor_l", "trig_r", "stick_r", "motor_r", "light")))
        self.stacked = False

    def refresh(self):
        self.plan.lit = {part for cell, part in self.links if cell.pending()}
        super().refresh()
        s = self.store
        if s.ready():
            n = s.count()
            self.meta.setText(tr("Valores gravados no controle · ") + (
                tr("{0} mudança{1} pendente{2} em laranja").format(n, 's' if n != 1 else '', 's' if n != 1 else '') if n
                else tr("use − e + para mudar um valor")))
        else:
            self.meta.setText(tr("Ligue o controle (cabo, 2.4G ou Bluetooth): a ficha se preenche quando ele responder."))
        self.plan.update()
        self.update()

    def flash(self, section):
        super().flash(section)
        self.plan.flash(part for cell, part in self.links if section in cell.sections)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        center = self.width() - 56 - 2 * 312 - 48  # margens, colunas laterais e espaços
        self.stacked = center < 612
        self.bottom.setDirection(QBoxLayout.TopToBottom if self.stacked else QBoxLayout.LeftToRight)
        for c in (self.light, self.general):  # empilhadas, ficam com a largura das laterais
            c.setMaximumWidth(312 if self.stacked else 16777215)
            self.bottom.setAlignment(c, Qt.AlignHCenter if self.stacked else Qt.AlignmentFlag(0))
        self.plan.setMinimumHeight(150 if self.stacked else 260)

    def lead_segments(self):
        origin = QPointF(self.plan.mapTo(self, QPoint(0, 0)))
        out = []
        for cell, part in self.links:
            tl, w = cell.mapTo(self, QPoint(0, 0)), cell.width()
            if cell is self.light:
                start = QPointF(tl.x() + w / 2, tl.y())
            elif tl.x() < self.width() / 2:
                start = QPointF(tl.x() + w, tl.y() + 22)
            else:
                start = QPointF(tl.x(), tl.y() + 22)
            out.append((start, origin + self.plan.anchor(part), part in self.plan.lit))
        return out

    def draw_leads(self, p):
        for start, end, pending in self.lead_segments():
            draw_lead(p, start, end, pending)


class AutoCal(SetupCell):
    """Calibragem automática dos sticks: zera a zona morta no controle só durante a medição, mede o drift parado
    e o alcance girando (pelo XInput), restaura e sugere predefinições como mudança pendente."""
    PHASES = {"rest": 3.0, "spin": 4.0}

    def __init__(self, store, link, pad, radars):
        super().__init__(store, tr("Calibragem automática"), "", columns=False)
        self.link, self.pad, self.radars = link, pad, radars
        self.phase, self.orig, self.t0, self.after_restore = "idle", None, 0.0, ("idle", None)
        self.drift, self.reach = {"left": 0.0, "right": 0.0}, {"left": 0.0, "right": 0.0}
        self.samples = {"left": [], "right": []}
        self.text = Para(color=C["chalk"])
        self.body.addWidget(self.text)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.body.addWidget(self.bar)
        self.table = QWidget()
        rows = QVBoxLayout(self.table)
        rows.setContentsMargins(0, 4, 0, 0)
        rows.setSpacing(6)
        self.head = PresetHead()
        rows.addWidget(self.head)
        self.presets = []
        for name, dz, mx, why in CAL_PRESETS:
            b = PresetRow(name, why)
            b.clicked.connect(lambda _=False, dz=dz, mx=mx: self._pick(dz, mx))
            rows.addWidget(b)
            self.presets.append((b, dz, mx))
        self.body.addWidget(self.table)
        row = QHBoxLayout()
        self.go = QPushButton(tr("Calibrar automaticamente"))  # laranja é só para mudança pendente e Aplicar
        self.cancel = QPushButton(tr("Cancelar"))
        for b in (self.go, self.cancel):
            b.setCursor(Qt.PointingHandCursor)
            row.addWidget(b)
        row.addStretch(1)
        self.body.addLayout(row)
        self.go.clicked.connect(self.start)
        self.cancel.clicked.connect(self.abort)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        link.rawdone.connect(self._raw)
        self._show("idle")

    def _show(self, phase, message=None):
        self.phase = phase
        texts = {
            "idle": tr("Mede quanto cada stick treme parado (drift) e até onde chega girando, e sugere zona morta e "
                    "máximo. Leva uns 10 segundos."),
            "prep": tr("Preparando: zona morta 0, máximo 100 e curva linear no controle, só durante a medição…"),
            "rest": tr("Solte os dois sticks e não toque no controle."),
            "spin": tr("Agora gire os dois sticks devagar, encostando na borda, em círculos."),
            "restore": tr("Devolvendo ao controle os valores que estavam gravados…"),
            "result": tr("Escolha uma predefinição: ela entra como mudança pendente (laranja). Confira e clique em Aplicar."),
            "error": message or "",
        }
        text = texts[phase]
        short = [tr(n) for side, n in (("left", "esquerdo"), ("right", "direito")) if self.reach[side] < 0.6]
        if phase == "result" and len(short) == 2:
            text += tr(" Os dois sticks não chegaram à borda girando: o máximo fica como está.")
        elif phase == "result" and short:
            text += tr(" O stick {0} não chegou à borda girando: o máximo dele fica como está.").format(short[0])
        self.text.setText(text, C["red"] if phase == "error" else C["chalk"])
        busy = phase in ("prep", "rest", "spin", "restore")
        self.bar.setVisible(busy)
        self.bar.setRange(0, 0 if phase in ("prep", "restore") else 100)
        self.go.setVisible(not busy)
        self.go.setText(tr("Medir de novo") if phase == "result" else tr("Calibrar automaticamente"))
        self.cancel.setVisible(phase in ("rest", "spin"))
        self.table.setVisible(phase == "result")
        for side, radar in self.radars.items():
            radar.drift = self.drift[side] if phase == "result" else None
            radar.reach = self.reach[side] if phase == "result" and self.reach[side] >= 0.6 else None
            radar.update()
        self.refresh()

    def refresh(self):
        super().refresh()
        if self.phase != "result" or "sticks" not in self.store.device:
            return
        d, r = self.drift, self.reach
        self.head.set_values([f"{num(d['left'] * 100)}%", f"{num(d['right'] * 100)}%", f"{round(r['left'] * 100)}%",
                              f"{round(r['right'] * 100)}%"])
        draft, dev = self.store.draft["sticks"], self.store.device["sticks"]
        for b, dz, mx in self.presets:  # laranja enquanto a ficha tiver exatamente esta predefinição pendente
            v = calibrated(draft, d, r, dz, mx)
            b.set_values([f"{v[s][k]}%" for k in ("deadzone", "max") for s in ("left", "right")],
                         v == draft and draft != dev)

    def start(self):
        if not self.store.ready() or "sticks" not in self.store.device:
            self._show("error", tr("O controle ainda não respondeu: espere a ficha preencher e tente de novo."))
            return
        if self.pad.read() is None:
            self._show("error", tr("O Windows não está vendo o controle como gamepad (XInput): conecte pelo cabo ou "
                                "dongle para medir."))
            return
        self.orig = copy.deepcopy(self.store.device["sticks"])
        temp = copy.deepcopy(self.orig)
        for side in ("left", "right"):
            temp[side].update(deadzone=0, max=100, curve=list(LINEAR))
        self.drift, self.reach = {"left": 0.0, "right": 0.0}, {"left": 0.0, "right": 0.0}
        self.samples = {"left": [], "right": []}
        self._show("prep")
        self.link.raw_apply("sticks", temp)

    def _restore(self, after, message=None):
        """Devolve os valores originais ao controle; a tela só diz "restaurados" depois que a releitura confere."""
        self.timer.stop()
        self.after_restore = (after, message)
        self._show("restore")
        self.link.raw_apply("sticks", self.orig)

    def abort(self):
        if self.phase in ("rest", "spin"):
            self._restore("idle")

    def _raw(self, section, stored, ok):
        if section != "sticks":
            return
        if self.phase == "prep":
            if ok:
                self.t0 = time.monotonic()
                self._show("rest")
                self.timer.start()
            elif stored == self.orig:  # a releitura mostra os valores de antes
                self._show("error", tr("O controle não confirmou a preparação. Nada mudou; tente de novo."))
            else:  # sem resposta ou outro valor gravado: devolve os originais por garantia
                self._restore("error", tr("O controle não confirmou a preparação. Os valores do controle foram "
                                       "restaurados; tente de novo."))
        elif self.phase == "restore":
            if ok:
                self._show(*self.after_restore)
            else:
                self._show("error", tr("Não consegui devolver os valores ao controle. Clique em Reler do controle e "
                                    "confira a zona morta antes de jogar."))

    def _tick(self):
        pad = self.pad.read()
        if pad is None:
            self._restore("error", tr("O Windows parou de ver o controle no meio da medição. Os valores do controle "
                                   "foram restaurados; conecte pelo cabo ou dongle e meça de novo."))
            return
        elapsed = time.monotonic() - self.t0
        if elapsed >= 0.3:  # o controle leva um instante para assentar depois de reconfigurado
            for side, axis in (("left", "l"), ("right", "r")):
                self.samples[side].append(min(1.0, math.hypot(*pad[axis])))
        self.bar.setValue(int(100 * min(1.0, elapsed / self.PHASES[self.phase])))
        if elapsed < self.PHASES[self.phase]:
            return
        if self.phase == "rest":
            moved = False
            for side in ("left", "right"):
                self.drift[side], m = rest_drift(self.samples[side])
                moved |= m
            self.samples = {"left": [], "right": []}
            if moved:
                self._restore("error", tr("Um stick se mexeu enquanto devia estar parado. Solte o controle numa mesa e "
                                       "meça de novo (os valores do controle foram restaurados)."))
                return
            self.t0 = time.monotonic()
            self._show("spin")
        else:
            for side in ("left", "right"):
                self.reach[side] = pctile(self.samples[side], 0.98)
            self._restore("result")

    def _pick(self, dz, mx):
        self.store.set(("sticks",), calibrated(self.store.draft["sticks"], self.drift, self.reach, dz, mx))


class SticksPage(Page):
    mode = "analogicos"

    def __init__(self, store, link, pad):
        super().__init__(store)
        head, _ = page_head(tr("Analógicos"), tr("Mova o stick para ver onde ele está. Ajuste com − e +, escolha a curva ou "
                                          "arraste os pontos dela."))
        self.outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.radars, self.plots, sides = {}, {}, []
        for side, name, tag, mirror in (("left", "esquerdo", tr("E"), False), ("right", "direito", tr("D"), True)):
            cell = SetupCell(store, tr("Stick " + name), tag, mirror=mirror)
            radar, plot = Radar(store, side), CurvePlot(store, "sticks", side, interactive=True)
            viz = QHBoxLayout()
            viz.setSpacing(12)
            for w in ((plot, radar) if mirror else (radar, plot)):
                viz.addWidget(w, 1)
            cell.top.addLayout(viz)
            stick_rows(cell, side, extended=True)
            self.radars[side], self.plots[side] = radar, plot
            sides.append(cell)
        self.cal = AutoCal(store, link, pad, self.radars)
        both = SetupCell(store, tr("Os dois"), tr("centro"))
        swap_row(both, "sticks", tr("Trocar lados"))
        body.addWidget(sides[0], 1, Qt.AlignTop)
        body.addWidget(column([self.cal, both], 320))
        body.addWidget(sides[1], 1, Qt.AlignTop)
        self.outer.addLayout(body, 1)
        self.cells = sides + [self.cal, both]

    def refresh(self):
        super().refresh()
        for w in list(self.radars.values()) + list(self.plots.values()):
            w.update()

    def live(self, pad):
        for side, axis in (("left", "l"), ("right", "r")):
            self.radars[side].live = pad[axis] if pad else None
            self.plots[side].live = min(1.0, math.hypot(*pad[axis])) if pad else None
            self.radars[side].update()
            self.plots[side].update()


class TriggersPage(Page):
    mode = "analogicos"

    def __init__(self, store):
        super().__init__(store)
        head, _ = page_head(tr("Gatilhos"), tr("Início e fim do curso e curva de cada gatilho. Puxe o gatilho para ver onde "
                                        "ele está."))
        self.outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.plots, sides = {}, []
        for side, name, tag, mirror in (("left", tr("L2"), tr("E"), False), ("right", tr("R2"), tr("D"), True)):
            cell = SetupCell(store, tr("Gatilho " + name), tag, mirror=mirror)
            plot = CurvePlot(store, "triggers", side, interactive=True)
            cell.top.addWidget(plot)
            trigger_rows(cell, side, extended=True)
            self.plots[side] = plot
            sides.append(cell)
        both = SetupCell(store, tr("Os dois"), tr("centro"))
        swap_row(both, "triggers", tr("Trocar lados"))
        self.readout = label("", F(13), C["pencil"])
        self.readout.setWordWrap(True)
        both.body.addWidget(self.readout)
        body.addWidget(sides[0], 1, Qt.AlignTop)
        body.addWidget(column([both], 300))
        body.addWidget(sides[1], 1, Qt.AlignTop)
        self.outer.addLayout(body, 1)
        self.cells = sides + [both]

    def refresh(self):
        super().refresh()
        for plot in self.plots.values():
            plot.update()

    def live(self, pad):
        self.readout.setText(tr("Linha azul: quanto o gatilho está saindo agora (o que os jogos recebem).") if pad else
                             tr("O Windows não está vendo o controle como gamepad (XInput): conecte pelo cabo ou dongle "
                             "para ver a posição ao vivo."))
        for side, key in (("left", "lt"), ("right", "rt")):
            self.plots[side].live = pad[key] / 255 if pad else None
            self.plots[side].update()


class PlanPage(Page):
    """Planta ao centro; cada tecla é uma linha de célula presa à sua parte por uma linha de chamada."""
    leads = True

    def __init__(self, store, title, meta):
        super().__init__(store)
        head, self.meta = page_head(title, meta)
        self.outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(24)
        self.left, self.right = QVBoxLayout(), QVBoxLayout()
        boxes = []
        for lay in (self.left, self.right):
            box = QWidget()
            box.setFixedWidth(330)
            box.setLayout(lay)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(16)
            boxes.append(box)
        self.plan = ControllerPlan(store, aspect=True)
        center = QVBoxLayout()
        center.setSpacing(16)
        center.addWidget(self.plan)
        self.under = QHBoxLayout()
        center.addLayout(self.under)
        center.addStretch(1)
        body.addWidget(boxes[0])
        body.addLayout(center, 1)
        body.addWidget(boxes[1])
        self.outer.addLayout(body, 1)
        self.notes, self.built, self.boxes, self.center = [], None, boxes, center

    def _side_cells(self, items, make_row):
        clear(self.left)
        clear(self.right)
        self.notes = []
        L = SetupCell(self.store, tr("Lado esquerdo"), tr("E"))
        R = SetupCell(self.store, tr("Lado direito"), tr("D"), mirror=True)
        for cell, keys, x in ((L, [k for k in items if k in LEFT_KEYS], -44),
                              (R, [k for k in items if k not in LEFT_KEYS], 604)):
            for k in leader_order(keys, x):
                self.notes.append((cell, make_row(cell, k), k))
        for lay, cell in ((self.left, L), (self.right, R)):
            lay.addWidget(cell)
            lay.addStretch(1)
        return [L, R]

    def refresh(self):
        s = self.store
        lit = set()
        for cell, b, k in self.notes:
            try:
                if b.get(s.draft) != b.get(s.device):
                    lit.add(k)
            except (KeyError, IndexError, TypeError):
                pass
        self.plan.lit_codes = lit
        super().refresh()
        self.plan.update()

    def lead_segments(self):
        origin = QPointF(self.plan.mapTo(self, QPoint(0, 0)))
        out = []
        for cell, b, k in self.notes:
            if not cell.isVisible() or k not in KEY_XY:
                continue
            y = cell.mapTo(self, QPoint(0, cell.grid.cellRect(b.row, 0).center().y())).y()
            tl = cell.mapTo(self, QPoint(0, 0))
            x = tl.x() + cell.width() if tl.x() < self.width() / 2 else tl.x()
            out.append((QPointF(x, y), origin + self.plan.point(KEY_XY[k]), k in self.plan.lit_codes))
        return out

    def draw_leads(self, p):
        for start, end, pending in self.lead_segments():
            draw_lead(p, start, end, pending)


class ButtonsPage(PlanPage):
    FRONT = tr("Escolha o que cada tecla faz. Padrão: o que ela sempre fez. Desativada: não faz nada.")
    BACK = (tr("Vista de trás, como quando você vira o controle. M3 e M4 são as traseiras; M1 e M2 não têm botão "
            "próprio. Cada macro imita teclas do controle ou vira uma tecla do PC."))


    def __init__(self, store):
        super().__init__(store, tr("Botões"), self.FRONT)
        self.view, self.paddles = "front", []
        self.views = Segmented([(tr("Frente"), "front"), (tr("Trás · macros M1–M4"), "back")])
        self.views.picked.connect(self.set_view)
        self.under.addStretch(1)
        self.under.addWidget(self.views)
        self.under.addStretch(1)

    def set_view(self, view):
        self.view = self.plan.view = "back" if view in ("back", "macros") else "front"
        self.meta.setText(self.BACK if self.view == "back" else self.FRONT)
        self.refresh()

    def refresh(self):
        keys = list(self.store.device.get("remap", {}))
        slots = [m["name"] for m in self.store.device.get("macros", {}).get("slots", [])]
        self.views.setVisible(bool(slots))
        self.views.show_state(self.view, self.view)
        sig = (self.view, tuple(keys), tuple(slots))
        if sig != self.built:
            self.built = sig
            if self.view == "back":
                clear(self.left)
                clear(self.right)
                self.notes, self.cells, self.paddles = [], [], []
                # traseiras com linha até o desenho; M1/M2 (sem botão físico) logo abaixo, sem linha
                for lay, names in ((self.left, (tr("M1"), tr("M3"))), (self.right, (tr("M2"), tr("M4")))):  # M1 M2 / M3 M4
                    for n in names:
                        if n not in slots:
                            continue
                        rear = n in ("M3", "M4")
                        cell = MacroCell(self.store, slots.index(n), tr("Traseira {0}").format(n) if rear else tr("Macro {0}").format(n),
                                         {"M3": tr("D"), "M4": tr("E")}.get(n, ""), mirror=lay is self.right)
                        lay.addWidget(cell)
                        self.cells.append(cell)
                        if rear:
                            self.paddles.append((cell, n.lower()))
                    lay.addStretch(1)
            else:
                self.paddles = []

                def row(cell, k):
                    opts = [(tr("Padrão"), k), (tr("Desativada"), 2048)] + [(key_name(c), c) for c in keys if c != k]
                    return cell.add_path(key_name(k), ChoiceField(opts, 124), ("remap", k),
                                         lambda t, k=k: remap_name(k, t))
                self.cells = self._side_cells(keys, row) if keys else []
        self.plan.lit = {part for cell, part in self.paddles if cell.pending()}
        super().refresh()

    def lead_segments(self):
        if self.view != "back":
            return super().lead_segments()
        origin = QPointF(self.plan.mapTo(self, QPoint(0, 0)))
        out = []
        for cell, part in self.paddles:
            tl = cell.mapTo(self, QPoint(0, 0))
            x = tl.x() + cell.width() if tl.x() < self.width() / 2 else tl.x()
            out.append((QPointF(x, tl.y() + 22), origin + self.plan.anchor(part), cell.pending()))
        return out


class TurboPage(PlanPage):
    def __init__(self, store):
        super().__init__(store, tr("Turbo"), tr("Manual: repete enquanto você segura. Automático: repete sozinho."))

    def refresh(self):
        t = self.store.device.get("turbo")
        keys = (tuple(t["keys"]), tuple(t["auto_capable"])) if t else None
        if keys != self.built:
            self.built = keys
            clear(self.under)
            self.cells = []
            if t:
                s, names = self.store, {"off": tr("Desligado"), "manual": tr("Manual"), "auto": tr("Automático")}

                def row(cell, k):
                    opts = [(tr("Desligado"), "off"), (tr("Manual"), "manual")] + (
                        [(tr("Automático"), "auto")] if k in t["auto_capable"] else [])
                    return cell.add(key_name(k), ChoiceField(opts, 124), lambda src, k=k: turbo_mode(src["turbo"], k),
                                    lambda mode, k=k: s.set(("turbo",), turbo_with(s.draft["turbo"], k, mode)),
                                    lambda mode: names[mode], "turbo")
                speed = SetupCell(s, tr("Velocidade"), tr("centro"))
                speed.setFixedWidth(312)
                speed.add_path(tr("Repetições"), ChoiceField([(hz(ms), ms) for ms in TURBO_PERIODS]), ("turbo", "speed"),
                               lambda ms: hz(ms) if ms else "—")
                self.under.addStretch(1)
                self.under.addWidget(speed)
                self.under.addStretch(1)
                self.cells = self._side_cells(t["keys"], row) + [speed]
        super().refresh()


def macro_text(slot):
    """A macro em palavras: "X por 350 ms, depois A + B por 50 ms"."""
    if not slot or slot.get("empty") or not slot.get("steps"):
        return tr("nada (vazia)")
    parts = []
    for st in slot["steps"]:
        names = [key_name(k) for k in st["keys"]] + [
            tr("stick {0} para {1}").format(tr('E') if n == 'stick_left' else tr('D'), tr(DIRECTIONS.get(st[n], '?')))
            for n in ("stick_left", "stick_right") if n in st]
        parts.append(tr("{0} por {1} ms").format(tr(' e ').join(names) or tr('pausa'), st['ms']))
    return tr(", depois ").join(parts) + (tr("; repete a cada {0} ms").format(slot['loop_ms']) if slot.get("loop") else "")


class KeyMenu(QMenu):
    """Teclas marcáveis que não fecham a lista a cada clique: um passo pode apertar várias juntas."""

    def mouseReleaseEvent(self, e):
        a = self.actionAt(e.position().toPoint())
        if a and a.isCheckable():
            a.trigger()
        else:
            super().mouseReleaseEvent(e)


class MacroCell(SetupCell):
    """Uma macro (M1–M4). "Imitar tecla" resolve o caso comum; os passos montam sequências (teclas juntas +
    duração). Tudo fica pendente em laranja até o Aplicar, como o resto da ficha."""

    def __init__(self, store, pos, title, side="", mirror=False):
        super().__init__(store, title, side, mirror=mirror, columns=False)
        self.pos, self.rows, self.single = pos, [], None
        self.sections = {"macros"}
        self.single_row = QHBoxLayout()
        self.single_label = label(tr("Imitar tecla"), F(14), C["chalk"])
        self.single_row.addWidget(self.single_label)
        self.single_row.addStretch(1)
        self.body.addLayout(self.single_row)
        self.summary, self.was = Para(color=C["ink"]), Para(font=F(13), color=C["pencil"])
        self.body.addWidget(self.summary)
        self.body.addWidget(self.was)
        self.steps = QVBoxLayout()
        self.steps.setSpacing(4)
        self.body.addLayout(self.steps)
        row = QHBoxLayout()
        self.add_b, self.empty_b = QPushButton(tr("Adicionar passo")), QPushButton(tr("Esvaziar"))
        self.factory_b = QPushButton(tr("Restaurar de fábrica"))
        self.factory_b.hide()
        self.factory_b.clicked.connect(self._factory)
        for b in (self.add_b, self.empty_b, self.factory_b):
            b.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.add_b)
        row.addWidget(self.empty_b)
        row.addStretch(1)
        self.body.addLayout(row)
        frow = QHBoxLayout()  # linha própria: três botões não cabem lado a lado na célula
        frow.addWidget(self.factory_b)
        frow.addStretch(1)
        self.body.addLayout(frow)
        self.add_b.clicked.connect(self._add)
        self.empty_b.clicked.connect(lambda: self._put([]))
        self.lock = Para(tr("Só leitura por enquanto: a gravação de macros é liberada depois do teste no controle."),
                         F(13), C["pencil"])
        self.body.addWidget(self.lock)
        self.pc = None
        name = (self.slot(store.device) or self.slot() or {}).get("name") if store.device else None
        if name in PC_MARK:
            self._pc_ui(name)

    def _pc_ui(self, name):
        """Ação no PC: a traseira aperta uma combinação rara e o app (aberto) troca por teclado."""
        self.pc_name = name
        row = QHBoxLayout()
        row.addWidget(label(tr("No PC"), F(14), C["chalk"]))
        row.addStretch(1)
        self.pc = ChoiceField([(tr("Nada"), "none"), (tr("Atalho"), "shortcut"), (tr("Tecla especial"), "special"),
                               (tr("Texto"), "text"), (tr("Sequência"), "sequence")], 150)
        row.addWidget(self.pc)
        self.body.addLayout(row)
        self.pc_key, self.pc_text = QKeySequenceEdit(), QLineEdit(objectName="pc")
        self.pc_key.setMaximumSequenceLength(1)
        self.pc_key.findChild(QLineEdit).setPlaceholderText(tr("Clique e aperte o atalho"))
        self.pc_key.setToolTip(tr("Clique e aperte o atalho (ex.: Ctrl+Shift+S)"))
        self.pc_text.setPlaceholderText(tr("Texto que o app digita"))
        self.pc_special = ChoiceField([(tr("F{0}").format(n), tr("F{0}").format(n)) for n in range(13, 25)], 112)
        self.pc_special.picked.connect(lambda v: (PC.put(self.pc_name, "special", v), self.flash(), self.refresh()))
        self.special_row = QWidget()
        sr = QHBoxLayout(self.special_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(label(tr("Tecla"), F(14), C["chalk"]))
        sr.addStretch(1)
        sr.addWidget(self.pc_special)
        for w in (self.pc_key, self.pc_text):
            w.setFixedHeight(32)
            self.body.addWidget(w)
        self.body.addWidget(self.special_row)
        self.pc_note = Para(font=F(13), color=C["pencil"])
        self.body.addWidget(self.pc_note)
        kind, value = PC.get(name)
        self.pc_key.setKeySequence(QKeySequence(value if kind == "shortcut" else ""))
        self.pc_text.setText(value if kind in ("text", "sequence") else "")
        self.pc.picked.connect(self._pc_kind)
        self.pc_key.keySequenceChanged.connect(lambda _: self._pc_save("shortcut"))  # Tab mexe no foco: salva já
        self.pc_text.textEdited.connect(lambda _: self._pc_save(PC.get(self.pc_name)[0]))

    def _pc_kind(self, kind):
        same = kind == PC.get(self.pc_name)[0]
        PC.put(self.pc_name, kind, PC.get(self.pc_name)[1] if same else "F13" if kind == "special" else "")
        if not same:
            self.pc_text.setText("")
        if kind != "none":  # a traseira passa a apertar a combinação (pendente até o Aplicar)
            self._put(pc_steps(self.pc_name))
        self.refresh()

    def _pc_save(self, kind):
        value = self.pc_key.keySequence().toString() if kind == "shortcut" else self.pc_text.text()
        if PC.get(self.pc_name)[0] == kind and value != PC.get(self.pc_name)[1]:
            PC.put(self.pc_name, kind, value)
            self.flash()  # pulso verde: a mudança já vale
        self.refresh()

    def _pc_refresh(self):
        kind, value = PC.get(self.pc_name)
        on = kind != "none"
        for w in [self.single_label, self.single, self.add_b, self.empty_b] + [x for r in self.rows for x in r[::2]]:
            w.setVisible(not on)
        for r in self.rows:
            r[2].setVisible(not on)
            r[0].parentWidget().setVisible(not on)
        self.pc.show_state(kind, kind)
        self.pc_key.setVisible(kind == "shortcut")
        self.pc_text.setVisible(kind in ("text", "sequence"))
        self.pc_text.setPlaceholderText(tr('Ex.: Ctrl+C, 100 ms, Ctrl+V, "gg", clique') if kind == "sequence"
                                        else tr("Texto que o app digita"))
        self.special_row.setVisible(kind == "special")
        if kind == "special":
            self.pc_special.show_state(value, value)
        if kind == "none":
            self.pc_note.hide()
            return
        combo = tr("{0} por {1} ms").format(tr(" e ").join(key_name(k) for k in pc_steps(self.pc_name)[0]["keys"]),
                                            PC_HOLD_MS)
        steps = [(st.get("keys"), st.get("ms")) for st in ((self.slot(self.store.device) or {}).get("steps") or [])]
        ready = [(st["keys"], st["ms"]) for st in pc_steps(self.pc_name)] == [(k, ms) for k, ms in steps]
        draft = [(st.get("keys"), st.get("ms")) for st in ((self.slot() or {}).get("steps") or [])]
        if not ready and draft != [(st["keys"], st["ms"]) for st in pc_steps(self.pc_name)]:
            self._put(pc_steps(self.pc_name))  # o sinal no controle está velho: deixa pendente para o Aplicar
            return
        unknown = sequence_steps(value)[1] if kind == "sequence" else []
        bad = (kind == "shortcut" and value and not shortcut_vks(value)) or unknown
        what = ({"shortcut": tr("o atalho {0}").format(value), "special": tr("a tecla {0}").format(value), "text": tr("o texto “{0}”").format(value),
                 "sequence": tr("a sequência")}[kind]) if value else None
        doing = {"shortcut": value, "special": value, "text": tr("digita “{0}”").format(value),
                 "sequence": f"{len(sequence_steps(value)[0])} passos"}.get(kind)
        self.factory_b.hide()
        self.summary.setText(tr("Ao apertar: {0} no PC").format(doing) if what
                             else tr("Ao apertar: escolha abaixo o que acontece no PC"), C["ink"] if ready else C["orange"])
        self.was.setVisible(not ready)
        self.was.setText(tr("No controle agora: ") + macro_text(self.slot(self.store.device)))
        if unknown:
            text, color = (tr("Não entendi: {0}. Use atalhos (Ctrl+C), esperas (100 ms), textos entre aspas (\"gg\") e clique, clique direito ou clique do meio, separados por vírgula.").format(', '.join(unknown))), C["red"]
        elif bad:
            text, color = tr("O atalho {0} não tem tecla equivalente no Windows; grave outro.").format(value), C["red"]
        elif not what:
            text, color = {"shortcut": tr("Clique no campo e aperte o atalho."), "text": tr("Escreva o texto."),
                           "sequence": tr('Escreva os passos separados por vírgula, ex.: Ctrl+C, 100 ms, Ctrl+V.')
                           }.get(kind, ""), C["pencil"]
        elif ready:
            hidden = VIRTUAL is not None and VIRTUAL.running
            text, color = ((tr("Pronto. No jogo, ligue {0} ao comando que quiser (nenhum teclado tem essa tecla). ").format(value)
                            if kind == "special" else tr("Pronto. ")) + tr("Funciona com o app aberto (pode minimizar). ") + (
                tr("Com o controle virtual ligado, o jogo não vê o sinal da traseira.") if hidden else
                tr("Ligue o Virtual (barra de cima): sem ele, o jogo também recebe o L1 e R1 rápido da traseira."))), C["pencil"]
        else:
            text, color = (tr("Clique em Aplicar (barra de cima) para gravar na traseira. Depois é só apertar: o app troca o sinal dela por {0}.").format(what)), C["orange"]
        self.pc_note.setText(text, color)
        stamps = [t for t in (PC.saved.get(self.pc_name), self.store.saved_at.get("macros")) if t]
        if ready and what and not bad and stamps and "macros" not in self.store.problems:
            self.note.say("check", C["green"], tr("Aplicado às {0}: a traseira manda {1}.").format(max(stamps), what))
        self.pc_note.show()

    def slot(self, src=None):
        slots = (self.store.draft if src is None else src).get("macros", {}).get("slots", [])
        return slots[self.pos] if self.pos < len(slots) else None

    def keys(self):  # sticks ficam de fora: são direções, não teclas
        return [k for k in self.store.device["macros"]["keys"] if k not in (18, 19)]

    def _steps(self):
        return copy.deepcopy((self.slot() or {}).get("steps") or [])

    def _put(self, steps):
        old = self.slot()
        new = {"name": old["name"], "empty": True} if not steps else {
            "name": old["name"], "index": kl.MACRO_SLOTS.index(old["name"]), "loop_ms": old.get("loop_ms", 0),
            "loop": old.get("loop", False), "steps": steps} | ({"tail": old["tail"]} if "tail" in old else {})
        self.store.set(("macros", "slots", self.pos), new)

    def _factory(self):
        name = self.slot()["name"]
        if name == getattr(self, "pc_name", None):
            PC.put(name, "none", "")  # volta a ser só macro do controle
        self.store.set(("macros", "slots", self.pos), {"name": name, "index": kl.MACRO_SLOTS.index(name)} |
                       copy.deepcopy(FACTORY_MACROS[name]))

    def _single(self, k):
        st = self._steps()
        self._put([{"ms": st[0]["ms"] if st else 100, "keys": [k]}])

    def _add(self):
        st = self._steps()
        st.append({"ms": st[-1]["ms"] if st else 100, "keys": []})
        self._put(st)

    def _remove(self, j):
        st = self._steps()
        del st[j]
        self._put(st)

    def _ms(self, j, v):
        st = self._steps()
        st[j]["ms"] = v // 5 * 5  # o controle guarda a duração em unidades de 5 ms
        self._put(st)

    def _toggle(self, j, k, on):
        st = self._steps()
        chosen = set(st[j]["keys"]) | {k} if on else set(st[j]["keys"]) - {k}
        st[j]["keys"] = [x for x in self.store.device["macros"]["keys"] if x in chosen]  # ordem da lista
        self._put(st)

    def pending(self):
        try:
            return self.slot() != self.slot(self.store.device)
        except (KeyError, TypeError, AttributeError):
            return False

    def _row(self, j):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        n = label(str(j + 1), F(13, 600, 85, tnum=True), C["pencil"])
        n.setFixedWidth(14)
        kb = QPushButton()
        kb.setCursor(Qt.PointingHandCursor)
        kb.setToolTip(tr("Teclas apertadas neste passo (marque várias para apertar juntas)"))
        menu = KeyMenu(kb)
        for k in self.keys():
            a = menu.addAction(key_name(k))
            a.setCheckable(True)
            a.setData(k)
            a.triggered.connect(lambda on, k=k, j=j: self._toggle(j, k, on))
        kb.clicked.connect(lambda: menu.popup(kb.mapToGlobal(QPoint(0, kb.height()))))
        ms = Stepper(10, 5000, " ms", inc=10, width=78)
        ms.valueChanged.connect(lambda v, j=j: self._ms(j, v))
        rm = QPushButton(objectName="step")
        rm.setIcon(icon("close", C["chalk"], C["ink"]))
        rm.setIconSize(QSize(16, 16))
        rm.setFixedSize(24, 28)
        rm.setCursor(Qt.PointingHandCursor)
        rm.setToolTip(tr("Remover este passo"))
        rm.clicked.connect(lambda _=False, j=j: self._remove(j))
        for x in (n, kb, ms, rm):
            h.addWidget(x, 1 if x is kb else 0)
        self.steps.addWidget(w)
        return kb, menu, ms, rm

    def refresh(self):
        super().refresh()
        s = self.store
        cur = self.slot()
        if "macros" not in s.device or cur is None:
            self.summary.setText("—")
            return
        dev, keys = self.slot(s.device), self.keys()
        if self.single is None:
            self.single = ChoiceField([(key_name(k), k) for k in keys], 132)
            self.single.picked.connect(self._single)
            self.single_row.addWidget(self.single)

        def one(m):  # a macro é só "aperta uma tecla"?
            st = (m or {}).get("steps") or []
            ok = len(st) == 1 and len(st[0]["keys"]) == 1 and not {"stick_left", "stick_right"} & set(st[0])
            return st[0]["keys"][0] if ok else None
        self.single.show_state(one(dev), one(cur))
        self.single.setPlaceholderText(tr("Sequência") if cur.get("steps") else tr("Nenhuma"))
        pend = self.pending()
        self.summary.setText(tr("Ao apertar: ") + macro_text(cur), C["orange"] if pend else C["ink"])
        self.was.setText(tr("No controle: ") + macro_text(dev))
        self.was.setVisible(pend)
        steps, dsteps = cur.get("steps") or [], (dev or {}).get("steps") or []
        if len(steps) != len(self.rows):
            clear(self.steps)
            self.rows = [self._row(j) for j in range(len(steps))]
        for j, (st, (kb, menu, ms, rm)) in enumerate(zip(steps, self.rows)):
            names = [key_name(k) for k in st["keys"]] + [
                f"stick {'E' if n == 'stick_left' else 'D'}" for n in ("stick_left", "stick_right") if n in st]
            kb.setText(tr(" e ").join(names) or tr("pausa"))
            for a in menu.actions():
                a.setChecked(a.data() in st["keys"])
            ms.show_state(dsteps[j]["ms"] if j < len(dsteps) else None, st["ms"])
            for w in (kb, ms, rm):
                w.setEnabled(MACROS_WRITABLE)
        self.add_b.setEnabled(MACROS_WRITABLE and len(steps) < 20)
        self.empty_b.setEnabled(MACROS_WRITABLE and bool(steps))
        self.single.setEnabled(MACROS_WRITABLE)
        self.lock.setVisible(not MACROS_WRITABLE)
        factory = FACTORY_MACROS.get(cur.get("name"))
        self.factory_b.setVisible(bool(factory) and {k: cur.get(k) for k in factory} != factory)
        self.factory_b.setEnabled(MACROS_WRITABLE)
        if self.pc:
            self._pc_refresh()


class CheckupPage(Page):
    mode = "teste"

    def __init__(self, store, link, pad):
        super().__init__(store)
        self.link, self.pad, self.confirm_key = link, pad, 94
        head, _ = page_head(tr("Check-up"), tr("Entradas ao vivo, vibração, bateria e calibração."))
        self.outer.addLayout(head)
        body = QHBoxLayout()
        body.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(12)
        self.plan = ControllerPlan(store, src="device")  # o anel do Home mostra a cor que o controle tem agora
        self.plan.live = {"down": set(), "lt": 0, "rt": 0, "l": (0, 0), "r": (0, 0)}
        left.addWidget(self.plan, 1)
        self.src = Para(font=F(13), color=C["pencil"])
        left.addWidget(self.src)
        self.keys = label("", F(16, 600, 85), C["ink"])
        left.addWidget(self.keys)
        body.addLayout(left, 1)

        self.batt_cell = SetupCell(store, tr("Bateria"), "", columns=False)
        row = QHBoxLayout()
        self.batt = Battery(big=True)
        self.batt_text = label(tr("Esperando o controle…"), F(16, 600, 85), C["ink"])
        row.addWidget(self.batt)
        row.addSpacing(10)
        row.addWidget(self.batt_text, 1)
        self.batt_cell.body.addLayout(row)

        vib = SetupCell(store, tr("Vibração"), "", columns=False)
        vib.body.addWidget(Para(tr("Testa os motores pelo Windows, com a força configurada no controle."), F(13),
                                C["pencil"]))
        vrow = QHBoxLayout()
        for text, l, r in ((tr("Esquerdo"), 52000, 0), (tr("Direito"), 0, 52000), (tr("Os dois"), 52000, 52000)):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, l=l, r=r: self._buzz(l, r))
            vrow.addWidget(b)
        vib.body.addLayout(vrow)

        cal = SetupCell(store, tr("Calibração do controle"), "", columns=False)
        self.cal_text = Para(color=C["chalk"])
        cal.body.addWidget(self.cal_text)
        crow = QHBoxLayout()
        self.cal_go = QPushButton(tr("Calibrar"))
        self.cal_ok = QPushButton(tr("Começar"), objectName="primary")
        self.cal_cancel = QPushButton(tr("Cancelar"))
        for b in (self.cal_go, self.cal_ok, self.cal_cancel):
            b.setCursor(Qt.PointingHandCursor)
            crow.addWidget(b)
        crow.addStretch(1)
        cal.body.addLayout(crow)
        self.cal_go.clicked.connect(lambda: self._cal("confirm"))
        self.cal_cancel.clicked.connect(lambda: self._cal("idle"))
        self.cal_ok.clicked.connect(self._cal_start)
        self._cal("idle")

        self.info = SetupCell(store, tr("Controle"), "", columns=False)
        self.info_text = Para("—", color=C["chalk"])
        self.info.body.addWidget(self.info_text)

        self.vcell = SetupCell(store, tr("Controle virtual"), "", columns=False)
        vrow = QHBoxLayout()
        vrow.addWidget(label(tr("Ligado"), F(14), C["chalk"]))
        vrow.addStretch(1)
        self.vswitch = Segmented([(tr("Sim"), True), (tr("Não"), False)])
        self.vswitch.picked.connect(self._virtual)
        vrow.addWidget(self.vswitch)
        self.vcell.body.addLayout(vrow)
        self.vtext = Para(font=F(13), color=C["pencil"])
        self.vcell.body.addWidget(self.vtext)
        body.addWidget(column([self.batt_cell, vib, cal, self.vcell, self.info], 380))
        self.outer.addLayout(body, 1)

    def _virtual(self, on):
        miss = VIRTUAL.missing() if on else []
        if miss:  # o app traz os instaladores: oferece instalar em vez de só dar erro
            box = QMessageBox(QMessageBox.Question, tr("Controle virtual"), tr(
                "O modo virtual precisa de drivers gratuitos da Nefarius que não estão instalados: {0}.\n\n"
                "O app já traz os instaladores. O Windows vai pedir permissão de administrador, e depois é "
                "preciso reiniciar o PC.").format(", ".join(miss)), parent=self.window())
            go = box.addButton(tr("Instalar drivers"), QMessageBox.AcceptRole)
            box.addButton(tr("Agora não"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is go and install_drivers(miss):
                VIRTUAL.error = tr("Siga os instaladores que abriram. Depois, reinicie o PC e ligue o Virtual de novo.")
            self.window().refresh()
            return
        VIRTUAL.start() if on else VIRTUAL.stop()
        PC.settings.setValue("virtual/on", "1" if on and VIRTUAL.running else "0")
        self.window().refresh()  # barra de cima, Check-up e textos das traseiras

    def _vrefresh(self):
        if VIRTUAL is None:
            return
        on = VIRTUAL.running
        self.vswitch.show_state(on, on)
        if VIRTUAL.error and not on:
            self.vtext.setText(VIRTUAL.error, C["red"])
        elif on:
            self.vtext.setText(tr("Ligado: os jogos veem um controle Xbox virtual que o app alimenta; o real fica "
                               "escondido. As traseiras M3/M4 viram as teclas do PC escolhidas em Botões › Trás, "
                               "e o jogo não vê o sinal delas."), C["chalk"])
        else:
            self.vtext.setText(tr("Desligado: os jogos veem o controle real. Ligue para as traseiras virarem teclas do PC "
                               "sem o jogo ver o sinal delas. O app precisa ficar aberto (pode minimizar)."),
                               C["pencil"])

    def _buzz(self, l, r):
        self.pad.vibrate(l, r)
        QTimer.singleShot(700, lambda: self.pad.vibrate(0, 0))

    def _cal(self, state, sent_at=None):
        key = key_name(self.confirm_key)
        texts = {"idle": tr("Recalibra o centro do controle (sensores). Para a zona morta e o drift dos sticks, use a "
                         "calibragem automática em Analógicos."),
                 "confirm": tr("Deixe o controle parado numa superfície plana, sem tocar nos sticks. Ao começar, o LED pisca: então aperte {0} no controle.").format(key),
                 "sent": tr("LED piscando? Aperte {0} no controle. Quando o LED parar de piscar, terminou (comando enviado às {1}).").format(key, sent_at)}
        self.cal_text.setText(texts[state])
        self.cal_go.setVisible(state != "confirm")
        self.cal_ok.setVisible(state == "confirm")
        self.cal_cancel.setVisible(state == "confirm")
        self.cal_go.setText(tr("Calibrar de novo") if state == "sent" else tr("Calibrar"))

    def _cal_start(self):
        self.link.calibrate()
        self._cal("sent", time.strftime(tr("%H:%M")))

    def vitals(self, st):
        self.confirm_key = st.get("confirm_key") or 94
        names = {1: tr("Quase vazia"), 2: tr("Baixa"), 3: tr("Boa"), 4: tr("Cheia")}
        self.batt.set(st["battery"], st["charging"])
        self.batt_text.setText(names[st["battery"]] + (tr(" · carregando") if st["charging"] else tr(" · na bateria")))

    def refresh(self):
        self._vrefresh()
        d = self.store.device
        self.info_text.setText(tr("Firmware {0}\nConfiguração lida às {1}").format(d['identity']['firmware'], self.store.read_at)
                               if d else tr("Esperando o controle…"))

    def live(self, pad):
        if pad is None:
            self.src.setText(tr("O Windows não está vendo o controle como gamepad (XInput). Conecte pelo cabo ou dongle "
                             "2.4G para testar as entradas."))
            self.plan.live = {"down": set(), "lt": 0, "rt": 0, "l": (0, 0), "r": (0, 0)}
            self.keys.setText("")
        else:
            self.src.setText(tr("Entradas lidas pelo Windows (XInput), já com zona morta e curva aplicadas: é o que os "
                             "jogos recebem. As traseiras aparecem como a tecla que elas imitam."))
            self.plan.live = pad
            down = sorted(pad["down"])
            self.keys.setText(tr("Apertado: ") + (", ".join(key_name(k) for k in down) if down else "nada"))
        self.plan.update()


# ---------------------------------------------------------------- moldura
class Chip(QFrame):
    def __init__(self, glyph=None):
        super().__init__(objectName="chip")
        self.setFixedHeight(32)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 5, 14, 5)
        lay.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        lay.addWidget(glyph or self.dot)
        self.text = label("", F(13), C["chalk"])
        lay.addWidget(self.text)

    def set(self, text, color=None):
        self.text.setText(text)
        self.setMinimumWidth(self.sizeHint().width())  # status nunca corta: os botões é que cedem espaço
        if color:
            self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")


class Rail(QWidget):
    picked = Signal(int)

    def __init__(self, items):
        super().__init__()
        self.setFixedWidth(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 6, 16)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        for i, (name, text) in enumerate(items):
            b = QToolButton(objectName="rail")
            b.setText(text)
            b.setFont(F(11, 700, 75, caps=True, track=0.5))
            b.setIcon(icon(name))
            b.setIconSize(QSize(22, 22))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setCheckable(True)
            b.setFixedSize(76, 58)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b)
        lay.addStretch(1)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.picked)

    def select(self, i):
        self.group.button(i).setChecked(True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C["rail"]))
        h = self.height()
        p.fillRect(QRectF(0, 0, 6, h), QColor(C["blue"]))
        p.fillRect(QRectF(0, h * 0.62, 6, h * 0.16), QColor(C["orange"]))
        p.setPen(QColor(C["rule"]))
        p.drawLine(self.width() - 1, 0, self.width() - 1, h)


NAV = [("sheet", tr("Ficha")), ("stick", tr("Analógicos")), ("trigger", tr("Gatilhos")), ("buttons", tr("Botões")),
       ("turbo", tr("Turbo")), ("checkup", tr("Check-up"))]


class Main(QMainWindow):
    def __init__(self, store, link, pad):
        super().__init__()
        self.store, self.link, self.pad, self.state = store, link, pad, "search"
        self.setWindowTitle(tr("G2 Pro V2 — Ficha de acerto"))
        self.setWindowIcon(QIcon(render_svg(APP_ICON, 32)))
        self.resize(1440, 900)
        self.setMinimumSize(1320, 880)
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.rail = Rail(NAV)
        h.addWidget(self.rail)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        bar = QFrame(objectName="bar")
        bar.setFixedHeight(64)
        top = QHBoxLayout(bar)
        top.setContentsMargins(28, 0, 28, 0)
        top.setSpacing(12)
        top.addWidget(label(tr("G2 Pro V2"), F(26, 700, 72, caps=True, track=0.4)))
        top.addSpacing(6)
        self.conn = Chip()
        self.battery = Battery()
        self.batt_chip = Chip(self.battery)
        self.read_chip = Chip()
        self.read_chip.dot.hide()
        for w in (self.conn, self.batt_chip, self.read_chip):
            top.addWidget(w)
        top.addStretch(1)
        self.b_virtual = QPushButton(tr("Virtual: desligado"))
        self.b_virtual.setToolTip(tr("Os jogos veem um controle Xbox que o app alimenta; as traseiras viram teclas do PC "
                                  "sem o jogo ver o sinal delas."))
        self.b_virtual.clicked.connect(lambda: self.pages[-1]._virtual(not VIRTUAL.running))
        self.b_reread, self.b_discard = QPushButton(tr("Reler do controle")), QPushButton(tr("Descartar"))
        self.b_apply = QPushButton(tr("Aplicar"), objectName="primary")
        self.lang = Segmented([("PT", "pt"), ("EN", "en")])
        self.lang.setToolTip(tr("Idioma"))
        self.lang.show_state(LANG, LANG)
        self.lang.picked.connect(self._set_lang)
        top.addWidget(self.lang)
        for b in (self.b_virtual, self.b_reread, self.b_discard, self.b_apply):
            b.setCursor(Qt.PointingHandCursor)
            top.addWidget(b)
        col.addWidget(bar)

        self.stack = QStackedWidget()
        self.pages = [SheetPage(store, self.go), SticksPage(store, link, pad), TriggersPage(store),
                      ButtonsPage(store), TurboPage(store),
                      CheckupPage(store, link, pad)]
        for pg in self.pages:
            self.stack.addWidget(pg)
        col.addWidget(self.stack, 1)

        foot = QFrame(objectName="foot")
        foot.setFixedHeight(40)
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(28, 0, 28, 0)
        fl.setSpacing(20)
        self.f_addr, self.f_msg, self.f_read = (label("", F(13), C["pencil"]) for _ in range(3))
        fl.addWidget(self.f_addr)
        fl.addWidget(self.f_msg, 1)
        fl.addWidget(self.f_read)
        col.addWidget(foot)
        h.addLayout(col, 1)
        self.setCentralWidget(root)

        self.rail.picked.connect(self.go)
        self.b_reread.clicked.connect(self._reread)
        self.b_discard.clicked.connect(store.discard)
        self.b_apply.clicked.connect(self._apply)
        link.status.connect(self._status)
        link.loaded.connect(store.load)
        link.stored.connect(store.stored)
        link.failed.connect(self._failed)
        link.vitals.connect(self._vitals)
        store.changed.connect(self.refresh)
        store.confirmed.connect(lambda s: [pg.flash(s) for pg in self.pages])
        store.confirmed.connect(lambda s: self.f_msg.setText(""))  # erro antigo some quando algo dá certo
        link.loaded.connect(lambda cfg: self.f_msg.setText(""))
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(lambda: None if self.isMinimized() else  # minimizado (jogando): nada a desenhar
                                   self.stack.currentWidget().live(self.pad.read()))
        self.timer.start()
        global VIRTUAL
        VIRTUAL = VirtualPad(self.pad)
        if PC.settings.value("virtual/on", "0") == "1":
            VIRTUAL.start()
        else:
            hidhide("--cloak-off")  # garante o real visível se o app caiu com o modo ligado
        PC.watch(self.pad)  # traseiras → teclado
        self._status("search", tr("Procurando o controle…"))
        self.refresh()

    def go(self, i, view=None):
        self.rail.select(i)
        self.stack.setCurrentIndex(i)
        self.link.set_mode(self.pages[i].mode)
        if view:  # ex.: "Macros" da Ficha abre Botões na vista das macros
            self.pages[i].set_view(view)

    def _set_lang(self, lang):
        """Troca a língua reabrindo o app: Bluetooth e controle virtual recomeçam limpos na língua nova."""
        if lang == LANG:
            return
        QSettings("Controle", "G2ProV2").setValue("lang", lang)
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        # no .exe, a cópia nova começa do zero; sem isso ela herda a pasta temporária desta, que some ao fechar
        os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        QProcess.startDetached(sys.executable, args)
        self.close()
        QApplication.quit()

    def _reread(self):
        self.f_msg.setText("")
        self.link.reread()

    def _apply(self):
        self.f_msg.setText("")
        self.link.apply([(s, copy.deepcopy(self.store.draft[s])) for s in self.store.pending()])

    def _failed(self, section, message):
        self.store.fail(section, message)
        self.f_msg.setText(message)
        self.f_msg.setStyleSheet(f"color: {C['red']};")

    def _vitals(self, st):
        self.battery.set(st["battery"], st["charging"])
        names = {1: tr("quase vazia"), 2: tr("baixa"), 3: tr("boa"), 4: tr("cheia")}
        self.batt_chip.set(tr("Bateria {0}").format(names[st['battery']]) + (tr(" · carregando") if st["charging"] else ""))
        self.pages[-1].vitals(st)

    def _status(self, kind, text):
        self.state = kind
        color = {"ok": C["green"], "off": C["red"], "error": C["red"]}.get(kind, C["blue"])
        self.conn.set(text, color)
        if kind != "ok":
            self.batt_chip.set(tr("Bateria —"))
        self.refresh_buttons()

    def refresh_buttons(self):
        if VIRTUAL is not None:
            on = VIRTUAL.running
            self.b_virtual.setText(tr("Virtual: ligado") if on else tr("Virtual: desligado"))
            self.b_virtual.setStyleSheet(f"color: {C['green']}; border-color: {C['green']};" if on else "")
            self.b_virtual.setToolTip(VIRTUAL.error if VIRTUAL.error and not on else self.b_virtual.toolTip())
        n = self.store.count() if self.store.ready() else 0
        idle = self.state == "ok"
        self.b_apply.setText(tr("Aplicar {0} mudança{1}").format(n, 's' if n != 1 else '') if n else tr("Aplicar"))
        self.b_apply.setEnabled(idle and n > 0)
        self.b_discard.setEnabled(n > 0 and self.state != "busy")
        self.b_reread.setEnabled(idle)

    def refresh(self):
        s = self.store
        for pg in self.pages:
            pg.refresh()
        self.refresh_buttons()
        self.read_chip.set(tr("Lido do controle às {0}").format(s.read_at) if s.read_at else tr("Ainda não lido"))
        if s.ready():
            m = s.device["motor"]["shutdown_min"]
            self.f_addr.setText(tr("{0}  ·  desliga após {1} sem uso").format(s.device.get('address', ''), 'nunca' if m >= kl.NO_SHUTDOWN else f'{m} min'))
            self.f_read.setText(tr("{0} seções lidas").format(len([k for k in kl.WRITERS if k in s.device]) + 1))

    def showEvent(self, e):
        super().showEvent(e)
        dark_titlebar(self)

    def closeEvent(self, e):
        VIRTUAL.stop()  # o real volta a aparecer para os jogos
        super().closeEvent(e)


def dark_titlebar(w):
    try:
        hwnd, dwm = int(w.winId()), ctypes.windll.dwmapi
        for attr, val in ((20, 1), (35, 0x001B1816), (34, 0x0038322E), (36, 0x00DDE7EC)):
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
    except (AttributeError, OSError):
        pass  # Windows antigo: barra padrão


def make_app(argv):
    try:  # a barra de tarefas mostra o ícone do app, não o do Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Controle.G2ProV2")
    except (AttributeError, OSError):
        pass
    try:  # relógio do Windows a 1 ms: sem isso, esperas curtas viram ~15 ms e os botões atrasam
        ctypes.windll.winmm.timeBeginPeriod(1)
    except (AttributeError, OSError):
        pass
    sys.setswitchinterval(0.001)  # threads trocam a cada 1 ms (padrão 5 ms): o repasse não fica na fila
    app = QApplication(argv)
    app.setStyle("Fusion")
    QFontDatabase.addApplicationFont(str(ROOT / "assets" / "fonts" / "Archivo-Variable.ttf"))
    app.setFont(F(14))
    pal = app.palette()
    for role, col in ((QPalette.Window, C["ground"]), (QPalette.WindowText, C["ink"]), (QPalette.Base, C["cell"]),
                      (QPalette.AlternateBase, C["cell_hi"]), (QPalette.Text, C["ink"]), (QPalette.Button, C["cell"]),
                      (QPalette.ButtonText, C["ink"]), (QPalette.ToolTipBase, C["cell"]),
                      (QPalette.ToolTipText, C["ink"]), (QPalette.PlaceholderText, C["pencil"]),
                      (QPalette.Highlight, "#34495A"), (QPalette.HighlightedText, C["ink"]),
                      (QPalette.Link, C["blue"])):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(qss())
    return app


def selftest():
    # medição real (2026-10-18, zona morta 0): stick E parado em ~13,6%, D em ~2%; depois alguém mexeu no E
    still_l, still_r = [0.136] * 40 + [0.140] * 2, [0.019, 0.020] * 21
    assert rest_drift(still_l) == (0.136, False) and rest_drift(still_r)[1] is False
    assert rest_drift([0.136] * 20 + [0.40, 0.59, 0.62] * 10)[1] is True  # mexeu: pede nova medição
    assert pctile([0.2] * 97 + [1.0] * 3, 0.95) == 0.2  # pico isolado não vira drift
    st = {s: {"deadzone": 18, "max": 85, "curve": LINEAR} for s in ("left", "right")}
    c = calibrated(st, {"left": 0.136, "right": 0.02}, {"left": 0.97, "right": 0.99}, 3, 3)
    assert (c["left"]["deadzone"], c["right"]["deadzone"], c["left"]["max"], c["right"]["max"]) == (17, 5, 94, 96)
    assert shortcut_vks("Ctrl+Shift+S") == [0x11, 0x10, 0x53] and shortcut_vks("F5") == [0x74]
    assert shortcut_vks("Alt+Left") == [0x12, 0x25] and shortcut_vks("") is None
    # marca: L1+R1 = M3, +X = M4, +A = M1, +B = M2; dispara no aperto; dedo (L1 antes do R1) não conta
    fired, pc = [], PcActions()
    pc.fire = fired.append
    pc.get = lambda m: ("none" if m == "M2" else "shortcut", "F1")
    for down in ({5, 6}, set(), {3, 5, 6}, {3, 5, 6}, set(), {1, 5, 6}, set(), {2, 5, 6}, set(), {5}, {5, 6}, set()):
        pc.tick({"down": down})
    assert fired == ["M3", "M4", "M1"], fired  # M2 sem ação no PC; segurar não repete; dedo não conta
    assert pc_steps("M4") == [{"ms": 40, "keys": [3, 5, 6]}] and pc_steps("M3") == [{"ms": 40, "keys": [5, 6]}]
    steps, bad = sequence_steps('Ctrl+C, 100 ms, espera 50 ms, "gg", clique direito, Ctrl+V, F13, ???')
    assert [k for k, _ in sequence_steps("wait 50 ms, right click, Ctrl+V")[0]] == ["wait", "click", "keys"]
    assert sequence_steps('Ctrl+A, "ok, M3", Enter')[0] == [("keys", "Ctrl+A"), ("text", "ok, M3"), ("keys", "Enter")]
    assert [k for k, _ in steps] == ["keys", "wait", "wait", "text", "click", "keys", "keys"] and bad == ["???"]
    assert shortcut_vks("F13") == [0x7C]
    assert all((ROOT / "assets" / "drivers" / f).exists() for f in DRIVERS.values())  # instaladores no pacote
    assert strip_signal(0x0100)[0] == 0x0100  # L1 sozinho (dedo) passa
    out, m = strip_signal(0x0300 | 0x4000 | 0x0001)  # M4: L1+R1+X, com o direcional apertado pelo jogador
    assert out == 0x0001 and m == 0x4300
    out, m = strip_signal(0x4100, m, 0x4301)  # soltura em degrau: o que sobrou não escapa
    assert out == 0 and m
    assert strip_signal(0, m, 0x4100) == (0, 0)
    assert strip_signal(0x0300, 0, 0x0100) == (0x0300, 0)  # dedo: L1 depois R1 passa inteiro para o jogo
    for pt, en in i18n.EN.items():  # tradução nunca pede um marcador {n} que a frase original não tem
        assert set(re.findall(r"\{(\d+)", en)) <= set(re.findall(r"\{(\d+)", pt)), pt
    print("selftest ok")


def main():
    if sys.argv[1:] == ["selftest"]:
        return selftest()
    app = make_app(sys.argv)
    w = Main(Store(), Link(), XInput())
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
