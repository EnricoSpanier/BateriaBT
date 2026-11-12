"""Controles PlayStation: só lê o input report que o controle já manda (sem comando nenhum, para não
mudar o modo do controle e quebrar Steam Input/DS4Windows). Layout do driver hid-playstation do Linux."""
import time

from . import Model

SONY = 0x054C


def _scan(h, offsets, timeout=0.5):
    """Primeiro report que traga o byte de status: offsets = {report_id: índice}. Devolve (report, índice)."""
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        r = h.read(78, max(1, int(left * 1000)))
        if r and r[0] in offsets and len(r) > offsets[r[0]] + 1:
            return r, offsets[r[0]]
    return None


def read_dualsense(h, m):
    got = _scan(h, {0x01: 53, 0x31: 54})
    if got is None:
        return None
    s = got[0][got[1]]
    level, state = s & 0x0F, s >> 4
    if state == 2:
        return 100, False  # carga completa
    return min(level * 10 + 5, 100), state == 1


def read_ds4(h, m):
    got = _scan(h, {0x01: 30, 0x11: 32})
    if got is None:
        return None
    r, i = got
    if m.pid == 0x0BA0 and r[i + 1] & 0x04:  # adaptador sem controle (DS4_STATUS1_DONGLE_STATE)
        return None
    level, cable = r[i] & 0x0F, bool(r[i] & 0x10)
    if level > 11:
        return None  # 14/15 = erro de carga ou temperatura
    if cable and level >= 10:
        return 100, level == 10  # 10 = ainda carregando; 11 = cheio
    return min(level * 10 + 5, 100), cable


GAMEPAD = dict(usage_page=0x01, usage=0x05, writes=False)
MODELS = [
    Model(SONY, 0x0CE6, "DualSense", "GAMEPAD", read_dualsense, **GAMEPAD),
    Model(SONY, 0x0DF2, "DualSense Edge", "GAMEPAD", read_dualsense, **GAMEPAD),
    Model(SONY, 0x05C4, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
    Model(SONY, 0x09CC, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
    Model(SONY, 0x0BA0, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
]
