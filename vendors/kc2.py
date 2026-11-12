"""Mouses Keychron 8K e VGN F1 V5 (mesmo protocolo de 64 bytes na coleção FFC1:01): output report 0xB3
com o comando 0x06, resposta no report 0xB4. Bateria em [20]: bits 0-6 = %, bit 7 = carregando.
Fontes: keychron-battery-dkms, OpenMouse, vigil-watt. Só lê."""
from . import Model, pad, xfer

REQUEST = pad([0xB3, 0x06], 64)


def _ok(r):
    return (len(r) >= 21 and r[0] == 0xB4 and r[1] == 0x06 and r[20] & 0x7F <= 100
            and sum(1 for b in r[1:41] if b) >= 3)  # quadro quase todo zero = sem dado


def read(h, m):
    r = xfer(h, REQUEST, 64, _ok, timeout=1.0)
    return (r[20] & 0x7F, bool(r[20] & 0x80)) if r else None


def _m(vid, pids, name):
    return [Model(vid, p, name, "MOUSE", read, usage_page=0xFFC1, usage=0x0001) for p in pids]


KEYCHRON = 0x3434
MODELS = [
    *_m(KEYCHRON, [0xD060, 0xD049], "Keychron M6"),
    *_m(KEYCHRON, [0xD048, 0xD068], "Keychron M5"),
    *_m(KEYCHRON, [0xD073], "Keychron M5 SE"),
    *_m(KEYCHRON, [0xD036, 0xD04F, 0xD051], "Keychron M3 Mini"),
    *_m(KEYCHRON, [0xD06C], "Keychron LM7 Ultra"),
    *_m(KEYCHRON, [0xD028, 0xD029], "Keychron (receptor)"),
    *_m(0x391D, [0x1A23, 0x1026], "VGN F1 V5"),
]
