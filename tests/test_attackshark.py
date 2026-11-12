from vendors import attackshark as ak
from tests.fakes import FakeDev


def test_attackshark_escalas_e_piscada():
    h = FakeDev(replies=[[0x03, 0x55, 0x01, 0, 0], [0x03, 0x55, 0x40, 0x01, 64]])
    assert ak.read(h, ak.MODELS[0]) == (64, False, "Attack Shark X11")
    h = FakeDev(replies=[[0x03, 0x10, 0x40, 0x01, 0x0A]])
    assert ak.read(h, ak.MODELS[0]) == (100, False, "Attack Shark R1/X6")


def test_attackshark_silencio_e_modelo_desconhecido(monkeypatch):
    t = iter(range(0, 100))
    monkeypatch.setattr(ak.time, "monotonic", lambda: next(t))
    assert ak.read(FakeDev(replies=[[0x03, 0x99, 0x40, 1, 50]]), ak.MODELS[0]) is None
    assert not ak.MODELS[0].writes

