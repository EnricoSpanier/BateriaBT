from vendors import sony
from tests.fakes import FakeDev


def resp(payload, kind=0x10):
    hl = 12 + len(payload)
    r = [0x02, hl, 0x04, 0xFF, 0x00, 0x00, 0x96, 0xC3, 0x14, 0x04, kind, 0x02, 0x00, *payload]
    r.append(sum(r[6:hl + 1]) & 0xFF)
    return r + [0] * (64 - len(r))


def m(pid):
    return next(x for x in sony.MODELS if x.pid == pid)


def test_pedido_e_o_get_de_bateria():
    h = FakeDev(on_write=lambda d: [resp([0x00, 55])])
    sony.read_headset(h, m(0x0EBF))
    assert h.writes[0][:14] == bytes([0x02, 0x0C, 0x01, 0x00, 0xFC, 0x08, 0x96, 0xC3, 0x41, 0x04, 0x01, 0x02, 0x00, 0xA1])
    assert len(h.writes[0]) == 64


def test_h5_e_h9_ii():
    assert sony.read_headset(FakeDev(on_write=lambda d: [resp([0x00, 55])]), m(0x0EBF)) == (55, False)
    assert sony.read_headset(FakeDev(on_write=lambda d: [resp([0x01, 80], 0xA0)]), m(0x0FA8)) == (80, True)


def test_desligado_da_none():
    assert sony.read_headset(FakeDev(on_write=lambda d: [resp([0x00, 0xFF])]), m(0x0EBF)) is None


def test_checksum_errado_e_descartado():
    r = resp([0x00, 55])
    r[15] ^= 1
    assert sony.read_headset(FakeDev(on_write=lambda d: [r]), m(0x0EBF)) is None


def test_evento_antes_da_resposta():
    outro = resp([0x00, 0x00])
    outro[9] = 0x05  # outro evento
    assert sony.read_headset(FakeDev(on_write=lambda d: [outro, resp([0x00, 40])]), m(0x0EBF)) == (40, False)


def test_buds():
    assert sony.read_buds(FakeDev(on_write=lambda d: [resp([1, 70, 1, 50, 1, 90])]), m(0x0EC2)) == (50, False)
    assert sony.read_buds(FakeDev(on_write=lambda d: [resp([1, 70, 0, 0xFF, 1, 90])]), m(0x0EC2)) == (70, False)
    assert sony.read_buds(FakeDev(on_write=lambda d: [resp([0, 0xFF, 0, 0xFF, 1, 90])]), m(0x0EC2)) is None


def test_sem_resposta_da_none():
    assert sony.read_headset(FakeDev(), m(0x0FA8)) is None
