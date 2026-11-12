from vendors import hyperx as hx
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in hx.MODELS if x.pid == pid)


def test_alpha_wireless():
    resp = {0x03: [0x21, 0xBB, 0x03, 0x02], 0x0C: [0x21, 0xBB, 0x0C, 0x01], 0x0B: [0x21, 0xBB, 0x0B, 64]}
    h = FakeDev(on_write=lambda d: [resp[d[2]]])
    assert hx.read_alpha(h, m(0x098D)) == (64, True)
    assert all(len(w) == 31 for w in h.writes)


def test_alpha_wireless_desligado():
    h = FakeDev(on_write=lambda d: [[0x21, 0xBB, d[2], 0x01]])
    assert hx.read_alpha(h, m(0x098D)) is None


def test_cloud2_hp(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    def on(d):
        r = [0x06, 0xFF, 0xBB, d[3]] + [0] * 16
        r[7], r[4] = 81, (1 if d[3] == 0x03 else 0)
        return [[0x01, 0x02], r]  # um evento antes da resposta
    h = FakeDev(on_write=on)
    assert hx.read_cloud2_hp(h, m(0x0696)) == (81, True)
    assert len(h.writes[0]) == 52


def test_cloud2_kingston(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    def on(d):
        r = [0x0B, 0x00, 0xBB, d[15]] + [0] * 60
        r[7] = 45
        return [r]
    h = FakeDev(on_write=on)
    assert hx.read_cloud2_kingston(h, m(0x1718)) == (45, False)
    assert len(h.writes[0]) == 62 and h.writes[0][14] == 0xBB


def test_flight_curva():
    assert [hx.flight_pct(v) for v in (3600, 3700, 3800, 3900, 4000)] == [4, 16, 55, 82, 100]


def test_flight():
    h = FakeDev(on_write=lambda d: [[0x21, 0xFF, 0x05, 0x0E, 0xD8] + [0] * 15])  # 3800 mV
    assert hx.read_flight(h, m(0x16C4)) == (55, False)


def test_flight_carregando():
    h = FakeDev(on_write=lambda d: [[0x21, 0xFF, 0x05, 0x10, 0x10] + [0] * 15])  # 4112 mV
    assert hx.read_flight(h, m(0x1723)) == (100, True)


def test_alpha2():
    def on(d):
        if d[0] == 0x52:
            return [[0xFB, 0x01], [0x53, 0x01, 0x01]]
        return [[0x51, 0x02, 77, 0x00]]
    assert hx.read_alpha2(FakeDev(on_write=on), m(0x08BE)) == (77, False)


def test_sem_resposta_da_none(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    for read, pid in ((hx.read_alpha, 0x098D), (hx.read_cloud2_hp, 0x0696),
                      (hx.read_cloud2_kingston, 0x1718), (hx.read_flight, 0x16C4), (hx.read_alpha2, 0x08BE)):
        assert read(FakeDev(), m(pid)) is None


def test_alpha2_desligado():
    h = FakeDev(on_write=lambda d: [[0x53, 0x01, 0x00]])
    assert hx.read_alpha2(h, m(0x08BE)) is None
