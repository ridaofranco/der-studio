"""Actualización automática desde GitHub (repositorio público).

Descarga el código nuevo y lo copia encima de la instalación, sin tocar nunca
lo que es tuyo: logos, música, piezas generadas ni el entorno de Python.
"""
from __future__ import annotations

import io
import json
import urllib.request
import zipfile
from pathlib import Path

REPO = "ridaofranco/der-studio"
BRANCH = "main"
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / ".version"

# Nunca se sobrescriben ni se borran
PROTECTED = (".venv/", "salidas/", ".subidas/", "brand/logos/", "brand/music/", ".version")
# iniciar.bat se está ejecutando mientras corre la app: cambiarlo en caliente lo rompe
SKIP = ("iniciar.bat",)


def _get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "der-studio-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def local_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return ""


def remote_version() -> dict | None:
    """Último commit publicado: {'sha', 'fecha', 'mensaje'} o None si no hay conexión."""
    try:
        data = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", timeout=6))
        return {
            "sha": data["sha"],
            "fecha": data["commit"]["committer"]["date"],
            "mensaje": data["commit"]["message"].split("\n")[0],
        }
    except Exception:  # noqa: BLE001 — sin internet o repo inexistente: seguimos con lo instalado
        return None


def check() -> dict:
    remote = remote_version()
    local = local_version()
    return {
        "local": local[:7],
        "remoto": remote["sha"][:7] if remote else None,
        "mensaje": remote["mensaje"] if remote else None,
        "hay_actualizacion": bool(remote and remote["sha"] != local),
    }


def apply(sha: str | None = None) -> dict:
    """Descarga e instala. Devuelve qué cambió."""
    remote = {"sha": sha} if sha else remote_version()
    if not remote:
        return {"actualizado": False, "motivo": "no pudo comprobar si hay actualizaciones (sin conexión)"}
    if remote["sha"] == local_version():
        return {"actualizado": False, "motivo": "ya está al día"}
    blob = _get(f"https://codeload.github.com/{REPO}/zip/{remote['sha']}", timeout=60)
    old_req = (ROOT / "requirements.txt").read_bytes() if (ROOT / "requirements.txt").exists() else b""
    changed = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            rel = info.filename.split("/", 1)[1] if "/" in info.filename else ""
            if not rel or rel.startswith(PROTECTED) or rel in SKIP or ".." in Path(rel).parts:
                continue
            dest = ROOT / rel
            data = z.read(info)
            if dest.exists() and dest.read_bytes() == data:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            changed.append(rel)
    VERSION_FILE.write_text(remote["sha"])
    new_req = (ROOT / "requirements.txt").read_bytes()
    return {"actualizado": True, "archivos": changed, "requisitos": old_req != new_req}
