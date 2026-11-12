from vendors import steelseries as ss
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in ss.MODELS if x.pid == pid)


def answer(resp):
    return FakeDev(on_write=lambda d: [resp])


def test_nova7_porcentagem_direta():
    assert ss.read_nova7(answer([0x00, 0x00, 73, 0x01]), m(0x2258)) == (73, True)


def test_nova7_discreto_0_a_4():
    assert ss.read_nova7(answer([0x00, 0x00, 3, 0x03]), m(0x2202)) == (75, False)


def test_nova7_desligado():
    assert ss.read_nova7(answer([0x00, 0x00, 50, 0x00]), m(0x2258)) is None


def test_nova7_envia_00_b0():
    h = answer([0x00, 0x00, 50, 0x03])
    ss.read_nova7(h, m(0x2258))
    assert h.writes == [b"\x00\xb0"]


def test_7plus():
    assert ss.read_7plus(answer([0, 0x00, 2, 0x01]), m(0x220E)) == (50, True)
    assert ss.read_7plus(answer([0, 0x01, 2, 0x00]), m(0x220E)) is None


def test_nova3p_e_nova5():
    assert ss.read_nova35(answer([0, 0x00, 0, 64, 0x00]), m(0x2269)) == (64, False)
    assert ss.read_nova35(answer([0, 0x02, 0, 64, 0x00]), m(0x2269)) is None
    assert ss.read_nova35(answer([0, 0x00, 0, 90, 0x01] + [0] * 11), m(0x2232)) == (90, True)
    assert ss.read_nova35(answer([0, 0x00, 0, 90, 0x01]), m(0x2232)) is None  # Nova 5 exige 16 bytes


def test_nova_pro():
    r = [0] * 16
    r[6], r[15] = 4, 0x02
    assert ss.read_novapro(answer(r), m(0x12E0)) == (50, True)
    r[15] = 0x01
    assert ss.read_novapro(answer(r), m(0x12E0)) is None


def test_arctis1_e_arctis7():
    assert ss.read_arctis1(answer([0, 0, 0x00, 80, 0, 0, 0, 0]), m(0x12B3)) == (80, False)
    assert ss.read_arctis1(answer([0, 0, 0x01, 80, 0, 0, 0, 0]), m(0x12B3)) is None
    assert ss.read_arctis7(answer([0, 0, 66, 0, 0, 0, 0, 0]), m(0x1260)) == (66, False)


def test_aerox_cabo_e_receptor(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    h = answer([0x00, 0x80 | 15])
    assert ss.read_aerox(h, m(0x183A)) == (70, True) and h.writes == [b"\x00\x92"]
    h = answer([0x00, 21])
    assert ss.read_aerox(h, m(0x1838)) == (100, False) and h.writes == [b"\x00\xd2"]


def test_aerox_fora_da_faixa_da_none(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    assert ss.read_aerox(answer([0x00, 0x00]), m(0x183A)) is None


def test_rival(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    assert ss.read_rival(answer([55, 0, 1]), m(0x1830)) == (55, True)


def test_sem_resposta_da_none():
    assert ss.read_nova7(FakeDev(), m(0x2258)) is None
