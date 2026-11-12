from vendors import kc2
from tests.fakes import FakeDev

M = kc2.MODELS[0]
RAW = [0xB4, 0x06, 0x00, 0x20, 0x20, 0x60, 0x90, 0x01, 0x20, 0x03, 0x40, 0x06, 0x80, 0x0C, 0x00, 0x19,
       0x01, 0x06, 0x00, 0x05, 0xA4, 0x50, 0xC3] + [0] * 41  # captura do vigil-watt: 36 % carregando


def test_le_bateria_carregando():
    h = FakeDev(on_write=lambda d: [RAW])
    assert kc2.read(h, M) == (36, True)
    assert h.writes[0][:2] == b"\xb3\x06" and len(h.writes[0]) == 64


def test_descarta_outro_trafego_e_quadro_zerado():
    zero = [0xB4, 0x06] + [0] * 62
    other = [0xB4, 0x03] + [1] * 62
    h = FakeDev(on_write=lambda d: [zero, other, RAW[:20] + [55] + RAW[21:]])
    assert kc2.read(h, M) == (55, False)


def test_colecao():
    assert all(m.usage_page == 0xFFC1 and m.usage == 0x0001 for m in kc2.MODELS)
