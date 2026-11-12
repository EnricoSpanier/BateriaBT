"""Glorious Model O / Model D Wireless (chip SinoWealth): feature report com o opcode de bateria 0x83.
Fontes: glorious-indicator, GloriousBatteryMonitor, glorious-ctl. A família Model O 2 / I 2 / D 2 fica de
fora: pelo receptor ela devolve o último valor ouvido ou não responde a pedido."""
import time

from . import Model, pad

VID = 0x258A


def read(h, m):
    h.send_feature_report(pad([0x00, 0x00, 0x00, 0x02, 0x02, 0x00, 0x83], 65))
    time.sleep(0.08)  # o receptor leva 50-100 ms para repassar ao mouse
    r = list(h.get_feature_report(0x00, 65))
    if len(r) < 9 or r[1] != 0xA1 or r[6] != 0x83 or r[8] > 100:  # 0xA4 = mouse dormindo/fora de alcance
        return None
    return r[8], r[7] == 1


# a coleção varia com o firmware: 0xFFFF nos novos, 0xFF01 nos antigos
MODELS = [Model(VID, pid, name, "MOUSE", read, usage_page=page)
          for pid, name in ((0x2011, "Glorious Model O Wireless"), (0x2022, "Glorious Model O Wireless"),
                            (0x2012, "Glorious Model D Wireless"), (0x2023, "Glorious Model D Wireless"))
          for page in (0xFFFF, 0xFF01)]
