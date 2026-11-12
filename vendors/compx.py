"""Mouses com chip Compx/Nordic (Pulsar, Hitscan, VGN, VXE, ATK, Redragon M916): quadro de 17 bytes no
report 8 da coleção FF02:0002. O protocolo é do chip, não da marca (ATK_tray, mouse_tray, HaloBattery,
vigil-watt, hitscan-battery). O comando 0x04 só lê; o mouse dormindo não responde."""
from . import Model, xfer

REQUEST = bytes([0x08, 0x04] + [0] * 14 + [0x49])  # soma dos 17 bytes = 0x55


def _ok(r):
    return (len(r) >= 17 and r[0] == 0x08 and r[1] == 0x04 and r[2] == 0 and sum(r[:17]) & 0xFF == 0x55
            and bytes(r[:17]) != REQUEST and r[6] <= 100)  # REQUEST = eco do próprio pedido


def read(h, m):
    r = xfer(h, REQUEST, 17, _ok, timeout=1.0, wait=0.1)
    if not r:
        return None
    return r[6], bool(r[7]) and r[6] < 100  # [7] = cabo ligado, não corrente de carga


def _m(vid, pids, name):
    return [Model(vid, p, name, "MOUSE", read, usage_page=0xFF02, usage=0x0002) for p in pids]


MODELS = [
    *_m(0x3554, [0xF507, 0xF508], "Pulsar X2 / Xlite V3"),
    *_m(0x3710, [0x3414, 0x5406, 0x3527], "Pulsar CrazyLight"),
    *_m(0x3770, [0x0100, 0x0200], "Hitscan Hyperlight"),
    *_m(0x3554, [0xFB56, 0xFB57], "VGN F2 Master+"),
    *_m(0x3554, [0xFB3E, 0xFB3D], "VGN F2 Pro Max"),
    *_m(0x3554, [0xF503, 0xF502], "VGN F1 Pro"),
    *_m(0x3554, [0xF58A, 0xF58C], "VXE R1 Pro Max"),
    *_m(0x3554, [0xF58E, 0xF58F], "VXE R1 SE+"),
    *_m(0x373B, [0x1085], "VXE R1 SE+"),
    *_m(0x373B, [0x104D, 0x103F], "VXE MAD R"),
    *_m(0x373B, [0x1040, 0x104C], "VXE MAD R Major+"),
    *_m(0x373B, [0x1031, 0x102E], "ATK F1 Ultimate"),
    *_m(0x373B, [0x101B, 0x101A, 0x1015], "ATK F1 Pro Max"),
    *_m(0x373B, [0x1303], "ATK (receptor 8K)"),
    *_m(0x373B, [0x12A9], "ATK F1 V3 Ultimate+"),
    *_m(0x373B, [0x1278, 0x1293], "ATK A9 Air Master+"),
    *_m(0x3554, [0xF54D, 0xF54F], "Redragon M916 ULT"),
    *_m(0x3554, [0xF5D5, 0xF55D, 0xF55E], "Redragon M916 Pro"),
]
