"""Headsets HyperX sem fio (protocolos documentados pelo HeadsetControl)."""
from . import Model, pad, xfer

HP, KINGSTON = 0x03F0, 0x0951


def _alpha(h, cmd):
    return xfer(h, pad([0x21, 0xBB, cmd], 31), 31, lambda r: len(r) >= 4)


def read_alpha(h, m):
    c = _alpha(h, 0x03)
    if not c or c[3] == 0x01:  # fone desligado ou fora da base
        return None
    ch, lv = _alpha(h, 0x0C), _alpha(h, 0x0B)
    if not lv or lv[3] > 100:
        return None
    return lv[3], bool(ch and ch[3] == 0x01)


def _hp(h, cmd):
    return xfer(h, pad([0x06, 0xFF, 0xBB, cmd], 52), 20, lambda r: r[:4] == [0x06, 0xFF, 0xBB, cmd], wait=0.1)


def read_cloud2_hp(h, m):
    lv = _hp(h, 0x02)
    if not lv or len(lv) < 8:
        return None
    ch = _hp(h, 0x03)
    return lv[7], bool(ch and ch[4] == 1)


_KINGSTON = [0x06, 0x00, 0x02, 0x00, 0x9A, 0x00, 0x00, 0x68, 0x4A, 0x8E, 0x0A, 0x00, 0x00, 0x00, 0xBB]


def _kingston(h, cmd):
    try:
        h.get_input_report(0x06, 64)
    except Exception:
        pass
    return xfer(h, pad(_KINGSTON + [cmd, 0x00], 62), 64,
                lambda r: len(r) > 7 and r[0] == 0x0B and r[2] == 0xBB and r[3] == cmd, wait=0.1)


def read_cloud2_kingston(h, m):
    lv = _kingston(h, 0x02)
    if not lv:
        return None
    ch = _kingston(h, 0x03)
    return lv[7], bool(ch and ch[4] == 1)


def flight_pct(mv):
    """Curva do HeadsetControl (derivada da do Logitech G633/G933)."""
    if mv <= 3648:
        return round(0.00125 * mv)
    if mv > 3975:
        return 100
    return round(0.00000002547505 * mv ** 4 - 0.0003900299 * mv ** 3 + 2.238321 * mv ** 2
                 - 5706.256 * mv + 5452299.0)


def read_flight(h, m):
    r = xfer(h, pad([0x21, 0xFF, 0x05], 20), 20, lambda r: len(r) in (15, 20))
    if not r:
        return None
    mv = r[3] << 8 | r[4]
    return max(0, min(100, flight_pct(mv))), mv > 0x100B


def _alpha2(h, cmd, sub):
    return xfer(h, pad([cmd, sub], 64), 64, lambda r: len(r) > 2 and r[0] == cmd + 1 and r[1] == sub, timeout=1.0)


def read_alpha2(h, m):
    c = _alpha2(h, 0x52, 0x01)
    if not c or c[2] == 0x00:
        return None
    b = _alpha2(h, 0x50, 0x02)
    if not b or len(b) < 4 or b[2] > 100:
        return None
    return b[2], b[3] == 0x01


MODELS = [
    Model(HP, 0x098D, "HyperX Cloud Alpha Wireless", "HEADSET", read_alpha, interface=0),
    Model(HP, 0x0696, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_hp, usage_page=0xFF90, usage=0x0303),
    Model(HP, 0x018B, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_hp, usage_page=0xFF90, usage=0x0303),
    Model(KINGSTON, 0x1718, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_kingston, interface=0),
    Model(KINGSTON, 0x16C4, "HyperX Cloud Flight", "HEADSET", read_flight, interface=0),
    Model(KINGSTON, 0x1723, "HyperX Cloud Flight", "HEADSET", read_flight, interface=0),
    Model(HP, 0x08BE, "HyperX Cloud Alpha 2 Wireless", "HEADSET", read_alpha2,
          usage_page=0xFF13, usage=0xFF00, interface=2),
]


# --- mouses ---
def read_dart(h, m):
    """Pulsefire Dart e Haste Wireless (1ª geração): heartbeat 0x51 pelo receptor (protocolo documentado
    em hyperx_pulsefire_dart_reverse_engineering e open-pulsefire-haste). [4] = %, [5] = 1 carregando."""
    r = xfer(h, pad([0x00, 0x51], 65), 64, lambda r: len(r) > 5 and r[0] == 0x51 and r[4] <= 100 and r[5] <= 2)
    return (r[4], r[5] == 1) if r else None


MOUSE = dict(usage_page=0xFF00, interface=2)
MODELS += [
    Model(KINGSTON, 0x16E1, "HyperX Pulsefire Dart", "MOUSE", read_dart, **MOUSE),
    Model(HP, 0x068E, "HyperX Pulsefire Dart", "MOUSE", read_dart, **MOUSE),
    Model(HP, 0x028E, "HyperX Pulsefire Haste Wireless", "MOUSE", read_dart, **MOUSE),
    # mesmo protocolo do Cloud Alpha 2 (52 01 = conectado, 50 02 = bateria), pelo receptor
    *[Model(HP, pid, name, "MOUSE", read_alpha2, usage_page=0xFF00, usage=0x0001, interface=2)
      for pid, name in ((0x0F98, "HyperX Pulsefire Haste 2 Wireless"), (0x0CBD, "HyperX Pulsefire Haste 2 Pro 4K"),
                        (0x06BF, "HyperX Pulsefire Saga Pro"))],
]
