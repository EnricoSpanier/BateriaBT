"""Pulsar XS-1 (X2A v3, X3, X3 LHD, Xlite v4 e os dongles 1K/8K): feature report 0 de 64 bytes na coleção
FFFF:01. Lê o registro 0x81 (%) e o 0x83 (carregando). Fontes: pulsar-mouse-linux, OpenMouse. Só lê."""
import time

from . import Model


def request(reg):
    buf = [0] * 65  # [0] = report ID 0
    buf[2], buf[3], buf[4] = 0x08, reg, 0x01  # categoria 0x08, registro, sub 0x01
    s = sum(buf[1:63])
    buf[63], buf[64] = s & 0xFF, s >> 8
    return bytes(buf)


def _get(h, reg):
    for _ in range(3):
        h.send_feature_report(request(reg))
        for _ in range(8):
            time.sleep(0.02)
            r = list(h.get_feature_report(0, 65))
            if len(r) >= 8 and r[1] == 0x01:  # 0x01 = resposta pronta
                return r
            if len(r) >= 2 and r[1] == 0x00:  # pedido não aceito: reenvia
                break
    return None


def read(h, m):
    r = _get(h, 0x81)
    if not r or r[7] > 100:  # 0xFF = dongle sem mouse pareado
        return None
    c = _get(h, 0x83)
    return r[7], bool(c and c[7] == 1)


MODELS = [Model(0x3710, pid, name, "MOUSE", read, usage_page=0xFFFF, usage=0x0001) for pid, name in [
    (0x3404, "Pulsar X2A v3"), (0x3409, "Pulsar X3"), (0x3410, "Pulsar X3 LHD"), (0x3401, "Pulsar Xlite v4"),
    (0x5402, "Pulsar (receptor XS-1)"), (0x5403, "Pulsar (receptor XS-1)")]]
