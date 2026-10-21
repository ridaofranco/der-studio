"""DER Studio — generador de piezas de Instagram con el brand kit de DER.

    python3 app.py          ->  http://localhost:5050
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from der import brand, graphics, reels, updater

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "salidas"
UPLOAD_DIR = ROOT / ".subidas"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024**3  # 4 GB, para videos largos

JOBS: dict[str, dict] = {}


def _job_dir(kind: str) -> Path:
    d = OUT_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}_{kind}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_uploads(field: str) -> list[Path]:
    batch = UPLOAD_DIR / uuid.uuid4().hex[:10]
    batch.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, f in enumerate(request.files.getlist(field)):
        if not f.filename:
            continue
        p = batch / f"{i:02d}_{secure_filename(f.filename) or 'archivo'}"
        f.save(p)
        paths.append(p)
    return paths


def _url(p: Path) -> str:
    return "/salidas/" + p.relative_to(OUT_DIR).as_posix()


def _zip(files: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, f.name)
    return dest


@app.get("/")
def index():
    return render_template("index.html", templates=graphics.TEMPLATES, music_styles=list(reels.music.STYLES))


@app.get("/api/estado")
def estado():
    return jsonify(brand.status())


@app.post("/api/graficos")
def api_graficos():
    try:
        photos = _save_uploads("fotos")
        template = request.form.get("plantilla", "impacto")
        formats = request.form.getlist("formatos") or ["post"]
        content = graphics.Content(
            title=request.form.get("titulo", "").strip(),
            subtitle=request.form.get("subtitulo", "").strip(),
            body=request.form.get("cuerpo", "").strip(),
            focus=request.form.get("enfoque", "centro"),
            logo=request.form.get("logo", "auto"),
        )
        if template not in graphics.PHOTO_TEMPLATES and not (content.title or content.subtitle or content.body):
            return jsonify(error="Escribí al menos un título o un texto."), 400
        out = _job_dir(template)
        designs = graphics.generate(template, formats, photos, content, out,
                                    carousel_text_first_only=request.form.get("texto_todas") != "1")
        for d in designs:
            d["base"] = _url(out / f"{d['name']}.base.jpg")
        return jsonify(lote=out.name, disenos=designs)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=str(e)), 400


def _run_reel(job_id: str, inputs: list[Path], opts: reels.ReelOptions, out: Path):
    job = JOBS[job_id]
    try:
        reels.generate(inputs, out, opts)
        job.update(estado="listo", archivo=_url(out))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.update(estado="error", error=str(e))
    job["fin"] = time.time()


@app.post("/api/reel")
def api_reel():
    inputs = _save_uploads("archivos")
    if not inputs:
        return jsonify(error="Subí al menos un video o foto."), 400
    f = request.form
    opts = reels.ReelOptions(
        title=f.get("titulo", "").strip(),
        subtitle=f.get("subtitulo", "").strip(),
        max_clip_seconds=float(f.get("max_clip") or 0),
        photo_seconds=float(f.get("seg_foto") or 3),
        transition=f.get("transicion", "fade"),
        music=f.get("musica", "auto:energico"),
        music_volume=float(f.get("volumen") or 0.9),
        keep_original_audio=f.get("audio_original") == "1",
        watermark=f.get("marca_agua", "1") == "1",
        logo=f.get("logo", "auto"),
    )
    out = _job_dir("reel") / f"DER-reel-{datetime.now():%H%M%S}.mp4"
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"estado": "procesando", "inicio": time.time(), "n": len(inputs)}
    threading.Thread(target=_run_reel, args=(job_id, inputs, opts, out), daemon=True).start()
    return jsonify(job=job_id)


@app.get("/api/reel/<job_id>")
def api_reel_estado(job_id):
    job = JOBS.get(job_id) or abort(404)
    return jsonify(job)


@app.post("/api/brand")
def api_brand():
    """Subir logos, tipografías o música al brand kit."""
    dest = {"logos": brand.LOGOS_DIR, "fuentes": brand.FONTS_DIR, "musica": brand.MUSIC_DIR}
    kind = request.form.get("tipo")
    if kind not in dest:
        return jsonify(error="tipo inválido"), 400
    dest[kind].mkdir(parents=True, exist_ok=True)
    saved = []
    for f in request.files.getlist("archivos"):
        if f.filename:
            name = secure_filename(f.filename)
            f.save(dest[kind] / name)
            saved.append(name)
    brand.fonts.cache_clear()
    brand.font.cache_clear()
    brand.logo.cache_clear()
    brand.logo_file.cache_clear()
    return jsonify(guardados=saved, estado=brand.status())


def _lote(lote: str) -> Path:
    d = OUT_DIR / secure_filename(lote)
    if not lote or not d.is_dir():
        abort(404)
    return d


@app.post("/api/guardar")
def api_guardar():
    """El navegador manda la pieza ya compuesta (JPG) y sus capas, para guardarla en salidas/."""
    d = _lote(request.form.get("lote", ""))
    name = secure_filename(request.form.get("nombre", ""))
    if not name:
        abort(400)
    request.files["imagen"].save(d / f"{name}.jpg")
    if request.form.get("capas"):
        (d / f"{name}.json").write_text(request.form["capas"], encoding="utf-8")
    return jsonify(ok=True, url=_url(d / f"{name}.jpg"))


@app.get("/api/zip/<lote>")
def api_zip(lote):
    d = _lote(lote)
    files = sorted(p for p in d.glob("*.jpg") if not p.name.endswith(".base.jpg"))
    zipf = _zip(files, d / "DER-piezas.zip")
    return send_from_directory(d, zipf.name, as_attachment=True)


@app.get("/logos/ver/<path:key>")
def logo_ver(key):
    from io import BytesIO

    from flask import send_file
    kind, _, value = key.partition(":")
    try:
        img = brand.logo_file(value) if kind == "file" else brand.logo(value or "on_dark")
    except FileNotFoundError:
        abort(404)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", max_age=0)


@app.delete("/api/logos/<name>")
def api_borrar_logo(name):
    p = brand.LOGOS_DIR / secure_filename(name)
    if p.exists():
        p.unlink()
    brand.logo.cache_clear()
    brand.logo_file.cache_clear()
    return jsonify(estado=brand.status())


@app.get("/elemento/<kind>.png")
def elemento(kind):
    from io import BytesIO

    from flask import send_file
    a = request.args
    try:
        img = graphics.element_png(kind, corner=a.get("c", "tl"), size=int(a.get("l", 110)),
                                   thick=int(a.get("g", 10)), cols=int(a.get("cols", 6)),
                                   rows=int(a.get("rows", 4)), gap=int(a.get("gap", 28)),
                                   r=int(a.get("r", 4)), color="#" + a.get("color", "ff5c00"))
    except ValueError:
        abort(404)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", max_age=3600)


@app.get("/api/version")
def api_version():
    return jsonify(updater.check())


@app.post("/api/actualizar")
def api_actualizar():
    """Cierra la app con el código 3: lanzador.py actualiza y la vuelve a abrir."""
    threading.Timer(0.5, lambda: os._exit(3)).start()
    return jsonify(ok=True)


@app.get("/salidas/<path:p>")
def salidas(p):
    return send_from_directory(OUT_DIR, p)


@app.get("/fuentes/<rol>")
def fuentes(rol):
    fs = brand.fonts()
    path = {"titulo": fs.title, "subtitulo": fs.subtitle, "cuerpo": fs.body}.get(rol) or abort(404)
    return send_from_directory(path.parent, path.name)


@app.get("/logo.png")
def logo_png():
    from io import BytesIO

    from flask import send_file
    buf = BytesIO()
    brand.logo_sized("on_dark", height=80).save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", max_age=0)


if __name__ == "__main__":
    import socket
    import webbrowser

    OUT_DIR.mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", 5050))
    url = f"http://localhost:{port}"
    with socket.socket() as sock:
        already_running = sock.connect_ex(("127.0.0.1", port)) == 0
    if already_running:
        # ya estaba abierta (por ejemplo, en otra ventana): solo abrimos el navegador
        webbrowser.open(url)
    else:
        print(f"\n  DER Studio funcionando en {url}")
        print("  Dejá esta ventana abierta mientras la usás. Para cerrarla, cerrá la ventana.\n")
        if not os.environ.get("DER_NO_BROWSER"):
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
