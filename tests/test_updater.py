import hashlib

import updater as up


def test_versoes():
    assert up.parse_version("v1.0.10") == (1, 0, 10)
    assert up.is_newer("v1.0.10", "1.0.9") and up.is_newer("1.1", "1.0.9")
    assert not up.is_newer("v1.0.0", "1.0.0") and not up.is_newer("0.9.9", "1.0.0")


def test_pick_asset():
    rel = {"assets": [{"name": "outro.zip", "browser_download_url": "x"},
                      {"name": "BateriaBT-Setup.exe", "browser_download_url": "u", "digest": "sha256:ab"}]}
    assert up.pick_asset(rel) == ("u", "ab")
    assert up.pick_asset({"assets": [{"name": "BateriaBT-Setup.exe", "browser_download_url": "u"}]}) == ("u", None)
    assert up.pick_asset({"assets": []}) is None


def test_sha():
    data = b"instalador"
    assert up.sha_ok(data, hashlib.sha256(data).hexdigest().upper())
    assert up.sha_ok(data, None)  # Release antiga sem digest: só confia no HTTPS
    assert not up.sha_ok(data, "00" * 32)


def _updater(monkeypatch, frozen):
    monkeypatch.setattr(up.sys, "frozen", frozen, raising=False)
    u = up.Updater(quit_app=lambda: None)
    return u


def test_release_nova_no_exe(monkeypatch):
    u = _updater(monkeypatch, True)
    u._on_release(b'{"tag_name": "v9.0.0", "html_url": "h", "assets": [{"name": "BateriaBT-Setup.exe", '
                  b'"browser_download_url": "u"}]}')
    assert u.action == "Atualizar para 9.0.0" and "9.0.0" in u.text


def test_release_nova_rodando_pelo_python(monkeypatch):
    u = _updater(monkeypatch, False)
    u._on_release(b'{"tag_name": "v9.0.0", "html_url": "h", "assets": []}')
    assert u.action == "Abrir página" and "git pull" in u.text


def test_ja_na_mais_recente(monkeypatch):
    u = _updater(monkeypatch, True)
    u._on_release(('{"tag_name": "v%s", "assets": []}' % up.VERSION).encode())
    assert u.action == "Buscar atualização" and "mais recente" in u.text


def test_download_corrompido_nao_roda(monkeypatch):
    u = _updater(monkeypatch, True)
    ran = []
    monkeypatch.setattr(up.subprocess, "Popen", lambda *a, **k: ran.append(a))
    u._run(b"x", "00" * 32)
    assert not ran and "corrompido" in u.text
