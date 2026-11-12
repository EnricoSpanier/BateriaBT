from vendors import logitech as lg
from tests.fakes import FakeDev

A50, G522 = lg.MODELS[0], lg.MODELS[2]


def instant(h, out, n, ok, **k):
    """xfer sem esperar: escreve e consome o que chegou."""
    h.write(out)
    rs, h.q = h.q, []
    return next((r for r in rs if ok(r)), None)


def a50_reply(p):
    return list(lg.frame(lg.A50, p))


def test_a50_descobre_indice_e_le():
    def on(d):
        p = lg.payload(d, lg.A50)
        if p[:2] == [0x00, lg.SW]:
            return [a50_reply([0x00, lg.SW, 0x06, 0x00, 0x04])]
        return [a50_reply([0x06, lg.SW, 0x64, 0x64, 0x01])]
    h = FakeDev(on_write=on)
    assert lg.read_a50(h, A50) == (100, True)
    assert h.writes[0][:8] == bytes([0x02, 0x0C, 0x05, 0x00, 0x00, 0x0A, 0x01, 0x04])
    assert h.writes[1][:6] == bytes([0x02, 0x0C, 0x03, 0x00, 0x06, 0x0A]) and len(h.writes[1]) == 64


def test_a50_descarta_evento_e_resposta_do_ghub():
    def on(d):
        p = lg.payload(d, lg.A50)
        if p[0] == 0:
            return [a50_reply([0x00, lg.SW, 0x06])]
        return [a50_reply([0x06, 0x00, 0x10, 0x10, 0x00]), a50_reply([0x06, 0x0B, 0x20, 0x20, 0x00]),
                a50_reply([0x06, lg.SW, 0x37, 0x37, 0x00])]
    assert lg.read_a50(FakeDev(on_write=on), A50) == (0x37, False)


def test_a50_sem_feature_indice_ruim_ou_mudo(monkeypatch):
    monkeypatch.setattr(lg, "xfer", instant)
    for idx in (0x00, 0xFF):
        h = FakeDev(on_write=lambda d, idx=idx: [a50_reply([0x00, lg.SW, idx])])
        assert lg.read_a50(h, A50) is None and len(h.writes) == 1
    h = FakeDev(on_write=lambda d: [a50_reply([0x00, lg.SW, 0x06])] if d[4] == 0 else [])
    assert lg.read_a50(h, A50) is None
    h = FakeDev(on_write=lambda d: [a50_reply([d[4], lg.SW, 0x06 if d[4] == 0 else 0xC8, 0, 0])])
    assert lg.read_a50(h, A50) is None  # % > 100


def g(p):
    return list(lg.frame(lg.G522, p))


BR, BAT = 0x03, 0x05


def g522_dev(battery=(0x2A, 0x2A, 0x02), noise=()):
    def on(d):
        p = lg.payload(d, lg.G522)
        if p[0] == 0x00:  # Root.getFeature(0x0003) no dongle
            return [g([0x00, lg.SW, BR, 0x00, 0x01])]
        inner = p[4:]
        ack = g([BR, 0x10 | lg.SW, 0x00, 0x00])
        if inner[1] == 0x00:  # Root.getFeature(0x0104) no fone
            return [ack, *noise, g([BR, 0x10, 0x00, 0x06, 0x00, 0x00, lg.SW, BAT, 0x00, 0x04])]
        return [ack, g([BR, 0x10, 0x00, 0x06, 0x00, BAT, lg.SW, *battery])]
    return FakeDev(on_write=on)


def test_g522_bridge_e_bateria():
    h = g522_dev()
    assert lg.read_g522(h, G522) == (0x2A, True)
    assert h.writes[1][:11] == bytes([0x50, 0x23, 0x0A, 0x00, BR, 0x1A, 0x00, 0x05, 0x00, 0x00, lg.SW])
    assert h.writes[2][:11] == bytes([0x50, 0x23, 0x08, 0x00, BR, 0x1A, 0x00, 0x03, 0x00, BAT, lg.SW])


def test_g522_so_funcao_0_dentro_e_fora_da_bridge():
    h = g522_dev()
    lg.read_g522(h, G522)
    for w in h.writes:
        p = lg.payload(w, lg.G522)
        if p[0] == 0x00:
            assert p[1] == lg.SW  # Root, função 0
        else:
            assert p[1] == 0x10 | lg.SW and p[5] in (0x00, BAT) and p[6] == lg.SW  # envio; dentro só função 0


def test_g522_evento_espontaneo_e_descartado():
    spont = g([BR, 0x10, 0x00, 0x06, 0x00, 0x09, 0x00, 0x33, 0x00, 0x00])  # outro índice, swId 0
    assert lg.read_g522(g522_dev(noise=[spont]), G522) == (0x2A, True)


def test_g522_so_evento_espontaneo_nao_manda_o_passo_3(monkeypatch):
    monkeypatch.setattr(lg, "xfer", instant)
    spont = g([BR, 0x10, 0x00, 0x06, 0x00, 0x09, 0x00, 0x33, 0x00, 0x00])

    def on(d):
        p = lg.payload(d, lg.G522)
        return [g([0x00, lg.SW, BR, 0, 1])] if p[0] == 0 else [g([BR, 0x1A, 0, 0]), spont]
    h = FakeDev(on_write=on)
    assert lg.read_g522(h, G522) is None and len(h.writes) == 2


def test_g522_fone_desligado():
    def on(d):
        p = lg.payload(d, lg.G522)
        return [g([0x00, lg.SW, BR, 0, 1])] if p[0] == 0 else [g([BR, 0x1A, 0, 0]), g([BR, 0x00, 0x00, 0x00])]
    assert lg.read_g522(FakeDev(on_write=on), G522) is None


def test_colecoes_e_nomes_distintos():
    assert {m.pid: (m.usage_page, m.usage) for m in lg.MODELS} == {
        0x0B1C: (0xFF32, 0x74), 0x0B0B: (0xFF32, 0x74), 0x0B18: (0xFFA0, 0x01)}
    assert len({m.name for m in lg.MODELS}) == 3
