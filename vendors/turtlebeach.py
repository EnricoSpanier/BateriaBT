"""Turtle Beach Stealth Gen 3 pelo dongle (chip Airoha, mesmo pedido do Audeze; ver race.py).
O Stealth 700 Gen 3 fica de fora: o dongle dele recusa esse pedido, e a outra rota exige ligar um
recurso no chip."""
from . import Model, race

VID = 0x10F5


def read(h, m):
    p = race.battery(h)
    return None if p is None else (p, False)


MODELS = [
    Model(VID, 0x224C, "Turtle Beach Stealth 600 Gen 3", "HEADSET", read, usage_page=0xFF13, usage=0x0001),
]
