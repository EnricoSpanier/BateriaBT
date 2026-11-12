from vendors import compx as cx
from tests.fakes import FakeDev

M = cx.MODELS[0]


def frame(pct, plug=0, status=0):
    r = [0x08, 0x04, status, 0, 0, 0x02, pct, plug, 0x0F, 0xC8] + [0] * 6
    return r + [(0x55 - sum(r)) & 0xFF]


def test_le_bateria():
    h = FakeDev(on_write=lambda d: [frame(80)])
    assert cx.read(h, M) == (80, False)
    assert h.writes == [cx.REQUEST] and sum(cx.REQUEST) & 0xFF == 0x55


def test_cabo_ligado_conta_como_carregando_ate_100():
    assert cx.read(FakeDev(on_write=lambda d: [frame(60, plug=1)]), M) == (60, True)
    assert cx.read(FakeDev(on_write=lambda d: [frame(100, plug=1)]), M) == (100, False)


def test_descarta_eco_evento_e_checksum_ruim():
    bad = frame(50)
    bad[16] ^= 1
    h = FakeDev(on_write=lambda d: [list(cx.REQUEST), [0x0A, 1, 2], bad, frame(42)])
    assert cx.read(h, M) == (42, False)


def test_mouse_dormindo_da_none(monkeypatch):
    monkeypatch.setattr(cx, "xfer", lambda *a, **k: None)
    assert cx.read(FakeDev(), M) is None


def test_status_de_erro_da_none(monkeypatch):
    h = FakeDev(on_write=lambda d: [frame(80, status=1)])
    monkeypatch.setattr(cx, "xfer", lambda h, out, n, ok, **k: next((r for r in h.on_write(out) if ok(r)), None))
    assert cx.read(h, M) is None


def test_colecao_e_pids():
    assert all(m.usage_page == 0xFF02 and m.usage == 0x0002 for m in cx.MODELS)
    assert len({(m.vid, m.pid) for m in cx.MODELS}) == len(cx.MODELS)
