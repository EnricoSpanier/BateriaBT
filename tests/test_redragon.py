from vendors import redragon as rd
from tests.fakes import FakeDev


def _nosleep(monkeypatch, *mods):
    for mod in mods:
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)


def test_redragon_m998(monkeypatch):
    _nosleep(monkeypatch, rd)
    assert sum(rd.REQUEST[2:]) & 0xFF == rd.REQUEST[1] and len(rd.REQUEST) == 64
    busy = [0x03, 0, 1, 0, 0, 0, 0]
    h = FakeDev(on_write=lambda d: [busy, [0x03, 0, 0, 0, 0x02, 0, 0x80 | 85]])
    assert rd.read(h, rd.MODELS[0]) == (85, True)
    assert rd.read(FakeDev(), rd.MODELS[0]) is None
