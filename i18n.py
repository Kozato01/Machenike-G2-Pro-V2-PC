"""Traduções do app (português → inglês). A chave é o texto exato em português que está no app.py;
um texto sem tradução aparece em português."""

EN = {
    # ---- navegação, barra e rodapé
    "Ficha": "Sheet",
    "Ficha de acerto": "Setup sheet",
    "G2 Pro V2 — Ficha de acerto": "G2 Pro V2 — Setup sheet",
    "Analógicos": "Sticks",
    "Gatilhos": "Triggers",
    "Botões": "Buttons",
    "Turbo": "Turbo",
    "Macros": "Macros",
    "Check-up": "Check-up",
    "Reler do controle": "Re-read controller",
    "Descartar": "Discard",
    "Aplicar": "Apply",
    "Aplicar {0} mudança{1}": "Apply {0} change{1}",
    "Virtual: desligado": "Virtual: off",
    "Virtual: ligado": "Virtual: on",
    "Os jogos veem um controle Xbox que o app alimenta; as traseiras viram teclas do PC sem o jogo ver o sinal delas.":
        "Games see an Xbox controller fed by the app; the rear buttons become PC keys without the game seeing their signal.",
    "Ainda não lido": "Not read yet",
    "Lido do controle às {0}": "Read from controller at {0}",
    "Bateria {0}": "Battery {0}",
    "Bateria —": "Battery —",
    "Bateria": "Battery",
    "quase vazia": "almost empty", "baixa": "low", "boa": "good", "cheia": "full",
    "{0}  ·  desliga após {1} sem uso": "{0}  ·  turns off after {1} idle",
    "nunca": "never",
    "{0} seções lidas": "{0} sections read",
    # ---- conexão
    "Procurando o controle…": "Looking for the controller…",
    "Bluetooth do Windows desligado — ligue em Configurações › Bluetooth":
        "Windows Bluetooth is off — turn it on in Settings › Bluetooth",
    "Conexão perdida — reconectando": "Connection lost — reconnecting",
    "Controle não encontrado — ligue-o; ele aparece sozinho": "Controller not found — turn it on; it shows up by itself",
    "Conectando…": "Connecting…",
    "Lendo a configuração do controle…": "Reading the controller settings…",
    "Conectado · firmware {0}": "Connected · firmware {0}",
    "Gravando {0} ({1} de {2})…": "Saving {0} ({1} of {2})…",
    "O controle saiu do alcance — reconectando": "Controller out of range — reconnecting",
    "O controle não está conectado. Espere ele aparecer e tente de novo.":
        "The controller is not connected. Wait for it to show up and try again.",
    "O controle não respondeu. Confira se está ligado e perto do PC e tente de novo.":
        "The controller did not respond. Check that it is on and near the PC, and try again.",
    "Falha na comunicação ({0}). Tente de novo.": "Communication failed ({0}). Try again.",
    "O controle guardou outro valor. A ficha mostra o que ficou gravado.":
        "The controller saved a different value. The sheet shows what was saved.",
    "Salvo no controle às {0}": "Saved on the controller at {0}",
    # ---- seções (mensagem "Gravando …")
    "analógicos": "sticks", "gatilhos": "triggers", "motores": "motors", "turbo": "turbo", "botões": "buttons",
    "luz": "light", "macros": "macros",
    # ---- ficha
    "Valores gravados no controle · ": "Values saved on the controller · ",
    "{0} mudança{1} pendente{2} em laranja": "{0} pending change{1} in orange",
    "use − e + para mudar um valor": "use − and + to change a value",
    "Ligue o controle (cabo, 2.4G ou Bluetooth): a ficha se preenche quando ele responder.":
        "Turn on the controller (cable, 2.4G or Bluetooth): the sheet fills in when it responds.",
    "no controle": "on controller",
    "novo": "new",
    "Gatilho L2": "L2 trigger",
    "Gatilho R2": "R2 trigger",
    "Gatilho ": "Trigger ",
    "Stick esquerdo": "Left stick",
    "Stick direito": "Right stick",
    "Stick ": "Stick ",
    "Motor esquerdo": "Left motor",
    "Motor direito": "Right motor",
    "Luz": "Light",
    "Geral": "General",
    "centro": "center",
    "E": "L",
    "D": "R",
    "EDED": "LRLR",
    "Remapeadas": "Remapped",
    "Desligado": "Off",
    "Nenhuma": "None",
    "Desligar": "Turn off",
    "Nunca": "Never",
    "Vibração": "Vibration",
    "Início": "Start",
    "Fim": "End",
    "Curva": "Curve",
    "Zona morta": "Dead zone",
    "Máximo": "Maximum",
    "Inverter eixo X": "Invert X axis",
    "Inverter eixo Y": "Invert Y axis",
    "Trocar lados": "Swap sides",
    "Os dois": "Both",
    "Cor": "Color",
    "Cor da luz": "Light color",
    "Escolher outra cor": "Pick another color",
    "Brilho": "Brightness",
    "Efeito": "Effect",
    "Fixa": "Steady",
    "Respirando": "Breathing",
    "Ritmo": "Speed",
    "Abrir o editor de curva": "Open the curve editor",
    "Personalizada": "Custom",
    "Padrão": "Default",
    "Rápido": "Fast",
    "Lento": "Slow",
    "Suave": "Smooth",
    "Fino": "Fine",
    "Sim": "Yes",
    "Não": "No",
    "saída": "output",
    "entrada": "input",
    "{0}  · no controle": "{0}  · on controller",
    "gravada no controle": "saved on controller",
    # cores
    "Apagada": "Off", "Branca": "White", "Cinza": "Gray", "Vermelha": "Red", "Laranja": "Orange",
    "Amarela": "Yellow", "Verde": "Green", "Ciano": "Cyan", "Azul": "Blue", "Roxa": "Purple", "Rosa": "Pink",
    # campos
    "Diminuir (segure para repetir)": "Decrease (hold to repeat)",
    "Aumentar (segure para repetir)": "Increase (hold to repeat)",
    "Digite o valor ou use ↑/↓; Enter confirma, Esc volta ao valor do controle":
        "Type a value or use ↑/↓; Enter confirms, Esc goes back to the controller value",
    # ---- analógicos e calibragem
    "Mova o stick para ver onde ele está. Ajuste com − e +, escolha a curva ou arraste os pontos dela.":
        "Move the stick to see where it is. Adjust with − and +, pick a curve or drag its points.",
    "Calibragem automática": "Automatic calibration",
    "Calibrar automaticamente": "Calibrate automatically",
    "Medir de novo": "Measure again",
    "Cancelar": "Cancel",
    "Mede quanto cada stick treme parado (drift) e até onde chega girando, e sugere zona morta e máximo. "
    "Leva uns 10 segundos.":
        "Measures how much each stick wobbles at rest (drift) and how far it reaches when rotated, and suggests "
        "dead zone and maximum. Takes about 10 seconds.",
    "Preparando: zona morta 0, máximo 100 e curva linear no controle, só durante a medição…":
        "Preparing: dead zone 0, maximum 100 and linear curve on the controller, only while measuring…",
    "Solte os dois sticks e não toque no controle.": "Let go of both sticks and don't touch the controller.",
    "Agora gire os dois sticks devagar, encostando na borda, em círculos.":
        "Now rotate both sticks slowly in circles, touching the edge.",
    "Devolvendo ao controle os valores que estavam gravados…": "Putting the saved values back on the controller…",
    "Escolha uma predefinição: ela entra como mudança pendente (laranja). Confira e clique em Aplicar.":
        "Pick a preset: it becomes a pending change (orange). Check it and click Apply.",
    " Os dois sticks não chegaram à borda girando: o máximo fica como está.":
        " Neither stick reached the edge while rotating: the maximum stays as it is.",
    " O stick {0} não chegou à borda girando: o máximo dele fica como está.":
        " The {0} stick did not reach the edge while rotating: its maximum stays as it is.",
    "esquerdo": "left", "direito": "right",
    "O controle ainda não respondeu: espere a ficha preencher e tente de novo.":
        "The controller has not responded yet: wait for the sheet to fill in and try again.",
    "O Windows não está vendo o controle como gamepad (XInput): conecte pelo cabo ou dongle para medir.":
        "Windows does not see the controller as a gamepad (XInput): connect it by cable or dongle to measure.",
    "O controle não confirmou a preparação. Nada mudou; tente de novo.":
        "The controller did not confirm the preparation. Nothing changed; try again.",
    "O controle não confirmou a preparação. Os valores do controle foram restaurados; tente de novo.":
        "The controller did not confirm the preparation. Its values were restored; try again.",
    "Não consegui devolver os valores ao controle. Clique em Reler do controle e confira a zona morta antes de jogar.":
        "Could not put the values back on the controller. Click Re-read controller and check the dead zone before "
        "playing.",
    "O Windows parou de ver o controle no meio da medição. Os valores do controle foram restaurados; conecte pelo "
    "cabo ou dongle e meça de novo.":
        "Windows lost the controller in the middle of the measurement. Its values were restored; connect it by cable "
        "or dongle and measure again.",
    "Um stick se mexeu enquanto devia estar parado. Solte o controle numa mesa e meça de novo (os valores do "
    "controle foram restaurados).":
        "A stick moved while it should have been still. Put the controller on a table and measure again (its values "
        "were restored).",
    "Medido": "Measured",
    "drift parado · alcance girando": "drift at rest · reach when rotating",
    "Competitivo": "Competitive",
    "Equilibrado": "Balanced",
    "Anti-drift": "Anti-drift",
    "resposta máxima; só cobre o drift medido": "fastest response; only covers the measured drift",
    "folga para o stick envelhecer": "room for the stick to age",
    "para sticks gastos ou que voltam tortos": "for worn sticks or ones that don't center",
    "{0}: zona morta E {1}, D {2}; máximo E {3}, D {4}": "{0}: dead zone L {1}, R {2}; maximum L {3}, R {4}",
    # ---- gatilhos
    "Início e fim do curso e curva de cada gatilho. Puxe o gatilho para ver onde ele está.":
        "Start and end of travel and curve of each trigger. Pull the trigger to see where it is.",
    "Linha azul: quanto o gatilho está saindo agora (o que os jogos recebem).":
        "Blue line: how much the trigger is outputting now (what games receive).",
    "O Windows não está vendo o controle como gamepad (XInput): conecte pelo cabo ou dongle para ver a posição ao "
    "vivo.":
        "Windows does not see the controller as a gamepad (XInput): connect it by cable or dongle to see the live "
        "position.",
    # ---- botões, turbo
    "Escolha o que cada tecla faz. Padrão: o que ela sempre fez. Desativada: não faz nada.":
        "Choose what each button does. Default: what it always did. Disabled: does nothing.",
    "Desativada": "Disabled",
    "Lado esquerdo": "Left side",
    "Lado direito": "Right side",
    "Frente": "Front",
    "Trás · macros M1–M4": "Back · macros M1–M4",
    "Vista de trás, como quando você vira o controle. M3 e M4 são as traseiras; M1 e M2 não têm botão próprio. "
    "Cada macro imita teclas do controle ou vira uma tecla do PC.":
        "Back view, as when you flip the controller. M3 and M4 are the rear buttons; M1 and M2 have no button. "
        "Each macro mimics controller buttons or becomes a PC key.",
    "vista de trás": "back view",
    "Manual: repete enquanto você segura. Automático: repete sozinho.":
        "Manual: repeats while you hold. Automatic: repeats by itself.",
    "Manual": "Manual",
    "Automático": "Automatic",
    "Velocidade": "Speed",
    "Repetições": "Repeats",
    " Hz": " Hz",
    # ---- macros e traseiras
    "Macro {0}": "Macro {0}",
    "Traseira {0}": "Rear {0}",
    "Imitar tecla": "Mimic button",
    "Sequência": "Sequence",
    "Ao apertar: ": "When pressed: ",
    "No controle: ": "On controller: ",
    "No controle agora: ": "On controller now: ",
    "nada (vazia)": "nothing (empty)",
    "pausa": "pause",
    " e ": " + ",
    "%d de %d": "%d of %d",
    "{0} por {1} ms": "{0} for {1} ms",
    ", depois ": ", then ",
    "; repete a cada {0} ms": "; repeats every {0} ms",
    "stick {0} para {1}": "stick {0} {1}",
    "Adicionar passo": "Add step",
    "Esvaziar": "Clear",
    "Restaurar de fábrica": "Factory restore",
    "Remover este passo": "Remove this step",
    "Teclas apertadas neste passo (marque várias para apertar juntas)":
        "Buttons pressed in this step (check several to press them together)",
    "Só leitura por enquanto: a gravação de macros é liberada depois do teste no controle.":
        "Read-only for now: saving macros is enabled after the test on the controller.",
    "No PC": "On PC",
    "No controle": "On controller",
    "Ação": "Action",
    "Ao apertar: nada (sobrou o sinal do PC). Escolha uma tecla ou Restaurar de fábrica.":
        "When pressed: nothing (the PC signal is left over). Pick a button or Factory restore.",
    "Ao apertar: nada (sobrou o sinal do PC). Escolha uma tecla ou Esvaziar.":
        "When pressed: nothing (the PC signal is left over). Pick a button or Clear.",
    "Nada": "Nothing",
    "Atalho": "Shortcut",
    "Tecla especial": "Special key",
    "Texto": "Text",
    "Tecla": "Key",
    "Tecla {0}": "Key {0}",
    "F{0}": "F{0}",
    "Clique e aperte o atalho": "Click and press the shortcut",
    "Clique e aperte o atalho (ex.: Ctrl+Shift+S)": "Click and press the shortcut (e.g. Ctrl+Shift+S)",
    "Texto que o app digita": "Text the app types",
    'Ex.: Ctrl+C, 100 ms, Ctrl+V, "gg", clique': 'E.g. Ctrl+C, 100 ms, Ctrl+V, "gg", click',
    "Ao apertar: escolha abaixo o que acontece no PC": "When pressed: choose below what happens on the PC",
    "Ao apertar: {0} no PC": "When pressed: {0} on the PC",
    "o atalho {0}": "the shortcut {0}",
    "a tecla {0}": "the key {0}",
    "o texto “{0}”": "the text “{0}”",
    "a sequência": "the sequence",
    "Aplicado às {0}: a traseira manda {1}.": "Applied at {0}: the rear button sends {1}.",
    "digita “{0}”": "types “{0}”",
    "L1 e R1 por {0} ms": "L1 and R1 for {0} ms",
    "Não entendi: {0}. Use atalhos (Ctrl+C), esperas (100 ms), textos entre aspas (\"gg\") e clique, clique direito "
    "ou clique do meio, separados por vírgula.":
        "Didn't understand: {0}. Use shortcuts (Ctrl+C), waits (100 ms), quoted text (\"gg\") and click, right click "
        "or middle click, separated by commas.",
    "O atalho {0} não tem tecla equivalente no Windows; grave outro.":
        "The shortcut {0} has no matching Windows key; record another one.",
    "Clique no campo e aperte o atalho.": "Click the field and press the shortcut.",
    "Escreva o texto.": "Type the text.",
    "Escreva os passos separados por vírgula, ex.: Ctrl+C, 100 ms, Ctrl+V.":
        "Write the steps separated by commas, e.g. Ctrl+C, 100 ms, Ctrl+V.",
    "Pronto. ": "Ready. ",
    "Pronto. No jogo, ligue {0} ao comando que quiser (nenhum teclado tem essa tecla). ":
        "Ready. In the game, bind {0} to any command you like (no keyboard has this key). ",
    "Funciona com o app aberto (pode minimizar). ": "Works while the app is open (it can be minimized). ",
    "Com o controle virtual ligado, o jogo não vê o sinal da traseira.":
        "With the virtual controller on, the game doesn't see the rear button's signal.",
    "Ligue o Virtual (barra de cima): sem ele, o jogo também recebe o L1 e R1 rápido da traseira.":
        "Turn on Virtual (top bar): without it, the game also gets the rear button's quick L1 and R1.",
    "Clique em Aplicar (barra de cima) para gravar na traseira. Depois é só apertar: o app troca o sinal dela por {0}.":
        "Click Apply (top bar) to save it to the rear button. Then just press it: the app turns its signal into {0}.",
    # ---- check-up
    "Entradas ao vivo, vibração, bateria e calibração.": "Live inputs, vibration, battery and calibration.",
    "Entradas lidas pelo Windows (XInput), já com zona morta e curva aplicadas: é o que os jogos recebem. As "
    "traseiras aparecem como a tecla que elas imitam.":
        "Inputs read by Windows (XInput), with dead zone and curve already applied: this is what games receive. The "
        "rear buttons show up as the button they mimic.",
    "O Windows não está vendo o controle como gamepad (XInput). Conecte pelo cabo ou dongle 2.4G para testar as "
    "entradas.":
        "Windows does not see the controller as a gamepad (XInput). Connect it by cable or 2.4G dongle to test the "
        "inputs.",
    "Apertado: ": "Pressed: ",
    "Esperando o controle…": "Waiting for the controller…",
    "Quase vazia": "Almost empty", "Baixa": "Low", "Boa": "Good", "Cheia": "Full",
    " · carregando": " · charging", " · na bateria": " · on battery",
    "Testa os motores pelo Windows, com a força configurada no controle.":
        "Tests the motors through Windows, at the strength set on the controller.",
    "Esquerdo": "Left", "Direito": "Right",
    "Calibração do controle": "Controller calibration",
    "Recalibra o centro do controle (sensores). Para a zona morta e o drift dos sticks, use a calibragem automática "
    "em Analógicos.":
        "Recalibrates the controller's center (sensors). For stick dead zone and drift, use the automatic calibration "
        "in Sticks.",
    "Deixe o controle parado numa superfície plana, sem tocar nos sticks. Ao começar, o LED pisca: então aperte {0} "
    "no controle.":
        "Leave the controller still on a flat surface without touching the sticks. When it starts, the LED blinks: "
        "then press {0} on the controller.",
    "LED piscando? Aperte {0} no controle. Quando o LED parar de piscar, terminou (comando enviado às {1}).":
        "LED blinking? Press {0} on the controller. When the LED stops blinking, it's done (command sent at {1}).",
    "Calibrar": "Calibrate",
    "Calibrar de novo": "Calibrate again",
    "Começar": "Start",
    "Controle": "Controller",
    "Firmware {0}\nConfiguração lida às {1}": "Firmware {0}\nSettings read at {1}",
    "Controle virtual": "Virtual controller",
    "Ligado": "On",
    "Ligado: os jogos veem um controle Xbox virtual que o app alimenta; o real fica escondido. As traseiras M3/M4 "
    "viram as teclas do PC escolhidas em Botões › Trás, e o jogo não vê o sinal delas.":
        "On: games see a virtual Xbox controller fed by the app; the real one is hidden. The M3/M4 rear buttons become "
        "the PC keys chosen in Buttons › Back, and the game doesn't see their signal.",
    "Desligado: os jogos veem o controle real. Ligue para as traseiras virarem teclas do PC sem o jogo ver o sinal "
    "delas. O app precisa ficar aberto (pode minimizar).":
        "Off: games see the real controller. Turn it on so the rear buttons become PC keys without the game seeing "
        "their signal. The app must stay open (it can be minimized).",
    "Faltam os drivers do controle virtual: {0}.": "The virtual controller drivers are missing: {0}.",
    "O modo virtual precisa de drivers gratuitos da Nefarius que não estão instalados: {0}.\n\nO app já traz os "
    "instaladores. O Windows vai pedir permissão de administrador, e depois é preciso reiniciar o PC.":
        "Virtual mode needs free drivers by Nefarius that are not installed: {0}.\n\nThe app already includes the "
        "installers. Windows will ask for administrator permission, and then the PC has to be restarted.",
    "Instalar drivers": "Install drivers",
    "Agora não": "Not now",
    "Siga os instaladores que abriram. Depois, reinicie o PC e ligue o Virtual de novo.":
        "Follow the installers that opened. Then restart the PC and turn Virtual on again.",
    "O Windows não está vendo o controle (XInput): conecte pelo cabo ou dongle.":
        "Windows does not see the controller (XInput): connect it by cable or dongle.",
    "Não consegui criar o controle virtual ({0}: {1}).": "Could not create the virtual controller ({0}: {1}).",
    "o HidHide não respondeu": "HidHide did not respond",
    # ---- teclas e direções do controle
    "Cima": "Up", "Baixo": "Down", "Esquerda": "Left", "Direita": "Right", "Stick E": "Left stick",
    "Stick D": "Right stick", "(vazia)": "(empty)",
    "cima": "up", "cima-direita": "up-right", "direita": "right", "baixo-direita": "down-right", "baixo": "down",
    "baixo-esquerda": "down-left", "esquerda": "left", "cima-esquerda": "up-left",
    # ---- idioma
    "Idioma": "Language",
}
