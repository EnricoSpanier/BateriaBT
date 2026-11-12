"""Controles Xbox pela API XInput do Windows (só informa níveis: vazio, baixo, médio, cheio)."""
import ctypes


class _Battery(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ubyte), ("level", ctypes.c_ubyte)]


LEVELS = (5, 30, 60, 99)  # 99: o XInput não diz se é pilha; 100 dispararia "tire do carregador"
SKIP = (0x00, 0x01, 0xFF)  # desconectado, com fio (sem bateria), desconhecido


def _api():
    for dll in ("xinput1_4", "xinput1_3"):
        try:
            return getattr(ctypes.windll, dll).XInputGetBatteryInformation
        except (OSError, AttributeError):
            continue
    return None


def scan(api=None):
    api = api or _api()
    if not api:
        return {}
    out = {}
    for i in range(4):
        b = _Battery()
        if api(i, 0, ctypes.byref(b)) != 0 or b.type in SKIP:
            continue
        out[f"xinput:{i}"] = {"name": f"Controle Xbox {i + 1}", "battery": LEVELS[min(b.level, 3)],
                              "connected": True, "kind": "GAMEPAD", "charging": False, "hours": None}
    return out
