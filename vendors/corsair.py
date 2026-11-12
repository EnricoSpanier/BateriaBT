"""Headsets Corsair sem fio (protocolos documentados pelo HeadsetControl)."""
from . import Model, flush, pad, xfer

VID = 0x1B1C


def read_void(h, m):
    r = xfer(h, bytes([0xC9, 0x64]), 5, lambda r: len(r) >= 5 and r[0] == 0x64 and r[3] == 0xB1)
    if not r or r[4] not in (1, 2, 4, 5):  # 0 = fone fora do receptor
        return None
    return r[2] & 0x7F, r[4] in (4, 5)


def _bragi(*cmd):
    return pad([0x00, 0x02, *cmd], 65)


def read_v2w(h, m):
    h.write(_bragi(0x08, 0x02, 0x13))
    h.write(_bragi(0x08, 0x02, 0x12))
    flush(h)
    if not xfer(h, _bragi(0x09, 0x02, 0x12), 64, lambda r: len(r) > 0):
        return None  # fone não está ligado ao receptor
    flush(h)
    for _ in range(4):  # às vezes o receptor devolve o ID do fone no lugar da bateria
        r = xfer(h, _bragi(0x09, 0x02, 0x0F), 64, lambda r: len(r) > 5)
        if r and 0 < (raw := r[4] | r[5] << 8) <= 1000:
            return raw // 10, False
    return None


def _xt_get(h, target, prop):
    flush(h)
    src = 0x01 if target == 0x09 else 0x00
    r = xfer(h, pad([0x02, target, 0x02, prop, 0x00], 64), 64,
             lambda r: len(r) > 7 and r[0] == 0x01 and r[1] == src and r[2] == 0x02, timeout=0.3)
    if r and r[3] == 0x00:
        return r[4] | r[5] << 8 | r[6] << 16 | r[7] << 24
    return None


def read_xt(h, m):
    first = 0x08 if m.pid == 0x0A62 else 0x09
    for target in (first, 0x09 if first == 0x08 else 0x08):
        v = _xt_get(h, target, 0x0F)
        if v is not None and v <= 1000:
            return v // 10, _xt_get(h, target, 0x10) == 1
    return None


VOID = dict(usage_page=0xFFC5, usage=0x0001, interface=3)
XT = dict(usage_page=0xFF42, usage=0x0001, interface=3)
_VOID_NAMES = {
    0x1B1C: "Corsair Void RGB", 0x1B27: "Corsair Void Wireless", 0x0A14: "Corsair Void Pro",
    0x0A16: "Corsair Void Pro", 0x0A17: "Corsair Void Pro", 0x0A1D: "Corsair Void Pro",
    0x0A1A: "Corsair Void Pro Wireless", 0x1B2A: "Corsair Void RGB", 0x1B23: "Corsair Void RGB",
    0x1B29: "Corsair Void RGB", 0x0A55: "Corsair Void Elite Wireless", 0x0A51: "Corsair Void RGB Elite Wireless",
    0x0A52: "Corsair Void Elite", 0x0A38: "Corsair HS70 Wireless", 0x0A4F: "Corsair HS70 Pro Wireless",
    0x0A2B: "Corsair Void RGB Wireless", 0x0A75: "Corsair Void Elite Wireless", 0x0A56: "Corsair Void",
}

MODELS = [
    *[Model(VID, pid, name, "HEADSET", read_void, **VOID) for pid, name in _VOID_NAMES.items()],
    Model(VID, 0x2A08, "Corsair Void Wireless V2", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x2A02, "Corsair Virtuoso MAX Wireless", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x0A97, "Corsair HS80 MAX Wireless", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x0A64, "Corsair Virtuoso XT", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A62, "Corsair Virtuoso XT", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A3E, "Corsair Virtuoso SE", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A3D, "Corsair Virtuoso SE", "HEADSET", read_xt, **XT),
]
