"""ASUS ROG: mouses e teclados sem fio (comandos 12 07 e 12 01, documentados pelo G-Helper e por
projetos de bateria ROG). Só consulta. Mouse dormindo responde FF AA e aparece como desconectado."""
from . import Model, pad, xfer

VID = 0x0B05


def _query(h, rid, cmd):
    """Pedido 12 <cmd>. Sem report ID (rid 0) a resposta vem sem ele; com ID (receptor Omni), com ele.
    Devolve (resposta, deslocamento) ou None."""
    off = 0 if rid == 0 else 1
    want = [0x12, cmd]
    r = xfer(h, pad([rid, 0x12, cmd], 65 if rid == 0 else 64), 64,
             lambda r: len(r) > off + 10 and list(r[off:off + 2]) in (want, [0xFF, 0xAA]))
    if not r or list(r[off:off + 2]) != want:  # FF AA = dormindo
        return None
    return r, off


def mouse(rid=0, scale=1):
    def read(h, m):
        got = _query(h, rid, 0x07)
        if not got:
            return None
        r, off = got
        pct, charging = r[off + 4] * scale, r[off + 9] > 0
        if pct > 100 or (pct == 0 and not charging):  # 0 sem carga = dormindo
            return None
        return pct, charging
    return read


def keyboard(rid=0, idx=5):
    def read(h, m):
        got = _query(h, rid, 0x01)
        if not got:
            return None
        r, off = got
        pct = r[off + idx]
        return (pct, r[off + 8] == 1) if pct <= 100 else None
    return read


def _m(pids, name, read, iface=0):
    return [Model(VID, p, name, "MOUSE", read, interface=iface) for p in pids]


MODELS = [
    *_m([0x197D, 0x197F], "ASUS ROG Gladius III Wireless", mouse()),
    *_m([0x1A70, 0x1A72], "ASUS ROG Gladius III Wireless AimPoint", mouse()),
    *_m([0x1B0A, 0x1B0C], "ASUS ROG Gladius III Wireless AimPoint EVA-02", mouse()),
    *_m([0x18E3, 0x18E5], "ASUS ROG Chakram", mouse(scale=25)),
    *_m([0x1A18, 0x1A1A], "ASUS ROG Chakram X", mouse()),
    *_m([0x18A0], "ASUS ROG Gladius II Wireless", mouse(scale=25), iface=2),
    *_m([0x1977, 0x1979], "ASUS ROG Spatha X", mouse()),
    *_m([0x195E, 0x1960], "ASUS ROG Keris Wireless", mouse(scale=25)),
    *_m([0x1A66, 0x1A68], "ASUS ROG Keris Wireless AimPoint", mouse()),
    *_m([0x1A92, 0x1A94], "ASUS ROG Harpe Ace Aim Lab Edition", mouse()),
    *_m([0x1B67], "ASUS ROG Harpe Ace Extreme", mouse()),
    *[Model(VID, p, "ASUS ROG Azoth", "KEYBOARD", keyboard(), interface=1) for p in (0x1A83, 0x1A85)],
    *[Model(VID, p, "ASUS ROG Falchion", "KEYBOARD", keyboard(idx=10), interface=1) for p in (0x193C, 0x193E)],
    Model(VID, 0x1A07, "ASUS ROG Strix Scope RX TKL Wireless Deluxe", "KEYBOARD", keyboard(), usage_page=0xFF00),
    # receptor ROG Omni: mouses na coleção 0xFF01 (report 3), teclados na 0xFF00 (report 2)
    Model(VID, 0x1ACE, "Mouse ASUS ROG (receptor Omni)", "MOUSE", mouse(rid=3), usage_page=0xFF01),
    Model(VID, 0x1ACE, "Teclado ASUS ROG (receptor Omni)", "KEYBOARD", keyboard(rid=2), usage_page=0xFF00),
]
