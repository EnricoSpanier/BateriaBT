from vendors import pulsar as ps
from tests.fakes import FakeDev

M = ps.MODELS[0]


def reply(state, value):
    return [0, state, 0x08, 0, 0x01, 0, 0, value] + [0] * 57


def test_pedido_com_checksum():
    r = ps.request(0x81)
    assert len(r) == 65 and r[2:5] == b"\x08\x81\x01" and r[63] == 0x8A and r[64] == 0


def test_le_bateria_e_carga(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    h = FakeDev(on_write=lambda d: [reply(0x02, 0), reply(0x01, 70 if d[3] == 0x81 else 1)])
    assert ps.read(h, M) == (70, True)


def test_reenvia_quando_recusado(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    answers = iter([[reply(0x00, 0)], [reply(0x01, 55)], [reply(0x01, 0)]])
    h = FakeDev(on_write=lambda d: next(answers))
    assert ps.read(h, M) == (55, False) and len(h.features) == 3


def test_sem_mouse_ou_sem_resposta(monkeypatch):
    monkeypatch.setattr(ps.time, "sleep", lambda s: None)
    assert ps.read(FakeDev(on_write=lambda d: [reply(0x01, 0xFF)]), M) is None
    assert ps.read(FakeDev(), M) is None
