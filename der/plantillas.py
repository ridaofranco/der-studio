"""Plantillas de reels (como las de CapCut): espacios para tus clips + textos y stickers ya armados.

Cada espacio define cuánto dura (en golpes de la música, así los cortes caen al ritmo), y cómo se ve:
filtro, animación, encuadre, velocidad y la transición al siguiente. Los textos usan campos
({titulo}, {fecha}…) que se completan en el formulario; si un campo queda vacío, ese texto no va.

Al usar una plantilla se arma un proyecto de reel común: después se edita con todas las herramientas.
También se puede guardar cualquier reel editado como plantilla propia (brand/plantillas/).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path

from . import music, reels

N, O, C, B = "#ff5c00", "#333333", "#f0f0f0", "#ffffff"  # naranja, oscuro, claro, blanco


def _s(beats, **kw):
    return {"beats": beats, **kw}


BUILTIN = {
    "resumen": {
        "nombre": "Resumen de evento", "descripcion": "8 tomas cortas al ritmo, título de entrada y cierre con la web.",
        "musica": "auto:energico", "campos": {"titulo": "Así vivimos el *Sponsor Day*", "lugar": "Córdoba · Noviembre 2026"},
        "espacios": [_s(4, anim="zoom_in", filtro="vivo"), *[_s(2, filtro="vivo", anim=a) for a in
                     ("ninguna", "latido", "ninguna", "zoom_out", "ninguna", "latido")], _s(4, filtro="vivo", anim="zoom_out")],
        "transicion": ("none", 0.2),
        "textos": [
            {"texto": "{titulo}", "desde": 0, "hasta": 0, "y": 0.45, "rol": "title", "tamano": 96, "anim": "subir"},
            {"texto": "{lugar}", "desde": 0, "hasta": 1, "y": 0.16, "tamano": 42, "caja": N, "anim": "deslizar"},
        ],
        "stickers": [{"tipo": "web", "desde": 7, "hasta": 7, "y": 0.86}],
    },
    "antes_despues": {
        "nombre": "Antes y después", "descripcion": "El armado en blanco y negro, la cortina y el evento a todo color.",
        "musica": "auto:corporativo", "campos": {"titulo": "Del armado al *show*"},
        "espacios": [_s(6, filtro="bn", anim="zoom_in", transition="wipeleft", transition_seconds=0.8),
                     _s(8, filtro="vivo", anim="zoom_out")],
        "textos": [
            {"texto": "ANTES", "desde": 0, "hasta": 0, "y": 0.14, "x": 0.25, "tamano": 46, "caja": O, "anim": "deslizar", "rol": "title"},
            {"texto": "DESPUÉS", "desde": 1, "hasta": 1, "y": 0.14, "x": 0.3, "tamano": 46, "caja": N, "anim": "deslizar", "rol": "title"},
            {"texto": "{titulo}", "desde": 1, "hasta": 1, "y": 0.8, "rol": "title", "tamano": 84, "anim": "subir"},
        ],
    },
    "detras": {
        "nombre": "Detrás de escena", "descripcion": "Tono cine, fundidos suaves y la etiqueta fija arriba.",
        "musica": "auto:corporativo", "campos": {"titulo": "Cómo se arma un *evento*", "lugar": "Buenos Aires"},
        "espacios": [_s(4, filtro="cine", anim=a, transition="fade", transition_seconds=0.5)
                     for a in ("kenburns", "zoom_in", "ninguna", "kenburns", "zoom_out", "ninguna")],
        "textos": [
            {"texto": "DETRÁS DE ESCENA", "desde": 0, "hasta": 5, "y": 0.1, "tamano": 36, "caja": N, "rol": "title", "anim": "aparecer"},
            {"texto": "{titulo}", "desde": 0, "hasta": 1, "y": 0.5, "rol": "title", "tamano": 90, "anim": "escribir"},
            {"texto": "{lugar}", "desde": 4, "hasta": 5, "y": 0.86, "tamano": 40, "anim": "subir"},
        ],
    },
    "anuncio": {
        "nombre": "Anuncio / lanzamiento", "descripcion": "Golpe de título, fecha grande y llamado a la acción.",
        "musica": "auto:energico", "campos": {"titulo": "Se viene el *Event Hub*", "fecha": "15 NOV", "lugar": "Asunción · Paraguay",
                                                "cta": "Escribinos · somosder.ar"},
        "espacios": [_s(4, anim="zoom_in", filtro="noche", transition="zoomin", transition_seconds=0.4),
                     _s(4, anim="latido", filtro="der", transition="slideup", transition_seconds=0.4),
                     _s(6, anim="zoom_out", filtro="vivo", fit="ajustar")],
        "textos": [
            {"texto": "{titulo}", "desde": 0, "hasta": 0, "y": 0.5, "rol": "title", "tamano": 104, "anim": "golpe"},
            {"texto": "{fecha}", "desde": 1, "hasta": 1, "y": 0.45, "rol": "title", "tamano": 150, "anim": "golpe", "color": N},
            {"texto": "{lugar}", "desde": 1, "hasta": 2, "y": 0.6, "tamano": 46, "anim": "subir"},
            {"texto": "{cta}", "desde": 2, "hasta": 2, "y": 0.84, "tamano": 46, "caja": O, "anim": "golpe"},
        ],
        "stickers": [{"tipo": "marco", "desde": 0, "hasta": 2}],
    },
    "testimonio": {
        "nombre": "Testimonio", "descripcion": "Un video con su voz original, la frase arriba y el nombre en una etiqueta.",
        "musica": "auto:suave", "volumen_musica": 0.25, "campos": {"frase": "La mejor producción que tuvimos", "nombre": "Ana Gómez · Marca X"},
        "espacios": [_s(0, segundos=20, sonido=True, filtro="suave", anim="ninguna")],
        "textos": [
            {"texto": "“{frase}”", "desde": 0, "hasta": 0, "y": 0.2, "tamano": 60, "anim": "subir"},
            {"texto": "{nombre}", "desde": 0, "hasta": 0, "y": 0.84, "tamano": 40, "caja": N, "anim": "deslizar", "inicio_extra": 1.0},
        ],
    },
    "cuenta_regresiva": {
        "nombre": "Cuenta regresiva", "descripcion": "3, 2, 1 en blanco y negro… y la revelación a todo color.",
        "musica": "auto:energico", "campos": {"titulo": "Falta *nada*", "fecha": "SÁBADO 21 HS"},
        "espacios": [_s(2, filtro="bn", anim="latido"), _s(2, filtro="bn", anim="latido"), _s(2, filtro="bn", anim="latido"),
                     _s(8, filtro="vivo", anim="zoom_out")],
        "transicion": ("none", 0.2),
        "textos": [
            {"texto": "3", "desde": 0, "hasta": 0, "y": 0.5, "rol": "title", "tamano": 260, "anim": "golpe", "color": N},
            {"texto": "2", "desde": 1, "hasta": 1, "y": 0.5, "rol": "title", "tamano": 260, "anim": "golpe", "color": N},
            {"texto": "1", "desde": 2, "hasta": 2, "y": 0.5, "rol": "title", "tamano": 260, "anim": "golpe", "color": N},
            {"texto": "{titulo}", "desde": 3, "hasta": 3, "y": 0.42, "rol": "title", "tamano": 100, "anim": "subir"},
            {"texto": "{fecha}", "desde": 3, "hasta": 3, "y": 0.58, "tamano": 48, "caja": N, "anim": "golpe"},
        ],
    },
    "top3": {
        "nombre": "Top 3", "descripcion": "Intro con título y tres momentos numerados.",
        "musica": "auto:energico", "campos": {"titulo": "3 claves de un *gran evento*", "punto1": "Accesos sin filas",
                                                "punto2": "Técnica que no falla", "punto3": "Un equipo que resuelve"},
        "espacios": [_s(4, anim="zoom_in", filtro="der", transition="slideleft", transition_seconds=0.35),
                     *[_s(6, anim="kenburns", filtro="der", transition="slideleft", transition_seconds=0.35) for _ in range(3)]],
        "textos": [
            {"texto": "{titulo}", "desde": 0, "hasta": 0, "y": 0.5, "rol": "title", "tamano": 96, "anim": "subir"},
            *[{"texto": str(k + 1), "desde": k + 1, "hasta": k + 1, "y": 0.2, "x": 0.18, "rol": "title", "tamano": 140,
               "anim": "golpe", "color": N} for k in range(3)],
            *[{"texto": f"{{punto{k + 1}}}", "desde": k + 1, "hasta": k + 1, "y": 0.8, "tamano": 54, "caja": O,
               "anim": "subir"} for k in range(3)],
        ],
    },
    "fotos_ritmo": {
        "nombre": "Fotos al ritmo", "descripcion": "Hasta 12 fotos, una por golpe, con zoom y latidos.",
        "musica": "auto:energico", "campos": {"titulo": "Una noche *épica*"},
        "espacios": [_s(2, anim=("kenburns" if k % 2 else "latido"), filtro="vivo") for k in range(12)],
        "transicion": ("none", 0.2),
        "textos": [{"texto": "{titulo}", "desde": 0, "hasta": 1, "y": 0.82, "rol": "title", "tamano": 92, "anim": "subir"}],
        "stickers": [{"tipo": "marco", "desde": 0, "hasta": 11}],
    },
}

CAMPO_NOMBRE = {"titulo": "Título", "lugar": "Lugar y fecha", "fecha": "Fecha", "cta": "Llamado a la acción",
                "frase": "Frase", "nombre": "Nombre y cargo", "punto1": "Punto 1", "punto2": "Punto 2", "punto3": "Punto 3"}


def _slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "mi-plantilla"


def user_dir(root: Path) -> Path:
    d = root / "brand" / "plantillas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bpm(music_choice: str) -> float:
    if music_choice.startswith("auto:"):
        return music.tempo(music_choice.split(":", 1)[1])
    return 120.0


def catalog(root: Path) -> list[dict]:
    """Lo que necesita el navegador para mostrar las plantillas."""
    out = []
    for key, t in BUILTIN.items():
        beat = 60 / _bpm(t["musica"])
        secs = [e.get("segundos") or e["beats"] * beat for e in t["espacios"]]
        out.append({"key": key, "nombre": t["nombre"], "descripcion": t["descripcion"], "propia": False,
                    "espacios": [round(x, 2) for x in secs], "duracion": round(sum(secs) + 2.5, 1),
                    "musica": t["musica"], "campos": [{"key": k, "nombre": CAMPO_NOMBRE.get(k, k), "ejemplo": v}
                                                       for k, v in t.get("campos", {}).items()]})
    for f in sorted(user_dir(root).glob("*.json")):
        t = json.loads(f.read_text(encoding="utf-8"))
        secs = [e["segundos"] for e in t["espacios"]]
        out.append({"key": "mia:" + f.stem, "nombre": t["nombre"], "descripcion": "Guardada desde el editor.",
                    "propia": True, "espacios": secs, "duracion": round(sum(secs) + 2.5, 1),
                    "musica": t["opciones"].get("music", ""), "campos": []})
    return out


def _fill(text: str, campos: dict) -> str | None:
    missing = False

    def sub(m):
        nonlocal missing
        v = str(campos.get(m.group(1), "")).strip()
        missing = missing or not v
        return v
    out = re.sub(r"\{(\w+)\}", sub, text)
    return None if missing else out


def _apply_slot(clip: reels.Clip, slot: dict, want: float) -> None:
    for k in ("filtro", "anim", "fit", "fondo", "zoom", "pan_x", "pan_y", "brillo", "contraste", "saturacion",
              "temperatura", "vineta", "rotate", "flip_h", "flip_v", "transition", "transition_seconds"):
        if k in slot:
            setattr(clip, k, slot[k])
    if clip.kind == "video":
        clip.speed = float(slot.get("speed", 1.0))
        clip.mute = not slot.get("sonido", slot.get("mute") is False)
        if "volume" in slot:
            clip.volume = float(slot["volume"])
        need = want * clip.speed
        if clip.source_duration > need:
            clip.start = round((clip.source_duration - need) / 2, 2)
            clip.end = round(clip.start + need, 2)
        else:
            clip.start, clip.end = 0.0, clip.source_duration
    else:
        clip.start, clip.end, clip.source_duration = 0.0, round(want, 2), round(want, 2)


def build(root: Path, key: str, campos: dict, srcs: list[Path], formato: str = "historia") -> dict:
    """Arma el proyecto del reel con la plantilla y los archivos (en el orden en que se subieron)."""
    if not srcs:
        raise ValueError("Subí al menos un video o una foto.")
    if key.startswith("mia:"):
        f = user_dir(root) / f"{_slug(key[4:])}.json"
        if not f.exists():
            raise ValueError("No encuentro esa plantilla.")
        return _build_user(json.loads(f.read_text(encoding="utf-8")), srcs, formato)
    t = BUILTIN.get(key)
    if not t:
        raise ValueError("No encuentro esa plantilla.")
    beat = 60 / _bpm(t["musica"])
    espacios = list(t["espacios"])
    # menos archivos que espacios: se usan los primeros; más archivos: se repite el estilo del último
    if len(srcs) < len(espacios):
        espacios = espacios[:len(srcs)]
    while len(espacios) < len(srcs):
        espacios.append(dict(espacios[-1]))
    tr_def = t.get("transicion", ("fade", 0.4))
    clips = []
    for src, slot in zip(srcs, espacios):
        c = reels.clip_from_file(src, reels.ReelOptions(max_clip_seconds=0, photo_seconds=3))
        slot = {"transition": tr_def[0], "transition_seconds": tr_def[1], **slot}
        want = slot.get("segundos") or slot["beats"] * beat
        _apply_slot(c, slot, want)
        clips.append(c)
    # comienzo y fin de cada espacio en el reel (para ubicar los textos)
    # cada espacio "se ve" desde la mitad de la transición de entrada hasta la mitad de la de salida
    starts, ends, t_acc, prev_T = [], [], 0.0, 0.0
    for i, c in enumerate(clips):
        T = 0 if c.transition == "none" or i == len(clips) - 1 else min(c.transition_seconds, c.duration / 2,
                                                                          clips[i + 1].duration / 2)
        starts.append(t_acc + prev_T / 2)
        ends.append(t_acc + c.duration - T / 2)
        t_acc += c.duration - T
        prev_T = T
    last = len(clips) - 1
    textos, stickers = [], []
    for tx in t.get("textos", []):
        a, b = min(tx["desde"], last), min(tx["hasta"], last)
        if tx["desde"] > last:
            continue
        txt = _fill(tx["texto"], campos)
        if not txt:
            continue
        textos.append({**{k: v for k, v in tx.items() if k not in ("desde", "hasta", "inicio_extra")}, "texto": txt,
                       "inicio": round(starts[a] + 0.1 + tx.get("inicio_extra", 0), 2), "fin": round(ends[b] - 0.05, 2)})
    for st in t.get("stickers", []):
        if st["desde"] > last:
            continue
        a, b = min(st["desde"], last), min(st["hasta"], last)
        stickers.append({**{k: v for k, v in st.items() if k not in ("desde", "hasta")},
                         "inicio": round(starts[a], 2), "fin": round(ends[b], 2)})
    opts = reels.ReelOptions(music=t["musica"], music_volume=t.get("volumen_musica", 0.9), formato=formato)
    opts.music_seed = __import__("random").randint(1, 10**6)
    project = {"version": 0, "clips": [asdict(c) for c in clips], "opciones": opts.to_dict(),
               "textos": textos, "stickers": stickers, "plantilla": t["nombre"]}
    return project


def _build_user(t: dict, srcs: list[Path], formato: str) -> dict:
    espacios = list(t["espacios"])
    if len(srcs) < len(espacios):
        espacios = espacios[:len(srcs)]
    while len(espacios) < len(srcs):
        espacios.append(dict(espacios[-1]))
    clips = []
    for src, slot in zip(srcs, espacios):
        c = reels.clip_from_file(src, reels.ReelOptions(max_clip_seconds=0, photo_seconds=3))
        _apply_slot(c, slot, slot["segundos"])
        clips.append(c)
    opts = {**t["opciones"], "formato": t["opciones"].get("formato", formato), "voz": ""}
    return {"version": 0, "clips": [asdict(c) for c in clips], "opciones": opts,
            "textos": t.get("textos", []), "stickers": t.get("stickers", []), "plantilla": t["nombre"]}


def save_user(root: Path, name: str, project: dict) -> str:
    """Guarda un reel editado como plantilla propia: cada clip pasa a ser un espacio con su estilo."""
    espacios = []
    for c in project["clips"]:
        cl = reels.load_clip(c)
        slot = {k: v for k, v in asdict(cl).items() if k not in ("src", "kind", "source_duration", "start", "end", "id")}
        slot["segundos"] = round(cl.duration, 2)
        slot["sonido"] = not cl.mute
        espacios.append(slot)
    data = {"nombre": name.strip()[:60] or "Mi plantilla", "espacios": espacios,
            "opciones": {k: v for k, v in project["opciones"].items() if k != "voz"},
            "textos": project.get("textos", []), "stickers": project.get("stickers", [])}
    slug = _slug(data["nombre"])
    (user_dir(root) / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return slug


def delete_user(root: Path, key: str) -> None:
    f = user_dir(root) / f"{_slug(key.removeprefix('mia:'))}.json"
    f.unlink(missing_ok=True)
