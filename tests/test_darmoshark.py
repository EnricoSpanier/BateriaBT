from vendors import darmoshark as dm
from tests.fakes import FakeDev


def _nosleep(monkeypatch, *mods):
    for mod in mods:
        monkeypatch.setattr(mod.time, "sleep", lambda s: None)


def dm_reply(op, status=1, pct=0, bond=b""):
    r = [0x51, op, status] + [0] * 18
    r[11] = pct
    r[3:3 + len(bond)] = list(bond)
    return r


def test_darmoshark_m3(monkeypatch):
    _nosleep(monkeypatch, dm)
    h = FakeDev(on_write=lambda d: [dm_reply(d[1], pct=77 if d[1] == 6 else 0, bond=bytes([0x8A, 0x24, 0x12, 0xFF]))])
    assert dm.read(h, dm.MODELS[1]) == (77, False, "Darmoshark M3")
    assert [f[:2] for f in h.features] == [b"\x51\x03", b"\x51\x06"] and len(h.features[0]) == 21


def test_darmoshark_n3_pelo_bond(monkeypatch):
    _nosleep(monkeypatch, dm)
    h = FakeDev(on_write=lambda d: [dm_reply(d[1], pct=9, bond=dm.N3_BOND)])
    assert dm.read(h, dm.MODELS[1]) == (9, False, "Darmoshark N3")


def test_darmoshark_resposta_velha_ou_erro(monkeypatch):
    _nosleep(monkeypatch, dm)
    assert dm.read(FakeDev(on_write=lambda d: [dm_reply(0x03)]), dm.MODELS[1]) is None  # nunca veio o 0x06
    assert dm.read(FakeDev(on_write=lambda d: [dm_reply(d[1], status=2, pct=50)]), dm.MODELS[1]) is None
