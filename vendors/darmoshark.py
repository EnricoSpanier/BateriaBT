"""Darmoshark M3/N3 (Telink): feature report 0x51 de 21 bytes na coleção 0x8C. O comando 0x03 lê o mouse
pareado e limpa a resposta velha; o 0x06 traz o % em [11]. Não informa carga. Fontes: M3-N87-battery-viewer,
quiet-battery, darmoshark-m3-configurator. Só lê."""
import time

from . import Model

VID = 0x248A
N3_BOND = bytes([0x8A, 0x24, 0x10, 0xFF])  # VID/PID do N3 em little-endian


def _cmd(h, op, polls):
    h.send_feature_report(bytes([0x51, op] + [0] * 19))
    for _ in range(polls):
        time.sleep(0.02)
        r = list(h.get_feature_report(0x51, 21))
        if len(r) >= 12 and r[0] == 0x51 and r[1] == op:
            return r
    return None


def read(h, m):
    bond = _cmd(h, 0x03, 3)
    r = _cmd(h, 0x06, 18)
    if not r or r[2] != 0x01 or r[11] > 100:  # [2] = status ok
        return None
    name = "Darmoshark N3" if bond and N3_BOND in bytes(bond) else m.name
    return r[11], False, name


MODELS = [Model(VID, pid, "Darmoshark M3", "MOUSE", read, usage_page=0x008C, interface=1) for pid in (0xFF12, 0xFF30)]
