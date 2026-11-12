"""SteelSeries: headsets Arctis/Nova e GameBuds (HeadsetControl) e mouses Aerox/Rival sem fio (rivalcfg)."""
from . import Model, pad, xfer

VID = 0x1038
NOVA = dict(usage_page=0xFFC0, usage=0x0001, interface=3)
LEGACY3 = dict(usage_page=0xFF43, usage=0x0202, interface=3)
LEGACY5 = dict(usage_page=0xFF43, usage=0x0202, interface=5)


def _map(v, lo, hi):
    return max(0, min(100, round((v - lo) * 100 / (hi - lo))))


def _nova(h, n):
    return xfer(h, bytes([0x00, 0xB0]), 128, lambda r: len(r) >= n)


NOVA7_DISCRETE = {0x2202, 0x2206, 0x220A, 0x223A, 0x227A, 0x22A4}


def read_nova7(h, m):
    r = _nova(h, 4)
    if not r or r[3] == 0x00:
        return None
    return min(100, r[2] * 25 if m.pid in NOVA7_DISCRETE else r[2]), r[3] in (0x01, 0x02)


def read_7plus(h, m):
    r = _nova(h, 4)
    if not r or r[1] == 0x01:
        return None
    return _map(r[2], 0, 4), r[3] == 0x01


NOVA5 = {0x2232, 0x2253}


def read_nova35(h, m):
    r = _nova(h, 16 if m.pid in NOVA5 else 5)
    if not r or r[1] == 0x02:
        return None
    return r[3], r[4] == 0x01


def read_novapro(h, m):
    r = xfer(h, pad([0x06, 0xB0], 31), 128, lambda r: len(r) >= 16)
    if not r or r[15] == 0x01:
        return None
    return _map(r[6], 0, 8), r[15] == 0x02


def read_arctis1(h, m):
    r = xfer(h, bytes([0x06, 0x12]), 8, lambda r: len(r) >= 4)
    if not r or r[2] == 0x01:
        return None
    return r[3], False


def read_arctis7(h, m):
    r = xfer(h, bytes([0x06, 0x18]), 8, lambda r: len(r) >= 3)
    return (r[2], False) if r else None


AEROX_WIRED = {0x183A, 0x187A, 0x1854, 0x185E, 0x1862, 0x185A, 0x1876}


def read_aerox(h, m):
    cmd = 0x92 if m.pid in AEROX_WIRED else 0xD2  # pelo receptor o comando ganha o bit 6
    r = xfer(h, bytes([0x00, cmd]), 2, lambda r: len(r) >= 2, timeout=0.25, wait=0.05)
    if not r:
        return None
    level = ((r[1] & 0x7F) - 1) * 5
    return (level, bool(r[1] & 0x80)) if 0 <= level <= 100 else None


def read_rival(h, m):
    r = xfer(h, bytes([0x00, 0xAA, 0x01]), 3, lambda r: len(r) >= 3, timeout=0.25, wait=0.05)
    return (r[0], bool(r[2])) if r and r[0] <= 100 else None


def read_arctis9(h, m):
    r = xfer(h, bytes([0x00, 0x20]), 12, lambda r: len(r) >= 5)
    if not r or r[4] == 0xFF:  # fone desligado
        return None
    return _map(r[3], 0x64, 0x9A), r[4] == 0x01


def read_pro_wireless(h, m):
    st = xfer(h, pad([0x41, 0xAA], 31), 2, lambda r: len(r) >= 1)
    if not st or st[0] != 0x04:  # 0x02 = fone desligado
        return None
    r = xfer(h, pad([0x40, 0xAA], 31), 1, lambda r: len(r) >= 1 and r[0] <= 4)
    return (_map(r[0], 0, 4), False) if r else None


def read_gamebuds(h, m):
    r = _nova(h, 7)
    if not r:
        return None
    on = [r[5 + i] for i in (0, 1) if r[3 + i] == 0x03]  # 0x03 = fone fora do estojo
    return (min(100, min(on)), False) if on else None


def _h(pids, name, read, coll):
    return [Model(VID, p, name, "HEADSET", read, **coll) for p in pids]


def _mouse(pids, name, read, iface):
    return [Model(VID, p, name, "MOUSE", read, interface=iface) for p in pids]


MODELS = [
    *_h([0x2202, 0x22A1, 0x227E, 0x2258, 0x229E, 0x223A], "SteelSeries Arctis Nova 7", read_nova7, NOVA),
    *_h([0x2206, 0x22AD, 0x22A4, 0x22A5], "SteelSeries Arctis Nova 7X", read_nova7, NOVA),
    *_h([0x22A9], "SteelSeries Arctis Nova 7 Diablo IV", read_nova7, NOVA),
    *_h([0x227A], "SteelSeries Arctis Nova 7 WoW", read_nova7, NOVA),
    *_h([0x220A, 0x22A7, 0x2298], "SteelSeries Arctis Nova 7P", read_nova7, NOVA),
    *_h([0x12C2, 0x12C4], "SteelSeries Arctis 9", read_arctis9, dict(interface=0)),
    *_h([0x1290], "SteelSeries Arctis Pro Wireless", read_pro_wireless, dict(interface=0)),
    *_h([0x230A], "SteelSeries Arctis GameBuds", read_gamebuds, NOVA),
    *_h([0x220E, 0x2212, 0x2216, 0x2236], "SteelSeries Arctis 7+", read_7plus, NOVA),
    *_h([0x2269, 0x226D], "SteelSeries Arctis Nova 3 Wireless", read_nova35, NOVA),
    *_h([0x2232, 0x2253], "SteelSeries Arctis Nova 5", read_nova35, NOVA),
    *_h([0x12E0, 0x12E5], "SteelSeries Arctis Nova Pro Wireless", read_novapro, dict(interface=4)),
    *_h([0x12B3, 0x12B6], "SteelSeries Arctis 1 Wireless", read_arctis1, LEGACY3),
    *_h([0x12D7], "SteelSeries Arctis 7X", read_arctis1, LEGACY3),
    *_h([0x12D5], "SteelSeries Arctis 7P", read_arctis1, LEGACY3),
    *_h([0x1260, 0x12AD], "SteelSeries Arctis 7", read_arctis7, LEGACY5),
    *_h([0x1252, 0x1280], "SteelSeries Arctis Pro", read_arctis7, LEGACY5),
    *_mouse([0x1838, 0x1878, 0x183A, 0x187A], "SteelSeries Aerox 3 Wireless", read_aerox, 3),
    *_mouse([0x1852, 0x185C, 0x1860, 0x1854, 0x185E, 0x1862], "SteelSeries Aerox 5 Wireless", read_aerox, 3),
    *_mouse([0x1858, 0x1874, 0x185A, 0x1876], "SteelSeries Aerox 9 Wireless", read_aerox, 3),
    *_mouse([0x1830], "SteelSeries Rival 3 Wireless", read_rival, 3),
    *_mouse([0x1872], "SteelSeries Rival 3 Wireless Gen 2", read_rival, 3),
    *_mouse([0x1726, 0x172B], "SteelSeries Rival 650 Wireless", read_rival, 0),
]
