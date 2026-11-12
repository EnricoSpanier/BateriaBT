from vendors import corsair as cs
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in cs.MODELS if x.pid == pid)


def test_void():
    h = FakeDev(on_write=lambda d: [[0x64, 0x00, 0x80 | 57, 0xB1, 0x01]])
    assert cs.read_void(h, m(0x0A55)) == (57, False) and h.writes == [b"\xc9\x64"]


def test_void_carregando_e_desligado():
    assert cs.read_void(FakeDev(on_write=lambda d: [[0x64, 0, 30, 0xB1, 0x05]]), m(0x0A55)) == (30, True)
    assert cs.read_void(FakeDev(on_write=lambda d: [[0x64, 0, 30, 0xB1, 0x00]]), m(0x0A55)) is None


def test_void_descarta_resposta_sem_assinatura():
    h = FakeDev(on_write=lambda d: [[0x01, 0, 30, 0x00, 0x01]])
    assert cs.read_void(h, m(0x0A55)) is None


def test_v2w():
    def on(d):
        if d[2] == 0x09 and d[4] == 0x12:
            return [[0x02, 0x09]]
        if d[4] == 0x0F:
            return [[0, 0, 0, 0, 0xEE, 0x02]]  # 750 -> 75 %
        return []
    assert cs.read_v2w(FakeDev(on_write=on), m(0x2A08)) == (75, False)


def test_v2w_fone_fora():
    assert cs.read_v2w(FakeDev(), m(0x2A08)) is None


def test_v2w_rejeita_id_e_tenta_de_novo():
    answers = iter([[0, 0, 0, 0, 0x34, 0x12], [0, 0, 0, 0, 0x64, 0x00]])  # 0x1234 > 1000; depois 100
    def on(d):
        if d[2] == 0x09 and d[4] == 0x12:
            return [[0x02, 0x09]]
        return [next(answers)] if d[4] == 0x0F else []
    assert cs.read_v2w(FakeDev(on_write=on), m(0x2A08)) == (10, False)


def test_xt_pelo_receptor():
    def on(d):
        target, prop = d[1], d[3]
        val = 830 if prop == 0x0F else 1
        return [[0x0E, 0x01], [0x01, 0x01 if target == 0x09 else 0x00, 0x02, 0x00, val & 0xFF, val >> 8, 0, 0]]
    h = FakeDev(on_write=on)
    assert cs.read_xt(h, m(0x0A64)) == (83, True)
    assert h.writes[0][:5] == b"\x02\x09\x02\x0f\x00" and len(h.writes[0]) == 64


def test_xt_com_fio_comeca_no_alvo_08():
    h = FakeDev(on_write=lambda d: [[0x01, 0x00, 0x02, 0x00, 0x20, 0x03, 0, 0]])
    assert cs.read_xt(h, m(0x0A62))[0] == 80
    assert h.writes[0][1] == 0x08


def test_xt_sem_fone():
    h = FakeDev(on_write=lambda d: [[0x01, 0x00, 0x02, 0x05, 0, 0, 0, 0]])
    assert cs.read_xt(h, m(0x0A64)) is None


def bragi(values, err=0):
    """Aparelho Bragi falso: values = {(endpoint, prop): valor}."""
    def on(d):
        key = (d[1], d[3])
        if key not in values:
            return [[0x00, 0x02, 0x05, 0, 0]]  # propriedade não suportada
        v = values[key]
        return [[0x00, 0x02, err, v & 0xFF, v >> 8]]
    return FakeDev(on_write=on)


def test_bragi_cabo():
    h = bragi({(0x08, 0x0F): 735, (0x08, 0x10): 1})
    assert cs.read_bragi(h, m(0x1BF2)) == (73, True)
    assert h.writes[0][:4] == b"\x00\x08\x02\x0f" and len(h.writes[0]) == 65


def test_bragi_erro_ou_zero_da_none():
    assert cs.read_bragi(bragi({(0x08, 0x0F): 500}, err=3), m(0x1BF2)) is None
    assert cs.read_bragi(bragi({(0x08, 0x0F): 0}), m(0x1BF2)) is None


def test_slipstream_le_o_pareado_e_informa_o_nome():
    h = bragi({(0x08, 0x36): 0b100, (0x0A, 0x0F): 420, (0x0A, 0x10): 2, (0x0A, 0x12): 0x1BAB})
    assert cs.read_slipstream(h, m(0x1BDC)) == (42, False, "Corsair K100 AIR Wireless", "KEYBOARD")


def test_slipstream_sem_pareado_da_none():
    assert cs.read_slipstream(bragi({(0x08, 0x36): 0}), m(0x1BDC)) is None


def test_slipstream_nunca_pede_bateria_ao_receptor():
    h = bragi({(0x08, 0x36): 0b10, (0x09, 0x0F): 900})
    cs.read_slipstream(h, m(0x1B65))
    assert not any(w[1] == 0x08 and w[3] == 0x0F for w in h.writes)


def test_nxp():
    h = FakeDev(on_write=lambda d: [[0x00, 0x0E, 0x50, 0, 0, 3, 2]])
    assert cs.read_nxp(h, m(0x1B4B)) == (75, True) and h.features[0][:3] == b"\x00\x0e\x50"
    assert cs.read_nxp(FakeDev(on_write=lambda d: [[0x00, 0x0E, 0x51, 0, 0, 3, 2]]), m(0x1B4B)) is None
