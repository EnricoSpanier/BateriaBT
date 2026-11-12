"""Bateria BT — bateria de dispositivos Bluetooth e Logitech (receptor direto ou G HUB) na barra de tarefas.

Config: %APPDATA%\\BateriaBT\\config.json (gravado a cada alteração, de forma atômica).
Rodar: pythonw bateria_bt.py
"""
import asyncio
import ctypes
import faulthandler
import json
import os
import sys
import threading
import time
import winreg
from pathlib import Path

from PySide6.QtCore import (QAbstractAnimation, QEvent, QLockFile, QObject, QPoint, QPointF, QRectF, Qt, QTimer,
                            QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetrics, QGuiApplication, QIcon,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket, QWebSocketHandshakeOptions
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QColorDialog, QComboBox, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)
import graphics as G  # desenho vetorial (ícones e pilhas) igual ao original
from updater import VERSION, Updater  # botão "Buscar atualização" (Releases do GitHub)
from vendors import VendorReader  # outras marcas (Razer, SteelSeries, HyperX, Corsair, PlayStation, Xbox)
from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind
from winrt.windows.foundation import IPropertyValue, PropertyType

APP = "BateriaBT"
CONFIG_DIR = Path(os.environ["APPDATA"]) / APP
CONFIG_FILE = CONFIG_DIR / "config.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
INTERVAL_MS = 60_000

DEFAULTS = {
    "hidden": [],              # ids ocultos
    "names": {},               # id -> nome personalizado
    "known": {},               # id -> nome original (para listar mesmo ausente)
    "kinds": {},               # id -> tipo (teclado, mouse...), para o ícone quando ausente
    "theme": "auto",           # auto (segue o Windows) / escuro / claro
    "threshold": 20,
    "show_disconnected": False,
    "offset": None,            # distância (px) da borda direita da barra até o widget
    "widget_visible": True,
    "thresholds": {},          # id -> limite de alerta próprio
    "colors": {"high": "#10B981", "medium": "#F59E0B", "low": "#EF4444"},
    "widget_style": "standard",  # standard / frameless / capsules / neon
    "icon_style": "outline",   # outline / filled / minimal
    "animation": "blink",      # none / blink / fade / scale / slide / pulse
    "tray_per_device": False,
    "full_charge_alert": True,
    "display_mode": "auto",    # auto / full / compact / battery / text_only / micro
    "layout_mode": "auto",     # auto / row / grid (duas linhas)
    "battery_orientation": "horizontal",
    "widget_opacity": 95,
    "icon_size": "auto",       # auto ou pixels
    "blink_alert_enabled": True,
}
HISTORY_FILE = CONFIG_DIR / "history.json"


# ---------- config ----------
def load_config():
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    return {**DEFAULTS, **{k: v for k, v in cfg.items() if k in DEFAULTS}}


def write_json(path, obj):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:  # alguns sistemas de arquivos virtualizados não deixam renomear
        path.write_text(text, encoding="utf-8")


def save_config(cfg):
    write_json(CONFIG_FILE, cfg)


def load_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_history(hist):
    write_json(HISTORY_FILE, hist)


# ---------- iniciar com o Windows (atalho na pasta Inicializar) ----------
# A entrada em HKCU\...\Run era ignorada pelo Windows nesta máquina; a pasta Inicializar funciona.
STARTUP_LNK = Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup" / f"{APP}.lnk"


def _old_run_entry():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return bool(winreg.QueryValueEx(k, APP))
    except OSError:
        return False


def startup_enabled():
    return STARTUP_LNK.exists()


def set_startup(on):
    try:  # remove a entrada antiga do registro
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP)
    except OSError:
        pass
    if not on:
        STARTUP_LNK.unlink(missing_ok=True)
        return
    from comtypes.client import CreateObject
    lnk = CreateObject("WScript.Shell", dynamic=True).CreateShortcut(str(STARTUP_LNK))
    if getattr(sys, "frozen", False):  # instalado pelo BateriaBT-Setup.exe (PyInstaller)
        lnk.TargetPath = sys.executable
        lnk.Arguments = ""  # o atalho pode ter vindo da versão em Python, com o caminho do script
        lnk.WorkingDirectory = str(Path(sys.executable).parent)
    else:
        lnk.TargetPath = str(Path(sys.executable).with_name("pythonw.exe"))
        lnk.Arguments = f'"{Path(__file__).resolve()}"'
        lnk.WorkingDirectory = str(Path(__file__).resolve().parent)
    lnk.Save()


# ---------- fonte 1: Bluetooth (WinRT) ----------
BAT = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2"
CID = "System.Devices.ContainerId"
CONNECTED = "System.Devices.Connected"


def _val(props, key):
    if not props.has_key(key) or (v := props.lookup(key)) is None:
        return None
    pv = v.as_(IPropertyValue)
    getter = {PropertyType.UINT8: pv.get_uint8, PropertyType.GUID: pv.get_guid,
              PropertyType.BOOLEAN: pv.get_boolean}.get(pv.type)
    return getter() if getter else None


async def _read_bluetooth():
    devs = await DeviceInformation.find_all_async("", [BAT, CID], DeviceInformationKind.DEVICE)
    out = {}
    for d in devs:
        bat, cid = _val(d.properties, BAT), _val(d.properties, CID)
        if bat is not None and cid is not None and str(cid) not in out:
            out[str(cid)] = {"name": d.name, "battery": int(bat), "connected": False,
                             "kind": "PHONE" if "phone" in d.name.lower() else "BT"}
    containers = await DeviceInformation.find_all_async(
        "System.Devices.Paired:=System.StructuredQueryType.Boolean#True",
        [CONNECTED], DeviceInformationKind.DEVICE_CONTAINER)
    for c in containers:
        cid = c.id.strip("{}").lower()
        if cid in out:
            out[cid]["connected"] = bool(_val(c.properties, CONNECTED))
    return out


class BluetoothReader(QObject):
    done = Signal(dict)

    def refresh(self):
        def run():
            try:
                self.done.emit(asyncio.run(asyncio.wait_for(_read_bluetooth(), 30)))
            except Exception as e:  # leitura falhou: mantém o último estado
                print("erro bluetooth:", e, file=sys.stderr)
        threading.Thread(target=run, daemon=True).start()


# ---------- fonte 2: Logitech G HUB (WebSocket local) ----------
class GHubReader(QObject):
    """Lê bateria pelo WebSocket do G HUB (ws://127.0.0.1:9010). Sem G HUB, fica vazio."""
    done = Signal(dict)

    def __init__(self):
        super().__init__()
        self.ws = QWebSocket()
        self.ws.connected.connect(self._subscribe)
        self.ws.textMessageReceived.connect(self._on_msg)
        # queda rápida: mantém a leitura e reconecta no próximo ciclo; se reconectar falhar (G HUB fechado), limpa
        self._connecting = False
        self.absent = False  # só vira True quando conectar falha: até lá o G HUB pode estar segurando os fones
        self.ws.connected.connect(lambda: (setattr(self, "_connecting", False), setattr(self, "absent", False)))
        self.ws.errorOccurred.connect(self._on_error)
        self.devices = {}   # ghub id -> info
        self.data = {}
        self.aliases = {}   # chave antiga -> nova

    def refresh(self):
        if self.ws.state() == QAbstractSocket.ConnectedState:
            self._list()
        elif self.ws.state() == QAbstractSocket.UnconnectedState:
            req = QNetworkRequest(QUrl("ws://127.0.0.1:9010"))
            req.setRawHeader(b"Origin", b"file://")
            opts = QWebSocketHandshakeOptions()
            opts.setSubprotocols(["json"])
            self._connecting = True
            self.ws.open(req, opts)

    def _on_error(self, _):
        if self._connecting:
            self._connecting, self.absent = False, True
            self.devices, self.data = {}, {}
            self.done.emit({})

    def _send(self, verb, path):
        self.ws.sendTextMessage(json.dumps({"msgId": "", "verb": verb, "path": path}))

    def _list(self):
        self._send("GET", "/devices/list")

    def _subscribe(self):
        """Como o original: o G HUB avisa na hora quando um dispositivo liga/desliga ou a bateria muda."""
        self._send("SUBSCRIBE", "/devices/state/changed")
        self._send("SUBSCRIBE", "/battery/state/changed")
        self._list()

    def _on_msg(self, msg):
        m = json.loads(msg)
        path, payload = m.get("path", ""), m.get("payload") or {}
        if path == "/devices/list":
            self.devices = {d["id"]: d for d in payload.get("deviceInfos", [])
                            if d.get("capabilities", {}).get("hasBatteryStatus")}
            self.data = {k: v for k, v in self.data.items() if k in self.devices}
            for gid, d in self.devices.items():  # desligado mantém a última leitura, marcado desconectado
                if ghub_online(d):
                    self._send("GET", f"/battery/{gid}/state")
            self._emit()
        elif path == "/devices/state/changed":
            self._list()
        elif path.startswith("/battery/") and "percentage" in payload:
            self.data[payload["deviceId"]] = payload
            self._emit()

    def _emit(self):
        out = {}
        for gid, d in self.devices.items():
            fw = (d.get("fwInfo") or [{}])[0].get("interfaceId", "")  # "046d_0afe": PID estável mesmo desligado
            old, pid = "ghub:" + d.get("deviceModel", gid), int(fw[5:], 16) if len(fw) == 9 else d.get("pid")
            key = logi_key(d.get("deviceUnitId"), pid) if d.get("deviceUnitId") or pid else old  # sem dados: não muda
            self.aliases[old] = key  # chave antiga, para migrar ajustes
            if gid in self.data:
                b = self.data[gid]
                out[key] = {"name": d.get("displayName", key), "battery": int(b["percentage"]),
                            "connected": ghub_online(d), "kind": d.get("deviceType", "BT"),
                            "charging": bool(b.get("charging")), "hours": b.get("mileage")}
        self.done.emit(out)


def ghub_online(d):
    """Mesmos estados que o original aceita; NOT_CONNECTED/ABSENT = desligado (ex.: fone fora)."""
    return d.get("state") in ("ACTIVE", "CONNECTED", "CHARGING", "READY", "PENDING") or bool(d.get("isConnected"))


# ---------- fonte 3: receptores Logitech direto (HID++ 2.0), sem precisar do G HUB ----------
def logi_key(unit, pid):
    """Mesma chave para o G HUB e para o HID++: unit ID do dispositivo, ou o PID se não houver."""
    unit = int(unit or 0)
    return f"logi:{unit}" if unit not in (0, 0xFFFFFFFF) else f"logi:pid{int(pid or 0):04x}"


# tensão (mV) -> % para bateria de lítio 3,7 V (mesma tabela do Solaar)
VOLT_CURVE = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50), (3778, 40),
              (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0))


def volt_pct(mv):
    for (v1, p1), (v0, p0) in zip(VOLT_CURVE, VOLT_CURVE[1:]):
        if mv >= v0:
            return round(p0 + (p1 - p0) * min(1, (mv - v0) / (v1 - v0)))
    return 0


HIDPP_KINDS = {0: "KEYBOARD", 3: "MOUSE", 4: "MOUSE", 5: "MOUSE", 8: "HEADSET", 12: "GAMEPAD"}


class HidppReader(QObject):
    """Pergunta a bateria direto aos receptores LIGHTSPEED/Unifying (e headsets USB) pelo protocolo HID++.
    Dispositivo em repouso não responde: fica a última leitura enquanto o receptor estiver ligado."""
    done = Signal(dict)

    def __init__(self):
        super().__init__()
        self.last = {}      # chave -> (caminho do receptor, leitura)
        self._busy = False

    def refresh(self):
        if self._busy:
            return
        self._busy = True

        def run():
            try:
                self.done.emit(self._read_all())
            except Exception as e:  # sem hidapi ou falha de leitura: mantém o último estado
                print("erro hid++:", e, file=sys.stderr)
            finally:
                self._busy = False
        threading.Thread(target=run, daemon=True).start()

    def _read_all(self):
        import hid  # pip install hidapi
        paths, seen = set(), set()
        for info in hid.enumerate(0x046D):
            if (info["usage_page"], info["usage"]) not in ((0xFF00, 2), (0xFF43, 0x202)):
                continue  # só a coleção HID++ "longa"
            path = info["path"]
            paths.add(path)
            h = hid.device()
            try:
                h.open_path(path)
            except OSError:
                continue
            try:
                for dev in (range(1, 7) if info["usage_page"] == 0xFF00 else [0xFF]):
                    r = self._read_device(h, dev, info["product_id"])
                    if r:
                        seen.add(r["key"])
                        self.last[r.pop("key")] = (path, r)
            finally:
                h.close()
        self.last = {k: v for k, v in self.last.items() if v[0] in paths}  # receptor removido: some
        # não respondeu agora (desligado/dormindo): mantém a última % como desconectado, igual ao original
        return {k: {**v[1], "connected": k in seen} for k, v in self.last.items()}

    @staticmethod
    def _req(h, dev, feat, func, *params):
        h.write(bytes([0x11, dev, feat, (func << 4) | 0x0B, *params]).ljust(20, b"\0"))
        end = time.monotonic() + 0.4
        while time.monotonic() < end:
            r = h.read(20, 100)
            if not r or r[1] != dev:
                continue
            if r[2] in (0x8F, 0xFF):
                return None  # dispositivo ausente/dormindo ou função inexistente
            if r[2] == feat and r[3] == (func << 4) | 0x0B:
                return bytes(r[4:])
        return None

    def _feature(self, h, dev, fid):
        r = self._req(h, dev, 0, 0, fid >> 8, fid & 0xFF)
        return r[0] if r and r[0] else None

    def _read_device(self, h, dev, usb_pid):
        f_unit = self._feature(h, dev, 0x0003)          # 1ª pergunta: slot vazio/dormindo não responde
        if not f_unit:
            return None
        pct = charging = None
        if i := self._feature(h, dev, 0x1004):        # bateria unificada: % direto
            if r := self._req(h, dev, i, 1):
                pct, charging = r[0], r[2] in (1, 2)
        elif i := self._feature(h, dev, 0x1000):      # status de bateria antigo
            if r := self._req(h, dev, i, 0):
                pct, charging = r[0], r[2] in (1, 2)
        elif i := self._feature(h, dev, 0x1001):      # tensão (G903, G915...)
            if r := self._req(h, dev, i, 0):
                pct, charging = volt_pct(int.from_bytes(r[:2], "big")), bool(r[2] & 0x80)
        elif i := self._feature(h, dev, 0x1F20):      # headsets (G733...): tensão
            if r := self._req(h, dev, i, 0):
                pct, charging = volt_pct(int.from_bytes(r[:2], "big")), r[2] == 3
        if pct is None:
            return None
        name, kind = f"Logitech {usb_pid:04X}", "BT"
        if i := self._feature(h, dev, 0x0005):        # nome e tipo do dispositivo
            n, raw = (self._req(h, dev, i, 0) or b"\0")[0], b""
            while len(raw) < n and (r := self._req(h, dev, i, 1, len(raw))):
                raw += r[:n - len(raw)]
            name = raw.decode(errors="replace").strip() or name
            if t := self._req(h, dev, i, 2):
                kind = HIDPP_KINDS.get(t[0], kind)
        r = self._req(h, dev, f_unit, 0)              # unit ID: o mesmo que o G HUB mostra
        unit = int.from_bytes(r[1:5], "big") if r else None
        return {"key": logi_key(unit, usb_pid), "name": name, "battery": pct, "connected": True,
                "kind": kind, "charging": charging, "hours": None}


# ---------- barra de tarefas (Win32) ----------
user32 = ctypes.windll.user32
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
for _f in (user32.GetTopWindow, user32.GetWindow, user32.MonitorFromWindow):
    _f.restype = ctypes.c_void_p


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def taskbar_rects():
    """(barra, área de notificação) em pixels físicos, ou None."""
    tb = user32.FindWindowW("Shell_TrayWnd", None)
    if not tb:
        return None
    r, n = RECT(), RECT()
    user32.GetWindowRect(tb, ctypes.byref(r))
    notify = user32.FindWindowExW(tb, None, "TrayNotifyWnd", None)
    if notify:
        user32.GetWindowRect(notify, ctypes.byref(n))
    else:
        n = r
    return tb, r, n


# ---------- tema (mesmas paletas do original) ----------
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
WIN_DARK = dict(bg="#1A1A1F", surface="#24242B", border="#34343D", text="#FFFFFF", sub="#A7A7B0")
WIN_LIGHT = dict(bg="#F3F3F6", surface="#FFFFFF", border="#E1E1E6", text="#1B1B1F", sub="#5C5C66")
THEMES = {  # id: (nome, escuro, acento, fundo, superfície, borda, texto, texto secundário, brilho)
    "dark_cyber": ("Dark Cyber", True, "#818CF8", "#14141B", "#1D1D27", "#2D2D3B", "#F4F4F5", "#A1A1AA", True),
    "day_light": ("Dia", False, "#4F46E5", "#F6F7FA", "#FFFFFF", "#E2E4EA", "#18181B", "#5B5B66", False),
    "blue": ("Azul", True, "#38BDF8", "#0C1522", "#132034", "#22344F", "#F1F5F9", "#94A3B8", True),
    "cyan": ("Ciano", True, "#22D3EE", "#0B171C", "#11222A", "#193B47", "#ECFEFF", "#A5F3FC", True),
    "green": ("Verde", True, "#34D399", "#0A1812", "#11241B", "#1D392B", "#ECFDF5", "#9CC8B4", True),
    "purple": ("Roxo", True, "#A855F7", "#140E1E", "#1D142B", "#34224C", "#FAF5FF", "#C4B5FD", True),
    "pink": ("Rosa", True, "#F472B6", "#1C0E17", "#281520", "#3E2233", "#FFF1F7", "#D6A8BE", True),
    "orange": ("Laranja", True, "#FB923C", "#1C100C", "#271813", "#43281E", "#FFF7ED", "#FDBA74", True),
    "red": ("Vermelho", True, "#F87171", "#1B0C0F", "#281317", "#402228", "#FEF2F2", "#D6A6AB", True),
    "yellow": ("Amarelo", True, "#FBBF24", "#19140A", "#252012", "#3B321D", "#FFFBEB", "#D4C394", True),
    "oled": ("OLED", True, "#E4E4E7", "#000000", "#0D0D0E", "#27272A", "#FFFFFF", "#A1A1AA", False),
}
THEME_NAMES = {"auto": "Automático (Windows)", "escuro": "Escuro", "claro": "Claro",
               **{k: v[0] for k, v in THEMES.items()}}
STYLE_NAMES = {"standard": "Padrão", "frameless": "Sem bordas", "capsules": "Cápsulas", "neon": "Neon"}
ICON_NAMES = {"outline": "Contorno", "filled": "Preenchido", "minimal": "Minimalista"}
DISPLAY_NAMES = {"auto": "Automático", "full": "Completo (ícone, pilha e %)", "compact": "Compacto (ícone e %)",
                 "battery": "Só pilha", "text_only": "Só porcentagem", "micro": "Micro (ícone com barra)"}
LAYOUT_NAMES = {"auto": "Automática", "row": "Uma linha", "grid": "Duas linhas"}
ORIENT_NAMES = {"horizontal": "Horizontal", "vertical": "Vertical"}
ANIM_NAMES = {"none": "Nenhuma", "blink": "Piscar", "fade": "Esmaecer", "scale": "Escala",
              "slide": "Deslizar", "pulse": "Pulsar"}
DEFAULT_COLORS = dict(DEFAULTS["colors"])
ICON_FONT = "Segoe Fluent Icons"
BOLT = ""
APP_TITLE = "Bateria BT"


def _reg(path, name, default):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def palette(theme):
    if theme in THEMES:
        _, dark, acc, bg, surface, border, text, sub, glow = THEMES[theme]
        base, acc = dict(bg=bg, surface=surface, border=border, text=text, sub=sub, glow=glow), QColor(acc)
    else:
        dark = theme == "escuro" if theme != "auto" else not _reg(PERSONALIZE, "AppsUseLightTheme", 0)
        base = {**(WIN_DARK if dark else WIN_LIGHT), "glow": False}
        v = _reg(r"Software\Microsoft\Windows\DWM", "AccentColor", None)  # ABGR
        acc = QColor(v & 255, v >> 8 & 255, v >> 16 & 255) if v is not None else QColor("#6366F1")
        if dark and acc.lightness() < 110:
            acc = acc.lighter(150)
        elif not dark and acc.lightness() > 150:
            acc = acc.darker(150)
    on = "#000000" if acc.lightnessF() > 0.62 else "#FFFFFF"
    return {**base, "accent": acc.name(), "on_accent": on, "dark": dark}


def bar_is_dark(theme):
    """Cor da própria barra do Windows (escuro/claro forçados pelo usuário valem também aqui)."""
    if theme in ("escuro", "claro"):
        return theme == "escuro"
    return not _reg(PERSONALIZE, "SystemUsesLightTheme", 0)


def taskbar_visible(bar):
    """No auto-ocultar a barra desce e fica só com ~2 px dentro da tela."""
    return bar.top < user32.GetSystemMetrics(1) - 6  # SM_CYSCREEN


_uia = None


def widgets_button(tb):
    """(esquerda, direita) em px físicos do botão de clima/Widgets da barra, ou None."""
    global _uia
    try:
        from comtypes.client import CreateObject, GetModule
        GetModule("UIAutomationCore.dll")
        from comtypes.gen.UIAutomationClient import CUIAutomation, IUIAutomation
        if _uia is None:
            _uia = CreateObject(CUIAutomation, interface=IUIAutomation)
        cond = _uia.CreatePropertyCondition(30011, "WidgetsButton")  # UIA_AutomationIdPropertyId
        el = _uia.ElementFromHandle(tb).FindFirst(4, cond)  # TreeScope_Descendants
        r = el.CurrentBoundingRectangle if el else None
        return (r.left, r.right) if r and r.right > r.left else None
    except Exception:
        return None


def fullscreen_app(tb):
    """Alguma janela em tela cheia (jogo, vídeo) está por cima da barra no monitor dela, mesmo sem foco
    (ex.: vídeo no monitor principal e o foco em outro monitor). Percorre a ordem Z de cima para baixo."""
    mi = (ctypes.c_long * 10)()  # MONITORINFO: cbSize, rcMonitor, rcWork, dwFlags
    mi[0] = ctypes.sizeof(mi)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(tb, 2), mi)
    mon, own, r, cloaked = tuple(mi[1:5]), os.getpid(), RECT(), ctypes.c_int()
    pid = ctypes.c_ulong()
    h = user32.GetTopWindow(None)
    while h and h != tb:
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if user32.IsWindowVisible(h) and not user32.IsIconic(h) and pid.value != own:
            ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), 4)  # DWMWA_CLOAKED
            user32.GetWindowRect(h, ctypes.byref(r))
            if not cloaked.value and (r.left, r.top) <= mon[:2] and r.right >= mon[2] and r.bottom >= mon[3]:
                return True
        h = user32.GetWindow(h, 2)  # GW_HWNDNEXT
    return False


def fmt_hours(h):
    if h is None:
        return None
    if h >= 48:
        return f"≈ {h / 24:.0f} dias"
    if h >= 1:
        return f"≈ {h:.0f} h"
    return f"≈ {max(1, round(h * 60))} min"


# ---------- widget na barra de tarefas ----------
class HoverPopup(QLabel):
    """Nome completo e estado do dispositivo ao passar o mouse numa pílula."""

    def __init__(self, app):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setTextFormat(Qt.RichText)

    def show_for(self, row, anchor):
        pal = palette(self.app.cfg["theme"])
        self.setStyleSheet(f"QLabel{{background:{pal['bg']};color:{pal['text']};border:1px solid {pal['border']};"
                           f"border-radius:8px;padding:8px 12px;font:9pt 'Segoe UI'}}")
        self.setText(f"<b>{row['name']}</b><br><span style='color:{pal['sub']}'>"
                     f"{self.app.status_text(row)} · {row['pct']}%</span>")
        self.adjustSize()
        self.move(anchor.x() - self.width() // 2, anchor.y() - self.height() - 6)
        self.show()


def metrics(pill_h, icon_size="auto"):
    """Medidas da pílula conforme a altura (mesmas fórmulas do original)."""
    h = max(16, min(64, pill_h))
    small = h <= 20
    if icon_size != "auto":
        icon = max(10, min(int(icon_size), max(10, h - 4 if h > 18 else h - 2)))
        r = icon / 16
    else:
        r = h / 32
        icon = max(12 if h >= 18 else 11, round(16 * r))
    bh = max(7 if small else 8, round(11 * r))
    m = dict(h=h, r=r, icon=icon, batt_h=bh, batt_w=round(2 * bh),
             bvw=max(6, round(9 * r)) if small else max(8, round(11 * r)),
             bvh=max(11, round(16 * r)) if small else max(14, round(19 * r)),
             pad=max(2, round(3 * r)) if small else max(3, round(4 * r)),
             sep=max(4, round(6 * r)) if small else max(5, round(7 * r)),
             frame_pad=max(1, round(2 * r)) if small else max(2, round(3 * r)),
             glow=1 if small else 3,
             bolt_h=max(7, round(12 * r)), bolt_w=max(4, round(7 * r)))
    m["radius"] = min(9 * r, (h + 2 * m["frame_pad"]) / 2 - 1.5)
    f = QFont("Segoe UI")
    f.setPixelSize(max(10 if small else 11, round(12 * r)))
    f.setWeight(QFont.DemiBold)
    m["font"], m["fm"] = f, QFontMetrics(f)
    return m


def blink_on(level, threshold, now):
    """3 piscadas a cada 4 s (baixa) ou 2 a cada 2 s (crítica)."""
    critical = level <= max(1, threshold // 2)
    period, pulses = (2.0, 2) if critical else (4.0, 3)
    t = now % period
    return any(i * 0.5 <= t < i * 0.5 + 0.25 for i in range(pulses))


def icon_kind(kind):
    k = (kind or "").lower()
    return k if k in G.DEVICE_KINDS else "generic"


class TaskbarWidget(QWidget):
    """Janela sem foco, 'possuída' pela barra de tarefas; cada dispositivo é uma pílula desenhada."""

    def __init__(self, app):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.rows, self.pills = [], []
        self.m, self.mode, self.frame, self.n_rows = None, "full", QRectF(), 1
        self.anim = {}            # did -> progresso 0..1 da animação de entrada
        self._seen = set()
        self._born = time.monotonic()
        self.popup = HoverPopup(app)
        self._press = self._drag = None
        self._owned = False
        self._want = False        # há o que mostrar e o usuário quer o widget
        self._bar_h = 48
        self.keep = QTimer(self, interval=2000, timeout=self.place)  # barra pode mudar/reiniciar
        self.keep.start()
        self.follow = QTimer(self, interval=150, timeout=self.sync_shown)  # some junto com a barra
        self.follow.start()
        self.tick = QTimer(self, interval=50, timeout=self.update)  # piscar e brilho de carga
        self._now = time.monotonic()

    def sync_shown(self):
        """Mostra só quando a barra está à vista: some no auto-ocultar e em apps de tela cheia."""
        rects = taskbar_rects()
        shown = self._want and rects is not None and taskbar_visible(rects[1]) and not fullscreen_app(rects[0])
        if shown != self.isVisible():
            self.setVisible(shown)
            if shown:
                self.place()
            else:
                self.popup.hide()

    # --- disposição ---
    def _pill_w(self, row, mode, m):
        gap = max(3, int(0.18 * m["h"]))
        text_w = m["fm"].horizontalAdvance(f"{row['pct']}%")
        bw = m["bvw"] if self.app.cfg["battery_orientation"] == "vertical" else m["batt_w"]
        return m["pad"] * 2 + {
            "full": m["icon"] + gap + bw + gap + text_w,
            "compact": m["icon"] + gap + text_w,
            "battery": m["icon"] + gap + bw,
            "text_only": (m["bolt_w"] + gap if row.get("charging") else 0) + text_w,
            "micro": m["icon"],
        }[mode]

    def set_rows(self, rows):
        new = {r["did"] for r in rows}
        if time.monotonic() - self._born > 8:  # não anima a carga inicial
            for did in new - self._seen:
                self._animate(did)
        self._seen = new
        self.rows = rows
        self.relayout()
        self._want = bool(rows) and self.app.cfg["widget_visible"]
        self.sync_shown()
        self.place()
        busy = any(r["connected"] and (r.get("charging") or r["pct"] <= self.app.limit(r["did"])) for r in rows)
        self.tick.start() if busy else self.tick.stop()
        self.update()

    def relayout(self):
        cfg, n = self.app.cfg, len(self.rows)
        H = self._bar_h
        self.mode = "full" if cfg["display_mode"] == "auto" else cfg["display_mode"]
        self.n_rows = 2 if cfg["layout_mode"] == "grid" and n >= 2 else 1
        if self.n_rows == 2:
            pill_h = max(18, min(20, (H - 4) // 2))
        else:
            m0 = metrics(32)
            pill_h = max(18, H - 2 * (m0["glow"] + m0["frame_pad"]) - 2)
        m = self.m = metrics(pill_h, cfg["icon_size"])
        cols = -(-n // self.n_rows) if n else 1
        widths = [self._pill_w(r, self.mode, m) for r in self.rows]
        col_w = [max([widths[i] for i in range(c, n, cols)] or [0]) for c in range(cols)]
        sep_y = max(2, round(0.6 * m["sep"]))
        content_h = self.n_rows * m["h"] + sep_y * (self.n_rows - 1)
        left = m["glow"] + m["frame_pad"]
        top = (H - content_h) / 2
        self.pills = []
        for i in range(n):
            r, c = divmod(i, cols)
            x = left + sum(col_w[:c]) + m["sep"] * c
            self.pills.append(QRectF(x, top + r * (m["h"] + sep_y), col_w[c], m["h"]))
        width = 2 * left + sum(col_w) + m["sep"] * (cols - 1)
        self.frame = QRectF(m["glow"] + 0.5, top - m["frame_pad"] + 0.5,
                            width - 2 * m["glow"] - 1, content_h + 2 * m["frame_pad"] - 1)
        self.setFixedWidth(max(1, round(width)))

    # --- animação de entrada ---
    def _animate(self, did):
        if self.app.cfg["animation"] == "none":
            return
        a = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=520)
        a.valueChanged.connect(lambda v, did=did: (self.anim.__setitem__(did, v), self.update()))
        a.finished.connect(lambda did=did: (self.anim.pop(did, None), self.update()))
        a.start(QAbstractAnimation.DeleteWhenStopped)

    def replay(self):
        for r in self.rows:
            self._animate(r["did"])

    # --- desenho ---
    def _palettes(self):
        """(fundo do tema, cores do conteúdo): sem bordas o texto segue a barra do Windows."""
        cfg = self.app.cfg
        pal = palette(cfg["theme"])
        content = dict(pal)
        if cfg["widget_style"] == "frameless":
            dark = bar_is_dark(cfg["theme"])
            content.update(text="#F9FAFB" if dark else "#111827", sub="#D1D5DB" if dark else "#374151",
                           bg="#1C1C1C" if dark else "#EEEEEE")
        return pal, content

    def paintEvent(self, _):
        if not self.m:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cfg, m = self.app.cfg, self.m
        st = cfg["widget_style"]
        pal, cp = self._palettes()
        op = cfg["widget_opacity"]
        acc = QColor(pal["accent"])
        glow = pal.get("glow")
        p.fillRect(self.rect(), QColor(0, 0, 0, 1))  # quase invisível: só para receber o mouse

        if st in ("standard", "neon"):
            fr, rad = self.frame, m["radius"]
            if st == "standard" and glow:
                for i, alpha in ((3, 22), (2, 38), (1, 60)):
                    c = QColor(acc)
                    c.setAlpha(alpha)
                    p.setPen(QPen(c, 1.2))
                    p.setBrush(Qt.NoBrush)
                    p.drawRoundedRect(fr.adjusted(-i, -i, i, i), rad + i, rad + i)
            bg = QColor(pal["bg"])
            bg.setAlpha(int(255 * op / 100))
            if st == "standard":
                border = QColor(acc)
                border.setAlpha(210 if glow else 150)
                p.setPen(QPen(border, 1.2))
            else:
                p.setPen(QPen(QColor(pal["border"]), 1))
            p.setBrush(bg)
            p.drawRoundedRect(fr, rad, rad)
            if st == "neon":
                p.setPen(QPen(acc, 1.8))
                p.drawLine(QPointF(fr.left() + rad, fr.bottom()), QPointF(fr.right() - rad, fr.bottom()))
            else:
                self._separators(p, pal)

        self._now = time.monotonic()
        for r, row in zip(self.pills, self.rows):
            self._paint_pill(p, r, row, cp, pal, st, op)
        p.end()

    def _separators(self, p, pal):
        c = QColor(pal["sub"])
        c.setAlpha(60)
        p.setPen(QPen(c, 1))
        inset = max(3, 0.16 * self.m["h"])
        for a, b in zip(self.pills, self.pills[1:]):
            if abs(a.top() - b.top()) < 1:
                x = round((a.right() + b.left()) / 2) + 0.5
                p.drawLine(QPointF(x, a.top() + inset), QPointF(x, a.bottom() - inset))
        tops = sorted({round(r.top()) for r in self.pills})
        for t0, t1 in zip(tops, tops[1:]):
            y = round((t0 + self.m["h"] + t1) / 2) + 0.5
            p.drawLine(QPointF(self.frame.left() + inset, y), QPointF(self.frame.right() - inset, y))

    def _paint_pill(self, p, rect, row, cp, pal, st, op):
        cfg, m, mode = self.app.cfg, self.m, self.mode
        h = m["h"]
        t = self.anim.get(row["did"], 1.0)
        anim = cfg["animation"]
        p.save()
        cx, cy = rect.center().x(), rect.center().y()
        opacity = 1.0 if row["connected"] else 0.55
        if anim == "blink":
            opacity *= 1 if int(t * 6) % 2 == 0 else 0.15
        elif anim in ("fade", "scale", "slide", "pulse"):
            opacity *= t
        p.setOpacity(opacity)
        if anim == "scale":
            s = 0.6 + 0.4 * t
            p.translate(cx, cy)
            p.scale(s, s)
            p.translate(-cx, -cy)
        elif anim == "slide":
            p.translate(0, (1 - t) * -14)

        if st == "capsules":
            surf = QColor(pal["surface"])
            surf.setAlpha(int(240 * op / 100))
            pen = QColor(pal["accent"] if pal.get("glow") else pal["border"])
            pen.setAlpha(160 if pal.get("glow") else 120)
            p.setPen(QPen(pen, 1))
            p.setBrush(surf)
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), m["radius"], m["radius"])
        if anim == "pulse" and t < 1:
            ring = QColor(pal["accent"])
            ring.setAlphaF(1 - t)
            p.setPen(QPen(ring, 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1.2, 1.2, -1.2, -1.2), m["radius"], m["radius"])

        pct, charging, did = row["pct"], row.get("charging"), row["did"]
        fill = self.app.level_color(did, pct, charging)
        low = not charging and pct <= self.app.limit(did)
        gap = max(3.0, 0.18 * h)
        x = rect.x() + m["pad"]
        icon = m["icon"]
        has_batt = mode in ("full", "battery")
        text_color = QColor(cp["text"])

        if mode != "text_only":
            iy = cy - icon / 2 - (max(1.5, 0.06 * h) if mode == "micro" else 0)
            irect = QRectF(x, iy, icon, icon)
            if (low and row["connected"] and cfg["blink_alert_enabled"]
                    and blink_on(pct, self.app.limit(did), self._now)):
                halo = QColor(cfg["colors"]["low"])
                halo.setAlpha(70)
                p.setPen(Qt.NoPen)
                p.setBrush(halo)
                p.drawEllipse(irect.adjusted(-2, -2, 2, 2))
            G.draw_device_icon(p, irect, icon_kind(row["kind"]), cp["accent"] if has_batt else fill,
                               style=cfg["icon_style"])
            if charging and mode in ("compact", "micro"):
                bw, bh = max(5, 0.42 * icon), max(7, 0.6 * icon)
                G.draw_bolt(p, QRectF(irect.right() - 0.6 * bw, irect.top() - 0.35 * bh, bw, bh),
                            cfg["colors"]["high"], cp["bg"], 0.9)
            if mode == "micro":
                bar_h = max(2, 0.08 * h)
                bar = QRectF(irect.left() + 1, irect.bottom() + max(1.5, 0.06 * h), icon - 2, bar_h)
                track = QColor(cp["sub"])
                track.setAlpha(70)
                p.setPen(Qt.NoPen)
                p.setBrush(track)
                p.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
                bar.setWidth(max(1.5, bar.width() * pct / 100))
                p.setBrush(fill)
                p.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
            x += icon + gap

        if has_batt:
            vertical = cfg["battery_orientation"] == "vertical"
            bw, bh = (m["bvw"], m["bvh"]) if vertical else (m["batt_w"], m["batt_h"])
            draw = G.draw_battery_vertical if vertical else G.draw_battery
            draw(p, QRectF(x, cy - bh / 2, bw, bh), pct, fill, cp["sub"], None, charging=charging,
                 phase=self._now % 1.6 / 1.6, bolt_fill=cp["text"], bolt_outline=cp["bg"])
            x += bw + gap

        if mode in ("full", "compact", "text_only"):
            if mode == "text_only" and charging:
                G.draw_bolt(p, QRectF(x, cy - m["bolt_h"] / 2, m["bolt_w"], m["bolt_h"]), cfg["colors"]["high"])
                x += m["bolt_w"] + gap
            if mode == "full":
                col = (cfg["colors"]["low"] if low and row["connected"] else
                       cfg["colors"]["high"] if charging else text_color)
            else:
                col = fill
            p.setFont(m["font"])
            p.setPen(QColor(col))
            p.drawText(QRectF(x, rect.top(), rect.right() - x + 2, h), Qt.AlignVCenter | Qt.AlignLeft, f"{pct}%")
        p.restore()

    # --- posição ---
    def place(self):
        rects = taskbar_rects()
        if not rects or not self.isVisible():
            return
        tb, bar, notify = rects
        hwnd = int(self.winId())
        if not self._owned or user32.GetWindowLongPtrW(hwnd, -8) != tb:  # GWLP_HWNDPARENT
            user32.SetWindowLongPtrW(hwnd, -8, tb)
            ex = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, ex | 0x08000000)  # WS_EX_NOACTIVATE
            self._owned = True
        dpr = self.devicePixelRatioF()
        H = round((bar.bottom - bar.top) / dpr)
        self.setFixedHeight(H)
        if H != self._bar_h:
            self._bar_h = H
            self.relayout()
        right = bar.right / dpr
        offset = self.app.cfg["offset"]
        if offset is None:  # padrão: à esquerda da área de notificação e do widget do clima
            offset = (bar.right - notify.left) / dpr + 168
        x = right - offset - self.width()
        wb = widgets_button(tb)  # não cobre o clima, que cresce/encolhe com o texto e a bandeja
        if wb and x < wb[1] / dpr and x + self.width() > wb[0] / dpr:
            x = wb[0] / dpr - self.width() - 4
        x = max(bar.left / dpr, min(x, right - self.width()))
        if self._press is None:
            self.move(round(x), round(bar.top / dpr))
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # TOPMOST, NOSIZE|NOMOVE|NOACTIVATE

    # --- mouse ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().x()
            self._drag = self._press - self.x()
            self.popup.hide()

    def mouseMoveEvent(self, e):
        gx = e.globalPosition().x()
        if self._press is not None:
            if abs(gx - self._press) > 4:
                self.move(round(gx - self._drag), self.y())
            return
        px = e.position().x()
        py = e.position().y()
        i = next((i for i, r in enumerate(self.pills)
                  if r.left() - 4 <= px <= r.right() + 4 and r.top() - 2 <= py <= r.bottom() + 2), None)
        if i is None:
            self.popup.hide()
        else:
            self.popup.show_for(self.rows[i], self.mapToGlobal(QPoint(round(self.pills[i].center().x()), 0)))

    def mouseReleaseEvent(self, e):
        if self._press is None or e.button() != Qt.LeftButton:
            return
        moved = abs(e.globalPosition().x() - self._press) > 4
        self._press = None
        if not moved:  # clique abre o painel, como no original
            self.app.panel.toggle()
            return
        rects = taskbar_rects()
        if rects:
            right = rects[1].right / self.devicePixelRatioF()
            self.app.set("offset", round(right - self.x() - self.width()))

    def leaveEvent(self, _):
        self.popup.hide()

    def contextMenuEvent(self, e):
        self.popup.hide()
        self.app.menu.exec(e.globalPos())


# ---------- painel (flyout) ----------
def stylesheet(c):
    return f"""
    #FlyoutRoot QLabel {{ color: {c['text']}; background: transparent; }}
    QLabel[role="title"] {{ font-size: 15px; font-weight: 700; }}
    QLabel[role="subtitle"] {{ font-size: 12px; color: {c['sub']}; }}
    QLabel[role="section"] {{ font-size: 12px; font-weight: 700; color: {c['sub']}; padding: 4px 2px 0 2px; }}
    QLabel[role="rowtitle"] {{ font-size: 13px; }}
    QLabel[role="rowsub"] {{ font-size: 11px; color: {c['sub']}; }}
    QLabel[role="value"] {{ font-size: 12px; font-weight: 700; color: {c['sub']}; }}
    QScrollArea, QStackedWidget, #Page {{ background: transparent; border: none; }}
    QFrame#Group {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame[role="divider"] {{ background: {c['border']}; border: none; }}
    QFrame#Tabs {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 9px; }}
    QPushButton[kind="tab"] {{ background: transparent; border: none; border-radius: 7px; padding: 6px;
                               color: {c['sub']}; font-size: 12px; font-weight: 600; }}
    QPushButton[kind="tab"]:hover {{ color: {c['text']}; }}
    QPushButton[kind="tab"]:checked {{ background: {c['accent']}; color: {c['on_accent']}; }}
    QPushButton[kind="icon"] {{ background: transparent; border: none; border-radius: 8px; color: {c['sub']};
                                font-family: "{ICON_FONT}"; font-size: 14px; min-width: 30px; min-height: 30px; }}
    QPushButton[kind="icon"]:hover {{ background: {c['border']}; color: {c['text']}; }}
    QPushButton[kind="secondary"] {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']};
                                     border-radius: 8px; padding: 6px 12px; font-size: 12px; font-weight: 600; }}
    QPushButton[kind="secondary"]:hover {{ border-color: {c['accent']}; }}
    QPushButton[kind="chip"] {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']};
                                border-radius: 10px; padding: 2px 10px; font-size: 11px; font-weight: 600; min-height: 16px; }}
    QPushButton[kind="chip"]:hover {{ border-color: {c['accent']}; }}
    QPushButton[kind="chip"]:checked {{ background: {c['accent']}; color: {c['on_accent']}; border-color: {c['accent']}; }}
    QPushButton[kind="disclosure"] {{ background: transparent; border: none; color: {c['sub']}; text-align: left;
                                      font-size: 12px; font-weight: 600; padding: 6px 2px; }}
    QPushButton[kind="disclosure"]:hover {{ color: {c['text']}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px 0 2px 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 36px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    QSlider {{ min-height: 20px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal:disabled {{ background: {c['sub']}; }}
    QSlider::handle:horizontal {{ background: {c['bg']}; border: 3px solid {c['accent']}; width: 10px; height: 10px;
                                  margin: -6px 0; border-radius: 8px; }}
    QSlider::handle:horizontal:disabled {{ border-color: {c['sub']}; }}
    QSpinBox, QLineEdit {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px;
                           padding: 2px 6px; font-size: 12px; min-height: 24px; }}
    QSpinBox {{ font-weight: 700; min-width: 62px; }}
    QSpinBox:hover, QSpinBox:focus, QLineEdit:hover, QLineEdit:focus {{ border-color: {c['accent']}; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
    QComboBox {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px;
                 padding: 4px 10px; font-size: 12px; min-height: 22px; min-width: 120px; }}
    QComboBox:hover, QComboBox:on {{ border-color: {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']};
                                   padding: 4px; outline: none; selection-background-color: {c['accent']};
                                   selection-color: {c['on_accent']}; }}
    QToolTip {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px 8px; }}
    """


def menu_stylesheet(c):
    return f"""
    QMenu {{ background: {c['bg']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px;
             padding: 5px; font-size: 12px; }}
    QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {c['surface']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    """


def round_menu(menu):
    menu.setWindowFlags(menu.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
    menu.setAttribute(Qt.WA_TranslucentBackground)
    return menu


class Toggle(QAbstractButton):
    """Interruptor redondo, no lugar de checkbox."""

    def __init__(self, panel, checked, on_change):
        super().__init__()
        self.panel = panel
        self.setCheckable(True)
        self.setChecked(checked)
        self.toggled.connect(on_change)
        self.setFixedSize(40, 22)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        c = self.panel.pal
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = self.isChecked()
        p.setPen(Qt.NoPen if on else QPen(QColor(c["sub"]), 1.2))
        p.setBrush(QColor(c["accent"]) if on else Qt.NoBrush)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - (8 if on else 10)
        x = r.right() - d - 4 if on else r.left() + 5
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["on_accent"] if on else c["sub"]))
        p.drawEllipse(QRectF(x, r.center().y() - d / 2, d, d))
        p.end()


class DeviceCard(QWidget):
    """Cartão desenhado: ícone com fundo do acento, nome, estado, % + pilha e olho para ocultar da barra."""

    def __init__(self, panel, d, clickable=True):
        super().__init__()
        self.panel, self.d, self.clickable = panel, d, clickable
        self.setFixedHeight(62)
        self.hidden = d["did"] in panel.app.cfg["hidden"]
        self.eye = QPushButton("" if self.hidden else "", self)
        self.eye.setProperty("kind", "icon")
        self.eye.setCursor(Qt.PointingHandCursor)
        self.eye.setToolTip("Mostrar na barra de tarefas" if self.hidden else "Ocultar da barra de tarefas")
        self.eye.clicked.connect(lambda: panel.app.toggle_hidden(d["did"]))
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip("Detalhes, histórico e alerta deste dispositivo")

    def resizeEvent(self, _):
        self.eye.move(self.width() - 12 - 30, (self.height() - 30) // 2)

    def paintEvent(self, _):
        c, d, app = self.panel.pal, self.d, self.panel.app
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(c["border"]))
        p.setBrush(QColor(c["surface"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        acc = QColor(c["accent"] if d["connected"] else c["sub"])
        tint = QColor(acc)
        tint.setAlpha(40)
        box = QRectF(12, 12, 38, 38)
        p.setPen(Qt.NoPen)
        p.setBrush(tint)
        p.drawRoundedRect(box, 10, 10)
        G.draw_device_icon(p, box.adjusted(8, 8, -8, -8), icon_kind(d["kind"]), acc, style=app.cfg["icon_style"])

        right = self.width() - 12 - 30 - 10
        if d["connected"] and d["pct"] is not None:
            f = QFont("Segoe UI")
            f.setPixelSize(15)
            f.setBold(True)
            txt = f"{d['pct']}%"
            tw = QFontMetrics(f).horizontalAdvance(txt)
            p.setFont(f)
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(right - tw, 0, tw, self.height()), Qt.AlignVCenter | Qt.AlignRight, txt)
            bw, bh = 25, 13
            G.draw_battery(p, QRectF(right - tw - 8 - bw, (self.height() - bh) / 2, bw, bh), d["pct"],
                           app.level_color(d["did"], d["pct"], d.get("charging")), c["sub"], None,
                           charging=d.get("charging"), bolt_fill=c["text"], bolt_outline=c["surface"])
            right -= tw + 8 + bw + 10

        f = QFont("Segoe UI")
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(c["text"] if d["connected"] else c["sub"]))
        w = right - 62
        p.drawText(QRectF(62, 12, w, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(d["name"], Qt.ElideRight, int(w)))
        status = app.status_text(d) + (" · oculto" if self.hidden else "")
        f.setPixelSize(11)
        f.setWeight(QFont.Normal)
        p.setFont(f)
        p.setPen(QColor(c["sub"]))
        p.drawText(QRectF(62, 32, w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(status, Qt.ElideRight, int(w)))
        p.end()

    def mouseReleaseEvent(self, e):
        if self.clickable and e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.panel.open_detail(self.d["did"])


class BatteryChart(QWidget):
    """Gráfico do histórico de bateria (últimas 24 h ou 7 dias)."""

    def __init__(self, panel, samples):
        super().__init__()
        self.panel, self.samples, self.days = panel, samples, 1
        self.setFixedHeight(130)

    def set_days(self, n):
        self.days = n
        self.update()

    def paintEvent(self, _):
        c = self.panel.pal
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(34, 8, -6, -20)
        f = QFont("Segoe UI")
        f.setPixelSize(10)
        p.setFont(f)
        for lvl in (0, 50, 100):
            y = r.bottom() - r.height() * lvl / 100
            p.setPen(QPen(QColor(c["border"]), 1, Qt.DashLine if lvl == 50 else Qt.SolidLine))
            p.drawLine(QPoint(round(r.left()), round(y)), QPoint(round(r.right()), round(y)))
            p.setPen(QColor(c["sub"]))
            p.drawText(QRectF(0, y - 8, 30, 16), Qt.AlignRight | Qt.AlignVCenter, f"{lvl}%")
        now = time.time()
        t0 = now - self.days * 86400
        p.setPen(QColor(c["sub"]))
        p.drawText(QRectF(r.left(), r.bottom() + 4, 120, 14), Qt.AlignLeft,
                   "há 24 h" if self.days == 1 else f"há {self.days} dias")
        p.drawText(QRectF(r.right() - 60, r.bottom() + 4, 60, 14), Qt.AlignRight, "agora")
        pts = [(t, v) for t, v in self.samples if t >= t0]
        if len(pts) < 2:
            p.drawText(r, Qt.AlignCenter, "Ainda sem leituras suficientes")
            p.end()
            return

        def xy(t, v):
            return QPointF(r.left() + r.width() * (t - t0) / (now - t0), r.bottom() - r.height() * v / 100)

        line = QPainterPath(xy(*pts[0]))
        for (t, v), (_, prev) in zip(pts[1:], pts):
            line.lineTo(xy(t, prev))  # degrau: o nível vale até a próxima leitura
            line.lineTo(xy(t, v))
        line.lineTo(xy(now, pts[-1][1]))
        area = QPainterPath(line)
        area.lineTo(QPointF(r.right(), r.bottom()))
        area.lineTo(QPointF(xy(*pts[0]).x(), r.bottom()))
        acc = QColor(c["accent"])
        fill = QColor(acc)
        fill.setAlpha(45)
        p.setPen(Qt.NoPen)
        p.setBrush(fill)
        p.drawPath(area)
        p.setPen(QPen(acc, 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(line)
        p.end()


class Panel(QWidget):
    """Painel que abre ao clicar no ícone da bandeja ou no widget: Dispositivos / Geral / Design."""
    W = 372

    def __init__(self, app):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName("FlyoutRoot")
        self.setFixedWidth(self.W)
        self.app = app
        self.tab = 0
        self.detail_did = None
        self.show_disc = False
        self._modal = False
        self._hidden_at = 0.0
        self.body = None
        self.pal = palette(app.cfg["theme"])
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 14, 16, 16)

    # --- construção ---
    def build(self):
        if self.body:  # tira o corpo antigo do layout já, senão o novo é espremido/esticado
            self.root.removeWidget(self.body)
            self.body.hide()
            self.body.deleteLater()
        self.pal = palette(self.app.cfg["theme"])
        self.setStyleSheet(stylesheet(self.pal))
        self.body = QWidget()
        self.root.addWidget(self.body)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addLayout(self._header())
        self.tabs_frame = self._tabs()
        lay.addWidget(self.tabs_frame)
        self.stack = QStackedWidget()
        self.pages = [self._scroll(self._devices_page()), self._scroll(self._general_page()),
                      self._scroll(self._design_page())]
        for pg in self.pages:
            self.stack.addWidget(pg)
        self.stack.setCurrentIndex(self.tab)
        lay.addWidget(self.stack)
        self.body.show()
        self._fit()
        if self.detail_did:
            self.open_detail(self.detail_did)

    def _scroll(self, content):
        content.setObjectName("Page")
        content.setFixedWidth(self.W - 32 - 10)  # largura do painel menos margens e barra de rolagem
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.setWidget(content)
        return s

    def _fit(self):
        h = max(pg.widget().sizeHint().height() for pg in self.pages)
        self.stack.setFixedHeight(min(h, 440))
        bottom = self.geometry().bottom()
        self.root.activate()
        self.adjustSize()
        if self.isVisible():
            self.move(self.x(), bottom - self.height() + 1)

    def _header(self):
        h = QHBoxLayout()
        h.setSpacing(10)
        logo = QLabel("")
        logo.setFixedSize(34, 34)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"background:{self.pal['accent']};color:{self.pal['on_accent']};border-radius:9px;"
                           f"font-family:'{ICON_FONT}';font-size:16px")
        v = QVBoxLayout()
        v.setSpacing(0)
        v.addWidget(self._label(APP_TITLE, "title"))
        self.subtitle = self._label(self._subtitle_text(), "subtitle")
        v.addWidget(self.subtitle)
        h.addWidget(logo)
        h.addLayout(v)
        h.addStretch()
        for glyph, tip, fn in (("", "Buscar dispositivos novamente", self.app.refresh),
                               ("", "Fechar (Esc)", self.hide)):
            h.addWidget(self._icon_button(glyph, tip, fn))
        return h

    def _icon_button(self, glyph, tip, fn):
        b = QPushButton(glyph)
        b.setProperty("kind", "icon")
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def _subtitle_text(self):
        n = len(self.app.panel_devices()[0])
        return "Nenhum dispositivo conectado" if not n else f"{n} dispositivo{'s' if n > 1 else ''} conectado{'s' if n > 1 else ''}"

    def _tabs(self):
        fr = QFrame()
        fr.setObjectName("Tabs")
        hl = QHBoxLayout(fr)
        hl.setContentsMargins(3, 3, 3, 3)
        hl.setSpacing(3)
        grp = self.tab_group = QButtonGroup(fr)
        for i, t in enumerate(("Dispositivos", "Geral", "Design")):
            b = QPushButton(t)
            b.setProperty("kind", "tab")
            b.setCheckable(True)
            b.setChecked(i == self.tab)
            b.setCursor(Qt.PointingHandCursor)
            grp.addButton(b, i)
            hl.addWidget(b)
        grp.idClicked.connect(self._set_tab)
        return fr

    def _set_tab(self, i):
        self.tab = i
        self.tab_group.button(i).setChecked(True)
        self.close_detail()

    @staticmethod
    def _label(text, role, wrap=False):
        lbl = QLabel(text)
        lbl.setProperty("role", role)
        lbl.setWordWrap(wrap)
        return lbl

    def _page(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(8)
        return w, v

    def _group(self, *rows):
        fr = QFrame()
        fr.setObjectName("Group")
        v = QVBoxLayout(fr)
        v.setContentsMargins(14, 8, 14, 8)
        v.setSpacing(6)
        for i, r in enumerate(rows):
            if i:
                div = QFrame()
                div.setProperty("role", "divider")
                div.setFixedHeight(1)
                v.addWidget(div)
            v.addWidget(r)
        return fr

    def _row(self, title, sub, control):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(12)
        t = QVBoxLayout()
        t.setSpacing(2)
        t.addWidget(self._label(title, "rowtitle", True))
        if sub:
            t.addWidget(self._label(sub, "rowsub", True))
        h.addLayout(t, 1)
        if control is not None:
            h.addWidget(control, 0, Qt.AlignVCenter)
        return w

    def _update_row(self):
        """Versão + botão que busca e instala a atualização (ver updater.py)."""
        up = self.app.updater
        btn = QPushButton()
        btn.setProperty("kind", "secondary")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(up.click)
        row = self._row(f"Versão {VERSION}", up.text, btn)
        sub = row.findChildren(QLabel)[-1]

        def show():
            sub.setText(up.text)
            btn.setText(up.action or "Aguarde…")
            btn.setEnabled(bool(up.action))
        show()
        up.changed.connect(show)
        row.destroyed.connect(lambda: up.changed.disconnect(show))  # o painel recria as páginas
        return row

    def _toggle(self, title, sub, checked, fn):
        return self._row(title, sub, Toggle(self, checked, fn))

    def _combo(self, title, sub, names, key):
        combo = QComboBox()
        for k, label in names.items():
            combo.addItem(label, k)
        combo.setCurrentIndex(max(0, combo.findData(self.app.cfg[key])))
        combo.currentIndexChanged.connect(lambda i: self.app.set(key, combo.itemData(i)))
        return self._row(title, sub, combo)

    def _chips(self, options, current, on_pick):
        """Linha de atalhos tipo chip; options = [(rótulo, valor)]."""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        grp = QButtonGroup(w)
        for label, val in options:
            c = QPushButton(label)
            c.setProperty("kind", "chip")
            c.setCheckable(True)
            c.setChecked(val == current)
            c.setCursor(Qt.PointingHandCursor)
            c.clicked.connect(lambda _=False, val=val: on_pick(val))
            grp.addButton(c)
            h.addWidget(c)
        h.addStretch()
        return w

    def _limit_slider(self, title, sub, value, on_change, enabled=True):
        """Barra + campo + atalhos para um limite de alerta (0–99 %)."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(6)
        v.addWidget(self._label(title, "rowtitle", True))
        if sub:
            v.addWidget(self._label(sub, "rowsub", True))
        s = QSlider(Qt.Horizontal)
        s.setRange(0, 99)
        sp = QSpinBox()
        sp.setRange(0, 99)
        sp.setSuffix(" %")
        chips = []

        def setv(val, emit=True):
            for x in (s, sp):
                x.blockSignals(True)
                x.setValue(val)
                x.blockSignals(False)
            for c in chips:
                c.setChecked(c.value == val)
            if emit:
                on_change(val)

        s.valueChanged.connect(setv)
        sp.valueChanged.connect(setv)
        h = QHBoxLayout()
        h.addWidget(s, 1)
        h.addWidget(sp)
        v.addLayout(h)
        hc = QHBoxLayout()
        hc.setSpacing(6)
        for n in (10, 20, 50, 80):
            c = QPushButton(f"{n} %")
            c.value = n
            c.setProperty("kind", "chip")
            c.setCheckable(True)
            c.setCursor(Qt.PointingHandCursor)
            c.clicked.connect(lambda _=False, n=n: setv(n))
            chips.append(c)
            hc.addWidget(c)
        hc.addStretch()
        v.addLayout(hc)
        setv(value, emit=False)
        w.setEnabled(enabled)
        return w

    # --- páginas ---
    def _devices_page(self):
        w, v = self._page()
        conn, disc = self.app.panel_devices()
        v.addWidget(self._label("Conectados", "section"))
        if not conn:
            v.addWidget(self._label("Nenhum dispositivo conectado. Ligue o dispositivo e clique em atualizar.",
                                    "rowsub", True))
        for d in conn:
            v.addWidget(DeviceCard(self, d))
        if disc:
            b = QPushButton(("▾  " if self.show_disc else "▸  ") + f"Desconectados ({len(disc)})")
            b.setProperty("kind", "disclosure")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(self._toggle_disc)
            v.addWidget(b)
            if self.show_disc:
                for d in disc:
                    v.addWidget(DeviceCard(self, d))
        v.addStretch()
        return w

    def _toggle_disc(self):
        self.show_disc = not self.show_disc
        self.refresh_devices()

    def _general_page(self):
        app, cfg = self.app, self.app.cfg
        w, v = self._page()
        v.addWidget(self._label("Posição do widget", "section"))
        reset = QPushButton("Restaurar")
        reset.setProperty("kind", "secondary")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(lambda: app.set("offset", None))
        v.addWidget(self._group(
            self._toggle("Mostrar na barra de tarefas", "Bateria dos dispositivos ao lado da área de notificação.",
                         cfg["widget_visible"], lambda on: app.set("widget_visible", on)),
            self._row("Posição na barra", "Arraste o widget para os lados; a posição fica salva.", reset)))

        v.addWidget(self._label("Comportamento", "section"))
        v.addWidget(self._group(
            self._toggle("Mostrar desconectados na barra", "Exibe o último nível conhecido, esmaecido.",
                         cfg["show_disconnected"], lambda on: app.set("show_disconnected", on)),
            self._toggle("Um ícone por dispositivo na bandeja",
                         "Cada um com seu nível. O Windows pode colocá-los nos ícones ocultos até você fixá-los.",
                         cfg["tray_per_device"], lambda on: app.set("tray_per_device", on))))

        v.addWidget(self._label("Alertas", "section"))
        v.addWidget(self._group(
            self._limit_slider("Avisar quando a bateria estiver abaixo de",
                               "Limite geral. Cada dispositivo pode ter o seu na tela de detalhes.",
                               cfg["threshold"], lambda n: app.set("threshold", n)),
            self._toggle("Aviso de carga completa", "Avisa ao chegar a 100 % para você tirar do carregador.",
                         cfg["full_charge_alert"], lambda on: app.set("full_charge_alert", on)),
            self._toggle("Piscar com bateria baixa", "O ícone na barra pisca enquanto estiver abaixo do limite.",
                         cfg["blink_alert_enabled"], lambda on: app.set("blink_alert_enabled", on))))

        v.addWidget(self._label("Sistema", "section"))
        v.addWidget(self._group(self._toggle("Iniciar com o Windows", None, startup_enabled(), set_startup),
                                self._update_row()))
        v.addStretch()
        return w

    def _design_page(self):
        app, cfg = self.app, self.app.cfg
        w, v = self._page()
        v.addWidget(self._label("Aparência", "section"))
        v.addWidget(self._group(
            self._combo("Tema", "Painel e widget.", THEME_NAMES, "theme"),
            self._combo("Estilo do widget", "Fundo das pílulas na barra.", STYLE_NAMES, "widget_style"),
            self._value_slider("Opacidade do fundo", 30, 100, cfg["widget_opacity"], "%",
                               lambda n: app.set("widget_opacity", n))))

        v.addWidget(self._label("Exibição", "section"))
        v.addWidget(self._group(
            self._combo("O que mostrar", "Como cada dispositivo aparece na barra.", DISPLAY_NAMES, "display_mode"),
            self._combo("Disposição", "Duas linhas cabem mais dispositivos.", LAYOUT_NAMES, "layout_mode"),
            self._combo("Pilha", None, ORIENT_NAMES, "battery_orientation"),
            self._icon_size_row()))

        v.addWidget(self._label("Ícones e animação", "section"))
        v.addWidget(self._group(
            self._combo("Ícones", None, ICON_NAMES, "icon_style"),
            self._combo("Animação de entrada", "Quando um dispositivo aparece na barra.", ANIM_NAMES, "animation")))

        v.addWidget(self._label("Cores da bateria", "section"))
        swatches = QWidget()
        h = QHBoxLayout(swatches)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(8)
        for key, label in (("high", "Alta"), ("medium", "Média"), ("low", "Baixa")):
            b = QPushButton(label)
            col = cfg["colors"][key]
            fg = "#000000" if QColor(col).lightnessF() > 0.6 else "#FFFFFF"
            b.setStyleSheet(f"QPushButton{{background:{col};color:{fg};border:none;border-radius:8px;"
                            f"padding:6px 10px;font-weight:700}}")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, key=key: self.pick_color(key))
            h.addWidget(b)
        h.addStretch()
        reset = QPushButton("Padrão")
        reset.setProperty("kind", "secondary")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(lambda: app.set("colors", dict(DEFAULT_COLORS)))
        h.addWidget(reset)
        v.addWidget(self._group(
            self._row("Níveis", "Alta acima de 50 %, média até 50 %, baixa abaixo do limite de alerta.", None),
            swatches))
        v.addStretch()
        return w

    def _value_slider(self, title, lo, hi, value, unit, on_change):
        w = QWidget()
        sv = QVBoxLayout(w)
        sv.setContentsMargins(0, 4, 0, 4)
        sv.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(self._label(title, "rowtitle"))
        head.addStretch()
        val = self._label(f"{value} {unit}", "value")
        head.addWidget(val)
        sv.addLayout(head)
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(value)
        s.valueChanged.connect(lambda n: (val.setText(f"{n} {unit}"), on_change(n)))
        sv.addWidget(s)
        w.slider, w.value = s, val
        return w

    def _icon_size_row(self):
        """Tamanho dos ícones: automático (segue a barra) ou fixo em px."""
        app, cur = self.app, self.app.cfg["icon_size"]
        w = self._value_slider("Tamanho dos ícones", 10, 32, 16 if cur == "auto" else int(cur), "px",
                               lambda n: app.set("icon_size", n))
        s, val = w.slider, w.value
        auto = QPushButton("Automático")
        auto.setProperty("kind", "chip")
        auto.setCheckable(True)
        auto.setChecked(cur == "auto")
        auto.setCursor(Qt.PointingHandCursor)
        if cur == "auto":
            val.setText("auto")

        def set_auto(on):
            app.set("icon_size", "auto" if on else s.value())
            val.setText("auto" if on else f"{s.value()} px")

        auto.toggled.connect(set_auto)
        s.valueChanged.connect(lambda _: auto.setChecked(False) if auto.isChecked() else None)
        w.layout().itemAt(0).layout().insertWidget(2, auto)
        return w

    # --- detalhe de um dispositivo ---
    def open_detail(self, did):
        d = self.app.device_entry(did)
        if d is None:
            return self.close_detail()
        self.detail_did = did
        if self.stack.count() > 3:
            old = self.stack.widget(3)
            self.stack.removeWidget(old)
            old.deleteLater()
        pg = self._scroll(self._detail_page(d))
        self.stack.addWidget(pg)
        self.stack.setCurrentWidget(pg)
        self.tabs_frame.hide()

    def close_detail(self):
        self.detail_did = None
        if hasattr(self, "stack"):
            if self.stack.count() > 3:
                old = self.stack.widget(3)
                self.stack.removeWidget(old)
                old.deleteLater()
            self.stack.setCurrentIndex(self.tab)
            self.tabs_frame.show()

    def _detail_page(self, d):
        app, cfg, did = self.app, self.app.cfg, d["did"]
        w, v = self._page()
        top = QHBoxLayout()
        top.addWidget(self._icon_button("", "Voltar", self.close_detail))
        top.addWidget(self._label(d["name"], "title"))
        top.addStretch()
        v.addLayout(top)
        v.addWidget(DeviceCard(self, d, clickable=False))

        name = QLineEdit(cfg["names"].get(did, ""))
        name.setPlaceholderText(cfg["known"].get(did, ""))
        name.setFixedWidth(160)
        name.editingFinished.connect(lambda: app.rename(did, name.text()))
        v.addWidget(self._group(self._row("Nome", "Vazio = nome original.", name)))

        v.addWidget(self._label("Histórico", "section"))
        chart = BatteryChart(self, app.history.get(did, []))
        est = fmt_hours(app.estimate(did))
        v.addWidget(self._group(
            self._chips([("24 h", 1), ("7 dias", 7)], 1, chart.set_days), chart,
            self._row("Autonomia estimada", None,
                      self._label(f"{est} restantes" if est else "Calculando…", "value"))))

        v.addWidget(self._label("Alerta deste dispositivo", "section"))
        own = did in cfg["thresholds"]
        slider = self._limit_slider("Avisar abaixo de", None, app.limit(did),
                                    lambda n: app.set_limit(did, n), enabled=own)

        def use_general(on):
            slider.setEnabled(not on)
            app.set_limit(did, None if on else app.limit(did))

        v.addWidget(self._group(
            self._toggle(f"Usar o limite geral ({cfg['threshold']} %)", None, not own, use_general), slider))
        v.addStretch()
        return w

    # --- atualização ---
    def refresh_devices(self):
        if not self.body:
            return
        self.subtitle.setText(self._subtitle_text())
        old = self.pages[0].takeWidget()
        old.deleteLater()
        page = self._devices_page()
        page.setObjectName("Page")
        page.setFixedWidth(self.W - 32 - 10)
        self.pages[0].setWidget(page)
        self._fit()

    def on_config(self, key):
        if not self.isVisible():
            return
        if key in ("theme", "colors"):
            QTimer.singleShot(0, self.build)  # o controle que disparou ainda está na pilha
        elif key in ("hidden", "names", "threshold", "thresholds"):
            self.refresh_devices()

    def pick_color(self, key):
        self._modal = True
        c = QColorDialog.getColor(QColor(self.app.cfg["colors"][key]), None, "Cor da bateria")
        self._modal = False
        if c.isValid():
            self.app.set("colors", {**self.app.cfg["colors"], key: c.name()})
        self.show()
        self.activateWindow()

    # --- mostrar/esconder ---
    def toggle(self):
        if self.isVisible():
            self.hide()
            return
        if time.monotonic() - self._hidden_at < 0.3:  # o clique na bandeja já fechou o painel
            return
        self.detail_did = None
        self.build()
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 11, scr.bottom() - self.height() - 11)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(self.pal["border"]))
        p.setBrush(QColor(self.pal["bg"]))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.end()

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() and not self._modal:
            self.hide()
        super().changeEvent(e)

    def hideEvent(self, e):
        self._hidden_at = time.monotonic()
        super().hideEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_detail() if self.detail_did else self.hide()


# ---------- aplicativo ----------
SAMPLE_EVERY = 600        # s: grava ao menos uma leitura a cada 10 min mesmo sem mudança
HISTORY_DAYS = 7


class App:
    def __init__(self, qapp):
        self.qapp = qapp
        self.cfg = load_config()
        self.history = load_history()   # did -> [[timestamp, %], ...]
        self._hist_dirty = False
        self.sources = {"bt": {}, "vendor": {}, "hid": {}, "ghub": {}}
        self.alerted, self.full_alerted, self.last_pct = set(), set(), {}
        self.dev_trays = {}

        self.updater = Updater(qapp.quit)  # antes do painel, que mostra o estado dele
        self.widget = TaskbarWidget(self)
        self.panel = Panel(self)
        self.tray = QSystemTrayIcon()
        self.menu = round_menu(QMenu())
        self.menu.aboutToShow.connect(lambda: self.menu.setStyleSheet(menu_stylesheet(palette(self.cfg["theme"]))))
        self.menu.addAction("Abrir painel", lambda: self.panel.isVisible() or self.panel.toggle())
        self.menu.addAction("Atualizar agora", self.refresh)
        self.menu.addSeparator()
        self.toggle_act = QAction("Mostrar na barra de tarefas", checkable=True)
        self.toggle_act.setChecked(self.cfg["widget_visible"])
        self.toggle_act.toggled.connect(lambda on: self.set("widget_visible", on))
        self.menu.addAction(self.toggle_act)
        self.menu.addAction("Restaurar posição", lambda: self.set("offset", None))
        self.menu.addSeparator()
        self.menu.addAction("Sair", qapp.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_click)
        self.tray.setIcon(self.make_icon(None))
        self.tray.show()

        self.bt = BluetoothReader()
        self.bt.done.connect(lambda d: self.on_source("bt", d))
        self.ghub = GHubReader()
        self.ghub.done.connect(lambda d: self.on_source("ghub", d))
        self.hidpp = HidppReader()
        self.hidpp.done.connect(lambda d: self.on_source("hid", d))
        self.vendor = VendorReader()
        self.vendor.done.connect(lambda d: self.on_source("vendor", d))
        self.timer = QTimer(interval=INTERVAL_MS, timeout=self.refresh)
        self.timer.start()
        self.hist_timer = QTimer(interval=300_000, timeout=self.flush_history)  # grava o histórico a cada 5 min
        self.hist_timer.start()
        qapp.aboutToQuit.connect(self.flush_history)

        self.redraw()
        self.refresh()

    def _tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.panel.toggle()

    @property
    def devices(self):
        s = self.sources
        out = {**s["bt"], **s["vendor"], **s["hid"], **s["ghub"]}  # G HUB tem prioridade nos dados
        for k in s["hid"].keys() & s["ghub"].keys():  # conectado se qualquer fonte vê o dispositivo
            out[k] = {**out[k], "connected": s["hid"][k]["connected"] or s["ghub"][k]["connected"]}
        return out

    # --- config ---
    def set(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        if key == "widget_visible" and self.toggle_act.isChecked() != value:
            self.toggle_act.setChecked(value)
        self.redraw()
        if key == "animation":
            self.widget.replay()  # mostra a animação escolhida
        self.panel.on_config(key)

    def toggle_hidden(self, did):
        self.set("hidden", sorted(set(self.cfg["hidden"]) ^ {did}))

    def rename(self, did, new):
        names = dict(self.cfg["names"])
        new = new.strip()
        if new and new != self.cfg["known"].get(did):
            names[did] = new
        else:
            names.pop(did, None)
        if names != self.cfg["names"]:
            self.set("names", names)

    def limit(self, did):
        return self.cfg["thresholds"].get(did, self.cfg["threshold"])

    def set_limit(self, did, n):
        th = {k: v for k, v in self.cfg["thresholds"].items() if k != did}
        if n is not None:
            th[did] = n
        self.set("thresholds", th)

    def level_color(self, did, pct, charging=False):
        c = self.cfg["colors"]
        if charging:
            return QColor(c["high"])
        return QColor(c["low"] if pct <= self.limit(did) else c["medium"] if pct <= 50 else c["high"])

    # --- dados ---
    def refresh(self):
        self.bt.refresh()
        self.ghub.refresh()
        self.hidpp.refresh()
        self.vendor.ghub_absent = self.ghub.absent  # headsets Logitech Centurion: só sem G HUB
        self.vendor.refresh()

    def migrate(self, aliases):
        """Leva nomes, ocultos, limites e histórico das chaves antigas do G HUB para as novas."""
        cfg, moved = self.cfg, False
        for old, new in aliases.items():
            if old == new:
                continue
            for k in ("known", "kinds", "names", "thresholds"):
                if old in cfg[k]:
                    cfg[k] = {**{new: cfg[k][old]}, **{x: y for x, y in cfg[k].items() if x != old}}
                    moved = True
            if old in cfg["hidden"]:
                cfg["hidden"] = sorted((set(cfg["hidden"]) - {old}) | {new})
                moved = True
            if old in self.history:
                self.history[new] = sorted(self.history.pop(old) + self.history.get(new, []))
                self._hist_dirty = moved = True
        if moved:
            save_config(cfg)

    def on_source(self, src, devices):
        if src == "ghub":
            self.migrate(self.ghub.aliases)
        self.sources[src] = devices
        names = {did: d["name"] for did, d in devices.items()}
        # o nome do G HUB é o curto ("G915"); o do receptor só vale para quem ainda não tem nome
        known = {**names, **self.cfg["known"]} if src in ("hid", "vendor") else {**self.cfg["known"], **names}
        kinds = {**self.cfg["kinds"], **{did: d["kind"] for did, d in devices.items()}}
        if known != self.cfg["known"] or kinds != self.cfg["kinds"]:
            self.cfg["known"], self.cfg["kinds"] = known, kinds
            save_config(self.cfg)
        for did, d in devices.items():
            if d["connected"]:
                self.record(did, d["battery"])
        self.redraw()
        self.check_alerts()
        if self.panel.isVisible():
            self.panel.refresh_devices()

    def record(self, did, pct):
        now = time.time()
        h = self.history.setdefault(did, [])
        if h and h[-1][1] == pct and now - h[-1][0] < SAMPLE_EVERY:
            return
        h.append([round(now), pct])
        cut = now - HISTORY_DAYS * 86400
        while h and h[0][0] < cut:
            h.pop(0)
        self._hist_dirty = True

    def flush_history(self):
        if self._hist_dirty:
            save_history(self.history)
            self._hist_dirty = False

    def estimate(self, did):
        """Horas restantes: do G HUB quando houver; senão, pela queda recente no histórico."""
        d = self.devices.get(did)
        if not d or not d["connected"] or d.get("charging"):
            return None
        if d.get("hours"):
            return float(d["hours"])
        h = self.history.get(did, [])
        run = h[-1:]  # trecho final em que a bateria só caiu (subiu = carregou: recomeça)
        for t, v in reversed(h[:-1]):
            if v < run[0][1]:
                break
            run.insert(0, [t, v])
        (t0, v0), (t1, v1) = run[0], run[-1]
        if v0 <= v1 or t1 - t0 < 1800:
            return None
        return v1 / ((v0 - v1) / (t1 - t0)) / 3600

    def status_text(self, d):
        if not d["connected"]:
            return "Desconectado" + (f" · último nível {d['pct']}%" if d.get("pct") is not None else "")
        if d.get("charging"):
            return "Carregando"
        est = fmt_hours(self.estimate(d["did"]))
        return f"Conectado · {est} restantes" if est else "Conectado"

    def _entry(self, did, d, orig):
        return {"did": did, "name": self.cfg["names"].get(did, d.get("name", orig)), "pct": d["battery"],
                "connected": d["connected"], "kind": d["kind"], "charging": d.get("charging", False)}

    def device_entry(self, did):
        if did not in self.cfg["known"]:
            return None
        d = self.devices.get(did) or {"battery": None, "connected": False,
                                      "kind": self.cfg["kinds"].get(did, "BT")}
        return self._entry(did, d, self.cfg["known"][did])

    def panel_devices(self):
        """(conectados, desconectados) para o painel, incluindo os ocultos."""
        out = sorted((self.device_entry(did) for did in self.cfg["known"]), key=lambda r: r["name"].lower())
        return [r for r in out if r["connected"]], [r for r in out if not r["connected"]]

    def visible_rows(self):
        rows = [self._entry(did, d, d["name"]) for did, d in self.devices.items()
                if did not in self.cfg["hidden"] and (d["connected"] or self.cfg["show_disconnected"])]
        return sorted(rows, key=lambda r: (not r["connected"], r["name"].lower()))

    # --- saída ---
    def redraw(self):
        rows = self.visible_rows()
        self.widget.set_rows(rows)
        connected = [r for r in rows if r["connected"]]
        low = min(connected, key=lambda r: r["pct"]) if connected else None
        self.tray.setIcon(self.make_icon(low))
        self.tray.setToolTip(APP_TITLE + "\n" + ("\n".join(f"{r['name']}: {r['pct']}%" +
                                                           ("" if r["connected"] else " (desconectado)")
                                                           for r in rows) or "Sem dispositivos"))
        self.update_trays(connected)

    def update_trays(self, rows):
        want = {r["did"]: r for r in rows} if self.cfg["tray_per_device"] else {}
        for did in list(self.dev_trays):
            if did not in want:
                t = self.dev_trays.pop(did)
                t.hide()
                t.deleteLater()
        for did, r in want.items():
            t = self.dev_trays.get(did)
            if t is None:
                t = self.dev_trays[did] = QSystemTrayIcon()
                t.setContextMenu(self.menu)
                t.activated.connect(self._tray_click)
            t.setIcon(self.make_icon(r, number=True))
            t.setToolTip(f"{r['name']}: {r['pct']}%")
            t.show()
        self.tray.setVisible(not want)

    def notify(self, title, msg, icon=QSystemTrayIcon.Information):
        """Notificação por um ícone visível (o geral fica oculto no modo de um ícone por dispositivo)."""
        tray = self.tray if self.tray.isVisible() else next(iter(self.dev_trays.values()), self.tray)
        tray.showMessage(title, msg, icon, 10_000)

    def check_alerts(self):
        for did, d in self.devices.items():
            name = self.cfg["names"].get(did, d["name"])
            pct = d["battery"]
            if not d["connected"] or did in self.cfg["hidden"] or pct > self.limit(did):
                self.alerted.discard(did)  # rearma quando sobe acima do limite
            elif did not in self.alerted:
                self.alerted.add(did)
                self.notify("Bateria baixa", f"{name}: {pct}%", QSystemTrayIcon.Warning)
            prev = self.last_pct.get(did)
            if d["connected"]:
                self.last_pct[did] = pct
            if pct < 95:
                self.full_alerted.discard(did)
            elif (self.cfg["full_charge_alert"] and d["connected"] and pct >= 100 and did not in self.full_alerted
                  and prev is not None and prev < 100):  # só quando chegou a 100 agora, não ao abrir o app
                self.full_alerted.add(did)
                self.notify("Carga completa", f"{name} chegou a 100 %. Já pode tirar do carregador.")

    def make_icon(self, row, number=False):
        """Ícone da bandeja: pilha do menor nível, ou (por dispositivo) o número sobre a cor do nível."""
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        fill = self.level_color(row["did"], row["pct"]) if row else QColor("#808080")
        if number:
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(2, 6, 60, 52, 12, 12)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Segoe UI", 26, QFont.Bold))
            p.drawText(pm.rect(), Qt.AlignCenter, str(min(row["pct"], 99)))
        else:
            fg = QColor("#FFFFFF" if bar_is_dark(self.cfg["theme"]) else "#1B1B1F")
            G.draw_battery(p, QRectF(2, 14, 60, 36), row["pct"] if row else None, fill, fg)
        p.end()
        return QIcon(pm)


class NoWheel(QObject):
    """A roda do mouse rola o painel em vez de mudar caixas de seleção e controles deslizantes."""

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QSlider, QSpinBox)):
            w = obj.parent()
            while w and not isinstance(w, QScrollArea):
                w = w.parent()
            if w:
                QApplication.sendEvent(w.verticalScrollBar(), e)
            return True
        return False


def main():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(CONFIG_DIR / "app.lock"))
    if not lock.tryLock(10_000 if "--restart" in sys.argv else 100):  # --restart: o app antigo ainda fecha
        return  # já está rodando
    log = open(CONFIG_DIR / "erros.log", "a", encoding="utf-8", buffering=1)  # pythonw não tem console
    sys.stderr = log
    faulthandler.enable(log)  # registra até quedas nativas (ex.: driver USB)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "iniciado", file=log)
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setStyle("Fusion")
    qapp.setFont(QFont("Segoe UI", 9))
    no_wheel = NoWheel(qapp)
    qapp.installEventFilter(no_wheel)
    if startup_enabled() or _old_run_entry():  # mantém o atalho atualizado e migra a entrada antiga
        set_startup(True)
    app = App(qapp)  # noqa: F841 (mantém referência viva)
    code = qapp.exec()
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "encerrado normalmente", code, file=log)
    sys.exit(code)


if __name__ == "__main__":
    main()
