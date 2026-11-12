"""Headsets Audeze Maxwell pelo dongle (protocolo RACE, ver race.py). Não informa carga."""
from . import Model, race

VID = 0x3329


def read(h, m):
    p = race.battery(h)
    return None if p is None else (p, False)


MODELS = [
    Model(VID, 0x4B19, "Audeze Maxwell", "HEADSET", read, usage_page=0xFF13, usage=0x0001, interface=0),
    Model(VID, 0x4B18, "Audeze Maxwell", "HEADSET", read, usage_page=0xFF13, usage=0x0001, interface=0),
    Model(VID, 0x4B29, "Audeze Maxwell 2", "HEADSET", read, usage_page=0xFF13, usage=0x0001, interface=5),
    Model(VID, 0x4B28, "Audeze Maxwell 2", "HEADSET", read, usage_page=0xFF13, usage=0x0001, interface=5),
]
