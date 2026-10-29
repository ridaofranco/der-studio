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
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import hmac
import json
import secrets
import shutil

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session
from werkzeug.utils import secure_filename

from der import aviso, brand, carrusel, compose, graphics, reels, updater

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "salidas"
UPLOAD_DIR = ROOT / ".subidas"

app = Flask(__name__)
app.json.sort_keys = False  # el orden de los catálogos (transiciones, filtros) importa
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
            "/login", "/manifest.webmanifest", "/sw.js") or request.path.startswith("/icono-"):
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
JOBS_DIR = OUT_DIR / ".trabajos"
TIPO_NOMBRE = {"vista": "La vista previa", "reel": "Tu reel", "carrusel": "Tu carrusel", "piezas": "Tus piezas"}


def _job_new(tipo: str, lote: Path, extra: dict | None = None) -> str:
    """Trabajo en segundo plano. Su estado se guarda en disco: si el celular sale de la app
    (o el servidor se reinicia), al volver se puede consultar igual."""
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"id": job_id, "tipo": tipo, "lote": lote.name, "estado": "procesando",
                    "inicio": time.time(), **(extra or {})}
    _job_save(job_id)
    return job_id


def _job_save(job_id: str) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / f"{job_id}.json").write_text(json.dumps(JOBS[job_id], ensure_ascii=False), encoding="utf-8")


def _job_set(job_id: str, **kw) -> None:
    JOBS[job_id].update(kw)
    if kw.get("estado") in ("listo", "error"):
        JOBS[job_id]["fin"] = time.time()
    _job_save(job_id)
    if kw.get("estado") in ("listo", "error") and JOBS[job_id].get("tipo") != "vista":
        job = JOBS[job_id]
        nombre = TIPO_NOMBRE.get(job["tipo"], "Tu trabajo")
        ok = kw["estado"] == "listo"
        aviso.enviar(ROOT, f"{nombre} {'está listo' if ok else 'no se pudo generar'}",
                     "Tocá para verlo en DER Studio." if ok else str(job.get("error", ""))[:120],
                     f"/?trabajo={job_id}")


def _job_get(job_id: str) -> dict | None:
    if job_id in JOBS:
        return JOBS[job_id]
    f = JOBS_DIR / f"{secure_filename(job_id)}.json"
    if not f.exists():
        return None
    job = json.loads(f.read_text(encoding="utf-8"))
    if job.get("estado") == "procesando":
        # el hilo que lo procesaba ya no existe (el servidor se reinició a mitad de camino)
        job.update(estado="error", error="Se interrumpió porque DER Studio se reinició. Volvé a generarlo.")
    return job


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


def _partes(d: Path, name: str) -> list[int]:
    return sorted(int(p.suffix[6:]) for p in d.glob(f"{name}.parte*") if p.suffix[6:].isdigit())


@app.post("/api/subir")
def api_subir():
    """Subida por partes: Cloudflare (plan gratis) corta los envíos de más de 100 MB.
    Cada parte se guarda aparte, así reintentarla no duplica nada y la subida se puede retomar
    si el celular salió de la app a mitad de camino. Con todas las partes, se arma el archivo."""
    up_id = secure_filename(request.form.get("id", ""))
    name = secure_filename(request.form.get("nombre", "")) or "archivo"
    parte, total = int(request.form.get("parte", 0)), int(request.form.get("total", 1))
    if not up_id or "trozo" not in request.files or not 0 <= parte < total <= 10_000:
        abort(400)
    d = UPLOAD_DIR / "partes" / up_id
    d.mkdir(parents=True, exist_ok=True)
    if parte == 0:
        _limpiar_subidas()
    tmp = d / f"{name}.tmp{parte}"
    request.files["trozo"].save(tmp)
    tmp.replace(d / f"{name}.parte{parte:05d}")
    if len(_partes(d, name)) < total:
        return jsonify(ok=True, ref=None)
    with open(d / name, "wb") as out:
        for k in range(total):
            pf = d / f"{name}.parte{k:05d}"
            with open(pf, "rb") as fh:
                shutil.copyfileobj(fh, out, 8 * 1024 * 1024)
    for k in range(total):
        (d / f"{name}.parte{k:05d}").unlink(missing_ok=True)
    return jsonify(ok=True, ref=f"{up_id}/{name}")


@app.get("/api/subir/estado")
def api_subir_estado():
    """Qué partes ya llegaron (para retomar una subida sin volver a mandarlas)."""
    up_id = secure_filename(request.args.get("id", ""))
    name = secure_filename(request.args.get("nombre", "")) or "archivo"
    d = UPLOAD_DIR / "partes" / up_id
    if up_id and (d / name).is_file():
        return jsonify(completo=True, ref=f"{up_id}/{name}", partes=[])
    return jsonify(completo=False, partes=_partes(d, name) if up_id and d.is_dir() else [])


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
        if template in graphics.PHOTO_TEMPLATES and not photos:
            return jsonify(error="Esta plantilla necesita al menos una foto."), 400
        out = _job_dir(template)
        job_id = _job_new("piezas", out)
        threading.Thread(target=_run_graficos, daemon=True, args=(
            job_id, template, formats, photos, content, out, request.form.get("texto_todas") != "1")).start()
        return jsonify(job=job_id)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=str(e)), 400


def _design_out(out: Path, d: dict) -> dict:
    """Agrega las direcciones de la base y de la pieza terminada (con marca de tiempo contra el caché)."""
    fin = out / f"{d['name']}.jpg"
    stamp = int(fin.stat().st_mtime) if fin.exists() else 0
    return {**d, "base": _url(out / d["base_file"]), "final": _url(fin) + f"?t={stamp}"}


def _run_graficos(job_id, template, formats, photos, content, out, first_only):
    try:
        designs = graphics.generate(template, formats, photos, content, out, carousel_text_first_only=first_only)
        for k, d in enumerate(designs, 1):
            compose.save_final(d, out)
            _job_set(job_id, progreso=f"{k} de {len(designs)}")
        _job_set(job_id, estado="listo", disenos=[_design_out(out, d) for d in designs])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _job_set(job_id, estado="error", error=str(e))


def _reel_info(lote: Path, project: dict) -> dict:
    """Proyecto + miniaturas, tiras de cuadros y vistas previas, para el editor del navegador."""
    clips = []
    for c in project["clips"]:
        stem = Path(c["src"]).stem
        clips.append({**c, "miniatura": _url(lote / "miniaturas" / f"{stem}.jpg"),
                      "tira": _url(lote / "miniaturas" / f"{stem}.tira.jpg"),
                      "vista": _url(lote / "vistas" / f"{stem}.mp4") if c["kind"] == "video" else None})
    voz = project["opciones"].get("voz")
    return {**project, "lote": lote.name, "clips": clips,
            "voz_url": _url(lote / "fuentes" / voz) if voz and (lote / "fuentes" / voz).is_file() else None}


REEL_CATALOGO = {"transiciones": reels.TRANSITIONS, "filtros": {k: v[0] for k, v in reels.FILTERS.items()},
                 "animaciones": reels.ANIMATIONS, "anim_texto": reels.TEXT_ANIMS, "stickers": reels.STICKERS}


def _prepare_previews(lote: Path, project: dict) -> None:
    (lote / "miniaturas").mkdir(exist_ok=True)
    (lote / "vistas").mkdir(exist_ok=True)
    done = set()
    for c in project["clips"]:
        if c["src"] in done:
            continue
        done.add(c["src"])
        src, stem = lote / "fuentes" / c["src"], Path(c["src"]).stem
        thumb = lote / "miniaturas" / f"{stem}.jpg"
        if not thumb.exists():
            reels.thumbnail(src, thumb, (c["start"] + c["end"]) / 2)
        strip = lote / "miniaturas" / f"{stem}.tira.jpg"
        if not strip.exists():
            reels.filmstrip(src, strip, c["source_duration"], 10)
        view = lote / "vistas" / f"{stem}.mp4"
        if c["kind"] == "video" and not view.exists():
            reels.preview_proxy(src, view)


def _run_reel(job_id: str, lote: Path, project: dict, out: Path, previews: bool = False, preview: bool = False):
    try:
        if previews:
            _job_set(job_id, progreso="Preparando miniaturas")
            _prepare_previews(lote, project)
        reels.render_project(project, lote, out, preview=preview, progress=lambda t: _job_set(job_id, progreso=t))
        if preview:
            for old in lote.glob("vista-previa-*.mp4"):
                if old != out:
                    old.unlink(missing_ok=True)
            (lote / "borrador.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
        else:
            (lote / "proyecto.json").write_text(json.dumps(project, ensure_ascii=False), encoding="utf-8")
            (lote / "borrador.json").unlink(missing_ok=True)
        _job_set(job_id, estado="listo", archivo=_url(out), vista_previa=preview,
                 proyecto=_reel_info(lote, project), **REEL_CATALOGO)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _job_set(job_id, estado="error", error=str(e))


def _start_reel(lote: Path, project: dict, n: int, previews: bool, preview: bool = False) -> str:
    version = project.get("version", 0)
    if preview:
        out = lote / f"vista-previa-{datetime.now():%H%M%S}.mp4"
    else:
        out = lote / f"DER-reel{'-v' + str(version) if version else ''}-{datetime.now():%H%M%S}.mp4"
    job_id = _job_new("vista" if preview else "reel", lote, {"n": n})
    threading.Thread(target=_run_reel, args=(job_id, lote, project, out, previews, preview), daemon=True).start()
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


@app.get("/api/trabajo/<job_id>")
@app.get("/api/reel/<job_id>")
def api_trabajo(job_id):
    job = _job_get(job_id) or abort(404)
    return jsonify(job)


@app.get("/api/reel/proyecto/<lote>")
def api_reel_proyecto(lote):
    d = _lote(lote)
    p = d / "proyecto.json"
    if not p.exists():
        abort(404)
    project = json.loads(p.read_text(encoding="utf-8"))
    _prepare_previews(d, project)
    return jsonify(proyecto=_reel_info(d, project), **REEL_CATALOGO)


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
    preview = bool(data.get("vista_previa"))
    project["version"] = int(prev.get("version", 0)) + (0 if preview else 1)
    if any(j.get("estado") == "procesando" and j.get("tipo") in ("reel", "vista") for j in JOBS.values()):
        return jsonify(error="Ya hay un reel procesándose. Esperá a que termine y probá de nuevo."), 409
    _prepare_previews(d, project)
    return jsonify(job=_start_reel(d, project, len(project["clips"]), previews=False, preview=preview))


def _reel_lote(data: dict) -> Path:
    d = _lote(str(data.get("lote", "")))
    if not (d / "fuentes").is_dir():
        abort(400)
    return d


def _mover_a_fuentes(d: Path, refs: list[str], prefijo: str = "") -> list[Path]:
    fuentes = d / "fuentes"
    n = len(list(fuentes.iterdir()))
    out = []
    for k, ref in enumerate(refs):
        up_id, _, name = str(ref).partition("/")
        p = UPLOAD_DIR / "partes" / secure_filename(up_id) / secure_filename(name)
        if not p.is_file():
            continue
        dst = fuentes / f"{prefijo}{n + k:02d}_{secure_filename(name)}"
        shutil.move(str(p), dst)
        out.append(dst)
    return out


@app.post("/api/reel/agregar")
def api_reel_agregar():
    """Suma videos o fotos a un reel que ya existe (botón Agregar del editor)."""
    data = request.get_json(silent=True) or {}
    d = _reel_lote(data)
    try:
        srcs = _mover_a_fuentes(d, data.get("refs") or [])
        if not srcs:
            return jsonify(error="No llegaron los archivos."), 400
        clips = [asdict(reels.clip_from_file(p)) for p in srcs]
        info = {"clips": clips, "opciones": {}}
        _prepare_previews(d, info)
        return jsonify(clips=_reel_info(d, {**info, "opciones": {}})["clips"])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=str(e)), 400


@app.post("/api/reel/cuadro")
def api_reel_cuadro():
    """Congelar imagen: saca el cuadro de ese segundo y lo devuelve como un clip de foto."""
    data = request.get_json(silent=True) or {}
    d = _reel_lote(data)
    src = d / "fuentes" / Path(str(data.get("src", ""))).name
    if not src.is_file() or src.suffix.lower() in reels.IMAGE_EXT:
        return jsonify(error="Solo se puede congelar un cuadro de un video."), 400
    t = max(0.0, float(data.get("t") or 0))
    dst = d / "fuentes" / f"{src.stem}_cuadro{int(t * 1000):06d}.jpg"
    try:
        if not dst.exists():
            reels.extract_frame(src, dst, t)
        clip = reels.clip_from_file(dst, reels.ReelOptions(photo_seconds=2.0, transition="none"))
        clip.anim = "ninguna"
        info = {"clips": [asdict(clip)], "opciones": {}}
        _prepare_previews(d, info)
        return jsonify(clip=_reel_info(d, info)["clips"][0])
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify(error=str(e)), 400


@app.post("/api/reel/ritmo")
def api_reel_ritmo():
    """Pulso de la música elegida, para cortar los clips al ritmo."""
    data = request.get_json(silent=True) or {}
    choice = str(data.get("music") or "auto:energico")
    if choice == "none":
        return jsonify(error="Elegí una música primero."), 400
    if choice.startswith("auto"):
        return jsonify(bpm=reels.music.tempo(choice.split(":", 1)[-1]), primero=0.0)
    track = brand.MUSIC_DIR / Path(choice).name
    if not track.is_file():
        return jsonify(error="No encuentro ese tema."), 404
    bpm, first = reels.music.detect_beat(track, float(data.get("music_start") or 0), ffmpeg=reels.ffmpeg_exe())
    return jsonify(bpm=bpm, primero=first)


@app.post("/api/reel/voz")
def api_reel_voz():
    """Voz en off grabada desde el celular (o un audio subido)."""
    data = request.get_json(silent=True) or {}
    d = _reel_lote(data)
    srcs = _mover_a_fuentes(d, [data.get("ref", "")], prefijo="voz_")
    if not srcs:
        return jsonify(error="No llegó el audio."), 400
    dur = reels.probe(srcs[0])["duration"]
    if dur <= 0:
        srcs[0].unlink(missing_ok=True)
        return jsonify(error="No pude leer ese audio."), 400
    return jsonify(voz=srcs[0].name, segundos=round(dur, 1), url=_url(srcs[0]))


def _run_carrusel(job_id: str, inputs: list[Path], out: Path, form: dict):
    try:
        content = graphics.Content(title=form["titulo"], subtitle=form["subtitulo"], body=form["cuerpo"],
                                   focus=form["enfoque"], logo=form["logo"])
        slides = carrusel.generate(inputs, out, form["formato"], form["estilo"], content, form["max_video"],
                                   text_all=form["texto_todas"])
        for sl in slides:
            if sl["tipo"] == "foto":
                compose.save_final(sl["diseno"], out)
                sl["diseno"] = _design_out(out, sl["diseno"])
            else:
                sl["archivo"] = _url(out / sl["nombre"])
        _job_set(job_id, estado="listo", diapositivas=slides)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _job_set(job_id, estado="error", error=str(e))


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
    job_id = _job_new("carrusel", out, {"n": len(inputs)})
    threading.Thread(target=_run_carrusel, args=(job_id, inputs, out, form), daemon=True).start()
    return jsonify(job=job_id)


def _lote_tipo(d: Path) -> str:
    if (d / "proyecto.json").exists() or d.name.endswith("_reel"):
        return "reel"
    if d.name.endswith("_carrusel"):
        return "carrusel"
    return "piezas"


@app.get("/api/recientes")
def api_recientes():
    """Lo generado en los últimos 14 días (y lo que se está procesando)."""
    limite = time.time() - 14 * 86400
    items = []
    activos = {}
    for f in JOBS_DIR.glob("*.json") if JOBS_DIR.is_dir() else []:
        if f.stat().st_mtime < limite:
            continue
        j = _job_get(f.stem)
        if j and j.get("estado") == "procesando":
            activos[j["lote"]] = j["id"]
    for d in sorted((p for p in OUT_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")),
                    key=lambda p: p.name, reverse=True):
        if d.stat().st_mtime < limite or d.name == "prueba-compose" or len(items) >= 40:
            continue
        tipo = _lote_tipo(d)
        thumb, n = None, 0
        if tipo == "reel":
            mp4 = sorted(d.glob("DER-reel*.mp4"), key=lambda p: p.stat().st_mtime)
            minis = sorted((d / "miniaturas").glob("*.jpg")) if (d / "miniaturas").is_dir() else []
            thumb = _url(minis[0]) if minis else None
            n = len(mp4)
            if not mp4 and d.name not in activos:
                continue
        else:
            finals = sorted(p for p in d.glob("DER-*.jpg") if ".base." not in p.name)
            vids = sorted(d.glob("DER-carrusel-*.mp4"))
            thumb = _url(finals[0]) if finals else None
            n = len(finals) + len(vids)
            if not n and d.name not in activos:
                continue
        fecha = datetime.strptime(d.name[:17], "%Y-%m-%d_%H%M%S") if d.name[:4].isdigit() else None
        items.append({"lote": d.name, "tipo": tipo, "plantilla": d.name[18:], "n": n, "miniatura": thumb,
                      "fecha": fecha.strftime("%d/%m %H:%M") if fecha else "",
                      "trabajo": activos.get(d.name)})
    return jsonify(items=items)


@app.get("/api/lote/<lote>")
def api_lote(lote):
    """Vuelve a abrir algo ya generado (desde Recientes o desde una notificación)."""
    d = _lote(lote)
    tipo = _lote_tipo(d)
    if tipo == "reel":
        mp4 = sorted(d.glob("DER-reel*.mp4"), key=lambda p: p.stat().st_mtime)
        if not mp4:
            abort(404)
        info = {"tipo": "reel", "archivo": _url(mp4[-1])}
        if (d / "proyecto.json").exists():
            project = json.loads((d / "proyecto.json").read_text(encoding="utf-8"))
            _prepare_previews(d, project)
            # si quedó un borrador (vista previa sin exportar), se retoma desde ahí
            borrador = d / "borrador.json"
            if borrador.exists() and borrador.stat().st_mtime > (d / "proyecto.json").stat().st_mtime:
                project = json.loads(borrador.read_text(encoding="utf-8"))
                info["borrador"] = True
            _prepare_previews(d, project)
            info.update(proyecto=_reel_info(d, project), **REEL_CATALOGO)
        return jsonify(info)
    designs = []
    for j in sorted(d.glob("DER-*.json")):
        data = json.loads(j.read_text(encoding="utf-8"))
        if "base_file" not in data:  # piezas de versiones anteriores
            data["base_file"] = f"{data['name']}.base.jpg"
        designs.append(_design_out(d, data))
    if tipo == "carrusel":
        by_name = {x["name"]: {"tipo": "foto", "diseno": x} for x in designs}
        for v in d.glob("DER-carrusel-*.mp4"):
            by_name[v.stem] = {"tipo": "video", "archivo": _url(v), "nombre": v.name,
                               "segundos": round(reels.probe(v)["duration"], 1)}
        return jsonify(tipo="carrusel", lote=d.name, diapositivas=[by_name[k] for k in sorted(by_name)])
    return jsonify(tipo="piezas", lote=d.name, disenos=designs)


# --- Avisos al celular (Web Push) --------------------------------------------------

@app.get("/sw.js")
def service_worker():
    resp = send_from_directory(ROOT / "static", "sw.js", mimetype="application/javascript", max_age=0)
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.get("/api/avisos/clave")
def api_avisos_clave():
    clave = aviso.clave_publica(ROOT)
    return jsonify(clave=clave, disponible=bool(clave))


@app.post("/api/avisos/suscribir")
def api_avisos_suscribir():
    sub = request.get_json(silent=True) or {}
    if not sub.get("endpoint"):
        return jsonify(error="Suscripción inválida."), 400
    aviso.guardar(ROOT, sub)
    return jsonify(ok=True)


@app.post("/api/avisos/probar")
def api_avisos_probar():
    n = aviso.enviar(ROOT, "Avisos activados", "Te voy a avisar acá cuando termine cada reel o pieza.", "/")
    return jsonify(enviados=n)


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
