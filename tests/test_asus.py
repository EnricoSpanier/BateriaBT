from vendors import asus
from tests.fakes import FakeDev


def m(pid, name=None):
    return next(x for x in asus.MODELS if x.pid == pid and (name is None or name in x.name))


def resp(head, values, size=64):
    r = [0] * size
    r[:len(head)] = head
    for i, v in values.items():
        r[i] = v
    return r


def test_mouse_direto_sem_report_id():
    h = FakeDev(on_write=lambda d: [resp([0x12, 0x07], {4: 87, 9: 1})])
    assert asus.MODELS and m(0x197F).read(h, m(0x197F)) == (87, True)
    assert h.writes[0][:3] == b"\x00\x12\x07" and len(h.writes[0]) == 65


def test_mouse_em_passos_de_25():
    h = FakeDev(on_write=lambda d: [resp([0x12, 0x07], {4: 3})])
    assert m(0x18E5).read(h, m(0x18E5)) == (75, False)


def test_mouse_dormindo_da_none():
    assert m(0x197F).read(FakeDev(on_write=lambda d: [resp([0xFF, 0xAA], {})]), m(0x197F)) is None
    assert m(0x197F).read(FakeDev(on_write=lambda d: [resp([0x12, 0x07], {})]), m(0x197F)) is None


def test_omni_mouse_e_teclado():
    mm, kb = m(0x1ACE, "Mouse"), m(0x1ACE, "Teclado")
    h = FakeDev(on_write=lambda d: [resp([0x03, 0x12, 0x07], {5: 64, 10: 0})])
    assert mm.read(h, mm) == (64, False) and h.writes[0][:3] == b"\x03\x12\x07" and len(h.writes[0]) == 64
    h = FakeDev(on_write=lambda d: [resp([0x02, 0x12, 0x01], {6: 43, 9: 1})])
    assert kb.read(h, kb) == (43, True)


def test_teclados():
    assert m(0x1A85).read(FakeDev(on_write=lambda d: [resp([0x12, 0x01], {5: 55, 8: 1})]), m(0x1A85)) == (55, True)
    assert m(0x193E).read(FakeDev(on_write=lambda d: [resp([0x12, 0x01], {5: 6, 10: 61})]), m(0x193E)) == (61, False)


def test_resposta_de_outro_comando_e_descartada():
    h = FakeDev(on_write=lambda d: [resp([0x12, 0x00], {4: 50}), resp([0x12, 0x07], {4: 50})])
    assert m(0x197F).read(h, m(0x197F)) == (50, False)


def test_sem_resposta_da_none():
    assert m(0x1A85).read(FakeDev(), m(0x1A85)) is None
