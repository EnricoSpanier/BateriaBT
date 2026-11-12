from vendors import razer
from tests.fakes import FakeDev


def reply(req, status=0x02, value=0):
    r = bytearray(req[1:])  # sem o report ID
    r[0], r[9] = status, value
    return [0x00, *r]       # o hidapi devolve o report ID na frente


def dev(level=128, charging=1, status=0x02):
    def on(data):
        cmd = data[8]
        return [reply(data, status, level if cmd == 0x80 else charging)]
    return FakeDev(on_write=on)


def m(pid):
    return next(x for x in razer.MODELS if x.pid == pid)


def test_crc_do_pedido_de_bateria_e_0x85():
    assert razer.crc(razer.request(0x1F, 0x07, 0x80)) == 0x85


def test_basilisk_v3_pro_le_nivel_e_carga(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    h = dev(level=255, charging=1)
    assert razer.read(h, m(0x00AB)) == (100, True)
    assert h.features[0][2] == 0x1F and len(h.features[0]) == 91


def test_viper_ultimate_usa_transacao_ff(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    h = dev(level=128, charging=0)
    assert razer.read(h, m(0x007B)) == (50, False)
    assert h.features[0][2] == 0xFF


def test_mouse_de_pilha_nao_pergunta_carga(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    h = dev(level=64)
    assert razer.read(h, m(0x0083)) == (25, False) and len(h.features) == 1


def test_sem_resposta_da_none(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    assert razer.read(FakeDev(), m(0x00AB)) is None


def test_nao_suportado_da_none(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    assert razer.read(dev(status=0x05), m(0x00AB)) is None


def test_resposta_de_outro_comando_e_descartada(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    def on(data):
        r = reply(data, 0x02, 200)
        r[8] = 0x81  # id diferente do pedido
        return [r]
    assert razer.read(FakeDev(on_write=on), m(0x00AB)) is None


def test_teclado_usa_transacao_e_interface_do_openrazer(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)
    kb = m(0x0271)
    assert kb.kind == "KEYBOARD" and kb.interface == 3
    h = dev(level=204, charging=0)
    assert razer.read(h, kb) == (80, False) and h.features[0][2] == 0x9F


def test_colecao_sem_feature_report_da_none(monkeypatch):
    monkeypatch.setattr(razer.time, "sleep", lambda s: None)

    class Sem(FakeDev):
        def send_feature_report(self, data):
            raise OSError("sem feature report")
    assert razer.read(Sem(), m(0x0258)) is None


def test_wolverine_so_le():
    r = [0] * 64
    r[0], r[30] = 0x01, 0x16
    h = FakeDev(replies=[r])
    assert razer.read_wolverine(h, m(0x100C)) == (65, True) and h.writes == [] and h.features == []
    r[30] = 0x0C
    assert razer.read_wolverine(FakeDev(replies=[r]), m(0x100C)) is None
