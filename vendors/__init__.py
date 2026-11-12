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
