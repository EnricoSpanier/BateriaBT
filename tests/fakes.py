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
