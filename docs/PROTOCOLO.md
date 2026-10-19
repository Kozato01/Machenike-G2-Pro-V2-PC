# Machenike G2 Pro V2 — protocolo KeyLinker (BLE)

Reconstruído do app KeyLinker 3.73 (`com.pulsenet.inputset`, APK base sha256 `09408b71…bdee`) e
**confirmado no controle real** em 2026-10-18: `98:B6:ED:B7:9D:30`, nome BLE `G5Pro_V2`,
VID `1006` PID `200C`, firmware 1.44. Implementação de referência: `keylinker.py`.

| Situação | Comandos |
|---|---|
| Confirmado no hardware | todas as leituras (145, 176·1/3/4/5, 177–183); escritas 49, 50, 51, 52, 53, 54 e 55 (regravação idêntica com ACK + releitura igual; na 55 também verde→vermelho) |
| Conhecido, fora do escopo | 22 (restaurar fábrica, destrutivo), OTA Telink, família de mapeamento por toque |

## Conexão
- GATT por BLE sem pareamento (o app usa `connectGatt` em LE). Serviço `d7f010e0-660d-46e9-96c3-19c4148bdab5`,
  escrita `…e1` (com resposta), notificação `…e2`. Há um serviço `ff12` (ff13/ff14/ff15) que não é usado.
- Endereços: `98:B6:EC:xx` = Bluetooth clássico (HID do gamepad), `98:B6:ED:xx` = lado BLE de configuração
  (mesmo sufixo). `98:B6:E9:` é outra linha de produto.
- **O canal BLE funciona em paralelo ao modo de jogo** (cabo USB ou dongle 2.4G): não é preciso trocar de modo.
- Pelo USB (cabo ou dongle, `2345:2104`) só há XInput + mouse HID, sem coleção vendor: não dá para configurar por USB.

## Pacote
`[cmd, b1, b2, rand, payload (≤15), crc8]`, ofuscado com `scramble()` antes de escrever e `unscramble()` ao receber.
CRC-8 refletido, poly 0xEB (tabela em `e.f2735f`), sobre todos os bytes antes dele.

| Campo | Leituras e comandos simples | Escritas de config (49–55) |
|---|---|---|
| b1 | `len+5` | contador 3 bits (7,6,…,0,7…) `<<5 \| len+5`; no 53: `slot<<5 \| len+5` |
| b2 | seq: `n%128`, +128 quando n é par | `(c%2)<<7 \| página<<3 \| c%8` (c incrementa a cada pacote) |

- **Toda resposta é cmd 25 (0x19) e ecoa o b2 do pedido**; o payload traz os dados.
  O ACK de escrita observado foi `02 DF AA`.
- O app escreve 1 pacote a cada 20 ms. Esperar o ACK de cada pacote também funciona.
- Notificações espontâneas: 0x1F (eventos em tempo real), 0x20/0x23 (estado/modo), 0x28 (dois celulares).
  Nenhuma apareceu nos testes.

## Handshake
1. `145 []` → identidade: `[n, VIDh, VIDl, PIDh, PIDl, fw_maj, fw_min, gen<<5 | sensor<<4 | modelo]`.
   Se `gen == 2`, família = 1 quando modelo ∈ {0,7,8} e 2 nos outros casos. Família 2 = "host", configurador de gamepad (telas CK).
2. `176 [0,1]` → recursos (abaixo).
3. O app envia um keepalive `29 [5,223,171,0,X,Y]` a cada 750 ms, que também escolhe o fluxo 0x1F.
   **Não é necessário** para ler nem escrever (os testes não o enviaram).

## Recursos — resposta de `176 [0,1]`, F = payload[1:]
| Byte | Significado | G2 Pro V2 |
|---|---|---|
| F[0] | analógicos: bit1 = esquerdo, bit0 = direito | 3 |
| F[1] | gatilhos: bit1 = E, bit0 = D | 3 |
| F[2] | motores 1–4 (bits 0–3) | 3 (motores 1 e 2) |
| F[3] | turbo | 1 |
| F[4] | macros M1–M6, ML, MR (bits 0–7) | 0x0F (M1–M4) |
| F[5] | remapeamento; bit1 = lista extra (176·7) | 1 |
| F[6] | zonas de luz 1–4 | 1 |
| F[7] | bit1 (com F[4] > 0) = formato novo de macro | 0 |
| F[9] | sensor (giroscópio) | 0 |

## Listas paginadas e listas de teclas
- Primeira página: `[total, dados…]`; as seguintes trazem só dados. Peça página+1 até juntar `total` bytes.
- Listas de teclas usam RLE: um byte > 128 estende o código anterior em `v−129` códigos consecutivos.

## Recursos: leitura → escrita
| Recurso | Leitura | Escrita | Formato |
|---|---|---|---|
| Remapeamento | `176 [pág,3]` + `182 [pág]` | 54 (paginado) | teclas: `[total, X, RLE…]`. Mapa: um alvo por tecla: 0 = padrão; a própria tecla = **desativada**; outro código = remapeada. Escrita `[n, alvos…]`; tudo padrão = `[0]` |
| Analógicos | `177 [0]` | 49 | `[14, E(7), D(7)]`, cada lado: zona morta, `100−máx`, curva x1,y1,x2,y2 (0–255), flags (b0 inverte X, b1 inverte Y, b2 troca E/D) |
| Gatilhos | `178 [0]` | 50 | `[14, E(7), D(7)]`, cada lado: início, `200−fim` (curso 0–200), curva ×4, flags (b2 troca E/D) |
| Motor + desligamento | `179 [0]` | 51 | `[8, m1, m2, m3, m4, desligamento LE32 em unidades de 5 ms]`; `FF FF FF FF` = nunca. O app grava motores e desligamento juntos |
| Turbo | `176 [pág,4]` + `180 [0]` | 52 | teclas: `[total, N, RLE manuais…, M, RLE auto…]`. Estado: `[13, vel/10, g1, g2, máscara manual 3B, máscara auto 3B, extra ×4]` (máscara LSB-first sobre a lista) |
| Luz | `183 [pág]` | 55 (paginado) | cada zona: `[R, G, B, vel_lo, respirar<<7 \| vel_hi(4 bits), brilho]`. Escrita `[total, zonas…]` |
| Macros | `176 [pág,5]` + `181 [pág, slot]` | 53 (b1 = slot) | lista de teclas em RLE. Macro: `[total, loop_lo, loop<<7 \| loop_hi(4), passos…]`; cada passo tem 5 B: máscara de 24 bits LSB-first (tecla = 1 bit, stick = 4 bits: 0–7 = direção, ≥8 = parado) + `dur_lo, dur_hi` (× 5 ms) |

Presets de curva do app (`x1,y1,x2,y2`): padrão 85,85,170,170 · rápido 35,35,136,204 · lento 35,35,219,145 ·
suave 142,142,220,157 · fino 67,67,72,106.

### Configuração lida do controle (2026-10-18)
- Analógicos: zona morta E 18 / D 15, máx 85, curva "fino" no E e "padrão" no D. Gatilhos: curso 26–170.
- Motores 153/153, desligamento em 12 min. Turbo: 8 teclas (A B X Y L1 R1 L2 R2), velocidade 80, todas desligadas.
- Luz: vermelho fixo, brilho 125. Remapeamento: 16 teclas, todas no padrão (inclui 93 "−" e 94 "+").
- Macros: M1 e M2 vazias, M3 = X por 350 ms, M4 = Y por 315 ms. M3 e M4 são as **traseiras** (segundo o usuário).

### Escrita de macro (53), validada em 2026-10-19
- Slot começa em 0 (M1 = 0, M3 = 2, M4 = 3): `b1 = slot<<5 | len+5`, b2 como as outras escritas.
- Dados = exatamente o formato de leitura com o total na frente: `[total, loop_lo, loop<<7 | loop_hi, passos…]`.
  Macro vazia = `[0]`. O app remove passos finais sem tecla antes de gravar.
- M3/M4 de fábrica terminam com 4 bytes a mais (`136 0 0 15` e `136 0 0 33`: sticks parados, nenhuma tecla,
  e um byte). O total os inclui (11). O app não grava isso; `keylinker` preserva esses bytes (`tail`) para a
  regravação ser idêntica. Uma macro gravada pelo app volta sem esse rabo.
- Teste: M3 regravada idêntica (ACK + releitura igual), M1 recebeu X 100 ms e voltou a vazia.

## Keepalive, bateria e check-up (testado em 2026-10-18)
- **Keepalive** `29 [5,223,171,0,X,Y]`: o app envia a cada 750 ms; (X,Y) escolhe o modo: normal (10,2), teste (6,5),
  analógicos (6,2), motor (10,3), leitura (2,12). A resposta traz o **status**, por exemplo `09 df aa 00 80 1d 01 00 00 5e`.
  Com c = payload[1:], c[3] codifica a **bateria**: bit4 = carregando; bit5 = nível 2, bit6 = nível 3, bit7 = nível 4;
  sem bit = nível 1 (1 = quase vazia, 4 = cheia). c[8] é a **tecla de confirmação** da calibração (94 = "+").
- **Fluxo 0x1F**: `[tamanho, eventos…]`; tecla `[apertada, código]`, gatilho `[0, 7|8, corrigido, bruto]`,
  stick `[0, 18|19, x, y, x_bruto, y_bruto]` (128 = centro). No primeiro teste veio uma rajada só, com o estado
  inicial: stick E bruto (127,112), R2 bruto 3. Depois nada chegou, nem repetindo a sequência exata da tela de
  teste do app (28, `27 [..,0]`, keepalive no modo teste). Hipótese: o fluxo só sai pelo BLE quando o BLE é a
  ligação de jogo (modo celular); com dongle ou cabo, as entradas vão por lá. Por isso o check-up usa o **XInput**.
- `27 [3,223,171,0|1]`: alterna "antes/depois do efeito" na tela de teste; **não responde**.
  `28 [2,223,171]` responde `02 DF AA`.
- **Calibração** `29 [3,223,171,16]`: não responde. O LED pisca; com o controle parado na mesa, aperte a tecla de
  confirmação até o LED parar. O app mostra só o ícone da tecla e não espera sinal de fim.
  Ainda **não foi executada** neste controle; o check-up do `app.py` guia o processo.
- **Drift medido** (2026-10-18, pelo XInput, com zona morta 0 / máximo 100 / curva linear gravados por ~3 s e
  depois restaurados, tudo confirmado pela releitura): stick **esquerdo parado ≈ 13,6%** (repousa fora do centro,
  Y ≈ +0,14; bate com o bruto 112/128 do fluxo 0x1F), **direito ≈ 2%**. Por isso a zona morta de fábrica/usuário de
  18% no esquerdo. A calibragem automática do `app.py` usa esse método (percentil 95, descarta os 300 ms iniciais).
- **Turbo**: `velocidade` = período em ms (gravado ÷10). O app oferece 1000, 500, 330, 250, 200, 160, 140, 120, 110,
  100, 90, 80, 70, 60, 50, 40 e 30 ms (≈ 1 a 33 Hz); este controle está em 80 ms (12,5 Hz).

## Outros comandos
- `22 [3,223,169,2]`: **restaurar fábrica** (destrutivo; família 1 usa `…,1`).
- `30 [2,223,171]`: pede estado (resposta 0x1F na família de mapeamento).
- Família de mapeamento por toque (23/24/26/36–39, 144–168, 41): usada por outros produtos, irrelevante aqui.

## Códigos de tecla (`util/c.java`)
`01` A · `02` B · `03` X · `04` Y · `05` L1 · `06` R1 · `07` L2 · `08` R2 · `09` Select · `0A` Start · `0B` L3 · `0C` R3 ·
`0D` ↓ · `0E` ↑ · `0F` → · `10` ← · `11` Home · `12` stick E · `13` stick D · `14–17` L4 R4 L5 R5 · `18` ML · `19` MR ·
`1A` MC · `1B` M · `1C–27` F1–F12 · `28–31` 1–0 · `32–4B` letras · `4C–5B` Esc…Enter e setas do teclado ·
`5D` − · `5E` + · `5F` captura · `60` turbo · `63` modo · `64` Fn · `65/66` SL/SR · `67–6C` M1–M6.
Na UI do app, 2048 = tecla vazia.

## Fontes no APK descompilado (`re/kl_src`)
- `util/e.java`: monta os pacotes. `util/b.java`: GATT e fila de escrita. `util/b1.java`: respostas e escritas da família host.
- `z1/h.java`: fachada dos comandos. `z1/i.java`: codecs. `z1/j,o,p,n,q,l,m.java`: fluxo de leitura de cada recurso.
- `host/activity/CKAdvancedActivity.java` + `w1/*.java`: telas atuais (u = analógicos, z = gatilhos, n = motor, p = outros…).
- `host/activity/HostActivity.java`: tela legada (nada a abre), mas os logs nela nomeiam os ACKs de cada escrita.

## Histórico: MixDrive (PC, Thunderobot)
`Machenik.Installer.exe` (.NET) → `KeyLinkerlib.dll`. Configura por HID com usagePage `0xFF10` e lista
`1006:200C` como "G5Pro V2", o mesmo VID/PID que este controle informa pelo BLE. Só que o dongle e o cabo
dele (`2345:2104`) não expõem essa interface.
