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
