"""Headsets Logitech fora do HID++: Astro A50 Gen 5 / A50 X (base) e G522 LIGHTSPEED (dongle), pelo
transporte "Centurion": quadro de 64 bytes `<prefixo 2 bytes> <len> <flags> <payload>`, com feature de
bateria 0x0104. Fontes: HeadsetControl (logitech_astro_a50.hpp, logitech_centurion_protocol.hpp,
logitech_g522_lightspeed.hpp) e as capturas do G HUB no open-g-hub. Só Root.getFeature e a leitura da
bateria (função 0); no G522 essas mesmas leituras vão pela bridge 0x0003. Spec:
docs/superpowers/specs/2026-11-12-logitech-centurion-design.md."""
from . import Model, pad, xfer

VID = 0x046D
SW = 0x0A  # swId próprio (G HUB usa 0x0B, HeadsetControl 0x0C/0x01)
A50 = [0x02, 0x0C]
G522 = [0x50, 0x23]
BRIDGE, BATTERY = [0x00, 0x03], [0x01, 0x04]  # IDs de feature, big-endian


def frame(prefix, payload):
    return pad(bytes(prefix) + bytes([len(payload) + 1, 0x00]) + bytes(payload), 64)


def payload(r, prefix):
    if len(r) < 5 or list(r[:2]) != prefix or not 1 < r[2] <= len(r) - 3:
        return None
    return list(r[4:3 + r[2]])


def _direct(h, prefix, idx, params, timeout):
    """Função 0 do índice `idx` direto no aparelho; devolve os parâmetros da resposta."""
    def ok(r):
        p = payload(r, prefix)
        return bool(p) and len(p) >= 3 and p[0] == idx and p[1] == SW
    r = xfer(h, frame(prefix, [idx, SW, *params]), 64, ok, timeout=timeout)
    return payload(r, prefix)[2:] if r else None


def _index(p):
    return p[0] if p and 1 <= p[0] <= 0x7F else None  # 0 = feature ausente; 0xFF = erro


def read_a50(h, m):
    bat = _index(_direct(h, A50, 0x00, BATTERY, 1.0))
    if bat is None:
        return None
    b = _direct(h, A50, bat, [], 1.0)
    if not b or b[0] > 100:  # sem resposta = fone fora/desligado
        return None
    return b[0], b[2] == 1  # estado: 0 descarregando, 1 carregando, 3 cheio na doca


def _bridge(h, br, sub, params):
    """Função 0 do índice `sub` no fone, pela bridge `br` (função 1 da bridge = enviar mensagem). A
    resposta vem num evento (br, 0x10) cujo payload interno ecoa índice e swId; o ACK (br, 0x1A) é
    ignorado e o evento de conexão (br, 0x00) com [3] == 0 = fone desligado."""
    inner = [0x00, sub, SW, *params]

    def ok(r):
        p = payload(r, G522)
        if not p or len(p) < 4 or p[0] != br:
            return False
        if p[1] == 0x00:
            return p[3] == 0x00
        return p[1] == 0x10 and len(p) >= 7 and p[4] == 0x00 and p[5] == sub and p[6] == SW
    r = xfer(h, frame(G522, [br, 0x10 | SW, len(inner) >> 8, len(inner) & 0xFF, *inner]), 64, ok)
    p = payload(r, G522) if r else None
    return p[7:] if p and p[1] == 0x10 else None


def read_g522(h, m):
    br = _index(_direct(h, G522, 0x00, BRIDGE, 0.5))
    bat = _index(_bridge(h, br, 0x00, BATTERY)) if br else None
    b = _bridge(h, br, bat, []) if bat else None
    if not b or len(b) < 3 or b[0] > 100:
        return None
    return b[0], b[2] in (1, 2)


MODELS = [
    Model(VID, 0x0B1C, "Astro A50 Gen 5", "HEADSET", read_a50, usage_page=0xFF32, usage=0x0074),
    Model(VID, 0x0B0B, "Astro A50 X", "HEADSET", read_a50, usage_page=0xFF32, usage=0x0074),
    Model(VID, 0x0B18, "Logitech G522", "HEADSET", read_g522, usage_page=0xFFA0, usage=0x0001, interface=3),
]
