# Lote 5: headsets Logitech fora do HID++ (Astro A50 Gen 5 / A50 X e G522)

Data: 2026-11-12. Estende `2026-11-12-outras-marcas-design.md`.

## Problema

A Astro A50 Gen 5 / A50 X e o G522 LIGHTSPEED não falam HID++ 2.0: o `HidppReader` não os acha (só abre
as coleções FF00:0002 e FF43:0202). Os dois usam o transporte "Centurion" (quadro de 64 bytes, feature de
bateria 0x0104). Hoje o `VendorReader` ignora todo VID 0x046D, então sem o G HUB esses fones não aparecem.

## Decisões

1. **Exceção estreita à regra do 0x046D.** O `VendorReader` continua ignorando o 0x046D, menos os pares
   VID:PID declarados em `vendors/logitech.py`. Nenhuma outra marca/arquivo pode declarar 0x046D (teste).
   As coleções usadas (FF32:0074 e FFA0:0001) não são as do `HidppReader`: os dois leitores nunca abrem o
   mesmo handle.
2. **Enquanto não estiver provado que não há G HUB, não abrimos esses fones.** O G HUB segura o aparelho e
   já informa a bateria (o open-g-hub se recusa a falar com a base com o `lghub_agent` rodando). O default
   é "G HUB presente": o `GHubReader` só marca `absent` quando a tentativa de conexão falha (o `_on_error`
   com `_connecting`, que já limpa os dados do G HUB) e desmarca ao conectar. O `VendorReader` pula os
   modelos 0x046D enquanto `absent` for falso (a entrada deles some como "aparelho removido", e a do G HUB
   assume). Custo: sem G HUB, o fone aparece um ciclo depois na primeira vez. Isso evita ler junto com o
   G HUB no primeiro ciclo e após uma queda, e evita `logi:` e `vendor:` do mesmo fone ao mesmo tempo.
3. **Só leitura.** Só Root.getFeature (função 0) e a leitura da bateria (função 0) da feature 0x0104, mais,
   no G522, o envio pela bridge (feature 0x0003) dessas mesmas leituras.
   Nunca: escritas de sidetone/EQ/LED/auto-sleep, varredura de endereços 0x00-0xFF, o pedido legado 0x51.
4. **swId próprio = 0x0A** (o G HUB usa 0x0B, o HeadsetControl 0x0C), e a resposta só vale se ecoar
   índice + função|swId. Respostas e eventos de outros programas são descartados.
5. **Índices descobertos em runtime** (Root.getFeature), sem fixar o 6 do A50 nem a bridge do G522.
   Sem cache entre ciclos (YAGNI: 1-3 pedidos a cada minuto).

## A50 Gen 5 / A50 X (`vendors/logitech.py`, `read_a50`)

- PIDs 046D:0B1C ("Astro A50 Gen 5") e 046D:0B0B ("Astro A50 X"), nomes distintos para não formarem o
  mesmo grupo de chave; coleção FF32:0074; tipo HEADSET.
- Quadro: `02 0C <len> 00 <idx> <fn|sw> <params>`, 64 bytes, `len = 3 + nº de params`.
- 1) `02 0C 05 00 00 0A 01 04` (Root.getFeature 0x0104) → resposta `[4]==00 [5]==0A`, índice em `[6]`
  (0 = sem a feature → None).
- 2) `02 0C 03 00 <idx> 0A` → resposta `[4]==idx [5]==0A [2]>3`: % = `[6]` (>100 → None),
  carregando = `[8] == 1` (`3` = cheio na doca, `0` = descarregando).
- Sem resposta em 1 s (fone fora/desligado) → None (fica desconectado com a última %).
- Evidência: HeadsetControl PR #531 (hardware, 0B1C) e capturas USB do G HUB no open-g-hub (A50 X 0B0B).

## G522 LIGHTSPEED (`read_g522`)

- PID 046D:0B18 (dongle); coleção FFA0:0001, interface 3; nome "Logitech G522"; tipo HEADSET. O PID do
  cabo (0B19) fica fora: não há fonte do protocolo nele.
- Quadro: `50 23 <len> 00 <payload>`, 64 bytes, `len = len(payload) + 1`; resposta com o mesmo prefixo.
- 1) Root.getFeature(0x0003) no dongle → índice da bridge `br`.
- 2) Pela bridge, Root.getFeature(0x0104) no fone → índice `bat`.
- 3) Pela bridge, bateria (função 0 de `bat`) → % em params[0], estado em params[2]; carregando = 1 ou 2.
- A bridge responde primeiro com um ACK (`br`, função 1 | swId) e depois com o evento (`br`, função 1,
  swId 0) que traz a resposta do fone. Evento de conexão `[br, 00, 00, 0]` ou ACK sem evento até o tempo
  esgotar → fone desligado → None. 0,5 s por troca.
- O evento só vale se o payload interno ecoar o pedido: índice interno 0 e função|swId 0x0A no passo 2,
  índice `bat` e função|swId 0x0A no passo 3. Evento sem esse eco é descartado; `bat == 0` → None.
- Bytes montados a partir do código do HeadsetControl (`logitech_centurion_protocol.hpp`), sem captura
  real do G522: **nível de confiança menor**, registrado no commit.

## Fora de escopo

- G522 no cabo (0B19), A50 Gen 4 (VID 0x9886, outro protocolo), PRO X 2 e outros Centurion.
- Leitura simultânea com o G HUB (decisão 2).
- Unificar a chave do vendor com a do G HUB: com o G HUB ligado aparece a entrada `logi:`; sem ele, a
  `vendor:046d:...`. Ajustes (nome, ocultar) feitos numa não passam para a outra.

## Testes (critério de aceite)

1. `read_a50` com FakeDev: descobre o índice, lê `02 0C 06 00 06 0A 64 64 01` → (100, True).
2. `read_a50` descarta evento não solicitado (swId 0) e resposta com swId do G HUB (0x0B).
3. `read_a50` sem resposta / feature ausente (índice 0) / % > 100 → None.
4. `read_g522`: sequência bridge → bateria com ACK intercalado → (%, carregando); evento de desconexão → None.
4b. `read_g522`: um evento espontâneo da bridge com outro índice interno chega antes da resposta e é
   descartado; se só ele chega → None, sem enviar o passo 3.
5. Nenhum modelo fora de `vendors/logitech.py` tem VID 0x046D; um aparelho 0x046D que não está na lista
   continua ignorado pelo `VendorReader`.
6. Enquanto o G HUB não for dado como ausente (default), o `VendorReader` não abre os modelos 0x046D e
   eles saem do resultado; com `absent = True`, abre.
7. Os pedidos enviados só usam função 0 (fora a função 1 de envio da bridge), e o payload interno da
   bridge também só usa função 0 com índice 0 ou `bat` — conferido nos bytes escritos.
8. Duas bases 0B1C e 0B0B sem série dão duas entradas com chaves diferentes.
