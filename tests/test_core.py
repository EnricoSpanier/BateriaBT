import pytest

import vendors
from vendors import Model, VendorReader, path_id, xfer
from tests.fakes import FakeDev, FakeHid, info


def ok_read(h, m):
    h.write(b"\x01")
    return (50, False)


def model(read=ok_read, **kw):
    base = dict(vid=0x1111, pid=0x2222, name="Teste", kind="HEADSET", read=read,
                usage_page=0xFF00, usage=0x01)
    return Model(**{**base, **kw})


def reader(devs, models):
    return VendorReader(models=models, scan_xbox=lambda: {}, hid_mod=FakeHid(devs))


def test_aceite1_so_a_colecao_declarada_recebe_write():
    a, b, c = FakeDev(), FakeDev(), FakeDev()
    devs = [(info(0x1111, 0x2222, 0x0001, 0x06, path=b"a"), a),
            (info(0x1111, 0x2222, 0x000C, 0x01, path=b"b"), b),
            (info(0x1111, 0x2222, 0xFF00, 0x01, path=b"c"), c)]
    reader(devs, [model()]).read_all()
    assert (a.writes, b.writes, c.writes) == ([], [], [b"\x01"])


def test_aceite1_modelo_que_escreve_sem_colecao_da_erro():
    with pytest.raises(ValueError):
        Model(0x1111, 0x2222, "X", "MOUSE", ok_read)


def test_aceite2_dois_aparelhos_iguais_sem_serie_viram_duas_entradas():
    r = VendorReader(models=[model(read=lambda h, m: (h.pct, False))], scan_xbox=lambda: {},
                     hid_mod=FakeHid([(info(0x1111, 0x2222, 0xFF00, 1, path=b"x1"), FakeDev()),
                                      (info(0x1111, 0x2222, 0xFF00, 1, path=b"x2"), FakeDev())]))
    r._hid.devices[0][1].pct, r._hid.devices[1][1].pct = 30, 80
    out = r.read_all()
    assert sorted(v["battery"] for v in out.values()) == [30, 80]


def test_aceite2_none_nao_apaga_leitura_valida_da_mesma_chave():
    calls = iter([(50, False), None])
    m = model(read=lambda h, mm: next(calls), interface=2, usage_page=None, usage=None)
    path_a = rb"\\?\HID#VID_1111&PID_2222&MI_02&Col01#7&abc&0&0000#{guid}"
    path_b = rb"\\?\HID#VID_1111&PID_2222&MI_02&Col02#7&abc&0&0001#{guid}"
    devs = [(info(0x1111, 0x2222, 0xFF00, 1, 2, path=path_a), FakeDev()),
            (info(0x1111, 0x2222, 0xFF01, 2, 2, path=path_b), FakeDev())]
    out = reader(devs, [m]).read_all()
    assert list(out.values()) == [{"name": "Teste", "battery": 50, "connected": True,
                                   "kind": "HEADSET", "charging": False, "hours": None}]


def test_aceite3_xfer_descarta_evento_e_pega_a_resposta():
    h = FakeDev(replies=[[0x01, 0x02, 0x00], [0x06, 0xFF, 0xBB, 0x02, 0, 0, 0, 77]])
    r = xfer(h, b"\x06", 20, lambda r: r[:4] == [0x06, 0xFF, 0xBB, 0x02], timeout=0.2)
    assert r[7] == 77


def test_aceite3_so_evento_da_none():
    h = FakeDev(replies=[[0x01, 0x02, 0x00]])
    assert xfer(h, b"\x06", 20, lambda r: r[:2] == [0x06, 0xFF], timeout=0.1) is None


def test_aceite5_logitech_nunca_e_aberta():
    d = FakeDev()
    devs = [(info(0x046D, 0xC547, 0xFF00, 0x01), d)]
    out = reader(devs, [model(vid=0x046D, pid=0xC547)]).read_all()
    assert out == {} and not d.opened


def test_aceite5_chave_comeca_com_vendor():
    out = reader([(info(0x1111, 0x2222, 0xFF00, 1, serial="S1"), FakeDev())], [model()]).read_all()
    assert list(out) == ["vendor:1111:2222:S1"]


def test_parou_de_responder_fica_desconectado_com_a_ultima():
    answers = iter([(40, True), None])
    r = reader([(info(0x1111, 0x2222, 0xFF00, 1, serial="S"), FakeDev())],
               [model(read=lambda h, m: next(answers))])
    r.read_all()
    out = r.read_all()
    assert out["vendor:1111:2222:S"]["battery"] == 40 and out["vendor:1111:2222:S"]["connected"] is False


def test_aparelho_removido_some():
    r = reader([(info(0x1111, 0x2222, 0xFF00, 1, serial="S"), FakeDev())], [model()])
    r.read_all()
    r._hid.devices = []
    assert r.read_all() == {}


def test_excecao_num_leitor_nao_derruba_os_outros():
    def boom(h, m):
        raise RuntimeError("falha")
    devs = [(info(0x1111, 0x2222, 0xFF00, 1, path=b"a", serial="A"), FakeDev()),
            (info(0x3333, 0x4444, 0xFF00, 1, path=b"b", serial="B"), FakeDev())]
    out = reader(devs, [model(read=boom), model(vid=0x3333, pid=0x4444)]).read_all()
    assert list(out) == ["vendor:3333:4444:B"]


def test_falha_ao_abrir_e_ignorada():
    out = reader([(info(0x1111, 0x2222, 0xFF00, 1), OSError("negado"))], [model()]).read_all()
    assert out == {}


def test_porcentagem_fora_da_faixa_e_descartada():
    out = reader([(info(0x1111, 0x2222, 0xFF00, 1), FakeDev())],
                 [model(read=lambda h, m: (180, False))]).read_all()
    assert out == {}


def test_xbox_desligado_fica_desconectado():
    scans = iter([{"xinput:0": {"name": "Controle Xbox 1", "battery": 60, "connected": True,
                                "kind": "GAMEPAD", "charging": False, "hours": None}}, {}])
    r = VendorReader(models=[], scan_xbox=lambda: next(scans), hid_mod=FakeHid([]))
    r.read_all()
    assert r.read_all()["xinput:0"]["connected"] is False


def test_path_id_ignora_a_colecao_no_caminho():
    a = info(1, 2, path=rb"\\?\HID#VID_0001&PID_0002&MI_03&Col01#8&1f&0&0000#{g}")
    b = info(1, 2, path=rb"\\?\HID#VID_0001&PID_0002&MI_03&Col02#8&1f&0&0001#{g}")
    assert path_id(a) == path_id(b)


def test_achado1_so_interface_nao_escreve_em_colecao_padrao():
    consumer, vendor = FakeDev(), FakeDev()
    devs = [(info(0x1111, 0x2222, 0x000C, 1, 3, path=b"c"), consumer),
            (info(0x1111, 0x2222, 0xFFC0, 1, 3, path=b"v"), vendor)]
    m = model(read=lambda h, mm: h.write(b"\x01") and None, usage_page=None, usage=None, interface=3)
    reader(devs, [m]).read_all()
    assert consumer.writes == [] and vendor.writes == [b"\x01"]


def test_achado3_sem_serie_trocar_de_porta_mantem_a_chave():
    r = reader([(info(0x1111, 0x2222, 0xFF00, 1, path=b"porta-A"), FakeDev())], [model()])
    k1 = list(r.read_all())
    r._hid.devices = [(info(0x1111, 0x2222, 0xFF00, 1, path=b"porta-B"), FakeDev())]
    assert list(r.read_all()) == k1 == ["vendor:1111:2222:0"]


def test_achado4_cabo_e_receptor_do_mesmo_mouse_viram_uma_chave():
    cabo, receptor = model(pid=0x2222), model(pid=0x2223, read=lambda h, m: None)
    devs = [(info(0x1111, 0x2222, 0xFF00, 1, path=b"cabo"), FakeDev()),
            (info(0x1111, 0x2223, 0xFF00, 1, path=b"rx"), FakeDev())]
    out = reader(devs, [cabo, receptor]).read_all()
    assert list(out) == ["vendor:1111:2222:0"] and out["vendor:1111:2222:0"]["connected"] is True


def test_sem_hidapi_xbox_continua():
    class NoHid:
        def enumerate(self):
            raise OSError("hidapi ausente")
    xb = {"xinput:0": {"name": "Controle Xbox 1", "battery": 60, "connected": True,
                       "kind": "GAMEPAD", "charging": False, "hours": None}}
    assert list(VendorReader(models=[], scan_xbox=lambda: xb, hid_mod=NoHid()).read_all()) == ["xinput:0"]


def test_models_do_pacote_nao_tem_logitech_nem_duplicata():
    keys = [(m.vid, m.pid, m.usage_page, m.usage, m.interface) for m in vendors.MODELS]
    assert len(keys) == len(set(keys)) and all(m.vid != 0x046D for m in vendors.MODELS)


def test_usage_page_sem_usage_casa_qualquer_usage():
    d = FakeDev()
    devs = [(info(0x1111, 0x2222, 0xFF42, 0x07, 1), d)]
    out = reader(devs, [model(usage_page=0xFF42, usage=None, interface=1)]).read_all()
    assert d.writes == [b"\x01"] and len(out) == 1


def test_leitor_de_receptor_informa_nome_e_tipo_do_pareado():
    m = model(read=lambda h, mm: (40, False, "Teclado X", "KEYBOARD"))
    out = reader([(info(0x1111, 0x2222, 0xFF00, 1, serial="S"), FakeDev())], [m]).read_all()
    assert out["vendor:1111:2222:S"]["name"] == "Teclado X" and out["vendor:1111:2222:S"]["kind"] == "KEYBOARD"


def test_mesmo_pid_com_aparelhos_diferentes_nao_colidem():
    a = model(name="Mouse (receptor)", usage_page=0xFF01)
    b = model(name="Teclado (receptor)", usage_page=0xFF00)
    devs = [(info(0x1111, 0x2222, 0xFF01, 1, 2, path=b"c3", serial="S"), FakeDev()),
            (info(0x1111, 0x2222, 0xFF00, 1, 2, path=b"c2", serial="S"), FakeDev())]
    assert sorted(reader(devs, [a, b]).read_all()) == ["vendor:1111:2222:S:0", "vendor:1111:2222:S:1"]
