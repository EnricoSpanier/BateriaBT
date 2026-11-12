from types import SimpleNamespace

import bateria_bt as b


def dev(name, conn=True):
    return {"name": name, "battery": 50, "connected": conn, "kind": "MOUSE", "charging": False, "hours": None}


def test_quatro_fontes_sem_duplicar():
    app = SimpleNamespace(sources={"bt": {"bt1": dev("Fone BT")},
                                   "vendor": {"vendor:1532:00ab:S": dev("Razer Basilisk V3 Pro")},
                                   "hid": {"logi:1": dev("G903", False)},
                                   "ghub": {"logi:1": dev("G903 LIGHTSPEED")}})
    out = b.App.devices.fget(app)
    assert sorted(out) == ["bt1", "logi:1", "vendor:1532:00ab:S"]
    assert out["logi:1"]["connected"] is True and out["vendor:1532:00ab:S"]["name"] == "Razer Basilisk V3 Pro"
