# Outras marcas (lote 1) — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ler a bateria de periféricos Razer, SteelSeries, HyperX, Corsair, PlayStation e Xbox e mostrá-los no Bateria BT, com as mesmas regras de conectado/desconectado da Logitech.

**Architecture:** um pacote `vendors/`, com um arquivo por marca. O `vendors/__init__.py` traz o `Model`, os auxiliares de troca de mensagens e o `VendorReader`, que varre o `hid.enumerate()` numa thread igual ao `HidppReader`. No `bateria_bt.py` ele entra como a fonte `"vendor"`.

**Tech Stack:** Python 3.12, PySide6, `hidapi` (`import hid`), `ctypes` (XInput), `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-12-outras-marcas-design.md`

## Global Constraints

- Código próprio, a partir de protocolos públicos (HeadsetControl, OpenRazer, rivalcfg, hid-playstation do Linux). Nada vem do executável do app original.
- Entradas com vid `0x046D` (Logitech) nunca são abertas pela fonte vendor.
- Chave: `vendor:<vid 4 hex>:<pid 4 hex>:<serial ou hash>`. Controles Xbox usam `xinput:<n>`.
- Todo `Model` com `writes=True` declara a coleção: `usage_page`/`usage` e/ou `interface`. Senão dá `ValueError` no import.
- `read` só aceita a resposta que o protocolo permite validar (report ID, eco do comando, tamanho, faixa). Todo o resto é descartado até o tempo limite.
- `playstation.py` não chama `write`, `send_feature_report` nem `get_feature_report`.
- Tempo limite padrão de cada troca: 0,5 s.
- Um leitor que falha (`None` ou exceção) afeta só o próprio aparelho, e o erro vai para `stderr`.
- Nenhuma dependência nova: `hidapi` já está no `requirements.txt`.
- Comentários e textos de interface em PT-BR.

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `vendors/__init__.py` | `Model`, `pad`, `flush`, `xfer`, `device_key`, `VendorReader`, `MODELS` (junta as marcas) |
| `vendors/razer.py` | mouses Razer (feature report de 90 bytes, OpenRazer) |
| `vendors/steelseries.py` | headsets Arctis/Nova, mouses Aerox e Rival (HeadsetControl, rivalcfg) |
| `vendors/hyperx.py` | Cloud Alpha Wireless, Cloud II Wireless (HP e Kingston), Cloud Flight, Cloud Alpha 2 (HeadsetControl) |
| `vendors/corsair.py` | Void/HS70, Void V2/Virtuoso MAX/HS80 MAX, Virtuoso XT/SE (HeadsetControl) |
| `vendors/playstation.py` | DualSense e DS4, só leitura de input report (hid-playstation) |
| `vendors/xbox.py` | `scan()` via XInput |
| `bateria_bt.py` | fonte `"vendor"` no `App` |
| `pytest.ini`, `tests/fakes.py`, `tests/test_*.py` | testes com aparelhos falsos |

## O que ficou fora do lote 1 (decidido na pesquisa)

| Fora | Por quê |
|---|---|
| Headset Razer BlackShark V2 Pro PS | Para ler a bateria, troca o modo do receptor (`E1 01`) e precisa voltar depois. É escrita de estado, que a spec evita. |
| Arctis 9, Arctis Pro Wireless, Nova 7P | Protocolo só por paráfrase, ou conflito na fonte. |
| Cloud III Wireless, Cloud Flight S, Stinger 2, HS55, HS75 XB, Virtuoso original | Sem protocolo público. |
| Mouses Corsair (Bragi) | Já estavam fora na spec. |

---

### Task 0: Controle de versão

A pasta ainda não é um repositório git. Cada task termina com um commit, então rode o passo abaixo antes de começar. Só faça isso com o OK do Enrico.

- [ ] **Step 1:** `git init` e commit inicial do estado atual

```bash
cd E:/Proj/BateriaBT
git init
printf '__pycache__/\n*.pyc\n.pytest_cache/\n' > .gitignore
git add .
git commit -m "chore: estado inicial do Bateria BT"
```

---

### Task 1: Núcleo `vendors/` (Model, troca de mensagens, VendorReader)

**Files:**
- Create: `vendors/__init__.py`
- Create: `pytest.ini`
- Create: `tests/fakes.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces:
  - `Model(vid, pid, name, kind, read, usage_page=None, usage=None, interface=None, writes=True)`, com `matches(info) -> bool`.
  - `read(h, model) -> (pct:int, charging:bool) | None`.
  - `pad(data, n) -> bytes`.
  - `flush(h) -> None`.
  - `xfer(h, out: bytes, n: int, ok: Callable[[list], bool], timeout=0.5, wait=0.0) -> list | None`.
  - `device_key(info) -> str`.
  - `VendorReader(models=None, scan_xbox=None, hid_mod=None)`, com `done = Signal(dict)`, `refresh()` e `read_all() -> dict`.
  - `MODELS: list[Model]`.
- O formato de cada leitura é `{"name", "battery", "connected", "kind", "charging", "hours": None}`.

- [ ] **Step 1: Configuração do pytest e fakes**

`pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

`tests/fakes.py`:
```python
"""Aparelhos HID falsos: respondem com bytes de protocolo público e registram o que receberam."""


def info(vid, pid, usage_page=0, usage=0, interface=0, path=b"p0", serial=""):
    return {"vendor_id": vid, "product_id": pid, "usage_page": usage_page, "usage": usage,
            "interface_number": interface, "path": path, "serial_number": serial,
            "product_string": "", "manufacturer_string": ""}


class FakeDev:
    """`on_write(bytes) -> list[list[int]]` decide as respostas de cada envio; `replies` já fica na fila."""

    def __init__(self, on_write=None, replies=None):
        self.on_write, self.q = on_write, [list(r) for r in (replies or [])]
        self.writes, self.features, self.feature_gets, self.opened = [], [], 0, False

    def open_path(self, path):
        self.opened = True

    def close(self):
        pass

    def write(self, data):
        self.writes.append(bytes(data))
        if self.on_write:
            self.q += [list(r) for r in self.on_write(bytes(data))]
        return len(data)

    def send_feature_report(self, data):
        self.features.append(bytes(data))
        if self.on_write:
            self.q += [list(r) for r in self.on_write(bytes(data))]
        return len(data)

    def get_feature_report(self, report_id, length):
        self.feature_gets += 1
        return self.q.pop(0) if self.q else []

    def get_input_report(self, report_id, length):
        return []

    def read(self, n, timeout_ms=0):
        return self.q.pop(0)[:n] if self.q else []


class FakeHid:
    """Substitui o módulo `hid`: `devices` = lista de (info, FakeDev | Exception)."""

    def __init__(self, devices):
        self.devices = devices

    def enumerate(self, vid=0, pid=0):
        return [i for i, _ in self.devices]

    def device(self):
        hid = self

        class Proxy:
            def open_path(self, path):
                dev = next(d for i, d in hid.devices if i["path"] == path)
                if isinstance(dev, Exception):
                    raise dev
                self.dev = dev
                dev.open_path(path)

            def __getattr__(self, name):
                return getattr(self.__dict__["dev"], name)
        return Proxy()
```

- [ ] **Step 2: Escrever os testes do núcleo (falham)**

`tests/test_core.py`:
```python
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
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `python -m pytest tests/test_core.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'vendors'`

- [ ] **Step 4: Implementar `vendors/__init__.py`**

```python
"""Bateria de periféricos de outras marcas (não Logitech) por HID.

Código próprio a partir de protocolos públicos: HeadsetControl, OpenRazer, rivalcfg e o driver
hid-playstation do Linux. Cada marca fica no seu arquivo e exporta MODELS (e o xbox, scan()).
"""
import hashlib
import importlib
import re
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

LOGITECH = 0x046D  # tem leitor próprio (HID++ e G HUB): nunca abrimos aqui


@dataclass(frozen=True)
class Model:
    vid: int
    pid: int
    name: str
    kind: str                       # MOUSE / KEYBOARD / HEADSET / GAMEPAD
    read: Callable                  # read(h, model) -> (pct, charging) | None
    usage_page: Optional[int] = None
    usage: Optional[int] = None
    interface: Optional[int] = None
    writes: bool = True             # envia comando ao aparelho?

    def __post_init__(self):
        if self.writes and self.usage_page is None and self.interface is None:
            raise ValueError(f"{self.name}: modelo que envia comando precisa declarar a coleção HID")

    def matches(self, info):
        if (info["vendor_id"], info["product_id"]) != (self.vid, self.pid):
            return False
        if self.usage_page is not None:
            if (info["usage_page"], info["usage"]) != (self.usage_page, self.usage):
                return False
        elif self.writes and info["usage_page"] < 0xFF00:
            return False  # só a interface foi declarada: escreve apenas na coleção do fabricante
        return self.interface is None or info["interface_number"] == self.interface


def pad(data, n):
    return bytes(data).ljust(n, b"\0")


def flush(h):
    """Descarta respostas antigas que ficaram na fila."""
    for _ in range(32):
        if not h.read(64, 5):
            return


def xfer(h, out, n, ok, timeout=0.5, wait=0.0):
    """Envia `out` e devolve a primeira resposta em que ok(r) é verdade. Descarta eventos e respostas
    a outros programas (iCUE, Synapse, GG...). None se nada válido chegar no tempo."""
    h.write(out)
    if wait:
        time.sleep(wait)
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        r = h.read(n, max(1, int(left * 1000)))
        if r and ok(r):
            return r
    return None


def path_id(info):
    """Identifica o aparelho físico: o caminho HID sem a parte da coleção, para as coleções de um
    mesmo aparelho darem o mesmo id."""
    path = info["path"].decode(errors="replace").lower() if isinstance(info["path"], bytes) else str(info["path"])
    path = re.sub(r"&col[0-9a-f]+", "", path)
    path = re.sub(r"&[0-9a-f]{4}(?=#)", "", path)
    return hashlib.sha1(path.encode()).hexdigest()[:8]


def device_keys(matched, models):
    """Chave de cada entrada: vendor:<vid>:<grupo>:<série ou ordem>.
    - grupo = menor PID com o mesmo nome na mesma marca: cabo e receptor do mesmo mouse dão a mesma chave;
    - sem série, usa a ordem (0, 1...) entre os aparelhos iguais, e não o caminho: trocar de porta USB
      não cria outro aparelho, e dois aparelhos iguais ainda dão chaves diferentes."""
    order = {}
    for info, _ in sorted(matched, key=lambda x: path_id(x[0])):
        if not (info.get("serial_number") or "").strip():
            ids = order.setdefault((info["vendor_id"], info["product_id"]), [])
            if path_id(info) not in ids:
                ids.append(path_id(info))
    keys = []
    for info, m in matched:
        serial = (info.get("serial_number") or "").strip()
        tail = serial or str(order[(info["vendor_id"], info["product_id"])].index(path_id(info)))
        group = min(x.pid for x in models if x.vid == m.vid and x.name == m.name)
        keys.append(f"vendor:{m.vid:04x}:{group:04x}:{tail}")
    return keys


class VendorReader(QObject):
    """Mesmas regras do leitor HID++: quem não responde fica desconectado com a última %, e o
    aparelho removido some."""
    done = Signal(dict)

    def __init__(self, models=None, scan_xbox=None, hid_mod=None):
        super().__init__()
        self.models = MODELS if models is None else models
        self.scan_xbox = scan_xbox if scan_xbox is not None else _xbox_scan
        self._hid = hid_mod
        self.last = {}
        self._busy = False

    def refresh(self):
        if self._busy:
            return
        self._busy = True

        def run():
            try:
                self.done.emit(self.read_all())
            except Exception as e:  # sem hidapi ou falha geral: mantém o último estado
                print("erro vendor:", e, file=sys.stderr)
            finally:
                self._busy = False
        threading.Thread(target=run, daemon=True).start()

    def read_all(self):
        present, valid = set(), {}
        try:
            hid = self._hid or importlib.import_module("hid")
            infos = hid.enumerate()
        except Exception as e:  # sem hidapi: só os controles Xbox
            print("erro hidapi:", e, file=sys.stderr)
            hid, infos = None, []
        matched = [(i, m) for i in infos if i["vendor_id"] != LOGITECH
                   for m in [next((m for m in self.models if m.matches(i)), None)] if m]
        for (info, m), key in zip(matched, device_keys(matched, self.models)):
            present.add(key)
            if key in valid:  # outra coleção do mesmo aparelho já respondeu neste ciclo
                continue
            r = self._read_one(hid, info, m)
            if r:
                valid[key] = {"name": m.name, "battery": r[0], "connected": True, "kind": m.kind,
                              "charging": r[1], "hours": None}
        try:
            valid.update(self.scan_xbox())
        except Exception as e:
            print("erro xinput:", e, file=sys.stderr)
        # receptor removido some; o controle Xbox desligado fica como desconectado
        self.last = {k: v for k, v in self.last.items() if k in present or k.startswith("xinput:")}
        self.last.update(valid)
        return {k: {**v, "connected": k in valid} for k, v in self.last.items()}

    @staticmethod
    def _read_one(hid, info, m):
        h = hid.device()
        try:
            h.open_path(info["path"])
        except OSError:
            return None
        try:
            r = m.read(h, m)
            if r and 0 <= r[0] <= 100:
                return int(r[0]), bool(r[1])
        except Exception as e:
            print(f"erro {m.name}:", e, file=sys.stderr)
        finally:
            h.close()
        return None


def _xbox_scan():
    from . import xbox
    return xbox.scan()


def _all_models():
    from . import corsair, hyperx, playstation, razer, steelseries
    return [*razer.MODELS, *steelseries.MODELS, *hyperx.MODELS, *corsair.MODELS, *playstation.MODELS]


MODELS = []  # preenchido abaixo, depois de Model existir (as marcas importam Model daqui)
MODELS.extend(_all_models())
```

Nesta task as marcas ainda não existem. Para os testes rodarem, crie os 5 arquivos de marca só com `MODELS = []` e o `xbox.py` com `def scan(): return {}`. As tasks 2 a 7 preenchem esses arquivos.

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add pytest.ini vendors tests
git commit -m "feat(vendors): núcleo com Model, xfer e VendorReader"
```

---

### Task 2: Razer (mouses)

**Files:**
- Modify: `vendors/razer.py`
- Test: `tests/test_razer.py`

**Interfaces:**
- Consumes: `Model` de `vendors`.
- Produces: `MODELS`, `crc(report: bytes) -> int`, `request(tid, cls, cmd, size=2) -> bytearray`, `read(h, m)`.

Protocolo (OpenRazer `razercommon.h/.c`, `razermouse_driver.c/.h`):
- **Report:** 90 bytes, report ID 0 (91 bytes no hidapi, com o `0x00` na frente). Campos: `[0]` status, `[1]` transaction_id, `[5]` data_size, `[6]` class, `[7]` id, `[8..87]` args, `[88]` CRC.
- **CRC:** XOR dos bytes `[2..87]`.
- **Nível:** class `0x07`, id `0x80`, nível em `[9]`, escala 0–255.
- **Carregando:** id `0x84`, `[9] == 1`.
- **Status:** `0x02` = ok, `0x01` = ocupado (tenta de novo). Qualquer outro valor é falha.
- **Espera:** 60 ms; Atheris e Orochi V2 precisam de 400 ms.
- **Coleção:** interface 0, usage `0x01/0x02`.

- [ ] **Step 1: Testes (falham)**

`tests/test_razer.py`:
```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_razer.py -q`
Expected: FAIL (`AttributeError: module 'vendors.razer' has no attribute 'crc'`)

- [ ] **Step 3: Implementar `vendors/razer.py`**

```python
"""Mouses Razer sem fio: feature report de 90 bytes (protocolo documentado pelo OpenRazer)."""
import time

from . import Model

VID = 0x1532

# pid: (nome, transaction_id). Fonte: OpenRazer razermouse_driver.h/.c (razer_attr_read_charge_level).
DEVICES = {
    0x001F: ("Razer Naga Epic", 0xFF), 0x0024: ("Razer Mamba", 0xFF), 0x0025: ("Razer Mamba", 0xFF),
    0x0032: ("Razer Ouroboros", 0xFF), 0x003E: ("Razer Naga Epic Chroma", 0xFF),
    0x003F: ("Razer Naga Epic Chroma", 0xFF), 0x0044: ("Razer Mamba Chroma", 0xFF),
    0x0045: ("Razer Mamba Chroma", 0xFF), 0x007A: ("Razer Viper Ultimate", 0xFF),
    0x007B: ("Razer Viper Ultimate", 0xFF), 0x0083: ("Razer Basilisk X HyperSpeed", 0xFF),
    0x0059: ("Razer Lancehead", 0x3F), 0x005A: ("Razer Lancehead", 0x3F),
    0x0072: ("Razer Mamba Wireless", 0x3F), 0x0073: ("Razer Mamba Wireless", 0x3F),
    0x007C: ("Razer DeathAdder V2 Pro", 0x3F), 0x007D: ("Razer DeathAdder V2 Pro", 0x3F),
    0x0062: ("Razer Atheris", 0x1F), 0x006F: ("Razer Lancehead Wireless", 0x1F),
    0x0070: ("Razer Lancehead Wireless", 0x1F), 0x0077: ("Razer Pro Click", 0x1F),
    0x0080: ("Razer Pro Click", 0x1F), 0x0086: ("Razer Basilisk Ultimate", 0x1F),
    0x0088: ("Razer Basilisk Ultimate", 0x1F), 0x008F: ("Razer Naga Pro", 0x1F),
    0x0090: ("Razer Naga Pro", 0x1F), 0x0094: ("Razer Orochi V2", 0x1F),
    0x0095: ("Razer Orochi V2", 0x1F), 0x009A: ("Razer Pro Click Mini", 0x1F),
    0x009C: ("Razer DeathAdder V2 X HyperSpeed", 0x1F), 0x009E: ("Razer Viper Mini SE", 0x1F),
    0x009F: ("Razer Viper Mini SE", 0x1F), 0x00A5: ("Razer Viper V2 Pro", 0x1F),
    0x00A6: ("Razer Viper V2 Pro", 0x1F), 0x00A7: ("Razer Naga V2 Pro", 0x1F),
    0x00A8: ("Razer Naga V2 Pro", 0x1F), 0x00AA: ("Razer Basilisk V3 Pro", 0x1F),
    0x00AB: ("Razer Basilisk V3 Pro", 0x1F), 0x00AF: ("Razer Cobra Pro", 0x1F),
    0x00B0: ("Razer Cobra Pro", 0x1F), 0x00B3: ("Razer HyperPolling Wireless Dongle", 0x1F),
    0x00B4: ("Razer Naga V2 HyperSpeed", 0x1F), 0x00B6: ("Razer DeathAdder V3 Pro", 0x1F),
    0x00B7: ("Razer DeathAdder V3 Pro", 0x1F), 0x00B8: ("Razer Viper V3 HyperSpeed", 0x1F),
    0x00B9: ("Razer Basilisk V3 X HyperSpeed", 0x1F), 0x00BE: ("Razer DeathAdder V4 Pro", 0x1F),
    0x00BF: ("Razer DeathAdder V4 Pro", 0x1F), 0x00C0: ("Razer Viper V3 Pro", 0x1F),
    0x00C1: ("Razer Viper V3 Pro", 0x1F), 0x00C2: ("Razer DeathAdder V3 Pro", 0x1F),
    0x00C3: ("Razer DeathAdder V3 Pro", 0x1F), 0x00C4: ("Razer DeathAdder V3 HyperSpeed", 0x1F),
    0x00C5: ("Razer DeathAdder V3 HyperSpeed", 0x1F), 0x00C7: ("Razer Pro Click V2 Vertical", 0x1F),
    0x00C8: ("Razer Pro Click V2 Vertical", 0x1F), 0x00CC: ("Razer Basilisk V3 Pro 35K", 0x1F),
    0x00CD: ("Razer Basilisk V3 Pro 35K", 0x1F), 0x00D0: ("Razer Pro Click V2", 0x1F),
    0x00D1: ("Razer Pro Click V2", 0x1F), 0x00D3: ("Razer Basilisk Mobile", 0x1F),
    0x00D4: ("Razer Basilisk Mobile", 0x1F), 0x00D6: ("Razer Basilisk V3 Pro 35K Phantom Green", 0x1F),
    0x00D7: ("Razer Basilisk V3 Pro 35K Phantom Green", 0x1F), 0x00DA: ("Razer Cobra HyperSpeed", 0x1F),
    0x00DB: ("Razer Cobra HyperSpeed", 0x1F), 0x00DE: ("Razer Viper V3 Pro SE", 0x1F),
    0x00DF: ("Razer Viper V3 Pro SE", 0x1F),
}
SLOW = {0x0062, 0x0094, 0x0095}  # receptor do Atheris/Orochi V2: 400 ms
NO_CHARGE = {0x0062, 0x0083, 0x0094, 0x0095, 0x009C, 0x00B4, 0x00B8, 0x00B9, 0x00D3, 0x00D4}  # pilha AA


def crc(report):
    x = 0
    for b in report[2:88]:
        x ^= b
    return x


def request(tid, cls, cmd, size=0x02):
    r = bytearray(90)
    r[1], r[5], r[6], r[7] = tid, size, cls, cmd
    r[88] = crc(r)
    return r


def _query(h, tid, cls, cmd, wait):
    for _ in range(3):
        h.send_feature_report(b"\0" + bytes(request(tid, cls, cmd)))
        time.sleep(wait)
        r = bytes(h.get_feature_report(0, 91))[1:]  # o hidapi devolve o report ID na frente
        if len(r) < 90 or r[6] != cls or r[7] != cmd:
            return None
        if r[0] == 0x02:
            return r
        if r[0] != 0x01:  # 0x01 = ocupado: tenta de novo; o resto é falha/sem resposta/não suportado
            return None
    return None


def read(h, m):
    tid, wait = DEVICES[m.pid][1], (0.4 if m.pid in SLOW else 0.06)
    r = _query(h, tid, 0x07, 0x80, wait)
    if not r:
        return None
    charging = False
    if m.pid not in NO_CHARGE:
        c = _query(h, tid, 0x07, 0x84, wait)
        charging = bool(c and c[9] == 1)
    return round(r[9] * 100 / 255), charging


MODELS = [Model(VID, pid, name, "MOUSE", read, usage_page=0x01, usage=0x02, interface=0)
          for pid, (name, _) in DEVICES.items()]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_razer.py tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/razer.py tests/test_razer.py
git commit -m "feat(vendors): mouses Razer"
```

---

### Task 3: SteelSeries (headsets Arctis/Nova, mouses Aerox e Rival)

**Files:**
- Modify: `vendors/steelseries.py`
- Test: `tests/test_steelseries.py`

**Interfaces:**
- Consumes: `Model`, `pad`, `xfer` de `vendors`.
- Produces: `MODELS` e os leitores `read_nova7`, `read_7plus`, `read_nova35`, `read_novapro`, `read_arctis1`, `read_arctis7`, `read_aerox`, `read_rival`.

Protocolo (HeadsetControl `lib/devices/steelseries_*.hpp` e `protocols/steelseries_protocol.hpp`; rivalcfg `rivalcfg/devices/*.py`):

| Grupo | Pedido | Coleção | Resposta |
|---|---|---|---|
| Nova 7 | `00 B0` | `0xFFC0/0x01`, interface 3 | `[3]==0` desligado; `[3]` em (1, 2) carregando; nível `[2]` (PIDs "discretos": 0–4 × 25) |
| Arctis 7+ | `00 B0` | idem | `[1]==1` desligado; `[3]==1` carregando; nível 0–4 em `[2]` |
| Nova 3P/3X | `00 B0` | idem | `[1]==2` desligado; `[4]==1` carregando; nível `[3]`; mínimo de 5 bytes |
| Nova 5/5X | `00 B0` | idem | igual à Nova 3P/3X, mínimo de 16 bytes |
| Nova Pro | `06 B0` (31 bytes) | interface 4 | mínimo de 16 bytes; nível 0–8 em `[6]`; `[15]==1` desligado, `[15]==2` carregando |
| Arctis 1/7X/7P antigo | `06 12` | `0xFF43/0x0202`, interface 3 | `[2]==1` desligado; nível `[3]` |
| Arctis 7/Pro | `06 18` | `0xFF43/0x0202`, interface 5 | nível `[2]` |
| Aerox | `00 92` no cabo, `00 D2` no receptor; espera 50 ms | interface 3 | nível = `((b & 0x7F) - 1) * 5` com `b = [1]`; bit 7 = carregando |
| Rival 3 / 650 | `00 AA 01`; espera 50 ms | interface 3 (Rival 650: 0) | nível `[0]`, carregando `[2]` |

- [ ] **Step 1: Testes (falham)**

`tests/test_steelseries.py`:
```python
from vendors import steelseries as ss
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in ss.MODELS if x.pid == pid)


def answer(resp):
    return FakeDev(on_write=lambda d: [resp])


def test_nova7_porcentagem_direta():
    assert ss.read_nova7(answer([0x00, 0x00, 73, 0x01]), m(0x2258)) == (73, True)


def test_nova7_discreto_0_a_4():
    assert ss.read_nova7(answer([0x00, 0x00, 3, 0x03]), m(0x2202)) == (75, False)


def test_nova7_desligado():
    assert ss.read_nova7(answer([0x00, 0x00, 50, 0x00]), m(0x2258)) is None


def test_nova7_envia_00_b0():
    h = answer([0x00, 0x00, 50, 0x03])
    ss.read_nova7(h, m(0x2258))
    assert h.writes == [b"\x00\xb0"]


def test_7plus():
    assert ss.read_7plus(answer([0, 0x00, 2, 0x01]), m(0x220E)) == (50, True)
    assert ss.read_7plus(answer([0, 0x01, 2, 0x00]), m(0x220E)) is None


def test_nova3p_e_nova5():
    assert ss.read_nova35(answer([0, 0x00, 0, 64, 0x00]), m(0x2269)) == (64, False)
    assert ss.read_nova35(answer([0, 0x02, 0, 64, 0x00]), m(0x2269)) is None
    assert ss.read_nova35(answer([0, 0x00, 0, 90, 0x01] + [0] * 11), m(0x2232)) == (90, True)
    assert ss.read_nova35(answer([0, 0x00, 0, 90, 0x01]), m(0x2232)) is None  # Nova 5 exige 16 bytes


def test_nova_pro():
    r = [0] * 16
    r[6], r[15] = 4, 0x02
    assert ss.read_novapro(answer(r), m(0x12E0)) == (50, True)
    r[15] = 0x01
    assert ss.read_novapro(answer(r), m(0x12E0)) is None


def test_arctis1_e_arctis7():
    assert ss.read_arctis1(answer([0, 0, 0x00, 80, 0, 0, 0, 0]), m(0x12B3)) == (80, False)
    assert ss.read_arctis1(answer([0, 0, 0x01, 80, 0, 0, 0, 0]), m(0x12B3)) is None
    assert ss.read_arctis7(answer([0, 0, 66, 0, 0, 0, 0, 0]), m(0x1260)) == (66, False)


def test_aerox_cabo_e_receptor(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    h = answer([0x00, 0x80 | 15])
    assert ss.read_aerox(h, m(0x183A)) == (70, True) and h.writes == [b"\x00\x92"]
    h = answer([0x00, 21])
    assert ss.read_aerox(h, m(0x1838)) == (100, False) and h.writes == [b"\x00\xd2"]


def test_aerox_fora_da_faixa_da_none(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    assert ss.read_aerox(answer([0x00, 0x00]), m(0x183A)) is None


def test_rival(monkeypatch):
    monkeypatch.setattr("vendors.time.sleep", lambda s: None)
    assert ss.read_rival(answer([55, 0, 1]), m(0x1830)) == (55, True)


def test_sem_resposta_da_none():
    assert ss.read_nova7(FakeDev(), m(0x2258)) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_steelseries.py -q`
Expected: FAIL (`StopIteration`/`AttributeError`: `MODELS` vazio, leitores inexistentes)

- [ ] **Step 3: Implementar `vendors/steelseries.py`**

```python
"""SteelSeries: headsets Arctis/Nova (HeadsetControl) e mouses Aerox/Rival sem fio (rivalcfg)."""
from . import Model, pad, xfer

VID = 0x1038
NOVA = dict(usage_page=0xFFC0, usage=0x0001, interface=3)
LEGACY3 = dict(usage_page=0xFF43, usage=0x0202, interface=3)
LEGACY5 = dict(usage_page=0xFF43, usage=0x0202, interface=5)


def _map(v, lo, hi):
    return max(0, min(100, round((v - lo) * 100 / (hi - lo))))


def _nova(h, n):
    return xfer(h, bytes([0x00, 0xB0]), 128, lambda r: len(r) >= n)


NOVA7_DISCRETE = {0x2202, 0x2206, 0x223A, 0x227A, 0x22A4}


def read_nova7(h, m):
    r = _nova(h, 4)
    if not r or r[3] == 0x00:
        return None
    return min(100, r[2] * 25 if m.pid in NOVA7_DISCRETE else r[2]), r[3] in (0x01, 0x02)


def read_7plus(h, m):
    r = _nova(h, 4)
    if not r or r[1] == 0x01:
        return None
    return _map(r[2], 0, 4), r[3] == 0x01


NOVA5 = {0x2232, 0x2253}


def read_nova35(h, m):
    r = _nova(h, 16 if m.pid in NOVA5 else 5)
    if not r or r[1] == 0x02:
        return None
    return r[3], r[4] == 0x01


def read_novapro(h, m):
    r = xfer(h, pad([0x06, 0xB0], 31), 128, lambda r: len(r) >= 16)
    if not r or r[15] == 0x01:
        return None
    return _map(r[6], 0, 8), r[15] == 0x02


def read_arctis1(h, m):
    r = xfer(h, bytes([0x06, 0x12]), 8, lambda r: len(r) >= 4)
    if not r or r[2] == 0x01:
        return None
    return r[3], False


def read_arctis7(h, m):
    r = xfer(h, bytes([0x06, 0x18]), 8, lambda r: len(r) >= 3)
    return (r[2], False) if r else None


AEROX_WIRED = {0x183A, 0x187A, 0x1854, 0x185E, 0x1862, 0x185A, 0x1876}


def read_aerox(h, m):
    cmd = 0x92 if m.pid in AEROX_WIRED else 0xD2  # pelo receptor o comando ganha o bit 6
    r = xfer(h, bytes([0x00, cmd]), 2, lambda r: len(r) >= 2, timeout=0.25, wait=0.05)
    if not r:
        return None
    level = ((r[1] & 0x7F) - 1) * 5
    return (level, bool(r[1] & 0x80)) if 0 <= level <= 100 else None


def read_rival(h, m):
    r = xfer(h, bytes([0x00, 0xAA, 0x01]), 3, lambda r: len(r) >= 3, timeout=0.25, wait=0.05)
    return (r[0], bool(r[2])) if r and r[0] <= 100 else None


def _h(pids, name, read, coll):
    return [Model(VID, p, name, "HEADSET", read, **coll) for p in pids]


def _mouse(pids, name, read, iface):
    return [Model(VID, p, name, "MOUSE", read, interface=iface) for p in pids]


MODELS = [
    *_h([0x2202, 0x22A1, 0x227E, 0x2258, 0x229E, 0x223A], "SteelSeries Arctis Nova 7", read_nova7, NOVA),
    *_h([0x2206, 0x22AD, 0x22A4, 0x22A5], "SteelSeries Arctis Nova 7X", read_nova7, NOVA),
    *_h([0x22A9], "SteelSeries Arctis Nova 7 Diablo IV", read_nova7, NOVA),
    *_h([0x227A], "SteelSeries Arctis Nova 7 WoW", read_nova7, NOVA),
    *_h([0x220E, 0x2212, 0x2216, 0x2236], "SteelSeries Arctis 7+", read_7plus, NOVA),
    *_h([0x2269, 0x226D], "SteelSeries Arctis Nova 3 Wireless", read_nova35, NOVA),
    *_h([0x2232, 0x2253], "SteelSeries Arctis Nova 5", read_nova35, NOVA),
    *_h([0x12E0, 0x12E5], "SteelSeries Arctis Nova Pro Wireless", read_novapro, dict(interface=4)),
    *_h([0x12B3, 0x12B6], "SteelSeries Arctis 1 Wireless", read_arctis1, LEGACY3),
    *_h([0x12D7], "SteelSeries Arctis 7X", read_arctis1, LEGACY3),
    *_h([0x12D5], "SteelSeries Arctis 7P", read_arctis1, LEGACY3),
    *_h([0x1260, 0x12AD], "SteelSeries Arctis 7", read_arctis7, LEGACY5),
    *_h([0x1252, 0x1280], "SteelSeries Arctis Pro", read_arctis7, LEGACY5),
    *_mouse([0x1838, 0x1878, 0x183A, 0x187A], "SteelSeries Aerox 3 Wireless", read_aerox, 3),
    *_mouse([0x1852, 0x185C, 0x1860, 0x1854, 0x185E, 0x1862], "SteelSeries Aerox 5 Wireless", read_aerox, 3),
    *_mouse([0x1858, 0x1874, 0x185A, 0x1876], "SteelSeries Aerox 9 Wireless", read_aerox, 3),
    *_mouse([0x1830], "SteelSeries Rival 3 Wireless", read_rival, 3),
    *_mouse([0x1872], "SteelSeries Rival 3 Wireless Gen 2", read_rival, 3),
    *_mouse([0x1726, 0x172B], "SteelSeries Rival 650 Wireless", read_rival, 0),
]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_steelseries.py tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/steelseries.py tests/test_steelseries.py
git commit -m "feat(vendors): headsets e mouses SteelSeries"
```

---

### Task 4: HyperX (headsets)

**Files:**
- Modify: `vendors/hyperx.py`
- Test: `tests/test_hyperx.py`

**Interfaces:**
- Consumes: `Model`, `pad`, `xfer` de `vendors`.
- Produces: `MODELS`, `flight_pct(mv) -> int` e os leitores `read_alpha`, `read_cloud2_hp`, `read_cloud2_kingston`, `read_flight` e `read_alpha2`.

Protocolo (HeadsetControl `lib/devices/hyperx_*.hpp`):

| Modelo | VID:PID | Coleção | Troca |
|---|---|---|---|
| Cloud Alpha Wireless | `03F0:098D` | interface 0 | `21 BB 03` (`[3]==1` = desligado), `21 BB 0C` (`[3]==1` = carregando), `21 BB 0B` (nível em `[3]`); 31 bytes |
| Cloud II Wireless HP | `03F0:0696`, `03F0:018B` | `0xFF90/0x0303` | `06 FF BB <cmd>` com 52 bytes, espera 100 ms, resposta começa por `06 FF BB <cmd>`; cmd `02`: nível em `[7]`; cmd `03`: `[4]==1` = carregando |
| Cloud II Wireless Kingston | `0951:1718` | interface 0 | `get_input_report(0x06)`; pedido de 62 bytes `06 00 02 00 9A 00 00 68 4A 8E 0A 00 00 00 BB <cmd> 00`; espera 100 ms; resposta `[0]==0x0B`, `[2]==0xBB`, `[3]==cmd`; nível em `[7]`; carregando quando `[4]==1` |
| Cloud Flight | `0951:16C4`, `0951:1723` | interface 0 | `21 FF 05` com 20 bytes; resposta de 15 ou 20 bytes; mV = `[3]<<8 \| [4]`; carregando com mV > 4107; % pela curva |
| Cloud Alpha 2 Wireless | `03F0:08BE` | `0xFF13/0xFF00`, interface 2 | `52 01` → `53 01` (`[2]==0` = desligado); `50 02` → `51 02` (nível em `[2]`, `[3]==1` = carregando); 64 bytes, tempo limite de 1 s |

- [ ] **Step 1: Testes (falham)**

`tests/test_hyperx.py`:
```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_hyperx.py -q`
Expected: FAIL (leitores inexistentes)

- [ ] **Step 3: Implementar `vendors/hyperx.py`**

```python
"""Headsets HyperX sem fio (protocolos documentados pelo HeadsetControl)."""
from . import Model, pad, xfer

HP, KINGSTON = 0x03F0, 0x0951


def _alpha(h, cmd):
    return xfer(h, pad([0x21, 0xBB, cmd], 31), 31, lambda r: len(r) >= 4)


def read_alpha(h, m):
    c = _alpha(h, 0x03)
    if not c or c[3] == 0x01:  # fone desligado ou fora da base
        return None
    ch, lv = _alpha(h, 0x0C), _alpha(h, 0x0B)
    if not lv or lv[3] > 100:
        return None
    return lv[3], bool(ch and ch[3] == 0x01)


def _hp(h, cmd):
    return xfer(h, pad([0x06, 0xFF, 0xBB, cmd], 52), 20, lambda r: r[:4] == [0x06, 0xFF, 0xBB, cmd], wait=0.1)


def read_cloud2_hp(h, m):
    lv = _hp(h, 0x02)
    if not lv or len(lv) < 8:
        return None
    ch = _hp(h, 0x03)
    return lv[7], bool(ch and ch[4] == 1)


_KINGSTON = [0x06, 0x00, 0x02, 0x00, 0x9A, 0x00, 0x00, 0x68, 0x4A, 0x8E, 0x0A, 0x00, 0x00, 0x00, 0xBB]


def _kingston(h, cmd):
    try:
        h.get_input_report(0x06, 64)
    except Exception:
        pass
    return xfer(h, pad(_KINGSTON + [cmd, 0x00], 62), 64,
                lambda r: len(r) > 7 and r[0] == 0x0B and r[2] == 0xBB and r[3] == cmd, wait=0.1)


def read_cloud2_kingston(h, m):
    lv = _kingston(h, 0x02)
    if not lv:
        return None
    ch = _kingston(h, 0x03)
    return lv[7], bool(ch and ch[4] == 1)


def flight_pct(mv):
    """Curva do HeadsetControl (derivada da do Logitech G633/G933)."""
    if mv <= 3648:
        return round(0.00125 * mv)
    if mv > 3975:
        return 100
    return round(0.00000002547505 * mv ** 4 - 0.0003900299 * mv ** 3 + 2.238321 * mv ** 2
                 - 5706.256 * mv + 5452299.0)


def read_flight(h, m):
    r = xfer(h, pad([0x21, 0xFF, 0x05], 20), 20, lambda r: len(r) in (15, 20))
    if not r:
        return None
    mv = r[3] << 8 | r[4]
    return max(0, min(100, flight_pct(mv))), mv > 0x100B


def _alpha2(h, cmd, sub):
    return xfer(h, pad([cmd, sub], 64), 64, lambda r: len(r) > 2 and r[0] == cmd + 1 and r[1] == sub, timeout=1.0)


def read_alpha2(h, m):
    c = _alpha2(h, 0x52, 0x01)
    if not c or c[2] == 0x00:
        return None
    b = _alpha2(h, 0x50, 0x02)
    if not b or len(b) < 4 or b[2] > 100:
        return None
    return b[2], b[3] == 0x01


MODELS = [
    Model(HP, 0x098D, "HyperX Cloud Alpha Wireless", "HEADSET", read_alpha, interface=0),
    Model(HP, 0x0696, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_hp, usage_page=0xFF90, usage=0x0303),
    Model(HP, 0x018B, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_hp, usage_page=0xFF90, usage=0x0303),
    Model(KINGSTON, 0x1718, "HyperX Cloud II Wireless", "HEADSET", read_cloud2_kingston, interface=0),
    Model(KINGSTON, 0x16C4, "HyperX Cloud Flight", "HEADSET", read_flight, interface=0),
    Model(KINGSTON, 0x1723, "HyperX Cloud Flight", "HEADSET", read_flight, interface=0),
    Model(HP, 0x08BE, "HyperX Cloud Alpha 2 Wireless", "HEADSET", read_alpha2,
          usage_page=0xFF13, usage=0xFF00, interface=2),
]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_hyperx.py tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/hyperx.py tests/test_hyperx.py
git commit -m "feat(vendors): headsets HyperX"
```

---

### Task 5: Corsair (headsets)

**Files:**
- Modify: `vendors/corsair.py`
- Test: `tests/test_corsair.py`

**Interfaces:**
- Consumes: `Model`, `pad`, `flush`, `xfer` de `vendors`.
- Produces: `MODELS` e os leitores `read_void`, `read_v2w` e `read_xt`.

Protocolo (HeadsetControl `lib/devices/corsair_void_rich.hpp`, `corsair_void_v2w.hpp`, `corsair_virtuoso_xt.hpp`):

| Grupo | Coleção | Troca |
|---|---|---|
| Void, HS70 | `0xFFC5/0x0001`, interface 3 | `C9 64` → 5 bytes `64 00 <nível\|mic> B1 <status>`. Nível = `[2] & 0x7F`. Status: 0 = desligado; 1 ou 2 = ok; 4 ou 5 = carregando |
| Void V2, Virtuoso MAX, HS80 MAX | interface 4 | `00 02 08 02 13`, `00 02 08 02 12`, depois flush; `00 02 09 02 12` sem resposta = fone fora; flush; `00 02 09 02 0F` → bruto = `[4] \| [5]<<8`, válido de 1 a 1000, % = bruto // 10, até 4 tentativas; sem informação de carga |
| Virtuoso XT/SE | `0xFF42/0x0001`, interface 3 | `02 <alvo> 02 <prop> 00` (64 bytes) → `[0]==01`; `[1]==01` (alvo 09) ou `00` (alvo 08); `[2]==02`; `[3]==00` ok; valor `[4..7]` LE. Prop `0F` = nível ×10; prop `10` = carga (1). O alvo começa em 08 no PID `0A62` e em 09 nos outros; se falhar, tenta o outro |

- [ ] **Step 1: Testes (falham)**

`tests/test_corsair.py`:
```python
from vendors import corsair as cs
from tests.fakes import FakeDev


def m(pid):
    return next(x for x in cs.MODELS if x.pid == pid)


def test_void():
    h = FakeDev(on_write=lambda d: [[0x64, 0x00, 0x80 | 57, 0xB1, 0x01]])
    assert cs.read_void(h, m(0x0A55)) == (57, False) and h.writes == [b"\xc9\x64"]


def test_void_carregando_e_desligado():
    assert cs.read_void(FakeDev(on_write=lambda d: [[0x64, 0, 30, 0xB1, 0x05]]), m(0x0A55)) == (30, True)
    assert cs.read_void(FakeDev(on_write=lambda d: [[0x64, 0, 30, 0xB1, 0x00]]), m(0x0A55)) is None


def test_void_descarta_resposta_sem_assinatura():
    h = FakeDev(on_write=lambda d: [[0x01, 0, 30, 0x00, 0x01]])
    assert cs.read_void(h, m(0x0A55)) is None


def test_v2w():
    def on(d):
        if d[2] == 0x09 and d[4] == 0x12:
            return [[0x02, 0x09]]
        if d[4] == 0x0F:
            return [[0, 0, 0, 0, 0xEE, 0x02]]  # 750 -> 75 %
        return []
    assert cs.read_v2w(FakeDev(on_write=on), m(0x2A08)) == (75, False)


def test_v2w_fone_fora():
    assert cs.read_v2w(FakeDev(), m(0x2A08)) is None


def test_v2w_rejeita_id_e_tenta_de_novo():
    answers = iter([[0, 0, 0, 0, 0x34, 0x12], [0, 0, 0, 0, 0x64, 0x00]])  # 0x1234 > 1000; depois 100
    def on(d):
        if d[2] == 0x09 and d[4] == 0x12:
            return [[0x02, 0x09]]
        return [next(answers)] if d[4] == 0x0F else []
    assert cs.read_v2w(FakeDev(on_write=on), m(0x2A08)) == (10, False)


def test_xt_pelo_receptor():
    def on(d):
        target, prop = d[1], d[3]
        val = 830 if prop == 0x0F else 1
        return [[0x0E, 0x01], [0x01, 0x01 if target == 0x09 else 0x00, 0x02, 0x00, val & 0xFF, val >> 8, 0, 0]]
    h = FakeDev(on_write=on)
    assert cs.read_xt(h, m(0x0A64)) == (83, True)
    assert h.writes[0][:5] == b"\x02\x09\x02\x0f\x00" and len(h.writes[0]) == 64


def test_xt_com_fio_comeca_no_alvo_08():
    h = FakeDev(on_write=lambda d: [[0x01, 0x00, 0x02, 0x00, 0x20, 0x03, 0, 0]])
    assert cs.read_xt(h, m(0x0A62))[0] == 80
    assert h.writes[0][1] == 0x08


def test_xt_sem_fone():
    h = FakeDev(on_write=lambda d: [[0x01, 0x00, 0x02, 0x05, 0, 0, 0, 0]])
    assert cs.read_xt(h, m(0x0A64)) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_corsair.py -q`
Expected: FAIL (leitores inexistentes)

- [ ] **Step 3: Implementar `vendors/corsair.py`**

```python
"""Headsets Corsair sem fio (protocolos documentados pelo HeadsetControl)."""
from . import Model, flush, pad, xfer

VID = 0x1B1C


def read_void(h, m):
    r = xfer(h, bytes([0xC9, 0x64]), 5, lambda r: len(r) >= 5 and r[0] == 0x64 and r[3] == 0xB1)
    if not r or r[4] not in (1, 2, 4, 5):  # 0 = fone fora do receptor
        return None
    return r[2] & 0x7F, r[4] in (4, 5)


def _bragi(*cmd):
    return pad([0x00, 0x02, *cmd], 65)


def read_v2w(h, m):
    h.write(_bragi(0x08, 0x02, 0x13))
    h.write(_bragi(0x08, 0x02, 0x12))
    flush(h)
    if not xfer(h, _bragi(0x09, 0x02, 0x12), 64, lambda r: len(r) > 0):
        return None  # fone não está ligado ao receptor
    flush(h)
    for _ in range(4):  # às vezes o receptor devolve o ID do fone no lugar da bateria
        r = xfer(h, _bragi(0x09, 0x02, 0x0F), 64, lambda r: len(r) > 5)
        if r and 0 < (raw := r[4] | r[5] << 8) <= 1000:
            return raw // 10, False
    return None


def _xt_get(h, target, prop):
    flush(h)
    src = 0x01 if target == 0x09 else 0x00
    r = xfer(h, pad([0x02, target, 0x02, prop, 0x00], 64), 64,
             lambda r: len(r) > 7 and r[0] == 0x01 and r[1] == src and r[2] == 0x02, timeout=0.3)
    if r and r[3] == 0x00:
        return r[4] | r[5] << 8 | r[6] << 16 | r[7] << 24
    return None


def read_xt(h, m):
    first = 0x08 if m.pid == 0x0A62 else 0x09
    for target in (first, 0x09 if first == 0x08 else 0x08):
        v = _xt_get(h, target, 0x0F)
        if v is not None and v <= 1000:
            return v // 10, _xt_get(h, target, 0x10) == 1
    return None


VOID = dict(usage_page=0xFFC5, usage=0x0001, interface=3)
XT = dict(usage_page=0xFF42, usage=0x0001, interface=3)
_VOID_NAMES = {
    0x1B1C: "Corsair Void RGB", 0x1B27: "Corsair Void Wireless", 0x0A14: "Corsair Void Pro",
    0x0A16: "Corsair Void Pro", 0x0A17: "Corsair Void Pro", 0x0A1D: "Corsair Void Pro",
    0x0A1A: "Corsair Void Pro Wireless", 0x1B2A: "Corsair Void RGB", 0x1B23: "Corsair Void RGB",
    0x1B29: "Corsair Void RGB", 0x0A55: "Corsair Void Elite Wireless", 0x0A51: "Corsair Void RGB Elite Wireless",
    0x0A52: "Corsair Void Elite", 0x0A38: "Corsair HS70 Wireless", 0x0A4F: "Corsair HS70 Pro Wireless",
    0x0A2B: "Corsair Void RGB Wireless", 0x0A75: "Corsair Void Elite Wireless", 0x0A56: "Corsair Void",
}

MODELS = [
    *[Model(VID, pid, name, "HEADSET", read_void, **VOID) for pid, name in _VOID_NAMES.items()],
    Model(VID, 0x2A08, "Corsair Void Wireless V2", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x2A02, "Corsair Virtuoso MAX Wireless", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x0A97, "Corsair HS80 MAX Wireless", "HEADSET", read_v2w, interface=4),
    Model(VID, 0x0A64, "Corsair Virtuoso XT", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A62, "Corsair Virtuoso XT", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A3E, "Corsair Virtuoso SE", "HEADSET", read_xt, **XT),
    Model(VID, 0x0A3D, "Corsair Virtuoso SE", "HEADSET", read_xt, **XT),
]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_corsair.py tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/corsair.py tests/test_corsair.py
git commit -m "feat(vendors): headsets Corsair"
```

---

### Task 6: PlayStation (só leitura)

**Files:**
- Modify: `vendors/playstation.py`
- Test: `tests/test_playstation.py`

**Interfaces:**
- Consumes: `Model` de `vendors`.
- Produces: `MODELS` e os leitores `read_dualsense` e `read_ds4`.

Layout do input report (driver `hid-playstation` do Linux), contando com o report ID no byte 0:

| Controle | Conexão | Report | Byte de status | Como ler o status |
|---|---|---|---|---|
| DualSense | USB | `0x01` de 64 bytes | `[53]` | nibble baixo = nível 0–10; nibble alto: 1 = carregando, 2 = cheio |
| DualSense | BT estendido | `0x31` | `[54]` | igual ao USB |
| DS4 | USB | `0x01` | `[30]` | nibble baixo = nível; bit `0x10` = cabo |
| DS4 | BT | `0x11` | `[32]` | igual ao USB |

O report BT `0x01` simples é curto e não traz bateria, então nesse caso o resultado é `None`. Não há escrita de nenhum tipo.

- [ ] **Step 1: Testes (falham)**

`tests/test_playstation.py`:
```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_playstation.py -q`
Expected: FAIL (leitores inexistentes)

- [ ] **Step 3: Implementar `vendors/playstation.py`**

```python
"""Controles PlayStation: só lê o input report que o controle já manda (sem comando nenhum, para não
mudar o modo do controle e quebrar Steam Input/DS4Windows). Layout do driver hid-playstation do Linux."""
import time

from . import Model

SONY = 0x054C


def _scan(h, offsets, timeout=0.5):
    """Primeiro report que traga o byte de status: offsets = {report_id: índice}. Devolve (report, índice)."""
    end = time.monotonic() + timeout
    while (left := end - time.monotonic()) > 0:
        r = h.read(78, max(1, int(left * 1000)))
        if r and r[0] in offsets and len(r) > offsets[r[0]] + 1:
            return r, offsets[r[0]]
    return None


def read_dualsense(h, m):
    got = _scan(h, {0x01: 53, 0x31: 54})
    if got is None:
        return None
    s = got[0][got[1]]
    level, state = s & 0x0F, s >> 4
    if state == 2:
        return 100, False  # carga completa
    return min(level * 10 + 5, 100), state == 1


def read_ds4(h, m):
    got = _scan(h, {0x01: 30, 0x11: 32})
    if got is None:
        return None
    r, i = got
    if m.pid == 0x0BA0 and r[i + 1] & 0x04:  # adaptador sem controle (DS4_STATUS1_DONGLE_STATE)
        return None
    level, cable = r[i] & 0x0F, bool(r[i] & 0x10)
    if level > 11:
        return None  # 14/15 = erro de carga ou temperatura
    if cable and level >= 10:
        return 100, level == 10  # 10 = ainda carregando; 11 = cheio
    return min(level * 10 + 5, 100), cable


GAMEPAD = dict(usage_page=0x01, usage=0x05, writes=False)
MODELS = [
    Model(SONY, 0x0CE6, "DualSense", "GAMEPAD", read_dualsense, **GAMEPAD),
    Model(SONY, 0x0DF2, "DualSense Edge", "GAMEPAD", read_dualsense, **GAMEPAD),
    Model(SONY, 0x05C4, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
    Model(SONY, 0x09CC, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
    Model(SONY, 0x0BA0, "DualShock 4", "GAMEPAD", read_ds4, **GAMEPAD),
]
```

O teste do DualSense USB espera o report de 64 bytes com o status em `[53]`. O `h.read(78, ...)` da implementação só limita o tamanho máximo lido, e o fake devolve o report inteiro.

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_playstation.py tests/test_core.py -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/playstation.py tests/test_playstation.py
git commit -m "feat(vendors): controles PlayStation (só leitura)"
```

---

### Task 7: Xbox (XInput)

**Files:**
- Modify: `vendors/xbox.py`
- Test: `tests/test_xbox.py`

**Interfaces:**
- Produces: `scan(api=None) -> dict[str, dict]`, com chaves `xinput:<n>` e só os controles com bateria.

API do Windows: `XInputGetBatteryInformation(user_index, BATTERY_DEVTYPE_GAMEPAD=0, *XINPUT_BATTERY_INFORMATION{BatteryType: BYTE, BatteryLevel: BYTE})`. Retorna 0 em caso de sucesso.
- **Tipo da bateria:** 0 = desconectado, 1 = com fio, 0xFF = desconhecido. Os três ficam de fora.
- **Nível:** 0..3 vira 5/30/60/99% (99 e não 100, para não disparar o aviso "tire do carregador" com pilha).

- [ ] **Step 1: Testes (falham)**

`tests/test_xbox.py`:
```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_xbox.py -q`
Expected: FAIL (`scan()` não aceita `api`)

- [ ] **Step 3: Implementar `vendors/xbox.py`**

```python
"""Controles Xbox pela API XInput do Windows (só informa níveis: vazio, baixo, médio, cheio)."""
import ctypes


class _Battery(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ubyte), ("level", ctypes.c_ubyte)]


LEVELS = (5, 30, 60, 99)  # 99: o XInput não diz se é pilha; 100 dispararia "tire do carregador"
SKIP = (0x00, 0x01, 0xFF)  # desconectado, com fio (sem bateria), desconhecido


def _api():
    for dll in ("xinput1_4", "xinput1_3"):
        try:
            return getattr(ctypes.windll, dll).XInputGetBatteryInformation
        except (OSError, AttributeError):
            continue
    return None


def scan(api=None):
    api = api or _api()
    if not api:
        return {}
    out = {}
    for i in range(4):
        b = _Battery()
        if api(i, 0, ctypes.byref(b)) != 0 or b.type in SKIP:
            continue
        out[f"xinput:{i}"] = {"name": f"Controle Xbox {i + 1}", "battery": LEVELS[min(b.level, 3)],
                              "connected": True, "kind": "GAMEPAD", "charging": False, "hours": None}
    return out
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests -q`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add vendors/xbox.py tests/test_xbox.py
git commit -m "feat(vendors): controles Xbox via XInput"
```

---

### Task 8: Fonte `"vendor"` no app e teste real

**Files:**
- Modify: `bateria_bt.py`. As linhas são aproximadas: localize pelo texto.
  - import de `graphics` (cerca da linha 26);
  - `App.__init__`, `self.sources`, `self.hidpp` (cerca das 1744–1745);
  - propriedade `devices`;
  - `refresh` (cerca da 1810);
  - `on_source` (cerca da 1837).
- Test: `tests/test_app_merge.py`

**Interfaces:**
- Consumes: `VendorReader` de `vendors`.

- [ ] **Step 1: Teste da junção (falha)**

`tests/test_app_merge.py`:
```python
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
```

Run: `python -m pytest tests/test_app_merge.py -q`
Expected: FAIL com `AssertionError` (a chave `vendor:1532:00ab:S` ainda não entra na junção).

- [ ] **Step 2: Integrar**

Ao lado de `import graphics as G`:
```python
from vendors import VendorReader  # outras marcas (Razer, SteelSeries, HyperX, Corsair, PlayStation, Xbox)
```

Em `App.__init__`:
```python
        self.sources = {"bt": {}, "vendor": {}, "hid": {}, "ghub": {}}
```
Logo abaixo de `self.hidpp.done.connect(...)`:
```python
        self.vendor = VendorReader()
        self.vendor.done.connect(lambda d: self.on_source("vendor", d))
```

Na propriedade `devices`:
```python
        out = {**s["bt"], **s["vendor"], **s["hid"], **s["ghub"]}  # G HUB tem prioridade nos dados
```

Em `refresh`, depois de `self.hidpp.refresh()`:
```python
        self.vendor.refresh()
```

Em `on_source`, na regra de nomes:
```python
        known = {**names, **self.cfg["known"]} if src in ("hid", "vendor") else {**self.cfg["known"], **names}
```

Run: `python -m pytest tests -q`
Expected: todos PASS.

- [ ] **Step 3: Teste real nesta máquina**

```bash
python -c "
import time, vendors
t = time.monotonic(); out = vendors.VendorReader().read_all()
print(round(time.monotonic() - t, 2), 's', out)
assert not any(k.startswith('vendor:046d') for k in out)"
```
Expected: termina em menos de 5 s e não mostra nenhuma chave da Logitech. Sem aparelho das marcas do lote 1 conectado, a saída é `{}`, a não ser que haja um controle Xbox.

Depois reinicie o app pelo atalho da pasta Inicializar e confira:
- o `erros.log` sem erro novo;
- a barra igual à de antes: G903, G915 e o G733 quando ligado.

```powershell
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ? CommandLine -match 'bateria_bt' | % { Stop-Process -Id $_.ProcessId -Force }
Start-Process "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\BateriaBT.lnk"
Start-Sleep 70; Get-Content "$env:APPDATA\BateriaBT\erros.log" -Tail 5
```

- [ ] **Step 4: Commit**

```bash
git add bateria_bt.py tests/test_app_merge.py
git commit -m "feat: fonte de outras marcas no app"
```

---

## Ajustes na spec trazidos pela pesquisa (precisam de OK)

1. **Coleção declarada:** vale também só o número da interface (`interface=N`). Vários modelos do HeadsetControl e do rivalcfg não têm usage, só a interface.
2. **Validação da resposta:** "confere com o que o protocolo permite verificar: report ID, eco do comando, assinatura, tamanho e faixa do valor". Alguns protocolos (Nova, Cloud Alpha, Flight, Aerox, Rival) não têm eco publicado. Neles a validação é por tamanho e faixa.
3. **Tempo limite:** 0,5 s por troca de mensagem, não por leitura inteira. Exceções: Cloud Alpha 2 com 1 s e Atheris/Orochi V2 com 400 ms de espera.
4. **Escopo:** sai da lista do lote 1 o que está na tabela "fora do lote 1" acima. O principal é o headset Razer, que exige trocar o modo do receptor.
5. **Chave:** quando não há série, o hash é do caminho sem a parte da coleção. Isso faz as coleções de um mesmo aparelho darem a mesma chave.
6. **Contrato do leitor:** a função passa a ser `read(h, model)`, e não `read(h)`. Ela recebe o modelo para escolher a variante pelo PID (transaction ID da Razer, cabo/receptor no Aerox, alvo no Virtuoso XT).
7. **Só a interface declarada** (revisão adversarial, achado 1): nesse caso, o modelo que escreve só casa com coleção do fabricante (usage page ≥ 0xFF00). Sem isso, o comando iria para a coleção Consumer/Mouse da mesma interface.
8. **Chave sem série** (achados 3 e 4): passa a ser `vendor:<vid>:<grupo>:<série ou ordem>`.
   - **Grupo:** o menor PID com o mesmo nome. Assim, cabo e receptor do mesmo mouse viram um item só.
   - **Ordem:** a posição (0, 1...) entre aparelhos iguais, no lugar do hash do caminho. Assim, trocar o receptor de porta USB não cria um item novo.
9. **Adaptador DS4 sem controle** (achado 2): dá `None`. Os códigos de erro 14/15 também dão `None`. Nível 10 no cabo conta como "carregando".
10. **Sem `hidapi`:** os controles Xbox continuam aparecendo. Xbox cheio é mostrado como 99%.
11. **Texto da spec:**
    - **Aceite 5:** a chave começa com `vendor:` ou `xinput:`.
    - **Controle Xbox desligado:** fica como desconectado até reiniciar o app. A chave é a posição no XInput, não o controle.
    - **Regra de nomes:** o primeiro nome detectado fica gravado, igual ao HID++. O nome dado pelo usuário prevalece sempre.
    - **Limite conhecido:** um headset ligado ao mesmo tempo por BT e pelo receptor aparece duas vezes.
