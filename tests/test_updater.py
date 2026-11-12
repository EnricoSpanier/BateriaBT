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


REL = b'{"tag_name": "v9.0.0", "html_url": "h", "assets": []}'


def test_release_nova_pelo_python_com_git(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(up, "ROOT", tmp_path)
    u = _updater(monkeypatch, False)
    u._on_release(REL)
    assert u.action == "Atualizar para 9.0.0"


def test_release_nova_pelo_python_sem_git(monkeypatch, tmp_path):
    monkeypatch.setattr(up, "ROOT", tmp_path)
    u = _updater(monkeypatch, False)
    u._on_release(REL)
    assert u.action == "Buscar atualização" and "git" in u.text


def test_git_pull_falhou_nao_reinicia(monkeypatch):
    u = _updater(monkeypatch, False)
    calls, started = [], []

    class R:
        returncode, stdout, stderr = 1, "", "fatal: Not possible to fast-forward, aborting."
    monkeypatch.setattr(up.subprocess, "run", lambda args, **k: calls.append(args) or R())
    monkeypatch.setattr(up.subprocess, "Popen", lambda *a, **k: started.append(a))
    u._git_update()
    u._after_git("fatal: Not possible to fast-forward, aborting.")
    assert calls == [["git", "pull", "--ff-only"]] and not started  # pip nem roda
    assert "fast-forward" in u.text and u.action == "Buscar atualização"


def test_git_ok_instala_dependencias_e_reinicia(monkeypatch):
    quit_ = []
    monkeypatch.setattr(up.sys, "frozen", False, raising=False)
    u = up.Updater(quit_app=lambda: quit_.append(1))
    calls, started, done = [], [], []

    class R:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(up.subprocess, "run", lambda args, **k: calls.append(args) or R())
    monkeypatch.setattr(up.subprocess, "Popen", lambda args, **k: started.append(args))
    u._git_done.disconnect(u._after_git)
    u._git_done.connect(done.append)
    u._git_update()
    assert done == [""] and calls[1][-3:] == ["install", "-q", "-r", "requirements.txt"][-3:]
    u._after_git("")
    assert started[0][-2:] == [str(up.ROOT / "bateria_bt.py"), "--restart"] and quit_


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
