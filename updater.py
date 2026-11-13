"""Busca a última Release no GitHub e atualiza: no app instalado (.exe) baixa e roda o instalador novo;
rodando pelo Python num clone do git, faz git pull, instala as dependências e reinicia o app."""
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

VERSION = "1.1.1"
API = "https://api.github.com/repos/EnricoSpanier/BateriaBT/releases/latest"
ASSET = "BateriaBT-Setup.exe"
ROOT = Path(__file__).resolve().parent
NO_WINDOW = subprocess.CREATE_NO_WINDOW  # pythonw não tem console: sem piscar janela preta


def parse_version(tag):
    """'v1.2.10' -> (1, 2, 10); o que não for número vira 0."""
    return tuple(int(p) if p.isdigit() else 0 for p in tag.strip().lstrip("vV").split("."))


def is_newer(tag, current):
    return parse_version(tag) > parse_version(current)


def pick_asset(release):
    """(url do instalador, sha256 informado pelo GitHub ou None), ou None se a Release não tem instalador."""
    for a in release.get("assets", []):
        if a.get("name") == ASSET:
            digest = a.get("digest") or ""
            return a["browser_download_url"], digest[7:] if digest.startswith("sha256:") else None
    return None


def sha_ok(data, expected):
    return expected is None or hashlib.sha256(data).hexdigest() == expected.lower()


class Updater(QObject):
    """Estado para a linha "Versão" do painel: `text` (situação) e `action` (rótulo do botão, ou "" = sem
    botão ativo). O clique chama `click()`, que faz a próxima etapa."""
    changed = Signal()
    _git_done = Signal(str)  # erro ("" = ok), vindo da thread do git pull
    _git_step = Signal(str)  # texto da etapa, vindo da mesma thread

    def __init__(self, quit_app):
        super().__init__()
        self.net = QNetworkAccessManager(self)
        self.quit_app = quit_app
        self.text, self.action = "Busca a versão nova no GitHub.", "Buscar atualização"
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
            self._set("Sem conexão com o GitHub. Tente de novo mais tarde.", "Buscar atualização")
            return
        try:
            done(bytes(reply.readAll()))
        except Exception as e:  # resposta inesperada: não derruba o app
            print("erro atualização:", e, file=sys.stderr)
            self._set("Não foi possível ler a resposta do GitHub.", "Buscar atualização")

    def click(self):
        if self.action == "Buscar atualização":
            self._set("Buscando…", "")
            self._get(API, self._on_release)
        elif self.action.startswith("Atualizar"):
            if getattr(sys, "frozen", False):
                self._download()
            else:
                self._set("Baixando o código novo…", "")
                threading.Thread(target=self._git_update, daemon=True).start()

    def _on_release(self, data):
        rel = json.loads(data)
        tag = rel.get("tag_name", "")
        if not is_newer(tag, VERSION):
            self._set(f"Você está na versão mais recente ({VERSION}).", "Buscar atualização")
            return
        self.release = rel
        new = tag.lstrip("vV")
        if pick_asset(rel) if getattr(sys, "frozen", False) else (ROOT / ".git").exists():
            self._set(f"Versão {new} disponível.", f"Atualizar para {new}")
        else:  # Python sem git (ZIP) ou Release sem instalador
            self._set(f"Versão {new} disponível. Esta pasta não é um clone do git: veja o README.",
                      "Buscar atualização")

    @staticmethod
    def _run_cmd(args):
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, creationflags=NO_WINDOW)
        if r.returncode:
            raise RuntimeError(((r.stderr or r.stdout).strip().splitlines() or ["falhou"])[-1])

    def _git_update(self):
        """Roda numa thread: git pull (só avanço rápido) e dependências. Erro = nada reinicia."""
        python = Path(sys.executable).with_name("python.exe")
        try:
            self._run_cmd(["git", "pull", "--ff-only"])
            self._git_step.emit("Instalando dependências…")
            self._run_cmd([str(python), "-m", "pip", "install", "-q", "-r", "requirements.txt"])
            self._git_done.emit("")
        except Exception as e:
            print("erro atualização git:", e, file=sys.stderr)
            self._git_done.emit(str(e) or "falhou")

    def _after_git(self, err):
        if err:
            self._set(f"Não deu para atualizar: {err}", "Buscar atualização")
            return
        self._set("Reiniciando…", "")
        # o app novo espera o atual soltar o app.lock (ver main, --restart)
        subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")), str(ROOT / "bateria_bt.py"), "--restart"],
                         cwd=ROOT, creationflags=subprocess.DETACHED_PROCESS)
        self.quit_app()

    def _download(self):
        url, sha = pick_asset(self.release)
        self._set("Baixando…", "")
        self._get(url, lambda data: self._run(data, sha),
                  lambda got, total: total > 0 and self._set(f"Baixando… {got * 100 // total} %", ""))

    def _run(self, data, sha):
        if not sha_ok(data, sha):
            self._set("O arquivo baixado veio corrompido. Tente de novo.", "Buscar atualização")
            return
        setup = Path(tempfile.gettempdir()) / ASSET
        setup.write_bytes(data)
        # o instalador fecha o app (se ainda estiver aberto), instala por cima e abre de novo
        subprocess.Popen([str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                         creationflags=subprocess.DETACHED_PROCESS)
        self._set("Instalando…", "")
        self.quit_app()
