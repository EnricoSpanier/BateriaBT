"""Busca a Ãºltima Release no GitHub e atualiza: no app instalado (.exe) baixa e roda o instalador novo;
rodando pelo Python num clone do git, faz git pull, instala as dependÃªncias e reinicia o app."""
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

VERSION = "1.2.0"
API = "https://api.github.com/repos/EnricoSpanier/BateriaBT/releases/latest"
ASSET = "BateriaBT-Setup.exe"
ROOT = Path(__file__).resolve().parent
NO_WINDOW = subprocess.CREATE_NO_WINDOW  # pythonw nÃ£o tem console: sem piscar janela preta


def parse_version(tag):
    """'v1.2.10' -> (1, 2, 10); o que nÃ£o for nÃºmero vira 0."""
    return tuple(int(p) if p.isdigit() else 0 for p in tag.strip().lstrip("vV").split("."))


def is_newer(tag, current):
    return parse_version(tag) > parse_version(current)


def pick_asset(release):
    """(url do instalador, sha256 informado pelo GitHub ou None), ou None se a Release nÃ£o tem instalador."""
    for a in release.get("assets", []):
        if a.get("name") == ASSET:
            digest = a.get("digest") or ""
            return a["browser_download_url"], digest[7:] if digest.startswith("sha256:") else None
    return None


def sha_ok(data, expected):
    return expected is None or hashlib.sha256(data).hexdigest() == expected.lower()


class Updater(QObject):
    """Estado para a linha "VersÃ£o" do painel: `text` (situaÃ§Ã£o) e `action` (rÃ³tulo do botÃ£o, ou "" = sem
    botÃ£o ativo). O clique chama `click()`, que faz a prÃ³xima etapa."""
    changed = Signal()
    _git_done = Signal(str)  # erro ("" = ok), vindo da thread do git pull
    _git_step = Signal(str)  # texto da etapa, vindo da mesma thread

    def __init__(self, quit_app):
        super().__init__()
        self.net = QNetworkAccessManager(self)
        self.quit_app = quit_app
        self.text, self.action = "Busca a versÃ£o nova no GitHub.", "Buscar atualizaÃ§Ã£o"
        self.release = None
        self._git_done.connect(self._after_git)
        self._git_step.connect(lambda text: self._set(text, ""))

    def _set(self, text, action):
        self.text, self.action = text, action
        self.changed.emit()

    def _get(self, url, done, progress=None):
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", f"BateriaBT/{VERSION}".encode())
        reply = self.net.get(req)
        if progress:
            reply.downloadProgress.connect(progress)
        reply.finished.connect(lambda: self._finished(reply, done))

    def _finished(self, reply, done):
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError:
            self._set("Sem conexÃ£o com o GitHub. Tente de novo mais tarde.", "Buscar atualizaÃ§Ã£o")
            return
        try:
            done(bytes(reply.readAll()))
        except Exception as e:  # resposta inesperada: nÃ£o derruba o app
            print("erro atualizaÃ§Ã£o:", e, file=sys.stderr)
            self._set("NÃ£o foi possÃ­vel ler a resposta do GitHub.", "Buscar atualizaÃ§Ã£o")

    def click(self):
        if self.action == "Buscar atualizaÃ§Ã£o":
            self._set("Buscandoâ€¦", "")
            self._get(API, self._on_release)
        elif self.action.startswith("Atualizar"):
            if getattr(sys, "frozen", False):
                self._download()
            else:
                self._set("Baixando o cÃ³digo novoâ€¦", "")
                threading.Thread(target=self._git_update, daemon=True).start()

    def _on_release(self, data):
        rel = json.loads(data)
        tag = rel.get("tag_name", "")
        if not is_newer(tag, VERSION):
            self._set(f"VocÃª estÃ¡ na versÃ£o mais recente ({VERSION}).", "Buscar atualizaÃ§Ã£o")
            return
        self.release = rel
        new = tag.lstrip("vV")
        if pick_asset(rel) if getattr(sys, "frozen", False) else (ROOT / ".git").exists():
            self._set(f"VersÃ£o {new} disponÃ­vel.", f"Atualizar para {new}")
        else:  # Python sem git (ZIP) ou Release sem instalador
            self._set(f"VersÃ£o {new} disponÃ­vel. Esta pasta nÃ£o Ã© um clone do git: veja o README.",
                      "Buscar atualizaÃ§Ã£o")

    @staticmethod
    def _run_cmd(args):
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode:
            raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or ["falhou"])[-1])

    def _git_update(self):
        """Roda numa thread: git pull (sÃ³ avanÃ§o rÃ¡pido) e dependÃªncias. Erro = nada reinicia."""
        python = Path(sys.executable).with_name("python.exe")
        try:
            self._run_cmd(["git", "pull", "--ff-only"])
            self._git_step.emit("Instalando dependÃªnciasâ€¦")
            self._run_cmd([str(python), "-m", "pip", "install", "-q", "-r", "requirements.txt"])
            self._git_done.emit("")
        except Exception as e:
            print("erro atualizaÃ§Ã£o git:", e, file=sys.stderr)
            self._git_done.emit(str(e) or "falhou")

    def _after_git(self, err):
        if err:
            self._set(f"NÃ£o deu para atualizar: {err}", "Buscar atualizaÃ§Ã£o")
            return
        self._set("Reiniciandoâ€¦", "")
        # o app novo espera o atual soltar o app.lock (ver main, --restart)
        subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")), str(ROOT / "bateria_bt.py"), "--restart"],
                         cwd=ROOT, creationflags=subprocess.DETACHED_PROCESS)
        self.quit_app()

    def _download(self):
        url, sha = pick_asset(self.release)
        self._set("Baixandoâ€¦", "")
        self._get(url, lambda data: self._run(data, sha),
                  lambda got, total: total > 0 and self._set(f"Baixandoâ€¦ {got * 100 // total} %", ""))

    def _run(self, data, sha):
        if not sha_ok(data, sha):
            self._set("O arquivo baixado veio corrompido. Tente de novo.", "Buscar atualizaÃ§Ã£o")
            return
        setup = Path(tempfile.gettempdir()) / ASSET
        setup.write_bytes(data)
        # o instalador fecha o app (se ainda estiver aberto), instala por cima e abre de novo
        subprocess.Popen([str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                         creationflags=subprocess.DETACHED_PROCESS)
        self._set("Instalandoâ€¦", "")
        self.quit_app()
