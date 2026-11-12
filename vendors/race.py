"""Protocolo RACE dos chips Airoha (Audeze Maxwell, Turtle Beach Stealth Gen 3), documentado pelo
HeadsetControl. Mensagem: 05 <tipo> <tamanho LE16> <corpo>. Vai em reports 0x06 de 62 bytes
(06 <bytes> 80 <mensagem>; o 0x80 encaminha ao fone) e volta em fragmentos lidos por
get_input_report(0x07): 07 <bytes> <flag> <fragmento>."""
import time

from . import pad

TIMEOUT = 1.25  # por tentativa
BATTERY = [0x05, 0x5A, 0x03, 0x00, 0xD6, 0x0C, 0x00]  # pede a bateria do fone (comando 0x0CD6)


def _messages(buf):
    i = 0
    while i + 4 <= len(buf):
        if buf[i] != 0x05:
            i += 1
            continue
        end = i + 4 + (buf[i + 2] | buf[i + 3] << 8)
        if end > len(buf):
            return
        yield buf[i:end]
        i = end


def battery(h, tries=2):
    """% do fone atrás do dongle, ou None (fone desligado ou pedido recusado)."""
    for _ in range(tries):
        h.write(pad([0x06, len(BATTERY), 0x80, *BATTERY], 62))
        stream, end = [], time.monotonic() + TIMEOUT
        while time.monotonic() < end:
            time.sleep(0.05)
            r = list(h.get_input_report(0x07, 62))
            if len(r) <= 3 or r[0] != 0x07 or not 0 < r[1] <= 59:
                continue  # 0 bytes = nada novo
            stream += r[3:3 + r[1]]
            for msg in _messages(stream):
                if msg[4:6] != [0xD6, 0x0C]:
                    continue  # resposta a outro comando (o app do fabricante também pergunta)
                if msg[1] == 0x5B and len(msg) > 6 and msg[6] != 0:
                    return None
                if msg[1] == 0x5D and len(msg) > 8:
                    return min(msg[8], 100)
    return None
