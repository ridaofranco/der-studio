"""Generador y editor de reels.

Un reel es un PROYECTO editable (proyecto.json en la carpeta del lote):
  - clips: cada uno con su tramo, velocidad, encuadre, filtro, ajustes, animación, audio y la
    transición hacia el siguiente;
  - opciones: formato (9:16, 4:5, 1:1), título, música, voz en off, logo.
Cada clip se prepara por separado y se guarda en cache/ según sus parámetros: cambiar una cosa
solo vuelve a procesar ese clip. La vista previa usa la misma receta a 1/3 del tamaño.

Usa el ffmpeg que viene con el paquete imageio-ffmpeg (no hace falta instalarlo aparte).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from PIL import Image, ImageDraw

from . import brand, graphics, music
from .brand import DARK, LIGHT, ORANGE, WHITE

FPS = 30
W, H = 1080, 1920   # tamaño por defecto (historia 9:16)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
FORMATS = {"historia": (1080, 1920), "post": (1080, 1350), "cuadrado": (1080, 1080)}
PREVIEW_SCALE = 3     # la vista previa sale a 1/3 (360 px de ancho)

# Transiciones de ffmpeg (xfade) que se ofrecen en el editor, con su nombre en castellano
TRANSITIONS = {
    "fade": "Fundido",
    "fadeblack": "Fundido a negro",
    "fadewhite": "Fundido a blanco",
    "dissolve": "Disolver",
    "slideleft": "Deslizar a la izquierda",
    "slideright": "Deslizar a la derecha",
    "slideup": "Deslizar hacia arriba",
    "slidedown": "Deslizar hacia abajo",
    "smoothleft": "Barrido suave",
    "smoothup": "Subir",
    "wipeleft": "Cortina",
    "circleopen": "Círculo",
    "zoomin": "Zoom",
    "radial": "Radial",
    "hblur": "Desenfoque",
    "pixelize": "Pixelado",
    "none": "Corte seco",
}

# Filtros de color (cadena de ffmpeg), como los "Filtros" de CapCut
FILTERS = {
    "ninguno": ("Original", ""),
    "vivo": ("Vivo", "eq=saturation=1.35:contrast=1.08"),
    "der": ("DER cálido", "colorbalance=rh=0.10:gh=0.02:bh=-0.08:rm=0.04:bm=-0.03,eq=saturation=1.1"),
    "cine": ("Cine", "eq=contrast=1.15:saturation=0.9,colorbalance=rs=-0.06:bs=0.08:rh=0.08:bh=-0.06"),
    "calido": ("Cálido", "colortemperature=temperature=4800,eq=saturation=1.08"),
    "frio": ("Frío", "colortemperature=temperature=8800"),
    "vintage": ("Vintage", "curves=preset=vintage,eq=saturation=0.85"),
    "suave": ("Suave", "eq=contrast=0.9:brightness=0.03:saturation=0.9"),
    "noche": ("Noche", "eq=brightness=-0.05:contrast=1.2,colortemperature=temperature=8200"),
    "bn": ("Blanco y negro", "hue=s=0,eq=contrast=1.12"),
    "bn_suave": ("B/N suave", "hue=s=0,eq=contrast=0.95:brightness=0.03"),
}

# Animaciones del clip (zoom/movimiento a lo largo del clip)
ANIMATIONS = {
    "ninguna": "Sin animación",
    "zoom_in": "Acercar",
    "zoom_out": "Alejar",
    "kenburns": "Paneo lento",
    "latido": "Latido",
    "sacudida": "Sacudida",
}

MIN_CLIP = 0.3        # segundos mínimos de un clip (ya con la velocidad aplicada)
MAX_PHOTO = 15.0      # segundos máximos de una foto
MAX_REVERSE = 6.0     # invertir guarda todos los cuadros en memoria: solo tramos cortos


@dataclass
class ReelOptions:
    title: str = ""
    subtitle: str = ""
    max_clip_seconds: float = 6.0     # al crear: recorta cada clip a este máximo (0 = sin límite)
    photo_seconds: float = 3.0        # al crear: duración de cada foto
    transition: str = "fade"          # al crear: transición entre clips
    transition_seconds: float = 0.4
    music: str = "auto:energico"      # auto:<estilo> | <archivo en brand/music> | none
    music_volume: float = 0.9
    music_start: float = 0.0          # desde qué segundo del tema arranca (temas propios)
    music_fade_out: float = 1.8
    keep_original_audio: bool = False
    watermark: bool = True
    outro: bool = True
    outro_seconds: float = 3.0
    logo: str = "auto"                # auto | nombre de archivo en brand/logos
    music_seed: int = 0               # misma semilla = misma música al volver a editar
    formato: str = "historia"         # historia (9:16) | post (4:5) | cuadrado (1:1)
    voz: str = ""                     # archivo de voz en off en <lote>/fuentes
    voz_volume: float = 1.0
    voz_ducking: bool = True          # baja la música mientras habla la voz
    log: list[str] = field(default_factory=list)

    EDITABLE = ("title", "subtitle", "music", "music_volume", "music_start", "music_fade_out",
                "keep_original_audio", "watermark", "outro", "logo", "music_seed", "formato",
                "voz", "voz_volume", "voz_ducking")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.EDITABLE}


@dataclass
class Clip:
    """Un tramo del reel. `transition` es la que va entre este clip y el siguiente."""
    src: str                          # nombre del archivo en <lote>/fuentes
    kind: str                         # video | foto
    source_duration: float
    start: float
    end: float
    transition: str = "fade"
    transition_seconds: float = 0.4
    id: str = ""                      # identificador para el editor (los clips divididos comparten src)
    speed: float = 1.0                # 0,25x a 4x
    reverse: bool = False
    volume: float = 1.0               # audio original del clip (0 a 2)
    mute: bool = True
    fit: str = "llenar"               # llenar (recorta) | ajustar (entra entero, con fondo)
    fondo: str = "blur"               # blur | #rrggbb (para "ajustar")
    zoom: float = 1.0                 # 1 a 3
    pan_x: float = 0.0                # -1 (izquierda) a 1 (derecha)
    pan_y: float = 0.0                # -1 (arriba) a 1 (abajo)
    rotate: int = 0                   # 0 | 90 | 180 | 270
    flip_h: bool = False
    flip_v: bool = False
    filtro: str = "ninguno"
    brillo: float = 0.0               # -100 a 100
    contraste: float = 0.0
    saturacion: float = 0.0
    temperatura: float = 0.0          # -100 (frío) a 100 (cálido)
    vineta: float = 0.0               # 0 a 100
    anim: str = "ninguna"

    @property
    def duration(self) -> float:
        """Duración en el reel (con la velocidad aplicada)."""
        return (self.end - self.start) / (1.0 if self.kind == "foto" else self.speed)

    def render_key(self, fmt: str, preview: bool) -> str:
        skip = {"transition", "transition_seconds", "id", "source_duration"}
        d = {k: v for k, v in asdict(self).items() if k not in skip}
        return json.dumps({**d, "fmt": fmt, "preview": preview, "v": 3}, sort_keys=True)


CLIP_FIELDS = {f.name for f in fields(Clip)}


def ffmpeg_exe() -> str:
    """ffmpeg incluido en imageio-ffmpeg; si no está, el del sistema."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("No encuentro ffmpeg. Volvé a ejecutar iniciar.bat para reinstalar.")
        return exe


# En Windows, que ffmpeg no abra ventanas de consola
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ff(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([ffmpeg_exe(), *cmd[1:]] if cmd[0] == "ffmpeg" else cmd,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          creationflags=_NO_WINDOW)


def _run(cmd: list[str], log: list[str]) -> None:
    log.append(" ".join(cmd))
    proc = _ff(cmd)
    if proc.returncode != 0:
        # lo útil del error (sin el listado de metadatos de cada archivo)
        lines = [ln for ln in proc.stderr.splitlines() if ln.strip() and not ln.startswith(" ")
                 and not ln.startswith(("Input #", "Output #", "Stream mapping", "Press [q]"))]
        raise RuntimeError("ffmpeg falló:\n" + "\n".join(lines[-12:])[-1500:])


def probe(path: Path) -> dict:
    """Duración, tamaño (ya rotado) y si tiene audio, leyendo la salida de `ffmpeg -i`."""
    err = _ff(["ffmpeg", "-hide_banner", "-i", str(path)]).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    duration = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0
    w = h = 0
    vm = re.search(r"Stream #.*?Video:.*?(\d{2,5})x(\d{2,5})", err)
    if vm:
        w, h = int(vm[1]), int(vm[2])
    rm = re.search(r"rotat(?:e|ion of)\s*:?\s*(-?\d+(?:\.\d+)?)", err)
    if rm and abs(round(float(rm[1]))) % 180 == 90:
        w, h = h, w
    return {"duration": duration, "w": w, "h": h, "audio": bool(re.search(r"Stream #.*?Audio:", err))}


def frame_size(fmt: str, preview: bool = False) -> tuple[int, int]:
    w, h = FORMATS.get(fmt, FORMATS["historia"])
    if preview:
        w, h = w // PREVIEW_SCALE // 2 * 2, h // PREVIEW_SCALE // 2 * 2
    return w, h


# --- Gráficos de marca para el reel ------------------------------------------

def render_outro(path: Path, logo_choice: str = "auto", size: tuple[int, int] = (W, H)) -> Path:
    w, h = size
    s = w / 1080
    img = Image.new("RGB", (w, h), DARK)
    d = ImageDraw.Draw(img)
    m = 120 * s
    box_h = min(h - 2 * m, 800 * s)
    graphics.corner_brackets(d, (m, (h - box_h) / 2, w - m, (h + box_h) / 2), 120 * s, max(2, 12 * s), ORANGE, "all")
    lg = brand.logo_sized("on_dark", width=int(560 * s), choice=logo_choice)
    if lg.height > box_h * 0.6:
        lg = brand.logo_sized("on_dark", height=int(box_h * 0.6), choice=logo_choice)
    img.paste(lg, ((w - lg.width) // 2, (h - lg.height) // 2 - int(40 * s)), lg)
    f = brand.font("subtitle", max(10, int(44 * s)))
    yy = h / 2 + lg.height / 2 + 20 * s
    d.text((w / 2, yy), brand.WEBSITE.upper(), font=f, fill=LIGHT, anchor="mt")
    d.rectangle([w / 2 - 45 * s, yy + 80 * s, w / 2 + 45 * s, yy + 90 * s], fill=ORANGE)
    img.save(path)
    return path


def render_title_overlay(path: Path, title: str, subtitle: str, size: tuple[int, int] = (W, H)) -> Path:
    w, h = size
    s = w / 1080
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # degradé inferior para legibilidad
    shade = Image.new("RGB", (w, h), brand.DARK_RGB)
    mask = Image.new("L", (1, h), 0)
    for y in range(int(h * 0.45), h):
        mask.putpixel((0, y), int(210 * (max(0.0, y - h * 0.45) / (h * 0.55)) ** 1.3))
    img.paste(shade, (0, 0), mask.resize((w, h)))
    d = ImageDraw.Draw(img)
    c = graphics.Content(title=title, subtitle=subtitle)
    m = 80 * s
    block = graphics.measure_block(c, w - 2 * m, h * 0.3, s, title_size=100)
    bottom = (420 if h / w > 1.6 else 160) * s
    y = h - bottom - block
    graphics.accent_bar(d, m, y - 44 * s, s)
    graphics.text_block(d, m, y, w - 2 * m, h * 0.3, c, s, WHITE, ORANGE, LIGHT, title_size=100)
    img.save(path)
    return path


def render_watermark(path: Path, logo_choice: str = "auto", size: tuple[int, int] = (W, H)) -> Path:
    w, h = size
    s = w / 1080
    lg = brand.logo_sized("on_dark", width=max(8, int(150 * s)), choice=logo_choice)
    if lg.height > 150 * s:
        lg = brand.logo_sized("on_dark", height=max(8, int(150 * s)), choice=logo_choice)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    top = (200 if h / w > 1.6 else 70) * s
    canvas.paste(lg, (int(w - 70 * s - lg.width), int(top)), lg)
    alpha = canvas.getchannel("A").point(lambda a: int(a * 0.85))
    canvas.putalpha(alpha)
    canvas.save(path)
    return path


# --- Textos y stickers (capas con tiempo) -------------------------------------------

TEXT_ANIMS = {"aparecer": "Aparecer", "subir": "Subir", "deslizar": "Deslizar", "golpe": "Golpe",
              "escribir": "Máquina de escribir", "ninguna": "Sin animación"}
STICKERS = {"logo": "Logo", "marco": "Marco de esquineros", "puntos": "Grilla de puntos", "barra": "Barra naranja",
            "web": "SOMOSDER.AR", "flecha": "Flecha"}


def _rgb(c: str, default: str) -> str:
    return c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else default


def render_text(t: dict, size: tuple[int, int], dst: Path, upto: int | None = None) -> tuple[int, int]:
    """Dibuja un texto (con caja opcional) recortado a su tamaño. Devuelve (x, y) donde va en el cuadro.
    `upto` = cantidad de letras visibles (para la máquina de escribir)."""
    w, h = size
    s = w / 1080
    role = t.get("rol", "subtitle") if t.get("rol") in ("title", "subtitle", "body") else "subtitle"
    fsize = max(8, int(float(t.get("tamano", 64)) * s))
    f = brand.font(role, fsize)
    text = str(t.get("texto", ""))
    if t.get("mayus") or role == "title":
        text = text.upper()
    color = _rgb(t.get("color"), WHITE)
    hl = WHITE if color.lower() == ORANGE.lower() else ORANGE
    max_w = w * 0.84
    lines = []
    for para in text.split("\n"):
        lines += graphics._wrap(graphics._tokens(para), f, max_w) or [[]]
    if upto is not None:  # recortar a las primeras `upto` letras
        left, cut = upto, []
        for line in lines:
            row = []
            for word, hi in line:
                if left <= 0:
                    break
                row.append((word[:left], hi))
                left -= len(word) + 1
            cut.append(row)
            if left <= 0:
                break
        lines = cut
    gap = 1.18
    lh = fsize * gap
    asc = f.getmetrics()[0]
    widths = [sum(f.getlength(wd) for wd, _ in ln) + f.getlength(" ") * max(0, len(ln) - 1) for ln in lines]
    full_widths = widths if upto is None else [max(widths + [1])] * len(widths)
    bw = max([1] + [int(x) for x in widths])
    bh = max(1, int(len(lines) * lh))
    box = t.get("caja") if t.get("caja") not in (None, "", "ninguna") else None
    pad_x, pad_y = (int(fsize * 0.45), int(fsize * 0.28)) if box else (int(fsize * 0.1), int(fsize * 0.1))
    shadow = not box and t.get("sombra", True)
    img = Image.new("RGBA", (bw + 2 * pad_x, bh + 2 * pad_y), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if box:
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=int(fsize * 0.18), fill=_rgb(box, DARK))
    align = t.get("alinear", "centro")
    for i, ln in enumerate(lines):
        lw = widths[i]
        x0 = pad_x + ((bw - lw) / 2 if align == "centro" else (bw - lw) if align == "derecha" else 0)
        yy = pad_y + i * lh + (lh - asc) * 0.35
        x = x0
        for word, hi in ln:
            col = hl if hi else color
            if shadow:
                d.text((x + max(1, fsize * 0.04), yy + max(1, fsize * 0.05)), word, font=f, fill=(0, 0, 0, 150))
            d.text((x, yy), word, font=f, fill=col)
            x += f.getlength(word) + f.getlength(" ")
    img.save(dst)
    cx, cy = float(t.get("x", 0.5)), float(t.get("y", 0.5))
    if upto is not None:
        # la posición la fija el texto completo (así no "baila" mientras se escribe)
        full = render_text({**t}, size, dst.with_name(dst.stem + "_full.png"))
        fimg = Image.open(dst.with_name(dst.stem + "_full.png"))
        x = int(full[0] + (fimg.width - img.width) * (0 if align == "izquierda" else 0.5 if align == "centro" else 1))
        return x, full[1]
    x = int(min(w - img.width, max(0, cx * w - img.width / 2)))
    y = int(min(h - img.height, max(0, cy * h - img.height / 2)))
    return x, y


def render_sticker(st: dict, size: tuple[int, int], dst: Path, logo_choice: str = "auto") -> tuple[int, int]:
    w, h = size
    s = w / 1080
    kind = st.get("tipo", "logo")
    scale = max(0.2, min(3.0, float(st.get("tamano", 1.0))))
    color = _rgb(st.get("color"), ORANGE)
    if kind == "logo":
        variant = st.get("variante", "on_dark")
        img = brand.logo_sized(variant if variant in ("on_dark", "on_light", "on_orange") else "on_dark",
                               width=max(8, int(260 * s * scale)), choice=st.get("logo") or logo_choice)
    elif kind == "marco":
        m = int(60 * s)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        graphics.corner_brackets(ImageDraw.Draw(img), (m, m, w - m, h - m), int(110 * s * scale),
                                 max(2, int(10 * s * scale)), color, "all")
        img.save(dst)
        return 0, 0
    elif kind == "puntos":
        gap, r = int(28 * s * scale), max(2, int(4 * s * scale))
        img = graphics.element_png("puntos", cols=6, rows=4, gap=gap, r=r, color=color).copy()
    elif kind == "barra":
        img = Image.new("RGBA", (max(4, int(140 * s * scale)), max(2, int(14 * s * scale))), color)
    elif kind == "web":
        f = brand.font("subtitle", max(8, int(34 * s * scale)))
        tw = int(f.getlength(brand.WEBSITE.upper()))
        img = Image.new("RGBA", (tw + int(36 * s * scale), int(64 * s * scale)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=int(10 * s * scale), fill=color)
        d.text((img.width / 2, img.height / 2), brand.WEBSITE.upper(), font=f, fill=WHITE, anchor="mm")
    else:  # flecha
        L = int(160 * s * scale)
        img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        th = max(3, int(L * 0.12))
        d.line([(L * 0.1, L * 0.5), (L * 0.85, L * 0.5)], fill=color, width=th)
        d.polygon([(L * 0.95, L * 0.5), (L * 0.62, L * 0.22), (L * 0.62, L * 0.78)], fill=color)
        rot = float(st.get("giro", 0))
        if rot:
            img = img.rotate(-rot, expand=True, resample=Image.BICUBIC)
    op = max(0.1, min(1.0, float(st.get("opacidad", 1.0))))
    if op < 1:
        img.putalpha(img.getchannel("A").point(lambda a: int(a * op)))
    img.save(dst)
    cx, cy = float(st.get("x", 0.5)), float(st.get("y", 0.5))
    return int(min(w - img.width, max(0, cx * w - img.width / 2))), int(min(h - img.height, max(0, cy * h - img.height / 2)))


def layer_overlays(textos: list[dict], stickers: list[dict], size: tuple[int, int], tmp: Path,
                   logo_choice: str) -> list[dict]:
    out = []
    for i, st in enumerate(stickers):
        png = tmp / f"sticker{i}.png"
        x, y = render_sticker(st, size, png, logo_choice)
        out.append({"png": png, "t0": float(st["inicio"]), "t1": float(st["fin"]), "x": x, "y": y,
                    "anim": st.get("anim", "aparecer")})
    for i, t in enumerate(textos):
        if not str(t.get("texto", "")).strip():
            continue
        t0, t1 = float(t["inicio"]), float(t["fin"])
        if t.get("anim") == "escribir":
            n = len(str(t["texto"]))
            steps = max(1, min(n, 24))
            write_time = min(1.2, (t1 - t0) * 0.6)
            for k in range(1, steps + 1):
                png = tmp / f"texto{i}_{k}.png"
                x, y = render_text(t, size, png, upto=max(1, round(n * k / steps)))
                a = t0 + write_time * (k - 1) / steps
                b = t0 + write_time * k / steps if k < steps else t1
                out.append({"png": png, "t0": a, "t1": b, "x": x, "y": y, "anim": "ninguna"})
            continue
        png = tmp / f"texto{i}.png"
        x, y = render_text(t, size, png)
        out.append({"png": png, "t0": t0, "t1": t1, "x": x, "y": y, "anim": t.get("anim", "aparecer")})
    return out


# --- Un clip ------------------------------------------------------------------

def _atempo(speed: float) -> str:
    """atempo solo acepta 0,5 a 2 por etapa: se encadena."""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def _color_chain(c: Clip) -> list[str]:
    out = []
    preset = FILTERS.get(c.filtro, FILTERS["ninguno"])[1]
    if preset:
        out.append(preset)
    if c.brillo or c.contraste or c.saturacion:
        out.append(f"eq=brightness={c.brillo / 100 * 0.3:.3f}:contrast={1 + c.contraste / 100 * 0.6:.3f}:"
                   f"saturation={max(0, 1 + c.saturacion / 100):.3f}")
    if c.temperatura:
        out.append(f"colortemperature=temperature={6500 - c.temperatura * 30:.0f}")
    if c.vineta:
        out.append(f"vignette=angle={0.2 + c.vineta / 100 * 0.6:.3f}")
    return out


def _zoom_expr(c: Clip, D: float) -> str:
    z = max(1.0, min(3.0, c.zoom))
    D = max(D, 0.1)
    return {
        "zoom_in": f"{z}*(1+0.15*t/{D:.3f})",
        "zoom_out": f"{z}*(1.15-0.15*t/{D:.3f})",
        "kenburns": f"{z}*(1.08+0.08*t/{D:.3f})",
        "latido": f"{z}*(1.02+0.05*abs(sin(t*3.1416*2)))",
        "sacudida": f"{z}*1.06",
    }.get(c.anim, f"{z}")


def _clip_filter(c: Clip, src_w: int, src_h: int, w: int, h: int, D: float) -> str:
    """Cadena de video de un clip: tiempo → orientación → encuadre/animación → color."""
    pre = []
    if c.kind == "video":
        if c.reverse:
            pre.append("reverse")
        pre.append(f"setpts=(PTS-STARTPTS)/{c.speed:.4f}")
    rot = c.rotate % 360
    if rot == 90:
        pre.append("transpose=1")
    elif rot == 270:
        pre.append("transpose=2")
    elif rot == 180:
        pre.append("hflip,vflip")
    if c.flip_h:
        pre.append("hflip")
    if c.flip_v:
        pre.append("vflip")
    if rot in (90, 270):
        src_w, src_h = src_h, src_w
    src_w, src_h = max(2, src_w), max(2, src_h)
    pre.append(f"fps={FPS}")
    z = _zoom_expr(c, D)
    px, py = max(-1, min(1, c.pan_x)), max(-1, min(1, c.pan_y))
    px_e = f"({px:.3f}-0.5+t/{max(D, .1):.3f})" if c.anim == "kenburns" else f"{px:.3f}"
    shake_x = "+12*sin(t*47)" if c.anim == "sacudida" else ""
    shake_y = "+9*cos(t*39)" if c.anim == "sacudida" else ""
    color = _color_chain(c)
    color_s = ("," + ",".join(color)) if color else ""
    if c.fit == "ajustar":
        k = min(w / src_w, h / src_h)
        fg = f"scale=w='trunc({src_w * k:.3f}*{z}/2)*2':h='trunc({src_h * k:.3f}*{z}/2)*2':eval=frame"
        if c.fondo == "blur":
            kb = max(w / src_w, h / src_h)
            bg = (f"[s1]scale={max(2, int(src_w * kb / 4) * 2)}:{max(2, int(src_h * kb / 4) * 2)},boxblur=20:3,"
                  f"scale={int(src_w * kb) // 2 * 2 + 2}:{int(src_h * kb) // 2 * 2 + 2},crop={w}:{h},"
                  f"eq=brightness=-0.12[bg]")
        else:
            col = c.fondo if re.fullmatch(r"#[0-9a-fA-F]{6}", c.fondo or "") else "#333333"
            bg = f"[s1]scale={w}:{h},drawbox=c={col}:t=fill[bg]"
        # el filtro va sobre el clip (y su fondo desenfocado), no sobre un fondo de color liso
        return (f"[0:v]{','.join(pre)}{color_s},split[s0][s1];{bg};[s0]{fg}[fg];"
                f"[bg][fg]overlay=x='(W-w)/2-(W-w)/2*{px_e}{shake_x}':y='(H-h)/2-(H-h)/2*{py:.3f}{shake_y}'"
                f":eval=frame,format=yuv420p,setsar=1[v]")
    k = max(w / src_w, h / src_h)
    sc = f"scale=w='trunc({src_w * k:.3f}*{z}/2)*2+2':h='trunc({src_h * k:.3f}*{z}/2)*2+2':eval=frame"
    crop = (f"crop={w}:{h}:x='max(0,min(in_w-{w},(in_w-{w})*(0.5+0.5*{px_e}){shake_x}))'"
            f":y='max(0,min(in_h-{h},(in_h-{h})*(0.5+0.5*{py:.3f}){shake_y}))'")
    return f"[0:v]{','.join(pre)},{sc},{crop}{color_s},format=yuv420p,setsar=1[v]"


def render_clip(c: Clip, src: Path, dst: Path, w: int, h: int, tmp: Path, log: list[str], preview: bool) -> float:
    """Prepara un clip ya listo para unir: tamaño final, 30 cuadros, audio estéreo."""
    D = c.duration
    if c.kind == "foto":
        img = graphics.load_photo(src)
        img.thumbnail((2400, 2400))
        still = tmp / f"{dst.stem}.jpg"
        img.save(still, quality=93)
        sw, sh = img.size
        inp = ["-loop", "1", "-framerate", str(FPS), "-t", f"{D:.3f}", "-i", str(still)]
        has_audio = False
    else:
        info = probe(src)
        sw, sh = info["w"], info["h"]
        if c.reverse and D > MAX_REVERSE:
            raise ValueError(f"Para invertir, el clip tiene que durar {MAX_REVERSE:.0f} s o menos.")
        inp = ["-ss", f"{c.start:.3f}", "-t", f"{c.end - c.start:.3f}", "-i", str(src)]
        has_audio = info["audio"] and not c.mute and c.volume > 0
    vf = _clip_filter(c, sw, sh, w, h, D)
    if has_audio:
        af = ["areverse"] if c.reverse else []
        if abs(c.speed - 1) > 1e-3:
            af.append(_atempo(c.speed))
        af.append(f"volume={c.volume:.2f}")
        af.append("afade=in:d=0.04")
        filt = vf + f";[0:a]{','.join(af)},aresample=44100,aformat=channel_layouts=stereo[a]"
        amap, extra = ["-map", "[a]"], []
    else:
        filt = vf
        extra = ["-f", "lavfi", "-t", f"{D:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = ["-map", "1:a"]
    preset, crf = ("ultrafast", "30") if preview else ("veryfast", "19")
    _run(["ffmpeg", "-y", *inp, *extra, "-filter_complex", filt, "-map", "[v]", *amap,
          "-t", f"{D:.3f}", "-c:v", "libx264", "-preset", preset, "-crf", crf,
          "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)], log)
    return probe(dst)["duration"]


def _outro_clip(dst: Path, opts: ReelOptions, tmp: Path, size: tuple[int, int], preview: bool) -> float:
    w, h = size
    png = render_outro(tmp / "outro.png", opts.logo, size)
    frames = int(opts.outro_seconds * FPS)
    vf = (f"scale={w * 2}:{h * 2},zoompan=z='min(1+0.0006*on,1.06)':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},format=yuv420p,setsar=1")
    preset = "ultrafast" if preview else "veryfast"
    _run(["ffmpeg", "-y", "-i", str(png), "-f", "lavfi", "-t", f"{opts.outro_seconds}",
          "-i", "anullsrc=r=44100:cl=stereo", "-vf", vf, "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", preset, "-crf", "19", "-c:a", "aac", "-ar", "44100",
          "-ac", "2", "-shortest", str(dst)], opts.log)
    return probe(dst)["duration"]


def timeline_length(durs: list[float], transitions: list[tuple[str, float]]) -> float:
    """Duración total uniendo con transiciones (cada transición superpone los dos clips)."""
    if not durs:
        return 0.0
    acc = durs[0]
    for i in range(1, len(durs)):
        name, T = transitions[i - 1] if i - 1 < len(transitions) else ("fade", 0.4)
        T = 0 if name == "none" else min(T, durs[i - 1] / 2, durs[i] / 2)
        acc += durs[i] - T
    return acc


def _join(clips: list[tuple[Path, float]], transitions: list[tuple[str, float]],
          overlays: list, dst: Path, log: list[str], preview: bool = False) -> float:
    """Une los clips (una transición por corte) y aplica las capas: marca de agua, título, textos y stickers.
    Cada capa: (png, desde, hasta) o {"png", "t0", "t1", "x", "y", "anim"}."""
    overlays = [o if isinstance(o, dict) else {"png": o[0], "t0": o[1], "t1": o[2]} for o in overlays]
    cmd = ["ffmpeg", "-y"]
    for p, _ in clips:
        cmd += ["-i", str(p)]
    for o in overlays:
        cmd += ["-loop", "1", "-i", str(o["png"])]
    # misma base de tiempo y formato en todos los tramos: xfade no acepta mezclas
    # (por ejemplo, la salida de un corte seco con el clip siguiente)
    parts = [f"[{i}:v]fps={FPS},settb=AVTB,format=yuv420p,setsar=1[n{i}];"
             f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[m{i}]" for i in range(len(clips))]
    v_prev, a_prev = "[n0]", "[m0]"
    acc = clips[0][1]
    for i in range(1, len(clips)):
        dur = clips[i][1]
        name, T = transitions[i - 1] if i - 1 < len(transitions) else ("fade", 0.4)
        T = 0 if name == "none" else min(T, clips[i - 1][1] / 2, dur / 2)
        if T > 0:
            parts.append(f"{v_prev}[n{i}]xfade=transition={name}:duration={T:.3f}:"
                         f"offset={acc - T:.3f}[v{i}]")
            parts.append(f"{a_prev}[m{i}]acrossfade=d={T:.3f}[a{i}]")
            acc += dur - T
        else:
            parts.append(f"{v_prev}{a_prev}[n{i}][m{i}]concat=n=2:v=1:a=1[vc{i}][a{i}];[vc{i}]settb=AVTB[v{i}]")
            acc += dur
        v_prev, a_prev = f"[v{i}]", f"[a{i}]"
    n = len(clips)
    for k, o in enumerate(overlays):
        idx = n + k
        t0, t1 = max(0.0, o["t0"]), min(o["t1"], acc)
        if t1 - t0 < 0.05:
            parts.append(f"[{idx}:v]nullsink")
            continue
        anim = o.get("anim", "aparecer")
        d = 0.12 if anim == "golpe" else 0.35
        fades = []
        if anim not in ("ninguna", "escribir"):
            fades.append(f"fade=in:st={t0:.2f}:d={d}:alpha=1")
            if t1 < acc - 0.05:
                fades.append(f"fade=out:st={max(t0, t1 - d):.2f}:d={d}:alpha=1")
        fade_s = ("," + ",".join(fades)) if fades else ""
        x, y = o.get("x", 0), o.get("y", 0)
        xe, ye = f"{x}", f"{y}"
        if anim == "subir":
            ye = f"{y}+if(lt(t-{t0:.2f},0.45),(1-(t-{t0:.2f})/0.45)*main_h*0.05,0)"
        elif anim == "deslizar":
            xe = f"{x}-if(lt(t-{t0:.2f},0.45),(1-(t-{t0:.2f})/0.45)*main_w*0.08,0)"
        parts.append(f"[{idx}:v]format=rgba{fade_s}[ov{k}]")
        parts.append(f"{v_prev}[ov{k}]overlay=x='{xe}':y='{ye}':eval=frame:"
                     f"enable='between(t,{t0:.2f},{t1:.2f})':shortest=1[vo{k}]")
        v_prev = f"[vo{k}]"
    preset, crf = ("ultrafast", "30") if preview else ("veryfast", "19")
    cmd += ["-filter_complex", ";".join(parts), "-map", v_prev, "-map", a_prev,
            "-t", f"{acc:.3f}", "-c:v", "libx264", "-preset", preset, "-crf", crf,
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)]
    _run(cmd, log)
    return acc


def _add_music(src: Path, duration: float, opts: ReelOptions, tmp: Path, dst: Path,
               has_original: bool, voz: Path | None) -> None:
    """Mezcla: audio de los clips + música (con fundidos) + voz en off (baja la música al hablar)."""
    choice = opts.music or "none"
    inputs, mix = ["-i", str(src)], []
    labels = ["[0:a]"]
    k = 1
    music_label = None
    if choice != "none":
        if choice.startswith("auto"):
            style = choice.split(":", 1)[1] if ":" in choice else "energico"
            track = music.generate(duration + 0.5, tmp / "music.wav", style, seed=opts.music_seed)
            inputs += ["-i", str(track)]
        else:
            track = brand.MUSIC_DIR / Path(choice).name
            if not track.exists():
                raise FileNotFoundError(f"No encuentro el tema {choice} en brand/music")
            inputs += ["-stream_loop", "-1", "-ss", f"{max(0, opts.music_start):.2f}", "-i", str(track)]
        fo = max(0.0, min(opts.music_fade_out, duration / 2))
        vol = opts.music_volume * (0.35 if has_original else 1.0)
        mix.append(f"[{k}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={vol:.2f},"
                   f"afade=in:st=0:d=0.3,afade=out:st={max(0, duration - fo):.2f}:d={max(fo, 0.01):.2f}[m]")
        music_label = "[m]"
        k += 1
    if voz:
        inputs += ["-i", str(voz)]
        mix.append(f"[{k}:a]volume={opts.voz_volume:.2f},aresample=44100,aformat=channel_layouts=stereo,"
                   f"apad=whole_dur={duration:.3f},atrim=0:{duration:.3f},asplit=2[voz][vk]")
        if music_label and opts.voz_ducking:
            mix.append(f"{music_label}[vk]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md]")
            music_label = "[md]"
        else:
            mix.append("[vk]anullsink")
        labels.append("[voz]")
    if music_label:
        labels.append(music_label)
    if len(labels) == 1:
        shutil.copy(src, dst)
        return
    mix.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95[a]")
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(mix),
          "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", "-t", f"{duration:.3f}", str(dst)], opts.log)


# --- Proyecto -----------------------------------------------------------------

def _new_id() -> str:
    return hashlib.sha1(str(random.random()).encode()).hexdigest()[:8]


def clip_from_file(src: Path, opts: ReelOptions | None = None) -> Clip:
    opts = opts or ReelOptions()
    t_sec = opts.transition_seconds
    if src.suffix.lower() in IMAGE_EXT:
        d = float(opts.photo_seconds)
        return Clip(src.name, "foto", d, 0.0, d, opts.transition, t_sec, id=_new_id(), anim="kenburns")
    dur = probe(src)["duration"]
    if dur <= 0:
        raise ValueError(f"No pude leer el video {src.name}.")
    start, end = 0.0, dur
    if opts.max_clip_seconds and dur > opts.max_clip_seconds:
        # tomar el tramo central, que suele ser el más interesante
        start = (dur - opts.max_clip_seconds) / 2
        end = start + opts.max_clip_seconds
    return Clip(src.name, "video", round(dur, 2), round(start, 2), round(end, 2), opts.transition, t_sec,
                id=_new_id(), mute=not opts.keep_original_audio)


def build_project(inputs: list[Path], opts: ReelOptions) -> dict:
    """Arma el proyecto editable a partir de los archivos subidos (ya guardados en <lote>/fuentes)."""
    clips = [clip_from_file(src, opts) for src in inputs]
    if not opts.music_seed:
        opts.music_seed = random.randint(1, 10**6)
    return {"version": 0, "clips": [asdict(c) for c in clips], "opciones": opts.to_dict()}


def _num(v, default, lo, hi):
    try:
        return min(hi, max(lo, float(v)))
    except (TypeError, ValueError):
        return default


def clean_project(data: dict, fuentes: Path) -> dict:
    """Valida un proyecto que viene del navegador (no confiar en nada)."""
    clips, durations = [], {}
    for c in data.get("clips") or []:
        src = Path(str(c.get("src", ""))).name
        if not src or not (fuentes / src).is_file():
            raise ValueError(f"No encuentro el archivo {src or '?'} de este reel.")
        kind = "foto" if Path(src).suffix.lower() in IMAGE_EXT else "video"
        speed = _num(c.get("speed", 1), 1.0, 0.25, 4.0)
        if kind == "foto":
            secs = _num(_num(c.get("end", 3), 3, 0, 99) - _num(c.get("start", 0), 0, 0, 99), 3, MIN_CLIP, MAX_PHOTO)
            source, start, end = secs, 0.0, secs
        else:
            if src not in durations:
                durations[src] = probe(fuentes / src)["duration"]
            source = durations[src]
            start = min(_num(c.get("start", 0), 0, 0, source), max(0.0, source - MIN_CLIP * speed))
            end = min(source, max(start + MIN_CLIP * speed, _num(c.get("end", source), source, 0, source)))
        fondo = str(c.get("fondo", "blur"))
        try:
            rotate = int(c.get("rotate", 0) or 0)
        except (TypeError, ValueError):
            rotate = 0
        clip = Clip(
            src, kind, round(source, 2), round(start, 2), round(end, 2),
            transition=c.get("transition") if c.get("transition") in TRANSITIONS else "fade",
            transition_seconds=_num(c.get("transition_seconds", 0.4), 0.4, 0.2, 1.5),
            id=re.sub(r"[^a-z0-9]", "", str(c.get("id", "")))[:12] or _new_id(),
            speed=speed, reverse=bool(c.get("reverse")) and kind == "video",
            volume=_num(c.get("volume", 1), 1.0, 0, 2),
            # reels de la versión anterior: el sonido original dependía de una opción general
            mute=bool(c["mute"]) if "mute" in c else not (data.get("opciones") or {}).get("keep_original_audio"),
            fit="ajustar" if c.get("fit") == "ajustar" else "llenar",
            fondo=fondo if fondo == "blur" or re.fullmatch(r"#[0-9a-fA-F]{6}", fondo) else "blur",
            zoom=_num(c.get("zoom", 1), 1.0, 1, 3), pan_x=_num(c.get("pan_x", 0), 0, -1, 1),
            pan_y=_num(c.get("pan_y", 0), 0, -1, 1),
            rotate=rotate if rotate in (0, 90, 180, 270) else 0,
            flip_h=bool(c.get("flip_h")), flip_v=bool(c.get("flip_v")),
            filtro=c.get("filtro") if c.get("filtro") in FILTERS else "ninguno",
            brillo=_num(c.get("brillo", 0), 0, -100, 100), contraste=_num(c.get("contraste", 0), 0, -100, 100),
            saturacion=_num(c.get("saturacion", 0), 0, -100, 100),
            temperatura=_num(c.get("temperatura", 0), 0, -100, 100), vineta=_num(c.get("vineta", 0), 0, 0, 100),
            anim=c.get("anim") if c.get("anim") in ANIMATIONS else "ninguna",
        )
        if clip.reverse and clip.duration > MAX_REVERSE:
            raise ValueError(f"Para invertir un clip tiene que durar {MAX_REVERSE:.0f} s o menos.")
        clips.append(clip)
    if not clips:
        raise ValueError("El reel tiene que tener al menos un clip.")
    if len(clips) > 60:
        raise ValueError("Máximo 60 clips por reel.")
    o = data.get("opciones") or {}
    voz = Path(str(o.get("voz", "") or "")).name
    opts = ReelOptions(
        title=str(o.get("title", ""))[:140], subtitle=str(o.get("subtitle", ""))[:140],
        music=str(o.get("music", "auto:energico")), music_volume=_num(o.get("music_volume", 0.9), 0.9, 0, 1.5),
        music_start=_num(o.get("music_start", 0), 0, 0, 3600),
        music_fade_out=_num(o.get("music_fade_out", 1.8), 1.8, 0, 6),
        keep_original_audio=bool(o.get("keep_original_audio")), watermark=bool(o.get("watermark", True)),
        outro=bool(o.get("outro", True)), logo=str(o.get("logo", "auto")),
        music_seed=int(_num(o.get("music_seed"), 0, 0, 10**7)) or random.randint(1, 10**6),
        formato=o.get("formato") if o.get("formato") in FORMATS else "historia",
        voz=voz if voz and (fuentes / voz).is_file() else "",
        voz_volume=_num(o.get("voz_volume", 1), 1.0, 0, 2), voz_ducking=bool(o.get("voz_ducking", True)),
    )
    return {"version": int(_num(data.get("version", 0), 0, 0, 10**6)), "clips": [asdict(c) for c in clips],
            "opciones": opts.to_dict(), "textos": clean_textos(data.get("textos")),
            "stickers": clean_stickers(data.get("stickers"))}


def _id(v) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v or ""))[:12] or _new_id()


def clean_textos(items) -> list[dict]:
    out = []
    for t in (items or [])[:40]:
        txt = str(t.get("texto", ""))[:300]
        a = _num(t.get("inicio", 0), 0, 0, 3600)
        out.append({
            "id": _id(t.get("id")), "texto": txt, "inicio": a, "fin": max(a + 0.2, _num(t.get("fin", a + 3), a + 3, 0, 3600)),
            "x": _num(t.get("x", 0.5), 0.5, 0, 1), "y": _num(t.get("y", 0.5), 0.5, 0, 1),
            "tamano": _num(t.get("tamano", 64), 64, 16, 260),
            "rol": t.get("rol") if t.get("rol") in ("title", "subtitle", "body") else "subtitle",
            "color": _rgb(t.get("color"), WHITE),
            "caja": _rgb(t.get("caja"), "") if t.get("caja") not in (None, "", "ninguna") else "",
            "alinear": t.get("alinear") if t.get("alinear") in ("izquierda", "centro", "derecha") else "centro",
            "anim": t.get("anim") if t.get("anim") in TEXT_ANIMS else "aparecer",
            "mayus": bool(t.get("mayus")), "sombra": bool(t.get("sombra", True)),
        })
    return out


def clean_stickers(items) -> list[dict]:
    out = []
    for st in (items or [])[:30]:
        a = _num(st.get("inicio", 0), 0, 0, 3600)
        out.append({
            "id": _id(st.get("id")), "tipo": st.get("tipo") if st.get("tipo") in STICKERS else "logo",
            "inicio": a, "fin": max(a + 0.2, _num(st.get("fin", a + 3), a + 3, 0, 3600)),
            "x": _num(st.get("x", 0.5), 0.5, 0, 1), "y": _num(st.get("y", 0.5), 0.5, 0, 1),
            "tamano": _num(st.get("tamano", 1), 1, 0.2, 3), "color": _rgb(st.get("color"), ORANGE),
            "opacidad": _num(st.get("opacidad", 1), 1, 0.1, 1), "giro": _num(st.get("giro", 0), 0, -180, 180),
            "variante": st.get("variante") if st.get("variante") in ("on_dark", "on_light", "on_orange") else "on_dark",
            "logo": Path(str(st.get("logo") or "")).name, "anim": st.get("anim") if st.get("anim") in TEXT_ANIMS else "aparecer",
        })
    return out


def _cached(cache: Path, key: str) -> Path:
    return cache / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".mp4")


def load_clip(d: dict) -> Clip:
    return Clip(**{k: v for k, v in d.items() if k in CLIP_FIELDS})


def render_project(project: dict, lote: Path, out_path: Path, log: list[str] | None = None,
                   preview: bool = False, progress=None) -> Path:
    """Renderiza el proyecto (o su vista previa liviana). Los clips ya preparados se reutilizan."""
    log = log if log is not None else []
    fuentes, cache = lote / "fuentes", lote / "cache"
    cache.mkdir(exist_ok=True)
    opts = ReelOptions(**{k: v for k, v in project["opciones"].items() if k in ReelOptions.EDITABLE}, log=log)
    clips = [load_clip(c) for c in project["clips"]]
    size = frame_size(opts.formato, preview)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="der-reel-", ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        parts: list[tuple[Path, float]] = []
        for i, c in enumerate(clips, 1):
            dst = _cached(cache, c.render_key(opts.formato, preview))
            if not dst.exists():
                if progress:
                    progress(f"Preparando clip {i} de {len(clips)}")
                part = tmp / f"clip{i}.mp4"
                render_clip(c, fuentes / c.src, part, *size, tmp, log, preview)
                shutil.move(str(part), dst)
            parts.append((dst, probe(dst)["duration"]))
        if progress:
            progress("Uniendo los clips")
        trans = [(c.transition, c.transition_seconds) for c in clips[:-1]]
        body_end = timeline_length([d for _, d in parts], trans)
        if opts.outro:
            # el cierre va en la misma pasada (una sola codificación)
            outro = _cached(cache, f"outro|{opts.logo}|{opts.outro_seconds}|{size}|{preview}")
            if not outro.exists():
                _outro_clip(outro, opts, tmp, size, preview)
            parts.append((outro, probe(outro)["duration"]))
            trans.append(("fade", 0.5))
            body_end -= min(0.5, parts[-2][1] / 2, parts[-1][1] / 2)
        overlays = []
        if opts.watermark:
            overlays.append((render_watermark(tmp / "wm.png", opts.logo, size), 0.0, body_end))
        if opts.title or opts.subtitle:
            overlays.append((render_title_overlay(tmp / "title.png", opts.title, opts.subtitle, size), 0.2,
                             min(3.6, body_end)))
        overlays += layer_overlays(project.get("textos") or [], project.get("stickers") or [], size, tmp, opts.logo)
        full = tmp / "full.mp4"
        total = _join(parts, trans, overlays, full, log, preview)
        if progress:
            progress("Mezclando el audio")
        has_original = any(c.kind == "video" and not c.mute and c.volume > 0 for c in clips)
        voz = fuentes / opts.voz if opts.voz and (fuentes / opts.voz).is_file() else None
        _add_music(full, total, opts, tmp, out_path, has_original, voz)
    return out_path


def thumbnail(src: Path, dst: Path, at: float) -> Path:
    """Miniatura vertical para la línea de tiempo del editor."""
    if src.suffix.lower() in IMAGE_EXT:
        graphics.cover(graphics.load_photo(src), 180, 320).save(dst, quality=80)
        return dst
    _run(["ffmpeg", "-y", "-ss", f"{max(0, at):.2f}", "-i", str(src), "-frames:v", "1",
          "-vf", "scale=180:320:force_original_aspect_ratio=increase,crop=180:320", "-q:v", "5", str(dst)], [])
    return dst


def filmstrip(src: Path, dst: Path, duration: float, frames: int = 8) -> Path:
    """Tira de cuadros (como la línea de tiempo de CapCut) para ver dónde cortar."""
    if src.suffix.lower() in IMAGE_EXT:
        tile = graphics.cover(graphics.load_photo(src), 90, 160)
        strip = Image.new("RGB", (90 * frames, 160))
        for i in range(frames):
            strip.paste(tile, (90 * i, 0))
        strip.save(dst, quality=75)
        return dst
    step = max(duration / frames, 0.1)
    _run(["ffmpeg", "-y", "-i", str(src), "-vf",
          f"fps=1/{step:.3f},scale=90:160:force_original_aspect_ratio=increase,crop=90:160,tile={frames}x1",
          "-frames:v", "1", "-q:v", "6", str(dst)], [])
    return dst


def extract_frame(src: Path, dst: Path, at: float) -> Path:
    """Cuadro a tamaño completo (para congelar imagen)."""
    _run(["ffmpeg", "-y", "-ss", f"{max(0, at):.3f}", "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)], [])
    return dst


def preview_proxy(src: Path, dst: Path) -> Path:
    """Copia liviana del video (360p) para elegir el tramo desde el celular."""
    _run(["ffmpeg", "-y", "-i", str(src), "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast",
          "-crf", "30", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", str(dst)], [])
    return dst


def generate(inputs: list[Path], out_path: Path, opts: ReelOptions) -> Path:
    """Compatibilidad: arma el proyecto y lo renderiza en la carpeta de salida."""
    if not inputs:
        raise ValueError("Subí al menos un video o foto.")
    lote = out_path.parent
    (lote / "fuentes").mkdir(parents=True, exist_ok=True)
    srcs = []
    for p in inputs:
        dst = lote / "fuentes" / p.name
        if not dst.exists():
            shutil.copy(p, dst)
        srcs.append(dst)
    project = build_project(srcs, opts)
    return render_project(project, lote, out_path, opts.log)
