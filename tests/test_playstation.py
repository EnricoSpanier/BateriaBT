from vendors import playstation as ps
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in ps.MODELS if x.pid == pid)


def report(rid, size, idx, value):
    r = [0] * size
    r[0], r[idx] = rid, value
    return r


def test_dualsense_usb_descarregando():
    h = FakeDev(replies=[report(0x01, 64, 53, 0x07)])
    assert ps.read_dualsense(h, m(0x0CE6)) == (75, False)


def test_dualsense_carregando_e_cheio():
    assert ps.read_dualsense(FakeDev(replies=[report(0x01, 64, 53, 0x13)]), m(0x0CE6)) == (35, True)
    assert ps.read_dualsense(FakeDev(replies=[report(0x01, 64, 53, 0x2A)]), m(0x0CE6)) == (100, False)


def test_dualsense_bt_estendido():
    assert ps.read_dualsense(FakeDev(replies=[report(0x31, 78, 54, 0x05)]), m(0x0CE6)) == (55, False)


def test_aceite4_bt_simples_da_none_e_nada_e_enviado():
    h = FakeDev(replies=[[0x01, 0x80, 0x80, 0x80, 0x80, 0x08, 0, 0, 0, 0]])
    assert ps.read_dualsense(h, m(0x0CE6)) is None
    assert h.writes == [] and h.features == [] and h.feature_gets == 0


def test_ds4_usb_com_cabo_e_sem_cabo():
    assert ps.read_ds4(FakeDev(replies=[report(0x01, 64, 30, 0x10 | 4)]), m(0x09CC)) == (45, True)
    assert ps.read_ds4(FakeDev(replies=[report(0x01, 64, 30, 8)]), m(0x09CC)) == (85, False)
    assert ps.read_ds4(FakeDev(replies=[report(0x01, 64, 30, 0x10 | 11)]), m(0x09CC)) == (100, False)


def test_ds4_bt():
    assert ps.read_ds4(FakeDev(replies=[report(0x11, 78, 32, 6)]), m(0x05C4)) == (65, False)


def test_achado2_adaptador_ds4_sem_controle_da_none():
    r = report(0x01, 64, 30, 0)
    r[31] = 0x04
    assert ps.read_ds4(FakeDev(replies=[r]), m(0x0BA0)) is None


def test_ds4_codigo_de_erro_da_none():
    assert ps.read_ds4(FakeDev(replies=[report(0x01, 64, 30, 0x10 | 14)]), m(0x09CC)) is None


def test_sem_resposta_da_none():
    assert ps.read_dualsense(FakeDev(), m(0x0CE6)) is None
    assert ps.read_ds4(FakeDev(), m(0x09CC)) is None


def test_modelos_nao_escrevem():
    assert all(not x.writes for x in ps.MODELS)
