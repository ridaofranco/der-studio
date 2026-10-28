"""Avisos al celular (Web Push) cuando termina un reel, un carrusel o un lote de piezas.

- Las claves VAPID se generan solas la primera vez y quedan en .avisos/ (fuera del repo).
- Cada celular que activa los avisos guarda su suscripción en .avisos/suscripciones.json.
- En iPhone funciona con DER Studio agregado a la pantalla de inicio (iOS 16.4 o más nuevo).
Si falta la librería pywebpush, los avisos quedan desactivados sin romper nada.
"""
from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

_lock = threading.Lock()
CONTACTO = "mailto:franco@somosder.ar"


def _dir(root: Path) -> Path:
    d = root / ".avisos"
    d.mkdir(exist_ok=True)
    return d


def _claves(root: Path) -> tuple[Path, str] | None:
    """(archivo PEM privado, clave pública en base64url para el navegador)."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        return None
    pem = _dir(root) / "vapid.pem"
    with _lock:
        if not pem.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
            pem.chmod(0o600)
    key = serialization.load_pem_private_key(pem.read_bytes(), None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return pem, base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def clave_publica(root: Path) -> str | None:
    try:
        import pywebpush  # noqa: F401
    except ImportError:
        return None
    k = _claves(root)
    return k[1] if k else None


def _subs_file(root: Path) -> Path:
    return _dir(root) / "suscripciones.json"


def _leer(root: Path) -> list[dict]:
    f = _subs_file(root)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def guardar(root: Path, sub: dict) -> None:
    with _lock:
        subs = [s for s in _leer(root) if s.get("endpoint") != sub["endpoint"]]
        subs.append({"endpoint": sub["endpoint"], "keys": sub.get("keys", {})})
        _subs_file(root).write_text(json.dumps(subs), encoding="utf-8")


def enviar(root: Path, titulo: str, texto: str, url: str = "/") -> int:
    """Manda el aviso a todos los celulares suscriptos. Devuelve cuántos lo recibieron."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return 0
    k = _claves(root)
    subs = _leer(root)
    if not k or not subs:
        return 0
    data = json.dumps({"titulo": titulo, "texto": texto, "url": url})
    ok, vencidas = 0, []
    for s in subs:
        try:
            webpush(s, data, vapid_private_key=str(k[0]), vapid_claims={"sub": CONTACTO}, ttl=3600, timeout=10)
            ok += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                vencidas.append(s["endpoint"])  # el celular dio de baja los avisos
        except Exception:  # noqa: BLE001 — un aviso que falla nunca debe romper el trabajo
            pass
    if vencidas:
        with _lock:
            _subs_file(root).write_text(json.dumps([s for s in _leer(root) if s["endpoint"] not in vencidas]),
                                        encoding="utf-8")
    return ok
