"""Generador de posteos e historias de Instagram con el brand kit de DER.

Cada pieza se arma en dos partes:
  - una BASE (imagen JPG): foto, fondo, degradés, bandas y marcos;
  - CAPAS editables: textos, logo y elementos gráficos (barra, esquineros, puntos).
El navegador compone base + capas con el editor (static/editor.js), así que lo que
se descarga y lo que se edita es exactamente lo mismo.

Plantillas:
  impacto   foto a sangre + degradé gris oscuro, texto abajo
  marco     fondo gris claro, foto enmarcada con bloque naranja desplazado
  banda     foto arriba + banda naranja con el texto
  texto     solo texto sobre gris oscuro (sin foto)
  naranja   solo texto sobre naranja (sin foto)
  collage   2 a 4 fotos en grilla + franja con el texto

En el título, las palabras entre *asteriscos* se resaltan en naranja.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from PIL import Image, ImageDraw, ImageOps

from . import brand
from .brand import DARK, DARK_RGB, LIGHT, ORANGE, WHITE

TEMPLATES = {
    "impacto": "Foto a sangre",
    "marco": "Foto enmarcada",
    "banda": "Foto + banda naranja",
    "collage": "Collage (2-4 fotos)",
    "texto": "Solo texto (gris)",
    "naranja": "Solo texto (naranja)",
}
PHOTO_TEMPLATES = {"impacto", "marco", "banda", "collage"}
FONT_FAMILY = {"title": "DER Titulo", "subtitle": "DER Sub", "body": "DER Cuerpo"}


@dataclass
class Content:
    title: str = ""
    subtitle: str = ""
    body: str = ""
    focus: str = "centro"  # centro | arriba | abajo
    logo: str = "auto"     # auto | nombre de archivo en brand/logos


# --- Helpers de texto (Pillow mide con las mismas tipografías que usa el editor) ---

def load_photo(path: Path) -> Image.Image:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGB")


def cover(img: Image.Image, w: int, h: int, focus: str = "centro") -> Image.Image:
    centering = {"arriba": (0.5, 0.2), "abajo": (0.5, 0.8)}.get(focus, (0.5, 0.5))
    return ImageOps.fit(img, (int(w), int(h)), Image.LANCZOS, centering=centering)


def _tokens(text: str) -> list[tuple[str, bool]]:
    """Separa en palabras marcando las que van entre *asteriscos*."""
    out, hl = [], False
    for raw in text.split():
        word = raw
        if word.startswith("*"):
            hl, word = True, word[1:]
        end = word.endswith("*")
        if end:
            word = word[:-1]
        if word:
            out.append((word, hl))
        if end:
            hl = False
    return out


def _wrap(tokens, f, max_w):
    lines, cur, cur_w = [], [], 0.0
    space = f.getlength(" ")
    for word, hl in tokens:
        w = f.getlength(word)
        if cur and cur_w + space + w > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur_w += (space if cur else 0) + w
        cur.append((word, hl))
    if cur:
        lines.append(cur)
    return lines


def fit_text(text, role, max_w, max_h, size, min_size, line_gap=1.12, max_lines=None, upper=False):
    """Achica la tipografía hasta que el texto entra en la caja."""
    text = text.upper() if upper else text
    tokens = _tokens(text)
    while True:
        f = brand.font(role, size)
        lines = _wrap(tokens, f, max_w)
        too_wide = any(f.getlength(w) > max_w for line in lines for w, _ in line)
        height = len(lines) * size * line_gap
        if size <= min_size or (height <= max_h and not too_wide
                                and (max_lines is None or len(lines) <= max_lines)):
            return f, lines, size * line_gap
        size = max(min_size, int(size * 0.92))


def draw_lines(d, xy, f, lines, line_h, color, hl_color=ORANGE, align="left", box_w=0):
    x0, y = xy
    space = f.getlength(" ")
    ascent = f.getmetrics()[0]
    for line in lines:
        line_w = sum(f.getlength(w) for w, _ in line) + space * (len(line) - 1)
        x = x0 + (box_w - line_w) / 2 if align == "center" else x0
        for word, hl in line:
            d.text((x, y + (line_h - ascent) * 0.35), word, font=f, fill=hl_color if hl else color)
            x += f.getlength(word) + space
        y += line_h
    return y


def text_block(d, x, y, w, max_h, c: Content, scale, title_color, sub_color, body_color,
               align="left", title_size=96, title_hl=ORANGE):
    """Dibuja título + subtítulo + cuerpo directo con Pillow (lo usan los reels)."""
    y0 = y
    for role, txt, color, hl, size, mn, gap, upper, ml, ratio in _parts(c, scale, title_size, title_color,
                                                                        sub_color, body_color, title_hl):
        f, lines, lh = fit_text(txt, role, w, max(40, (y0 + max_h - y) * ratio), size, mn, gap, ml, upper)
        y = draw_lines(d, (x, y), f, lines, lh, color, hl_color=hl, align=align, box_w=w)
        y += _SPACING[role] * scale
    return y - y0


def measure_block(c: Content, w, max_h, scale, title_size=96):
    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    return text_block(scratch, 0, 0, w, max_h, c, scale, "#000", "#000", "#000", title_size=title_size)


_SPACING = {"title": 18, "subtitle": 14, "body": 0}


def _parts(c, scale, title_size, title_color, sub_color, body_color, title_hl):
    """(rol, texto, color, color_resaltado, tamaño, mínimo, interlineado, mayúsculas, máx_líneas, % del alto)"""
    out = []
    if c.title:
        out.append(("title", c.title, title_color, title_hl, int(title_size * scale), int(40 * scale),
                    1.08, True, None, 0.6))
    if c.subtitle:
        out.append(("subtitle", c.subtitle, sub_color, sub_color, int(46 * scale), int(28 * scale),
                    1.12, False, 3, 0.5))
    if c.body:
        out.append(("body", c.body, body_color, body_color, int(36 * scale), int(24 * scale),
                    1.3, False, None, 1.0))
    return out


# --- Elementos gráficos (Pillow) ------------------------------------------------

def corner_brackets(d, box, length, width, color, corners="all"):
    """Esquineros tipo visor: el recurso de 'estructura y tecnología'."""
    x0, y0, x1, y1 = box
    sel = {"all": "tl tr bl br", "diag": "tl br", "diag2": "tr bl"}.get(corners, corners).split()
    if "tl" in sel:
        d.rectangle([x0, y0, x0 + length, y0 + width], fill=color)
        d.rectangle([x0, y0, x0 + width, y0 + length], fill=color)
    if "tr" in sel:
        d.rectangle([x1 - length, y0, x1, y0 + width], fill=color)
        d.rectangle([x1 - width, y0, x1, y0 + length], fill=color)
    if "bl" in sel:
        d.rectangle([x0, y1 - width, x0 + length, y1], fill=color)
        d.rectangle([x0, y1 - length, x0 + width, y1], fill=color)
    if "br" in sel:
        d.rectangle([x1 - length, y1 - width, x1, y1], fill=color)
        d.rectangle([x1 - width, y1 - length, x1, y1], fill=color)


def dot_grid(d, x, y, cols, rows, gap, r, color):
    for i in range(cols):
        for j in range(rows):
            cx, cy = x + i * gap, y + j * gap
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)


def accent_bar(d, x, y, scale, color=ORANGE):
    d.rectangle([x, y, x + 90 * scale, y + 10 * scale], fill=color)


def bottom_gradient(img, start_frac, max_alpha=235, color=DARK_RGB):
    w, h = img.size
    start = int(h * start_frac)
    grad = Image.new("L", (1, h), 0)
    for yy in range(start, h):
        t = (yy - start) / max(1, h - start)
        grad.putpixel((0, yy), int(max_alpha * min(1, t * 1.35) ** 1.4))
    grad = grad.resize((w, h))
    overlay = Image.new("RGB", (w, h), color)
    img.paste(overlay, (0, 0), grad)


@lru_cache(maxsize=128)
def element_png(kind: str, corner: str = "tl", size: int = 110, thick: int = 10,
                cols: int = 6, rows: int = 4, gap: int = 28, r: int = 4, color: str = ORANGE) -> Image.Image:
    """Elementos sueltos como PNG transparente, para usarlos como capas del editor."""
    color = color if color.startswith("#") else "#" + color
    if kind == "esquinero":
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        corner_brackets(ImageDraw.Draw(img), (0, 0, size - 1, size - 1), size - 1, thick - 1, color, corner)
        return img
    if kind == "puntos":
        img = Image.new("RGBA", ((cols - 1) * gap + 2 * r + 2, (rows - 1) * gap + 2 * r + 2), (0, 0, 0, 0))
        dot_grid(ImageDraw.Draw(img), r + 1, r + 1, cols, rows, gap, r, color)
        return img
    raise ValueError(kind)


# --- Diseño en capas ----------------------------------------------------------

class Design:
    def __init__(self, fmt: str, content: Content, bg=LIGHT):
        self.fmt = fmt
        self.W, self.H = brand.FORMATS[fmt]
        self.s = self.W / 1080
        self.c = content
        self.base = Image.new("RGB", (self.W, self.H), bg)
        self.layers: list[dict] = []

    # Capas -----------------------------------------------------------------
    def text(self, role, text, x, y, w, color, size, line_gap, hl_color=None, upper=False, lines=None,
             align="left", name=None):
        if lines is None:
            text = text.upper() if upper else text
            lines = _wrap(_tokens(text), brand.font(role, size), w)
        styles = {}
        for li, line in enumerate(lines):
            pos = 0
            for word, hl in line:
                if hl and hl_color:
                    for k in range(len(word)):
                        styles.setdefault(str(li), {})[str(pos + k)] = {"fill": hl_color}
                pos += len(word) + 1
        self.layers.append({
            "type": "text", "name": name or role, "font": role, "family": FONT_FAMILY[role],
            "text": "\n".join(" ".join(wd for wd, _ in line) for line in lines),
            "x": round(x), "y": round(y), "w": round(w), "size": size, "lineGap": line_gap,
            "color": color, "styles": styles, "align": align,
        })
        return len(lines) * size * line_gap

    def text_block(self, x, y, w, max_h, title_color, sub_color, body_color, title_size=96,
                   title_hl=ORANGE, align="left"):
        y0 = y
        for role, txt, color, hl, size, mn, gap, upper, ml, ratio in _parts(
                self.c, self.s, title_size, title_color, sub_color, body_color, title_hl):
            f, lines, lh = fit_text(txt, role, w, max(40, (y0 + max_h - y) * ratio), size, mn, gap, ml, upper)
            y += self.text(role, "", x, y, w, color, f.size, gap, hl_color=hl if role == "title" else None,
                           lines=lines, align=align, name={"title": "Título", "subtitle": "Subtítulo",
                                                           "body": "Texto"}[role])
            y += _SPACING[role] * self.s
        return y - y0

    def measure(self, w, max_h, title_size=96):
        return measure_block(self.c, w, max_h, self.s, title_size)

    def logo(self, variant, width, x, y, anchor="lt"):
        img = brand.resolve_logo(self.c.logo, variant)
        key = brand.logo_key(self.c.logo, variant)
        h = img.height * width / img.width
        if anchor[0] == "r":
            x -= width
        if anchor[0] == "m":
            x -= width / 2
        if anchor[1] == "b":
            y -= h
        self.layers.append({"type": "image", "name": "Logo", "logo": key, "src": logo_url(key),
                            "x": round(x), "y": round(y), "w": round(width), "h": round(h)})
        return width, h

    def rect(self, x, y, w, h, color, name="Barra"):
        self.layers.append({"type": "rect", "name": name, "x": round(x), "y": round(y),
                            "w": round(w), "h": round(h), "color": color})

    def bar(self, x, y, color=ORANGE):
        self.rect(x, y, 90 * self.s, 10 * self.s, color, "Barra")

    def bracket(self, x, y, size, thick, color, corner):
        size, thick = round(size), max(2, round(thick))
        self.layers.append({"type": "image", "name": "Esquinero",
                            "src": element_url("esquinero", c=corner, l=size, g=thick, color=color[1:]),
                            "x": round(x), "y": round(y), "w": size, "h": size})

    def dots(self, x, y, cols, rows, gap, r, color):
        gap, r = round(gap), max(2, round(r))
        img = element_png("puntos", cols=cols, rows=rows, gap=gap, r=r, color=color)
        self.layers.append({"type": "image", "name": "Puntos",
                            "src": element_url("puntos", cols=cols, rows=rows, gap=gap, r=r, color=color[1:]),
                            "x": round(x - r - 1), "y": round(y - r - 1), "w": img.width, "h": img.height})

    def tag(self, x, y, color, align="left"):
        size = int(26 * self.s)
        f = brand.font("body", size)
        text = brand.WEBSITE.upper()
        w = f.getlength(text) + 4
        self.text("body", text, x - (w if align == "right" else 0), y - size, w, color, size, 1.2,
                  align=align, name="Web")

    def to_dict(self):
        return {"fmt": self.fmt, "W": self.W, "H": self.H, "layers": self.layers}


def logo_url(key: str) -> str:
    return "/logos/ver/" + quote(key, safe=":")


def element_url(kind: str, **params) -> str:
    return f"/elemento/{kind}.png?" + urlencode(params)


# --- Plantillas -------------------------------------------------------------

def _safe(fmt, h):
    """Márgenes seguros: en historias la UI de Instagram tapa arriba y abajo."""
    return (230, 330) if fmt == "historia" else (int(h * 0.06), int(h * 0.06))


def _has_text(c):
    return bool(c.title or c.subtitle or c.body)


def tpl_impacto(fmt, photos, c, first=True):
    D = Design(fmt, c)
    W, H, s = D.W, D.H, D.s
    D.base = cover(photos[0], W, H, c.focus)
    top, bottom = _safe(fmt, H)
    m = 80 * s
    has_text = first and _has_text(c)
    bottom_gradient(D.base, 0.35 if has_text else 0.7, 235 if has_text else 160)
    D.logo("on_dark", 190 * s, m, top)
    D.bracket(W - m - 70 * s, top, 70 * s, 8 * s, ORANGE, "tr")
    if has_text:
        box_w, max_h = W - 2 * m, H * 0.42
        y = H - bottom - D.measure(box_w, max_h)
        D.bar(m, y - 40 * s)
        D.text_block(m, y, box_w, max_h, WHITE, ORANGE, LIGHT)
    else:
        D.tag(m, H - bottom + 20 * s, LIGHT)
    return D


def tpl_marco(fmt, photos, c, first=True):
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    d = ImageDraw.Draw(D.base)
    top, bottom = _safe(fmt, H)
    m = 80 * s
    has_text = first and _has_text(c)
    box_w = W - 2 * m
    text_h = D.measure(box_w, H * 0.3, 80) if has_text else 0
    photo_top = top + 90 * s + 40 * s
    photo_bottom = H - bottom - (text_h + 70 * s if has_text else 40 * s)
    pw, ph = int(W - 2 * m - 24 * s), int(photo_bottom - photo_top)
    off = int(24 * s)
    d.rectangle([m + off, photo_top + off, m + off + pw, photo_top + off + ph], fill=ORANGE)
    D.base.paste(cover(photos[0], pw, ph, c.focus), (int(m), int(photo_top)))
    D.logo("on_light", 170 * s, m, top)
    D.dots(W - m - 4 * 26 * s, top + 12 * s, 5, 3, 26 * s, 4 * s, ORANGE)
    if has_text:
        D.text_block(m, photo_bottom + 60 * s, box_w, H * 0.3, DARK, ORANGE, DARK, title_size=80)
    return D


def tpl_banda(fmt, photos, c, first=True):
    D = Design(fmt, c, ORANGE)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 80 * s
    has_text = first and _has_text(c)
    box_w = W - 2 * m
    text_h = D.measure(box_w, H * 0.35, 84) if has_text else 0
    band_h = int(max(H * 0.22, text_h + bottom + 110 * s)) if has_text else int(bottom + 140 * s)
    D.base.paste(cover(photos[0], W, H - band_h, c.focus), (0, 0))
    tab_w, tab_h = 300 * s, 96 * s
    D.rect(W - m - tab_w, H - band_h - tab_h / 2, tab_w, tab_h, DARK, "Pestaña")
    D.logo("on_dark", 200 * s, W - m - tab_w / 2, H - band_h - 30 * s, "mt")
    D.bracket(m, top, 70 * s, 8 * s, ORANGE, "tl")
    if has_text:
        D.text_block(m, H - band_h + 80 * s, box_w - tab_w * 0.2, H * 0.35, WHITE, DARK, DARK,
                     title_size=84, title_hl=DARK)
    else:
        D.tag(m, H - bottom + 20 * s, DARK)
    return D


def tpl_texto(fmt, photos, c, first=True, bg=DARK):
    D = Design(fmt, c, bg)
    W, H, s = D.W, D.H, D.s
    on_orange = bg == ORANGE
    top, bottom = _safe(fmt, H)
    m = 90 * s
    accent = DARK if on_orange else ORANGE
    D.bracket(m - 30 * s, top - 30 * s, 110 * s, 10 * s, accent, "tl")
    D.bracket(W - m + 30 * s - 110 * s, H - bottom + 30 * s - 110 * s, 110 * s, 10 * s, accent, "br")
    D.dots(W - m - 5 * 28 * s, top + 20 * s, 6, 4, 28 * s, 4 * s, WHITE if on_orange else "#5a5a5a")
    box_w = W - 2 * m
    max_h = (H - top - bottom) * 0.7
    block_h = D.measure(box_w, max_h, 120)
    y = top + (H - top - bottom - block_h) / 2
    D.bar(m, y - 50 * s, accent)
    D.text_block(m, y, box_w, max_h, WHITE if on_orange else LIGHT, DARK if on_orange else ORANGE,
                 DARK if on_orange else LIGHT, title_size=120, title_hl=accent)
    D.logo("on_orange" if on_orange else "on_dark", 200 * s, m, H - bottom, "lb")
    D.tag(W - m, H - bottom, DARK if on_orange else LIGHT, align="right")
    return D


def tpl_naranja(fmt, photos, c, first=True):
    return tpl_texto(fmt, photos, c, first, bg=ORANGE)


def tpl_collage(fmt, photos, c, first=True):
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    g = int(12 * s)
    m = 80 * s
    box_w = W - 2 * m
    has_text = _has_text(c)
    text_h = D.measure(box_w - 220 * s, H * 0.25, 76) if has_text else 0
    strip_h = int(max(text_h + 90 * s, 200 * s) + bottom * 0.6)
    gx, gy, gw, gh = g, g, W - 2 * g, H - strip_h - g
    n = min(len(photos), 4)
    if n == 1:
        cells = [(0, 0, 1, 1)]
    elif n == 2:
        cells = [(0, 0, 1, .5), (0, .5, 1, .5)] if fmt == "historia" else [(0, 0, .5, 1), (.5, 0, .5, 1)]
    elif n == 3:
        cells = [(0, 0, 1, .55), (0, .55, .5, .45), (.5, .55, .5, .45)]
    else:
        cells = [(0, 0, .5, .5), (.5, 0, .5, .5), (0, .5, .5, .5), (.5, .5, .5, .5)]
    for photo, (cx, cy, cw, ch) in zip(photos, cells):
        x0, y0 = gx + int(cx * gw), gy + int(cy * gh)
        w = int(cw * gw) - (g if cx + cw < 1 else 0)
        h = int(ch * gh) - (g if cy + ch < 1 else 0)
        D.base.paste(cover(photo, w, h, c.focus), (x0, y0))
    D.rect(0, H - strip_h, W, 10 * s, ORANGE, "Línea")
    if has_text:
        D.text_block(m, H - strip_h + 60 * s, box_w - 220 * s, H * 0.25, WHITE, ORANGE, LIGHT, title_size=76)
    D.logo("on_dark", 180 * s, W - m, H - strip_h + 60 * s, "rt")
    return D


RENDERERS = {
    "impacto": tpl_impacto,
    "marco": tpl_marco,
    "banda": tpl_banda,
    "collage": tpl_collage,
    "texto": tpl_texto,
    "naranja": tpl_naranja,
}


def generate(template: str, formats: list[str], photo_paths: list[Path], content: Content,
             out_dir: Path, carousel_text_first_only: bool = True) -> list[dict]:
    """Genera los diseños (base JPG + capas JSON). Con varias fotos arma un carrusel."""
    out_dir.mkdir(parents=True, exist_ok=True)
    photos = [load_photo(p) for p in photo_paths]
    if template in PHOTO_TEMPLATES and not photos:
        raise ValueError("Esta plantilla necesita al menos una foto.")
    render = RENDERERS[template]
    designs = []
    for fmt in formats:
        groups = [photos] if template in ("texto", "naranja", "collage") else [[p] for p in photos]
        for i, group in enumerate(groups, 1):
            first = i == 1 or not carousel_text_first_only
            d = render(fmt, group, content, first=first)
            name = f"DER-{template}-{fmt}" + (f"-{i:02d}" if len(groups) > 1 else "")
            d.base.save(out_dir / f"{name}.base.jpg", "JPEG", quality=95, subsampling=0)
            data = {"name": name, **d.to_dict()}
            (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            designs.append(data)
    return designs
