import pytest

from vendors import audeze, race, turtlebeach
from tests.fakes import FakeDev

ACK = [0x05, 0x5B, 0x03, 0x00, 0xD6, 0x0C, 0x00]
BAT = [0x05, 0x5D, 0x05, 0x00, 0xD6, 0x0C, 0x00, 0x00, 73]


def frag(data):
    return [0x07, len(data), 0x00, *data] + [0] * (59 - len(data))


@pytest.fixture(autouse=True)
def rapido(monkeypatch):
    monkeypatch.setattr(race.time, "sleep", lambda s: None)
    monkeypatch.setattr(race, "TIMEOUT", 0.05)


def m(mod, pid):
    return next(x for x in mod.MODELS if x.pid == pid)


def test_audeze_le_a_bateria_em_fragmentos():
    msgs = ACK + BAT
    h = FakeDev(on_write=lambda d: [frag([]), frag(msgs[:10]), frag(msgs[10:])])
    assert audeze.read(h, m(audeze, 0x4B19)) == (73, False)
    assert h.writes[0][:10] == bytes([0x06, 0x07, 0x80, 0x05, 0x5A, 0x03, 0x00, 0xD6, 0x0C, 0x00])
    assert len(h.writes[0]) == 62


def test_resposta_de_outro_comando_e_ignorada():
    outro = [0x05, 0x5D, 0x05, 0x00, 0x01, 0x09, 0x00, 0x00, 1]
    h = FakeDev(on_write=lambda d: [frag(outro), frag(BAT)])
    assert turtlebeach.read(h, m(turtlebeach, 0x224C)) == (73, False)


def test_recusa_da_none():
    h = FakeDev(on_write=lambda d: [frag([0x05, 0x5B, 0x03, 0x00, 0xD6, 0x0C, 0x02])])
    assert audeze.read(h, m(audeze, 0x4B29)) is None


def test_sem_resposta_tenta_de_novo_e_da_none():
    h = FakeDev()
    assert audeze.read(h, m(audeze, 0x4B19)) is None and len(h.writes) == 2
