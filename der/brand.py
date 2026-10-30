"""Brand kit de DER — colores, tipografías y logos.

Fuente: "manual de marca DER.pdf" (Drive).
  Paleta:      #ff5c00 (naranja, principal) · #333333 (gris oscuro) · #f0f0f0 (gris claro)
  Títulos:     NETRON  — geométrica, compacta, futurista
  Subtítulos:  Articulat CF — geométrica, limpia, versátil
  Cuerpo:      Jost — minimalista, fácil lectura

Los archivos reales (Netron.ttf, Articulat CF, logos PNG) se copian a brand/fonts y
brand/logos. Si falta alguno, se usa un reemplazo parecido y la UI lo avisa.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "brand"
FONTS_DIR = BRAND_DIR / "fonts"
LOGOS_DIR = BRAND_DIR / "logos"
MUSIC_DIR = BRAND_DIR / "music"

ORANGE = "#ff5c00"
DARK = "#333333"
LIGHT = "#f0f0f0"
WHITE = "#ffffff"

ORANGE_RGB = (255, 92, 0)
DARK_RGB = (51, 51, 51)
LIGHT_RGB = (240, 240, 240)

WEBSITE = "somosder.ar"
INSTAGRAM = "@somosder"

FORMATS = {
    "post": (1080, 1350),      # feed 4:5
    "cuadrado": (1080, 1080),  # feed 1:1
    "historia": (1080, 1920),  # story / reel 9:16
}


def _unzip_font_archives() -> None:
    """Descomprime cualquier .zip de tipografías que se haya dejado en brand/fonts."""
    for z in FONTS_DIR.glob("*.zip"):
        marker = FONTS_DIR / f".{z.stem}.extracted"
        if marker.exists():
            continue
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                name = Path(member).name
                if name.lower().endswith((".ttf", ".otf")) and not name.startswith("._"):
                    (FONTS_DIR / name).write_bytes(zf.read(member))
        marker.touch()


NECESARIAS = "ÁÉÍÓÚÑáéíóúñ¿¡0123456789"
INCOMPLETAS: dict[str, str] = {}   # archivo -> letras que le faltan (se llena al buscar fuentes)


def _faltantes(path: Path) -> str:
    """Letras del castellano que no tiene la fuente (las versiones DEMO no traen tildes ni ñ)."""
    try:
        f = ImageFont.truetype(str(path), 48)
    except OSError:
        return NECESARIAS
    vacio = f.getmask("\uffff")
    sig = lambda c: (f.getmask(c).size, bytes(f.getmask(c)))  # noqa: E731
    nd = (vacio.size, bytes(vacio))
    return "".join(c for c in NECESARIAS if f.getmask(c).size == (0, 0) or sig(c) == nd)


def _find_font(keyword: str, prefer: tuple[str, ...] = ()) -> Path | None:
    candidates = []
    for p in FONTS_DIR.iterdir():
        if p.suffix.lower() not in (".ttf", ".otf") or keyword not in p.name.lower():
            continue
        falta = _faltantes(p)
        if falta:
            INCOMPLETAS[p.name] = falta   # no se usa: saldrían huecos en vez de letras
            continue
        candidates.append(p)
    if not candidates:
        return None
    for weight in prefer:
        for p in candidates:
            if weight in p.name.lower().replace("-", "").replace(" ", ""):
                return p
    return sorted(candidates)[0]


@dataclass
class FontSet:
    title: Path
    subtitle: Path
    body: Path
    body_bold: Path
    missing: list[str]


@lru_cache(maxsize=1)
def fonts() -> FontSet:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    INCOMPLETAS.clear()
    _unzip_font_archives()
    missing = []

    title = _find_font("netron")
    if not title:
        missing.append("Netron (títulos)")
        title = FONTS_DIR / "Fallback-Titulos-Orbitron.ttf"

    subtitle = _find_font("articulat", ("demibold", "semibold", "medium", "bold", "regular"))
    if not subtitle:
        demo = any("articulat" in n.lower() for n in INCOMPLETAS)
        missing.append("Articulat CF (subtítulos)" + (" — la que subiste es DEMO, sin tildes ni ñ" if demo else ""))
        subtitle = FONTS_DIR / "Jost-Medium.ttf"

    body = _find_font("jost", ("regular", "book")) or FONTS_DIR / "Jost-Regular.ttf"
    body_bold = _find_font("jost", ("bold", "semibold", "medium")) or FONTS_DIR / "Jost-Bold.ttf"
    return FontSet(title, subtitle, body, body_bold, missing)


@lru_cache(maxsize=256)
def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    path = getattr(fonts(), role)
    return ImageFont.truetype(str(path), size)


# --- Logos -----------------------------------------------------------------
# Nombres tal como están en el Drive ("LOGO SOMOS DER"):
#   LOGO-DER-NARANJA-Y-GRIS-CLARO.png  -> para fondos oscuros
#   LOGO-DER-NARANJA-Y-GRIS-OSCURO.png -> para fondos claros
#   LOGO-DER-NARANJA.png               -> monocromo naranja
#   LOGO-DER-GRIS-CLARO.png / LOGO-DER-GRIS-OSCURO.png
LOGO_VARIANTS = {
    "on_dark": ("naranja-y-gris-claro", "gris-claro", "solo-naranja"),
    "on_light": ("naranja-y-gris-oscuro", "gris-oscuro", "solo-naranja"),
    "on_orange": ("gris-claro", "gris-oscuro"),
    "orange": ("solo-naranja", "naranja-y-gris-claro"),
}


def _logo_files() -> list[Path]:
    LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in LOGOS_DIR.iterdir() if p.suffix.lower() in (".png", ".webp"))


def _matches(name: str, key: str) -> bool:
    n = name.lower().replace(" ", "-").replace("_", "-")
    if key == "solo-naranja":
        return "naranja" in n and "gris" not in n
    if key.startswith("gris"):
        return key in n and "naranja" not in n
    return key in n


def has_real_logo() -> bool:
    return bool(_logo_files())


def list_logos() -> list[str]:
    return [p.name for p in _logo_files()]


@lru_cache(maxsize=64)
def logo_file(name: str) -> Image.Image:
    """Un logo puntual de brand/logos, recortado a su contenido."""
    path = LOGOS_DIR / Path(name).name
    img = Image.open(path).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def resolve_logo(choice: str, variant: str) -> Image.Image:
    """choice = "auto" (elige según el fondo) o el nombre de un archivo de brand/logos."""
    if choice and choice != "auto" and (LOGOS_DIR / Path(choice).name).exists():
        return logo_file(Path(choice).name)
    return logo(variant)


def logo_key(choice: str, variant: str) -> str:
    """Identificador estable del logo para el editor: file:<nombre> o auto:<variante>."""
    if choice and choice != "auto" and (LOGOS_DIR / Path(choice).name).exists():
        return "file:" + Path(choice).name
    return "auto:" + variant


@lru_cache(maxsize=16)
def logo(variant: str = "on_dark") -> Image.Image:
    """Logo recortado a su contenido (los PNG del Drive traen mucho margen transparente)."""
    files = _logo_files()
    chosen = next(
        (p for key in LOGO_VARIANTS.get(variant, ()) for p in files if _matches(p.name, key)),
        None,
    )
    if chosen is None and files:
        chosen = files[0]
    if chosen is None:
        return _placeholder_logo(variant)
    img = Image.open(chosen).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def _placeholder_logo(variant: str) -> Image.Image:
    """Logotipo de texto provisorio hasta que se copien los PNG oficiales."""
    from PIL import ImageDraw

    f = font("title", 260)
    text_color = {"on_light": DARK, "on_orange": WHITE}.get(variant, LIGHT)
    l, t, r, b = f.getbbox("DER")
    img = Image.new("RGBA", (r - l + 40, b - t + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((20 - l, 20 - t), "D", font=f, fill=ORANGE if variant != "on_orange" else WHITE)
    dx = f.getlength("D")
    d.text((20 - l + dx, 20 - t), "ER", font=f, fill=text_color)
    return img


def logo_sized(variant: str, width: int | None = None, height: int | None = None,
               choice: str = "auto") -> Image.Image:
    img = resolve_logo(choice, variant)
    if width:
        height = round(img.height * width / img.width)
    elif height:
        width = round(img.width * height / img.height)
    return img.resize((width, height), Image.LANCZOS)


def status() -> dict:
    fs = fonts()
    return {
        "fuentes_faltantes": fs.missing,
        "fuentes_incompletas": INCOMPLETAS.copy(),
        "logo_oficial": has_real_logo(),
        "logos": list_logos(),
        "titulo": fs.title.name,
        "subtitulo": fs.subtitle.name,
        "cuerpo": fs.body.name,
        "musica": sorted(p.name for p in MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".ogg")),
    }
