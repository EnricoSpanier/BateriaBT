"""Attack Shark pelo receptor Beken 1D57:FA60: não há comando; o receptor envia `03 <modelo> 40 <p1> <p2>`
a cada ~2 s na coleção 0x0A. Só escuta. O ID do modelo define a escala de p2 (% direto ou 1-10). Carregando
fica falso: as fontes discordam de p1. Fontes: attack-shark-x11-driver, AttackSharkBattery, OpenMouse,
attack-shark-linux."""
import time

from . import Model

IDS = {0x55: ("Attack Shark X11", 1), 0x07: ("Attack Shark X11 SE", 1),
       0x10: ("Attack Shark R1/X6", 10), 0x85: ("Attack Shark X6", 10)}


def read(h, m):
    end = time.monotonic() + 2.5
    while (left := end - time.monotonic()) > 0:
        r = h.read(8, max(1, int(left * 1000)))
        if r and len(r) >= 5 and r[0] == 0x03 and r[2] == 0x40 and r[1] in IDS:  # 0x01 = piscada do link
            name, scale = IDS[r[1]]
            if 0 < r[4] * scale <= 100:
                return r[4] * scale, False, name
    return None


MODELS = [Model(0x1D57, 0xFA60, "Attack Shark", "MOUSE", read, usage_page=0x000A, interface=2, writes=False)]
