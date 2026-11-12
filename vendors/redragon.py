"""Redragon M998 ULT (BYTECH): feature report 0x03 de 64 bytes na coleção FF00. Pede o bloco de informação
básica e espera a resposta pronta; [6]: bits 0-6 = %, bit 7 = carregando. Fontes: M998-ULT-mouse-lcd e
OpenMouse (src/bytech). Só lê."""
import time

from . import Model, pad

REQUEST = pad([0x03, 0x22, 0x50, 0x00, 0x02, 0x4F, 0x81], 64)  # [1] = soma de [2:] & 0xFF


def read(h, m):
    h.send_feature_report(REQUEST)
    for _ in range(20):
        time.sleep(0.03)
        r = list(h.get_feature_report(0x03, 64))
        if len(r) >= 7 and r[0] == 0x03 and r[2] == 0 and r[4] == 0x02:
            return (r[6] & 0x7F, bool(r[6] & 0x80)) if r[6] & 0x7F <= 100 else None
    return None


MODELS = [Model(0x372E, pid, "Redragon M998 ULT", "MOUSE", read, usage_page=0xFF00, interface=2)
          for pid in (0x105F, 0x1060)]
