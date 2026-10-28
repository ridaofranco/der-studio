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

import hmac
import json
import secrets
import shutil

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session
from werkzeug.utils import secure_filename

from der import brand, carrusel, graphics, reels, updater

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "salidas"
UPLOAD_DIR = ROOT / ".subidas"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024**3  # 4 GB, para videos largos

# --- Acceso con contraseña (solo si se define DER_PASSWORD, p. ej. en el servidor) ---
PASSWORD = os.environ.get("DER_PASSWORD", "")
_secret_file = ROOT / ".secreto"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_hex(32))
app.secret_key = os.environ.get("DER_SECRET") or _secret_file.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)

LOGIN_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>DER Studio</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#333;font:16px system-ui,sans-serif}
form{background:#f0f0f0;padding:32px;border-radius:12px;width:min(340px,90vw);border-top:6px solid #ff5c00}
h1{margin:0 0 18px;font-size:22px;color:#333}input,button{width:100%;box-sizing:border-box;padding:12px;border-radius:8px;font:inherit}
input{border:1px solid #ccc;margin-bottom:12px}button{background:#ff5c00;color:#fff;border:0;cursor:pointer}
p{color:#b3261e;margin:0 0 12px}</style></head><body><form method="post">
<h1>DER Studio</h1>{error}<input type="password" name="clave" placeholder="Contraseña" autofocus required>
<button>Entrar</button></form></body></html>"""


@app.before_request
def _auth():
    if not PASSWORD or session.get("ok") or request.path in (
            "/login", "/manifest.webmanifest") or request.path.startswith("/icono-"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Tu sesión venció. Recargá la página e ingresá la contraseña."), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("clave", ""), PASSWORD):
            session.permanent = True
            session["ok"] = True
            return redirect("/")
        time.sleep(1)
        error = "<p>Contraseña incorrecta.</p>"
    return LOGIN_HTML.replace("{error}", error)

JOBS: dict[str, dict] = {}


def _job_dir(kind: str) -> Path:
    d = OUT_DIR / f"{datetime.now():%Y-%m-%d_%H%M%S}_{kind}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_uploads(field: str) -> list[Path]:
    """Archivos del formulario: los enviados directo y los ya subidos por partes (/api/subir)."""
    batch = UPLOAD_DIR / uuid.uuid4().hex[:10]
    batch.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, f in enumerate(request.files.getlist(field)):
        if not f.filename:
            continue
        p = batch / f"{i:02d}_{secure_filename(f.filename) or 'archivo'}"
        f.save(p)
        paths.append(p)
    for ref in request.form.getlist(field + "_subidos"):
        up_id, _, name = ref.partition("/")
        p = UPLOAD_DIR / "partes" / secure_filename(up_id) / secure_filename(name)
        if p.is_file():
            paths.append(p)
    return paths


def _limpiar_subidas(max_horas: float = 24) -> None:
    limite = time.time() - max_horas * 3600
    for d in [*UPLOAD_DIR.glob("*"), *(UPLOAD_DIR / "partes").glob("*")]:
        if d.is_dir() and d.name != "partes" and d.stat().st_mtime < limite:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


@app.post("/api/subir")
def api_subir():
    """Subida por partes: Cloudflare (plan gratis) corta los envíos de más de 100 MB."""
    up_id = secure_filename(request.form.get("id", ""))
    name = secure_filename(request.form.get("nombre", "")) or "archivo"
    parte, total = int(request.form.get("parte", 0)), int(request.form.get("total", 1))
    if not up_id or "trozo" not in request.files:
        abort(400)
    d = UPLOAD_DIR / "partes" / up_id
    d.mkdir(parents=True, exist_ok=True)
    if parte == 0:
        _limpiar_subidas()
    with open(d / name, "wb" if parte == 0 else "ab") as fh:
        request.files["trozo"].save(fh)
    return jsonify(ok=True, ref=f"{up_id}/{name}" if parte == total - 1 else None)


def _url(p: Path) -> str:
    return "/salidas/" + p.relative_to(OUT_DIR).as_posix()


def _zip(files: list[Path], dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:
        for f in files:
            z.write(f, f.name)
    return dest


@app.get("/")
def index():
    return render_template("index.html", templates=graphics.TEMPLATES, music_styles=list(reels.music.STYLES),
                           photo_styles=carrusel.PHOTO_STYLES,
                           transitions=reels.TRANSITIONS, template_hints=graphics.TEMPLATE_HINTS)


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
            d["base"] = _url(out / d["base_file"])
        return jsonify(lote=out.name, disenos=designs)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=str(e)), 400


def _reel_info(lote: Path, project: dict) -> dict:
    """Proyecto + direcciones de miniaturas y vistas previas, para el editor del navegador."""
    clips = []
    for c in project["clips"]:
        stem = Path(c["src"]).stem
        clips.append({**c, "miniatura": _url(lote / "miniaturas" / f"{stem}.jpg"),
                      "vista": _url(lote / "vistas" / f"{stem}.mp4") if c["kind"] == "video" else None})
    return {**project, "lote": lote.name, "clips": clips}


def _prepare_previews(lote: Path, project: dict) -> None:
    (lote / "miniaturas").mkdir(exist_ok=True)
    (lote / "vistas").mkdir(exist_ok=True)
    for c in project["clips"]:
        src, stem = lote / "fuentes" / c["src"], Path(c["src"]).stem
        thumb = lote / "miniaturas" / f"{stem}.jpg"
        if not thumb.exists():
            reels.thumbnail(src, thumb, (c["start"] + c["end"]) / 2)
        view = lote / "vistas" / f"{stem}.mp4"
        if c["kind"] == "video" and not view.exists():
            reels.preview_proxy(src, view)


def _run_reel(job_id: str, lote: Path, project: dict, out: Path, previews: bool = False):
    job = JOBS[job_id]
    try:
        reels.render_project(project, lote, out)
        (lote / "proyecto.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
        if previews:
            _prepare_previews(lote, project)
        job.update(estado="listo", archivo=_url(out), proyecto=_reel_info(lote, project),
                   transiciones=reels.TRANSITIONS)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.update(estado="error", error=str(e))
    job["fin"] = time.time()


def _start_reel(lote: Path, project: dict, n: int, previews: bool) -> str:
    version = project.get("version", 0)
    out = lote / f"DER-reel{'-v' + str(version) if version else ''}-{datetime.now():%H%M%S}.mp4"
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"estado": "procesando", "inicio": time.time(), "n": n}
    threading.Thread(target=_run_reel, args=(job_id, lote, project, out, previews), daemon=True).start()
    return job_id


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
        transition=f.get("transicion", "fade") if f.get("transicion") in reels.TRANSITIONS else "fade",
        music=f.get("musica", "auto:energico"),
        music_volume=float(f.get("volumen") or 0.9),
        keep_original_audio=f.get("audio_original") == "1",
        watermark=f.get("marca_agua", "1") == "1",
        logo=f.get("logo", "auto"),
    )
    lote = _job_dir("reel")
    fuentes = lote / "fuentes"
    fuentes.mkdir()
    srcs = []
    for i, p in enumerate(inputs):
        # se mueven (no se copian) al lote: así el reel se puede volver a editar después
        dst = fuentes / f"{i:02d}_{p.name}"
        shutil.move(str(p), dst)
        srcs.append(dst)
    try:
        project = reels.build_project(srcs, opts)
    except Exception as e:  # noqa: BLE001
        return jsonify(error=str(e)), 400
    return jsonify(job=_start_reel(lote, project, len(srcs), previews=True))


@app.get("/api/reel/<job_id>")
def api_reel_estado(job_id):
    job = JOBS.get(job_id) or abort(404)
    return jsonify(job)


@app.get("/api/reel/proyecto/<lote>")
def api_reel_proyecto(lote):
    d = _lote(lote)
    p = d / "proyecto.json"
    if not p.exists():
        abort(404)
    _prepare_previews(d, json.loads(p.read_text(encoding="utf-8")))
    return jsonify(proyecto=_reel_info(d, json.loads(p.read_text(encoding="utf-8"))),
                   transiciones=reels.TRANSITIONS)


@app.post("/api/reel/editar")
def api_reel_editar():
    """Vuelve a renderizar un reel con los cambios del editor (recortes, orden, transiciones…)."""
    data = request.get_json(silent=True) or {}
    d = _lote(str(data.get("lote", "")))
    if not (d / "fuentes").is_dir():
        return jsonify(error="Este reel no se puede editar (se generó con una versión anterior)."), 400
    try:
        project = reels.clean_project(data.get("proyecto") or {}, d / "fuentes")
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400
    prev = json.loads((d / "proyecto.json").read_text(encoding="utf-8")) if (d / "proyecto.json").exists() else {}
    project["version"] = int(prev.get("version", 0)) + 1
    if any(j.get("estado") == "procesando" for j in JOBS.values()):
        return jsonify(error="Ya hay un reel procesándose. Esperá a que termine y probá de nuevo."), 409
    return jsonify(job=_start_reel(d, project, len(project["clips"]), previews=False))


def _run_carrusel(job_id: str, inputs: list[Path], out: Path, form: dict):
    job = JOBS[job_id]
    try:
        content = graphics.Content(title=form["titulo"], subtitle=form["subtitulo"], body=form["cuerpo"],
                                   focus=form["enfoque"], logo=form["logo"])
        slides = carrusel.generate(inputs, out, form["formato"], form["estilo"], content, form["max_video"],
                                   text_all=form["texto_todas"])
        for sl in slides:
            if sl["tipo"] == "foto":
                sl["diseno"]["base"] = _url(out / sl["diseno"]["base_file"])
            else:
                sl["archivo"] = _url(out / sl["nombre"])
        job.update(estado="listo", lote=out.name, diapositivas=slides)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.update(estado="error", error=str(e))
    job["fin"] = time.time()


@app.post("/api/carrusel")
def api_carrusel():
    """Carrusel mixto: fotos (piezas editables) y videos (MP4 4:5 o 1:1) en el orden subido."""
    inputs = _save_uploads("archivos")
    if not inputs:
        return jsonify(error="Subí al menos una foto o un video."), 400
    f = request.form
    form = {
        "titulo": f.get("titulo", "").strip(), "subtitulo": f.get("subtitulo", "").strip(),
        "cuerpo": f.get("cuerpo", "").strip(), "enfoque": f.get("enfoque", "centro"), "logo": f.get("logo", "auto"),
        "formato": f.get("formato", "post"), "estilo": f.get("estilo", "impacto"),
        "max_video": float(f.get("max_video") or 30), "texto_todas": f.get("texto_todas") == "1",
    }
    out = _job_dir("carrusel")
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"estado": "procesando", "inicio": time.time(), "n": len(inputs)}
    threading.Thread(target=_run_carrusel, args=(job_id, inputs, out, form), daemon=True).start()
    return jsonify(job=job_id)


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
    files = sorted([*(p for p in d.glob("*.jpg") if not p.name.endswith(".base.jpg")),
                    *d.glob("DER-carrusel-*.mp4")], key=lambda p: p.name)
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


@app.get("/manifest.webmanifest")
def manifest():
    return app.response_class(json.dumps({
        "name": "DER Studio", "short_name": "DER Studio", "start_url": "/", "display": "standalone",
        "background_color": "#333333", "theme_color": "#333333", "lang": "es",
        "icons": [{"src": f"/icono-{n}.png", "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"}
                  for n in (192, 512)],
    }), mimetype="application/manifest+json")


@app.get("/icono-<int:size>.png")
def icono(size):
    """Ícono para la pantalla de inicio del celular: el logo sobre gris oscuro."""
    from io import BytesIO

    from flask import send_file
    from PIL import Image
    size = min(max(size, 32), 1024)
    img = Image.new("RGB", (size, size), brand.DARK)
    lg = brand.logo("on_dark")
    lg = lg.resize((int(size * 0.62), int(lg.height * size * 0.62 / lg.width)), Image.LANCZOS)
    if lg.height > size * 0.62:
        lg = lg.resize((int(lg.width * size * 0.62 / lg.height), int(size * 0.62)), Image.LANCZOS)
    img.paste(lg, ((size - lg.width) // 2, (size - lg.height) // 2), lg)
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png", max_age=3600)


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
        app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=False, threaded=True)
