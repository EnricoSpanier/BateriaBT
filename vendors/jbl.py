"""JBL Quantum 810 pelo dongle: só lê dois feature reports (0x68 = fone ligado, 0x49 = %), sem
enviar comando. Fontes: jbl-quantum-battery, QuantumEngine. Não informa carga."""
from . import Model

VID = 0x0ECB


def _feature(h, rid):
    r = list(h.get_feature_report(rid, 2))
    return r[1] if len(r) >= 2 and r[0] == rid else None  # sem eco do ID = outro report


def read(h, m):
    if _feature(h, 0x68) != 1:  # fone desligado ou fora de alcance
        return None
    pct = _feature(h, 0x49)
    return (pct, False) if pct is not None and pct <= 100 else None


MODELS = [Model(VID, 0x2069, "JBL Quantum 810", "HEADSET", read, interface=5, writes=False)]
