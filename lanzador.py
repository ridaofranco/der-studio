"""Arranca DER Studio: busca actualizaciones, abre la app y la reinicia si se actualizó.

iniciar.bat ejecuta este archivo. Si la app termina con el código 3 (botón
"Actualizar" en la app), se actualiza y vuelve a arrancar sola.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESTART = 3


def update() -> None:
    sys.path.insert(0, str(ROOT))
    from der import updater

    print("  Buscando actualizaciones...", flush=True)
    try:
        res = updater.apply()
    except Exception as e:  # noqa: BLE001
        print(f"  No se pudo actualizar ({e}). Sigo con la versión instalada.")
        return
    if not res["actualizado"]:
        print(f"  DER Studio {res['motivo']}.")
        return
    print(f"  Actualizado ({len(res['archivos'])} archivos).")
    if res["requisitos"]:
        print("  Instalando componentes nuevos...")
        subprocess.call([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                         "-r", str(ROOT / "requirements.txt")])


def main() -> int:
    env = dict(os.environ)
    while True:
        update()
        code = subprocess.call([sys.executable, str(ROOT / "app.py")], cwd=ROOT, env=env)
        if code != RESTART:
            return code
        env["DER_NO_BROWSER"] = "1"  # al reiniciar, la pestaña abierta se recarga sola


if __name__ == "__main__":
    sys.exit(main())
