"""Corsair sem fio: headsets (HeadsetControl) e mouses/teclados (protocolos Bragi e NXP, documentados
pelo OpenLinkHub e pelo ckb-next)."""
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


# --- mouses e teclados, protocolo Bragi (OpenLinkHub, ckb-next) ---
# Só faz GET de propriedade, sem pôr o aparelho no "modo software" que o iCUE usa.
BRAGI = {  # PID do aparelho (cabo, e o que o receptor informa do pareado): (nome, tipo)
    0x1B80: ("Corsair Dark Core RGB PRO", "MOUSE"), 0x1B7E: ("Corsair Dark Core RGB PRO SE", "MOUSE"),
    0x1B5E: ("Corsair Harpoon RGB Wireless", "MOUSE"), 0x2B2E: ("Corsair Harpoon RGB Wireless", "MOUSE"),
    0x1B4C: ("Corsair Ironclaw RGB Wireless", "MOUSE"), 0x2B32: ("Corsair Ironclaw RGB Wireless", "MOUSE"),
    0x1BB5: ("Corsair M65 RGB Ultra Wireless", "MOUSE"), 0x1BD6: ("Corsair M65 RGB Ultra Wireless", "MOUSE"),
    0x1BF1: ("Corsair M75 Wireless", "MOUSE"), 0x2B08: ("Corsair M75 Wireless", "MOUSE"),
    0x1BF2: ("Corsair M75 AIR Wireless", "MOUSE"), 0x1BB8: ("Corsair Nightsabre Wireless", "MOUSE"),
    0x1BDB: ("Corsair Scimitar RGB Elite Wireless", "MOUSE"), 0x2B22: ("Corsair Scimitar Elite Wireless SE", "MOUSE"),
    0x1BB2: ("Corsair Darkstar RGB Wireless", "MOUSE"), 0x1B98: ("Corsair Sabre RGB Pro Wireless", "MOUSE"),
    0x1BAB: ("Corsair K100 AIR Wireless", "KEYBOARD"), 0x1B6E: ("Corsair K57 RGB Wireless", "KEYBOARD"),
    0x2B10: ("Corsair K65 PLUS Wireless", "KEYBOARD"), 0x2B11: ("Corsair K65 PLUS Wireless", "KEYBOARD"),
    0x2B23: ("Corsair K65 PLUS Wireless", "KEYBOARD"), 0x1BB6: ("Corsair K70 PRO Mini Wireless", "KEYBOARD"),
    0x2B02: ("Corsair K70 Core TKL Wireless", "KEYBOARD"),
}
SLIPSTREAM = [0x1BDC, 0x1B7F, 0x1BA6, 0x2B00, 0x1B65, 0x1B81, 0x2B07, 0x1B94, 0x1B62, 0x1B66]  # receptores


def _bragi_get(h, ep, prop):
    """GET de propriedade: 00 <endpoint> 02 <prop>. Resposta: [1] = 02 (eco), [2] = erro, [3..4] = valor LE."""
    flush(h)
    r = xfer(h, pad([0x00, ep, 0x02, prop], 65), 64, lambda r: len(r) > 4 and r[1] == 0x02)
    return r[3] | r[4] << 8 if r and r[2] == 0x00 else None


def _bragi_battery(h, ep):
    v = _bragi_get(h, ep, 0x0F)  # décimos de %
    if not v or v > 1000:
        return None
    return v // 10, _bragi_get(h, ep, 0x10) == 1  # 1 = carregando, 2 = descarregando, 3 = cheio


def read_bragi(h, m):
    return _bragi_battery(h, 0x08)


def read_slipstream(h, m):
    """O receptor (0x08) diz quais aparelhos estão pareados; cada um responde em 0x08 | n."""
    bits = _bragi_get(h, 0x08, 0x36)
    for n in range(1, 8):
        if bits and bits & (1 << n):
            r = _bragi_battery(h, 0x08 | n)
            if r:
                name, kind = BRAGI.get(_bragi_get(h, 0x08 | n, 0x12), ("Corsair sem fio", "MOUSE"))
                return (*r, name, kind)
    return None


# --- protocolo NXP antigo (Dark Core, Dark Core SE, K63 Wireless): feature report 0E 50, nível 0-4 ---
NXP = {0x1B35: ("Corsair Dark Core RGB", "MOUSE"), 0x1B64: ("Corsair Dark Core RGB", "MOUSE"),
       0x1B4B: ("Corsair Dark Core RGB SE", "MOUSE"), 0x1B51: ("Corsair Dark Core RGB SE", "MOUSE"),
       0x1B45: ("Corsair K63 Wireless", "KEYBOARD"), 0x1B50: ("Corsair K63 Wireless", "KEYBOARD"),
       0x1B8C: ("Corsair K63 Wireless", "KEYBOARD"), 0x1B8F: ("Corsair K63 Wireless", "KEYBOARD")}


def read_nxp(h, m):
    h.send_feature_report(pad([0x00, 0x0E, 0x50], 65))
    r = list(h.get_feature_report(0, 65))
    if len(r) < 7 or r[1:3] != [0x0E, 0x50] or r[5] > 4:
        return None
    return r[5] * 25, r[6] == 2  # 2 = carregando (ckb-next)


BRAGI_COLL = dict(usage_page=0xFF42, interface=1)
MODELS += [
    *[Model(VID, pid, name, kind, read_bragi, **BRAGI_COLL) for pid, (name, kind) in BRAGI.items()],
    *[Model(VID, pid, "Receptor Corsair Slipstream", "MOUSE", read_slipstream, **BRAGI_COLL) for pid in SLIPSTREAM],
    *[Model(VID, pid, name, kind, read_nxp, interface=1) for pid, (name, kind) in NXP.items()],
]
