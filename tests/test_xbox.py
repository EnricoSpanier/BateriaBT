from vendors import xbox


def fake_api(table):
    """table = {indice: (tipo, nivel)}; os outros índices respondem 'não conectado'."""
    def api(i, devtype, ref):
        if i not in table:
            return 1167  # ERROR_DEVICE_NOT_CONNECTED
        ref._obj.type, ref._obj.level = table[i]
        return 0
    return api


def test_controle_com_pilha():
    out = xbox.scan(fake_api({0: (2, 2)}))
    assert out == {"xinput:0": {"name": "Controle Xbox 1", "battery": 60, "connected": True,
                                "kind": "GAMEPAD", "charging": False, "hours": None}}


def test_com_fio_e_desconhecido_ficam_de_fora():
    assert xbox.scan(fake_api({0: (1, 3), 1: (0xFF, 3), 2: (0, 0)})) == {}


def test_niveis():
    out = xbox.scan(fake_api({i: (3, i) for i in range(4)}))
    assert [out[f"xinput:{i}"]["battery"] for i in range(4)] == [5, 30, 60, 99]


def test_sem_xinput_devolve_vazio(monkeypatch):
    monkeypatch.setattr(xbox, "_api", lambda: None)
    assert xbox.scan() == {}
