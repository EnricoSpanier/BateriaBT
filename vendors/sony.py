"""Headsets Sony INZONE pelo dongle (protocolo HCI sobre HID, documentado pelo HeadsetControl e pelo
openinzone). Só faz GET da bateria (evento 0x04), sem mudar nada no fone."""
from . import Model, pad, xfer

SONY = 0x054C


def _request():
    buf = [0x02, 0x0C, 0x01, 0x00, 0xFC, 0x08,  # report 0x02, tamanho, comando HCI 0xFC00
           0x96, 0xC3, 0x41, 0x04, 0x01, 0x02, 0x00]  # chave, PC->dongle, bateria, GET, tid 2
    return pad(buf + [sum(buf[6:]) & 0xFF], 64)


def _ok(r):
    if len(r) < 15 or r[0] != 0x02 or not 12 <= r[1] <= 62 or len(r) < r[1] + 2:
        return False
    return (r[2] == 0x04 and r[3] == 0xFF and r[6:8] == [0x96, 0xC3] and r[8] >> 4 == 1
            and r[9] == 0x04 and r[10] in (0x10, 0xA0) and sum(r[6:r[1] + 1]) & 0xFF == r[r[1] + 1])


def _payload(h):
    r = xfer(h, _request(), 64, lambda r: _ok(list(r)), timeout=1.0)
    return list(r[13:r[1] + 1]) if r else None


def read_headset(h, m):
    p = _payload(h)
    if not p or len(p) < 2 or p[1] > 100:  # 0xFF = fone desligado
        return None
    return p[1], p[0] != 0


def read_buds(h, m):
    p = _payload(h)
    if not p or len(p) < 4:
        return None
    buds = [v for v in (p[1], p[3]) if v <= 100]  # 0xFF = fone no estojo
    return (min(buds), False) if buds else None


VENDOR = dict(usage_page=0xFF04)
MODELS = [
    # a fonte diverge sobre o usage do H5 (0x0002 no HeadsetControl, 0x0001 nos outros projetos)
    Model(SONY, 0x0EBF, "Sony INZONE H5", "HEADSET", read_headset, usage=0x0002, **VENDOR),
    Model(SONY, 0x0EBF, "Sony INZONE H5", "HEADSET", read_headset, usage=0x0001, **VENDOR),
    Model(SONY, 0x0FA8, "Sony INZONE H9 II", "HEADSET", read_headset, usage=0x0001, interface=5, **VENDOR),
    Model(SONY, 0x0EC2, "Sony INZONE Buds", "HEADSET", read_buds, usage=0x0001, **VENDOR),
]
