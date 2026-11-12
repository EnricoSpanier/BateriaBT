from vendors import glorious as gl
from tests.fakes import FakeDev

M = gl.MODELS[0]


def test_le_bateria(monkeypatch):
    monkeypatch.setattr(gl.time, "sleep", lambda s: None)
    h = FakeDev(on_write=lambda d: [[0x00, 0xA1, 0, 0, 0, 0, 0x83, 1, 66]])
    assert gl.read(h, M) == (66, True)
    assert h.features[0][:7] == bytes([0x00, 0x00, 0x00, 0x02, 0x02, 0x00, 0x83]) and len(h.features[0]) == 65


def test_mouse_fora_de_alcance_da_none(monkeypatch):
    monkeypatch.setattr(gl.time, "sleep", lambda s: None)
    assert gl.read(FakeDev(on_write=lambda d: [[0x00, 0xA4, 0, 0, 0, 0, 0x83, 0, 66]]), M) is None


def test_sem_eco_do_opcode_da_none(monkeypatch):
    monkeypatch.setattr(gl.time, "sleep", lambda s: None)
    assert gl.read(FakeDev(on_write=lambda d: [[0x00, 0xA1, 0, 0, 0, 0, 0x82, 0, 66]]), M) is None
    assert gl.read(FakeDev(), M) is None
