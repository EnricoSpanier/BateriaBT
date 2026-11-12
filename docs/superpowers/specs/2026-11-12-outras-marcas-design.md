# Outras marcas (lote 1) — design

Data: 2026-11-12 · Status: aprovada (com os patches da revisão adversarial e os ajustes do plano, 2026-11-12)

## Objetivo

Mostrar a bateria de periféricos de outras marcas além da Logitech, para distribuir o app.
Código próprio, escrito a partir de protocolos documentados publicamente (HeadsetControl,
OpenRazer, rivalcfg, o driver hid-playstation do Linux e a API XInput do Windows). Nada é copiado do executável do app original.

## Escopo do lote 1

| Marca | Aparelhos | Fonte do protocolo |
|---|---|---|
| Razer | mouses sem fio | OpenRazer |
| SteelSeries | headsets Arctis/Nova, mouses Aerox/Rival sem fio | HeadsetControl, rivalcfg |
| HyperX | Cloud Alpha Wireless, Cloud II Wireless, Cloud Flight, Cloud Alpha 2 Wireless | HeadsetControl |
| Corsair | headsets sem fio (Void/HS70, Void V2/Virtuoso MAX/HS80 MAX, Virtuoso XT/SE) | HeadsetControl |
| PlayStation | DualSense, DualShock 4 | relatório de entrada padrão (layout público); só lê |
| Xbox | controles via XInput | API do Windows (`XInputGetBatteryInformation`) |

Fora do lote 1: mouses Corsair (protocolo Bragi), headset Razer (exige trocar o modo do
receptor), Arctis 9, Arctis Pro Wireless, Nova 7P, Cloud III Wireless, Cloud Flight S, Stinger 2,
HS55, HS75, Virtuoso original (sem protocolo público confiável), Sony INZONE, Astro, JBL, ASUS,
Glorious e as demais marcas. Cada uma entra depois como um arquivo novo, sem mudar a estrutura.

## Estrutura

```
bateria_bt.py
graphics.py
vendors/
  __init__.py      VendorReader, varredura, junção das tabelas
  razer.py
  steelseries.py
  hyperx.py
  corsair.py
  playstation.py
  xbox.py
```

### Contrato de cada arquivo de marca

Cada arquivo de marca exporta duas coisas:

- `MODELS`: lista de `Model(vid, pid, name, kind, read, usage_page=None, usage=None, interface=None, writes=True)`.
  - `usage_page`/`usage` e/ou `interface` escolhem a coleção HID onde ele fala.
  - Todo modelo que envia comando (`writes=True`) precisa declarar `usage_page`/`usage` ou
    `interface`. Declarado só pela interface, ele escreve apenas em coleção do fabricante
    (usage page ≥ 0xFF00). Coleção livre só vale para leitor que apenas lê. O `Model` recusa no
    import um `writes=True` sem coleção.
  - `kind` é um destes: MOUSE, KEYBOARD, HEADSET, GAMEPAD.
- `read(h, model) -> (pct, charging) | None`: recebe um `hid.device` já aberto e o modelo (para a variante pelo PID) e devolve a
  porcentagem (0–100) e se está carregando, ou `None` quando não houver resposta (aparelho
  desligado, dormindo ou fora do alcance). Exceção de leitura também conta como `None`.
- `read` só aceita o report que confere com o que o protocolo permite verificar: report ID, eco
  do comando, assinatura, tamanho e faixa do valor. Reports de
  evento ou respostas a outro programa (iCUE, Synapse, GG) são descartados, e a leitura continua
  até o limite de tempo. Sem report válido, o resultado é `None`.

O `playstation.py` só lê reports de entrada: não envia `write` nem feature report, porque isso
mudaria o modo do controle e quebraria o Steam Input e o DS4Windows. Por Bluetooth, se o report
padrão não trouxer bateria, o controle fica sem leitura. O adaptador sem fio do DS4 sem controle
pareado e os códigos de erro 14/15 também dão `None`.

O `xbox.py` é a exceção: não usa HID. Ele exporta uma função `scan() -> dict` que já devolve
os controles no formato das leituras (ver abaixo).

### VendorReader (`vendors/__init__.py`)

Mesmo comportamento do `HidppReader` da Logitech:

- `refresh()` roda numa thread. Uma flag `_busy` impede duas varreduras ao mesmo tempo.
  `done = Signal(dict)` é emitido ao final.
- Cada ciclo funciona assim:
  1. Lista os aparelhos com `hid.enumerate()` e cruza com `MODELS` por (vid, pid) e coleção.
     Entradas do fabricante 0x046D (Logitech) são ignoradas, porque têm o seu próprio leitor.
  2. Para cada par, abre o aparelho, chama `read`, fecha e grava o resultado.
  3. Junta o resultado do `xbox.scan()`.
- **Chave estável:** `vendor:<vid>:<grupo>:<série ou ordem>`.
  - Grupo = menor PID com o mesmo nome na marca: cabo e receptor do mesmo mouse viram um item.
  - Sem série, usa a ordem (0, 1...) entre os aparelhos iguais, e não o caminho: trocar de porta
    USB não cria outro item, e dois aparelhos iguais não se juntam.
  - Os controles Xbox usam `xinput:<n>` (a posição no XInput, não o controle).
- **Várias coleções na mesma chave:** um resultado `None` nunca sobrescreve um resultado válido
  da mesma chave no mesmo ciclo.
- **Leitura devolvida:** `{name, battery, connected, kind, charging, hours: None}`.
- **Sem resposta:** quem não respondeu neste ciclo mas já tinha leitura volta com
  `connected: False` e a última porcentagem.
- **Aparelho removido:** some da lista quando não aparece mais na enumeração. O controle Xbox
  desligado fica como desconectado até reiniciar o app.
- **Erros:** uma exceção num leitor afeta só aquele aparelho; o erro vai para
  `stderr`, que é o `erros.log`. Sem `hidapi` instalado, só os controles Xbox aparecem.
- **Tempo:** cada troca de mensagem tem limite de 0,5 s (Cloud Alpha 2: 1 s), para um aparelho
  dormindo não travar a varredura.

### Integração no app (`bateria_bt.py`)

- Entra a fonte `"vendor"` em `App.sources`, com `devices = {**bt, **vendor, **hid, **ghub}`.
- A regra "conectado se qualquer fonte vê" vale para chaves repetidas entre fontes.
  Na prática as chaves não se repetem, porque cada fonte tem o seu prefixo.
- O nome vindo da fonte vendor segue a mesma regra do HID++: o primeiro nome detectado fica
  gravado, e o nome dado pelo usuário prevalece sempre.
- O ciclo continua a cada 60 s, e o lote 1 não ouve eventos de nenhuma marca.
- `requirements.txt`: nada novo, porque `hidapi` já está lá.

## Testes

- **Por leitor** (`tests/test_<marca>.py`):
  - um aparelho falso responde com os bytes do protocolo público;
  - confere `(pct, charging)` em pelo menos um caso normal, um carregando e um sem resposta.
- **Casos de aceite da revisão adversarial:**
  1. Um `enumerate` falso traz 3 coleções do mesmo vid/pid (0x0001/0x06, 0x000C/0x01, 0xFF00/0x01),
     e o `Model` declara 0xFF00/0x01: só a 0xFF00 é aberta e recebe `write`. Um `Model` com
     `writes=True` e coleção `None` dá erro no import, sem nenhuma escrita.
  2. Dois aparelhos iguais sem série, com 30% e 80%, viram duas entradas. No mesmo ciclo, uma
     coleção responde 50% e outra não responde: o resultado é 50%, conectado.
  3. Um aparelho falso devolve primeiro um report de evento e depois a resposta válida: sai a
     leitura válida. Se ele devolve só o evento, sai `None`.
  4. O PlayStation falso registra qualquer `write` ou feature report: o `read` termina sem
     nenhum. Um report BT 0x01 simples dá `None`.
  5. Um `enumerate` falso com vid 0x046D e um `Model` forjado com esse vid: nada é aberto. Toda
     chave da fonte vendor começa com `vendor:` ou `xinput:`.
- **VendorReader:**
  - aparelho que para de responder fica `connected: False` com a última porcentagem;
  - receptor removido some da lista;
  - leitor que lança exceção não derruba os outros.
- **App:** quatro fontes juntas, sem duplicar nem perder nome.
- **Real:**
  - a varredura roda nesta máquina sem travar;
  - não abre nem confunde os aparelhos Logitech, que têm o seu próprio leitor;
  - um controle Xbox, se houver, aparece com o nível.

## Limites conhecidos

- Com o software do fabricante aberto (iCUE, Synapse, GG, NGenuity), a leitura pode falhar
  em alguns ciclos.
- Os leitores seguem a documentação pública, e um firmware diferente pode responder em outro
  formato. Nesse caso aquele aparelho simplesmente não aparece, e o erro fica no log.
- O XInput só informa níveis (vazio, baixo, médio, cheio), mostrados como 5, 30, 60 e 99%
  (99 para não avisar "tire do carregador" em controle de pilha).
- Um headset ligado ao mesmo tempo por Bluetooth e pelo receptor aparece duas vezes (fonte BT e
  fonte vendor).
- Um headset ligado por cabo pode não informar bateria. Isso depende do modelo.
