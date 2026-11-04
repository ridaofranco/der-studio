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
  cita      frase grande con comillas naranjas (título = frase, subtítulo = quién la dijo)
  dato      un número enorme (título = número, subtítulo = qué es, texto = contexto); foto opcional de fondo
  lista     título + puntos numerados (una línea del texto = un punto)
  comparar  dos fotos lado a lado con etiquetas ANTES / DESPUÉS
  agenda    evento: foto opcional + bloque de fecha (subtítulo = fecha, texto = lugar y hora)
  cinta     foto impresa con borde blanco, levemente girada y pegada con cinta naranja

En el título, las palabras entre *asteriscos* se resaltan en naranja.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from PIL import Image, ImageDraw, ImageOps

try:  # fotos HEIC del iPhone
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from . import brand
from .brand import DARK, DARK_RGB, LIGHT, ORANGE, WHITE

TEMPLATES = {
    "impacto": "Foto a sangre",
    "marco": "Foto enmarcada",
    "banda": "Foto + banda naranja",
    "collage": "Collage (2-4 fotos)",
    "texto": "Solo texto (gris)",
    "naranja": "Solo texto (naranja)",
    "cita": "Frase / cita",
    "dato": "Dato / número grande",
    "lista": "Lista de puntos",
    "comparar": "Antes / después (2 fotos)",
    "agenda": "Evento / agenda",
    "cinta": "Foto con cinta",
    "hablemos": "Hablemos (contacto)",
    "mosaico": "Mosaico de fotos",
    "patron": "Patrón DER",
    "marco_tarjeta": "Marco tarjeta",
    "bloques": "Bloques",
    "galeria": "Galería B/N",
    "escenario": "Escenario",
}
PHOTO_TEMPLATES = {"impacto", "marco", "banda", "collage", "comparar", "cinta", "mosaico",
                   "marco_tarjeta", "bloques", "galeria", "escenario"}
# Plantillas que arman UNA pieza con todas las fotos (las demás hacen una pieza por foto = carrusel)
SINGLE_DESIGN = {  # (histórico) ahora todas arman carrusel con varias fotos
    "texto", "naranja", "collage", "cita", "dato", "lista", "comparar", "agenda"}
# Qué va en cada campo (se muestra en el formulario al elegir la plantilla)
TEMPLATE_HINTS = {
    "cita": "Título = la frase · Subtítulo = quién la dijo. No usa fotos.",
    "dato": "Título = el número (ej. +40.000) · Subtítulo = qué es · Texto = contexto. Si subís una foto, va de fondo.",
    "lista": "Título arriba · Texto = un punto por renglón (hasta 6).",
    "comparar": "Subí 2 fotos: la primera es ANTES, la segunda DESPUÉS. Título abajo.",
    "agenda": "Título = nombre del evento · Subtítulo = fecha (ej. 15 NOV) · Texto = lugar y hora. Foto opcional.",
    "cinta": "Una pieza por foto. Título y subtítulo debajo de la foto.",
    "hablemos": "Subtítulo = bajada naranja (ej. SOMOS DER) · Título = el mensaje · Texto: 1er renglón = mail, 2do = web. Foto opcional abajo a la derecha.",
    "mosaico": "De 3 a 10 fotos por pieza sobre naranja con textura. Título opcional arriba.",
    "patron": "La banda de patrón DER arriba y el texto abajo. Título · Subtítulo · Texto.",
    "marco_tarjeta": "1 foto. Título = palabra grande abajo a la izquierda · Subtítulo = fecha y hora (en la pestaña) · Texto: 1er renglón = nombre, 2do = palabra grande a la derecha.",
    "bloques": "3 fotos. Título = título grande · Subtítulo = fecha · Texto: 1er renglón = bloque naranja, 2do = recuadro naranja, 3ro = recuadro oscuro, el resto = datos a la derecha.",
    "galeria": "4 a 7 fotos (salen en blanco y negro). Título = 2 palabras gigantes · Subtítulo = fecha (ej. 23 NOV 2026) · Texto = un renglón por actividad o dato.",
    "escenario": "2 a 5 fotos (una por persona, la última va grande). Título = nombre del evento · Subtítulo = fecha y horario (al pie) · Texto = un nombre por renglón, en el mismo orden que las fotos.",
}
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


def textura(img: Image.Image, fuerza: float = 1.0, seed: int = 7) -> Image.Image:
    """Grano de papel y manchas suaves (como los fondos con textura de las piezas de Canva)."""
    import numpy as np
    rgb = img.convert("RGB")
    w, h = rgb.size
    rng = np.random.default_rng(seed)
    grano = rng.normal(0, 6 * fuerza, (h, w, 1))
    # manchas apenas perceptibles (papel), no nubes
    chico = Image.fromarray((rng.random((max(2, h // 40), max(2, w // 40))) * 255).astype("uint8"), "L")
    manchas = np.asarray(chico.resize((w, h), Image.BICUBIC), dtype=float)[..., None] / 255 - 0.5
    arr = np.asarray(rgb, dtype=float) + grano + manchas * 5 * fuerza
    out = Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGB")
    if img.mode == "RGBA":
        out.putalpha(img.getchannel("A"))
    return out


def difuminado(forma: str, w: int, h: int, color: str) -> Image.Image:
    """Difuminados de color (naranja, negro…) para usar como capas: brillo, degradé desde un borde, viñeta."""
    import numpy as np
    w, h = max(8, min(w, 2400)), max(8, min(h, 2400))
    y, x = np.mgrid[0:h, 0:w].astype(float)
    nx, ny = x / (w - 1), y / (h - 1)
    if forma == "abajo":
        a = np.clip(ny, 0, 1) ** 1.6
    elif forma == "arriba":
        a = np.clip(1 - ny, 0, 1) ** 1.6
    elif forma == "lado":
        a = np.clip(1 - nx, 0, 1) ** 1.6
    elif forma == "esquina":
        a = np.clip(1 - np.hypot(nx, 1 - ny) / 1.25, 0, 1) ** 1.8
    elif forma == "vineta":
        a = np.clip((np.hypot(nx - 0.5, ny - 0.5) / 0.72 - 0.35) / 0.65, 0, 1) ** 1.4
    else:  # radial: brillo suave en el centro
        a = np.clip(1 - np.hypot(nx - 0.5, ny - 0.5) / 0.5, 0, 1) ** 2.2
    rgb = Image.new("RGB", (w, h), color)
    out = rgb.convert("RGBA")
    out.putalpha(Image.fromarray((a * 255).astype("uint8"), "L"))
    return out


def element_from_query(kind: str, q: dict) -> Image.Image:
    """Las URLs /elemento/<tipo>.png?… que usa el editor (también las resuelve el compositor)."""
    return element_png(kind, corner=q.get("c", "tl"), size=int(q.get("l", 110)), thick=int(q.get("g", 10)),
                       cols=int(q.get("cols", 6)), rows=int(q.get("rows", 4)), gap=int(q.get("gap", 28)),
                       r=int(q.get("r", 4)), color="#" + str(q.get("color", "ff5c00")).lstrip("#"),
                       forma=q.get("forma", "radial"), w=int(q.get("w", 800)), h=int(q.get("h", 800)))


@lru_cache(maxsize=128)
def element_png(kind: str, corner: str = "tl", size: int = 110, thick: int = 10,
                cols: int = 6, rows: int = 4, gap: int = 28, r: int = 4, color: str = ORANGE,
                forma: str = "radial", w: int = 800, h: int = 800) -> Image.Image:
    """Elementos sueltos como PNG transparente, para usarlos como capas del editor."""
    color = color if color.startswith("#") else "#" + color
    if kind == "difuminado":
        return difuminado(forma, w, h, color)
    if kind == "rayas":   # franja de rayas diagonales (como en las piezas editoriales)
        W2, H2 = max(8, min(w, 2400)), max(8, min(h, 2400))
        img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        step = max(8, int(H2 * 0.5))
        for x0 in range(-H2, W2 + H2, step):
            d.polygon([(x0, H2), (x0 + step * 0.5, H2), (x0 + step * 0.5 + H2, 0), (x0 + H2, 0)], fill=color)
        return img
    if kind == "ondas":   # líneas onduladas paralelas
        import math
        W2, H2 = max(8, min(w, 2400)), max(8, min(h, 2400))
        img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        n = max(3, cols)
        for k in range(n):
            y0 = H2 * (k + 0.5) / n
            pts = [(x, y0 + math.sin(x / W2 * math.pi * 1.6 + k * 0.25) * H2 * 0.12) for x in range(0, W2 + 8, 8)]
            d.line(pts, fill=color, width=max(2, int(thick)))
        return img
    if kind == "modulo":  # forma DER como imagen recoloreable
        W2, H2 = max(8, min(w, 2400)), max(8, min(h, 2400))
        img = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if forma == "triangulo":
            d.polygon([(0, 0), (W2, H2), (0, H2)], fill=color)
        elif forma == "circulo":
            d.ellipse([0, 0, W2 - 1, H2 - 1], fill=color)
        else:  # cuarto de círculo
            d.pieslice([0, 0, 2 * W2, 2 * H2], 180, 270, fill=color)
        return img
    if kind == "textura":
        return textura(Image.new("RGBA", (max(8, min(w, 2400)), max(8, min(h, 2400))), color), 1.0 if forma == "papel" else 1.3)
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
        # La base es transparente donde va el fondo liso: ese color (bg) lo pinta el editor y se puede cambiar
        self.bg = bg
        self.base = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        self.layers: list[dict] = []
        self.pending: dict[str, Image.Image] = {}   # fotos de las capas, se guardan con la base

    def over(self, img: Image.Image, xy) -> None:
        """Pega una imagen con transparencia respetando el alfa (sombras, cintas)."""
        layer = Image.new("RGBA", self.base.size, (0, 0, 0, 0))
        img = img.convert("RGBA")
        layer.paste(img, (int(xy[0]), int(xy[1])), img)
        self.base = Image.alpha_composite(self.base.convert("RGBA"), layer)

    # Capas -----------------------------------------------------------------
    def text(self, role, text, x, y, w, color, size, line_gap, hl_color=None, upper=False, lines=None,
             align="left", name=None, angle=0, stroke=None, stroke_width=0):
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
            **({"angle": angle} if angle else {}), **({"stroke": stroke, "strokeWidth": round(stroke_width)} if stroke else {}),
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

    def rect(self, x, y, w, h, color, name="Barra", radius=0, stroke=None, stroke_width=0, angle=0, opacity=1.0,
             shadow=False, gradient=None, grupo=None):
        layer = {"type": "rect", "name": name, "x": round(x), "y": round(y), "w": round(w), "h": round(h), "color": color}
        if grupo:
            layer["grupo"] = grupo   # el editor junta en un grupo las capas con el mismo nombre de grupo
        if gradient:
            layer["gradient"] = gradient   # {"a": color, "b": color, "ang": grados}
        if radius:
            layer["rx"] = round(radius)
        if stroke:
            layer.update(stroke=stroke, strokeWidth=round(stroke_width))
        if angle:
            layer["angle"] = angle
        if opacity < 1:
            layer["opacity"] = opacity
        if shadow:
            layer["shadow"] = True
        self.layers.append(layer)

    def photo(self, img, x, y, w, h, name="Foto", radius=0, angle=0, filtro=None, grupo=None):
        """Foto como capa editable (se mueve, se recorta, se le pone marco o filtro en el editor)."""
        key = _photo_key(img)
        self.pending[key] = img
        layer = {"type": "photo", "name": name, "ref": key, "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                 "py": {"arriba": -0.6, "abajo": 0.6}.get(self.c.focus, 0.0)}
        if radius:
            layer["radius"] = round(radius)
        if angle:
            layer["angle"] = angle
        if filtro:
            layer["filtro"] = filtro
        if grupo:
            layer["grupo"] = grupo
        self.layers.append(layer)

    def element(self, kind, x, y, w, h, color=ORANGE, name="Elemento", opacity=1.0, **params):
        """Elemento gráfico de la marca (rayas, ondas, formas) como capa recoloreable."""
        layer = {"type": "image", "name": name, "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                 "src": element_url(kind, w=max(8, round(w)), h=max(8, round(h)), color=color.lstrip("#"), **params)}
        if opacity < 1:
            layer["opacity"] = opacity
        self.layers.append(layer)

    def fade(self, x, y, w, h, forma="abajo", color=DARK, opacity=0.9, name="Degradé"):
        """Degradé de color como capa (se puede achicar, mover o borrar)."""
        self.layers.append({"type": "image", "name": name, "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                            "opacity": opacity,
                            "src": element_url("difuminado", forma=forma, w=max(8, round(w / 2)), h=max(8, round(h / 2)),
                                               color=color.lstrip("#"))})

    def image(self, src, x, y, w, h, name="Imagen", bloqueado=False):
        layer = {"type": "image", "name": name, "src": src, "x": round(x), "y": round(y), "w": round(w), "h": round(h)}
        if bloqueado:
            layer["bloqueado"] = True
        self.layers.append(layer)

    def texture(self, color, fuerte=False):
        """Textura de papel como capa al fondo (bloqueada para no moverla sin querer; se borra desde Capas)."""
        self.image(element_url("textura", color=color.lstrip("#"), w=self.W, h=self.H, forma="fuerte" if fuerte else "papel"),
                   0, 0, self.W, self.H, "Textura", bloqueado=True)

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
        return {"fmt": self.fmt, "W": self.W, "H": self.H, "bg": self.bg, "layers": self.layers}

    def save_base(self, path_stem: Path) -> str:
        """JPG si la base es opaca (foto a sangre); PNG si deja ver el color de fondo.
        Las fotos de las capas se guardan en <lote>/capas/ (una vez por foto)."""
        if self.pending:
            capas = path_stem.parent / "capas"
            capas.mkdir(exist_ok=True)
            for key, img in self.pending.items():
                f = capas / f"{key}.jpg"
                if not f.exists():
                    im = img.copy()
                    im.thumbnail((2000, 2000))
                    im.convert("RGB").save(f, "JPEG", quality=90)
            for l in self.layers:
                if l.get("type") == "photo":
                    l["src_rel"] = f"capas/{l['ref']}.jpg"
        base = self.base
        if base.mode == "RGBA" and base.getchannel("A").getextrema()[0] < 255:
            out = path_stem.with_name(path_stem.name + ".base.png")
            base.save(out, "PNG", optimize=False, compress_level=3)
        else:
            out = path_stem.with_name(path_stem.name + ".base.jpg")
            base.convert("RGB").save(out, "JPEG", quality=95, subsampling=0)
        return out.name


def _photo_key(img: Image.Image) -> str:
    import hashlib
    return hashlib.md5(img.resize((48, 48)).tobytes() + repr(img.size).encode()).hexdigest()[:14]


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
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    D.photo(photos[0], 0, 0, W, H, "Foto de fondo")
    top, bottom = _safe(fmt, H)
    m = 80 * s
    has_text = first and _has_text(c)
    start = 0.35 if has_text else 0.7
    D.fade(0, H * start, W, H * (1 - start), "abajo", DARK, 0.95 if has_text else 0.65)
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
    top, bottom = _safe(fmt, H)
    m = 80 * s
    has_text = first and _has_text(c)
    box_w = W - 2 * m
    text_h = D.measure(box_w, H * 0.3, 80) if has_text else 0
    photo_top = top + 90 * s + 40 * s
    photo_bottom = H - bottom - (text_h + 70 * s if has_text else 40 * s)
    pw, ph = int(W - 2 * m - 24 * s), int(photo_bottom - photo_top)
    off = int(24 * s)
    D.rect(m + off, photo_top + off, pw, ph, ORANGE, "Bloque naranja", grupo="Foto con bloque")
    D.photo(photos[0], m, photo_top, pw, ph, grupo="Foto con bloque")
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
    D.photo(photos[0], 0, 0, W, H - band_h)
    D.rect(0, H - band_h, W, band_h, ORANGE, "Banda")
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
        D.photo(photo, x0, y0, w, h)
    D.rect(0, H - strip_h, W, 10 * s, ORANGE, "Línea")
    if has_text:
        D.text_block(m, H - strip_h + 60 * s, box_w - 220 * s, H * 0.25, WHITE, ORANGE, LIGHT, title_size=76)
    D.logo("on_dark", 180 * s, W - m, H - strip_h + 60 * s, "rt")
    return D


# --- Plantillas nuevas (oct 2026) -------------------------------------------------

def _fit_lines(text, role, w, max_h, size, min_size, gap, upper=False, max_lines=None):
    f, lines, _ = fit_text(text, role, w, max_h, size, min_size, gap, max_lines, upper)
    return f.size, lines


def tpl_cita(fmt, photos, c, first=True):
    """Frase grande sobre gris claro, comillas naranjas gigantes y firma."""
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 96 * s
    D.logo("on_light", 170 * s, m, top)
    D.dots(W - m - 4 * 26 * s, top + 12 * s, 5, 3, 26 * s, 4 * s, ORANGE)
    q = int(300 * s)
    box_w = W - 2 * m
    quote = c.title or c.body or c.subtitle
    size, lines = _fit_lines(quote, "subtitle", box_w, (H - top - bottom) * 0.5, int(78 * s), int(38 * s), 1.15)
    text_h = len(lines) * size * 1.15
    who_h = 60 * s if c.subtitle and c.title else 0
    y = top + (H - top - bottom - text_h - who_h - q * 0.55) / 2 + q * 0.55
    D.text("subtitle", "“", m - 12 * s, y - q * 0.78, q * 0.7, ORANGE, q, 1.0, name="Comillas")
    D.text("subtitle", "", m, y, box_w, DARK, size, 1.15, hl_color=ORANGE, lines=lines, name="Frase")
    y += text_h + 36 * s
    if who_h:
        D.rect(m, y + 14 * s, 50 * s, 6 * s, ORANGE, "Línea")
        D.text("body", c.subtitle.upper(), m + 70 * s, y, box_w - 70 * s, DARK, int(30 * s), 1.2, name="Firma")
    D.tag(W - m, H - bottom, DARK, align="right")
    return D


def tpl_dato(fmt, photos, c, first=True):
    """Un número enorme en naranja. Con foto, la foto va de fondo bien oscurecida."""
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 90 * s
    if photos:
        D.photo(photos[0], 0, 0, W, H, "Foto de fondo")
        D.rect(0, 0, W, H, DARK, "Oscurecer", opacity=0.72)
    D.logo("on_dark", 180 * s, m, top)
    D.bracket(W - m - 80 * s, top, 80 * s, 9 * s, ORANGE, "tr")
    box_w = W - 2 * m
    num = c.title or "+40"
    nsize, nlines = _fit_lines(num, "title", box_w, H * 0.3, int(300 * s), int(90 * s), 1.0, upper=True, max_lines=2)
    sub = c.subtitle
    ssize, slines = _fit_lines(sub, "subtitle", box_w, H * 0.14, int(54 * s), int(30 * s), 1.12) if sub else (0, [])
    bsize, blines = _fit_lines(c.body, "body", box_w, H * 0.16, int(34 * s), int(24 * s), 1.3) if c.body else (0, [])
    total_h = (len(nlines) * nsize + 40 * s + len(slines) * ssize * 1.12 + (30 * s if blines else 0)
               + len(blines) * bsize * 1.3)
    y = top + (H - top - bottom - total_h) / 2
    D.text("title", "", m, y, box_w, ORANGE, nsize, 1.0, hl_color=WHITE, lines=nlines, name="Número")
    y += len(nlines) * nsize + 14 * s
    D.rect(m, y, box_w, 4 * s, "#5a5a5a", "Línea")
    D.rect(m, y - 3 * s, 140 * s, 10 * s, ORANGE, "Barra")
    y += 26 * s
    if slines:
        D.text("subtitle", "", m, y, box_w, WHITE, ssize, 1.12, lines=slines, name="Qué es")
        y += len(slines) * ssize * 1.12 + 30 * s
    if blines:
        D.text("body", "", m, y, box_w, LIGHT, bsize, 1.3, lines=blines, name="Texto")
    D.tag(m, H - bottom + 20 * s, LIGHT)
    return D


def tpl_lista(fmt, photos, c, first=True):
    """Título + hasta 6 puntos numerados con cuadraditos naranjas."""
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 90 * s
    box_w = W - 2 * m
    items = [ln.strip(" -•·*\t") for ln in (c.body or "").splitlines() if ln.strip(" -•·*\t")][:6]
    if not items and c.subtitle:
        items = [x.strip() for x in c.subtitle.split("·") if x.strip()][:6]
    _, logo_h = D.logo("on_light", 160 * s, m, top)
    y = top + logo_h + 110 * s
    if c.title:
        tsize, tlines = _fit_lines(c.title, "title", box_w, H * 0.22, int(92 * s), int(44 * s), 1.06, upper=True)
        D.bar(m, y - 34 * s)
        D.text("title", "", m, y, box_w, DARK, tsize, 1.06, hl_color=ORANGE, lines=tlines, name="Título")
        y += len(tlines) * tsize * 1.06 + 60 * s
    if c.subtitle and c.body:
        D.text("subtitle", c.subtitle, m, y, box_w, ORANGE, int(40 * s), 1.12, name="Subtítulo")
        y += 80 * s
    n = max(1, len(items))
    avail = H - bottom - 60 * s - y
    row = min(avail / n, 190 * s)
    sq = int(min(row * 0.62, 84 * s))
    isize = int(min(46 * s, row * 0.42))
    for k, it in enumerate(items):
        D.rect(m, y + (row - sq) / 2 - 8 * s, sq, sq, ORANGE, f"Número {k + 1}")
        D.text("title", f"{k + 1}", m, y + (row - sq) / 2 - 8 * s + sq * 0.2, sq, WHITE, int(sq * 0.62), 1.0,
               align="center", name=f"N{k + 1}")
        size, lines = _fit_lines(it, "subtitle", box_w - sq - 34 * s, row * 0.9, isize, int(24 * s), 1.1, max_lines=2)
        ty = y + (row - len(lines) * size * 1.1) / 2 - 8 * s
        D.text("subtitle", "", m + sq + 34 * s, ty, box_w - sq - 34 * s, DARK, size, 1.1, lines=lines,
               name=f"Punto {k + 1}")
        if k < n - 1:
            D.rect(m + sq + 34 * s, y + row - 4 * s, box_w - sq - 34 * s, 2 * s, "#d0d0d0", "Separador")
        y += row
    D.tag(W - m, H - bottom + 20 * s, DARK, align="right")
    return D


def tpl_comparar(fmt, photos, c, first=True):
    """Dos fotos (antes / después) separadas por una línea naranja, con etiquetas."""
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 70 * s
    pair = (photos * 2)[:2]
    has_text = _has_text(c)
    strip = int((D.measure(W - 2 * m - 220 * s, H * 0.2, 70) + 90 * s + bottom * 0.5) if has_text else bottom * 0.6 + 60 * s)
    area_h = H - strip
    vertical = fmt == "historia"
    line = int(10 * s)
    if vertical:
        h1 = (area_h - line) // 2
        D.photo(pair[0], 0, 0, W, h1, "Foto antes")
        D.photo(pair[1], 0, h1 + line, W, area_h - h1 - line, "Foto después")
        D.rect(0, h1, W, line, ORANGE, "Divisor")
        tags = [(m, top), (m, h1 + line + 40 * s)]
    else:
        w1 = (W - line) // 2
        D.photo(pair[0], 0, 0, w1, area_h, "Foto antes")
        D.photo(pair[1], w1 + line, 0, W - w1 - line, area_h, "Foto después")
        D.rect(w1, 0, line, area_h, ORANGE, "Divisor")
        tags = [(40 * s, top), (w1 + line + 40 * s, top)]
    for (tx, ty), label, bg, fg in zip(tags, ("ANTES", "DESPUÉS"), (DARK, ORANGE), (WHITE, WHITE)):
        tw = (190 if label == "ANTES" else 250) * s
        D.rect(tx, ty, tw, 64 * s, bg, f"Etiqueta {label.lower()}")
        D.text("title", label, tx, ty + 15 * s, tw, fg, int(34 * s), 1.0, align="center", name=label.capitalize())
    D.rect(0, area_h, W, 6 * s, ORANGE, "Línea")
    if has_text:
        D.text_block(m, area_h + 50 * s, W - 2 * m - 220 * s, H * 0.2, WHITE, ORANGE, LIGHT, title_size=70)
    D.logo("on_dark", 170 * s, W - m, area_h + 50 * s, "rt")
    return D


def tpl_agenda(fmt, photos, c, first=True):
    """Evento: foto arriba (opcional), bloque naranja con la fecha y los datos abajo."""
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 80 * s
    split = int(H * (0.5 if fmt == "historia" else 0.46))
    if photos:
        D.photo(photos[0], 0, 0, W, split)
        D.fade(0, split * 0.25, W, split * 0.75, "abajo", DARK, 0.47)
    else:
        D.dots(W - m - 8 * 30 * s, top + 120 * s, 9, 6, 30 * s, 4 * s, "#5a5a5a")
        D.bracket(m, top + 100 * s, 120 * s, 10 * s, ORANGE, "tl")
    D.logo("on_dark", 180 * s, m, top)
    # bloque de fecha montado sobre el borde de la foto
    date = (c.subtitle or "PRÓXIMAMENTE").upper()
    bw, bh = 420 * s, 230 * s
    bx, by = m, split - bh * 0.55
    D.rect(bx, by, bw, bh, ORANGE, "Bloque fecha")
    dsize, dlines = _fit_lines(date, "title", bw - 60 * s, bh - 60 * s, int(92 * s), int(34 * s), 1.0, upper=True, max_lines=2)
    dy = by + (bh - len(dlines) * dsize) / 2
    D.text("title", "", bx + 30 * s, dy, bw - 60 * s, WHITE, dsize, 1.0, lines=dlines, name="Fecha")
    y = by + bh + 60 * s
    box_w = W - 2 * m
    if c.title:
        tsize, tlines = _fit_lines(c.title, "title", box_w, (H - bottom - y) * 0.55, int(96 * s), int(42 * s), 1.06,
                                   upper=True)
        D.text("title", "", m, y, box_w, WHITE, tsize, 1.06, hl_color=ORANGE, lines=tlines, name="Evento")
        y += len(tlines) * tsize * 1.06 + 30 * s
    if c.body:
        D.rect(m, y + 6 * s, 10 * s, 50 * s, ORANGE, "Marca lugar")
        bsize, blines = _fit_lines(c.body, "subtitle", box_w - 34 * s, H - bottom - y - 60 * s, int(42 * s),
                                   int(26 * s), 1.2)
        D.text("subtitle", "", m + 34 * s, y, box_w - 34 * s, LIGHT, bsize, 1.2, lines=blines, name="Lugar y hora")
    D.tag(W - m, H - bottom + 20 * s, LIGHT, align="right")
    return D


def tpl_cinta(fmt, photos, c, first=True):
    """Foto 'impresa' con borde blanco, girada apenas y pegada con dos tiras de cinta naranja."""
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m = 90 * s
    has_text = first and _has_text(c)
    box_w = W - 2 * m
    text_h = D.measure(box_w, H * 0.26, 80) if has_text else 0
    _, logo_h = D.logo("on_light", 160 * s, m, top)
    area_top = top + logo_h + 50 * s
    area_bot = H - bottom - (text_h + 110 * s if has_text else 40 * s)
    pw = int(W - 2 * m - 40 * s)
    ph = int(min(area_bot - area_top - 60 * s, pw * 1.25))
    border = int(26 * s)
    cw, ch = pw + 2 * border, ph + 2 * border + int(40 * s)
    angle = -2.5 if sum(map(ord, c.title or "")) % 2 == 0 else 2.5
    cx = (W - cw) / 2
    cy = area_top + (area_bot - area_top - ch) / 2
    import math
    rad = math.radians(angle)
    rot = lambda dx, dy: (cx + dx * math.cos(rad) - dy * math.sin(rad), cy + dx * math.sin(rad) + dy * math.cos(rad))  # noqa: E731
    D.rect(cx, cy, cw, ch, "#ffffff", "Tarjeta", angle=angle, shadow=True, grupo="Foto con cinta")
    px, py = rot(border, border)
    D.photo(photos[0], px, py, pw, ph, angle=angle, grupo="Foto con cinta")
    tw, th = 230 * s, 62 * s
    for (dx, dy), ta in (((cw - 250 * s, -20 * s), angle - 24), ((20 * s, ch - 90 * s), angle + 28)):
        tx, ty = rot(dx, dy)
        D.rect(tx, ty, tw, th, ORANGE, "Cinta", angle=ta, opacity=0.85, grupo="Foto con cinta")
    if has_text:
        D.text_block(m, H - bottom - text_h, box_w, H * 0.26, DARK, ORANGE, DARK, title_size=80)
    else:
        D.tag(W - m, H - bottom + 20 * s, DARK, align="right")
    return D


# --- Plantillas a partir de las piezas de Canva de DER (nov 2026) --------------------------------

def _rounded(img: Image.Image, r: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=r, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def tpl_hablemos(fmt, photos, c, first=True):
    """Fondo claro con textura, logo, bajada naranja, título grande, mail y web en píldoras, foto tipo sticker."""
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    D.texture(LIGHT)
    top, bottom = _safe(fmt, H)
    m = 80 * s
    _, lh = D.logo("on_light", 120 * s, m, top)
    y = top + lh + 50 * s
    box_w = W - 2 * m
    if c.subtitle:
        D.text("subtitle", c.subtitle.upper(), m, y, box_w, ORANGE, int(78 * s), 1.05, name="Bajada")
        y += 78 * s * 1.05 + 40 * s
    if c.title:
        size, lines = _fit_lines(c.title, "title", box_w * 0.95, H * 0.3, int(112 * s), int(48 * s), 1.08, upper=True)
        D.text("title", "", m, y, box_w, DARK, size, 1.08, hl_color=ORANGE, lines=lines, name="Título")
        y += len(lines) * size * 1.08
    renglones = [ln.strip() for ln in (c.body or "").splitlines() if ln.strip()]
    mail = renglones[0] if renglones else ""
    web = renglones[1] if len(renglones) > 1 else brand.WEBSITE
    pill_w, pill_h = 470 * s, 108 * s
    py = H - bottom - pill_h * 2 - 40 * s
    if photos:
        # foto tipo sticker: girada, con marco naranja grueso y sombra, saliendo por abajo a la derecha
        import math
        pw = int(W * (0.42 if fmt == "historia" else 0.46))
        ph = int(pw * 1.28)
        b = 16 * s
        ang = -9
        fx = W - (pw + 2 * b) * 0.86
        fy = H - (ph + 2 * b) * (0.8 if fmt == "historia" else 0.86) - (bottom * 0.6 if fmt == "historia" else 0)
        D.rect(fx, fy, pw + 2 * b, ph + 2 * b, ORANGE, "Marco sticker", radius=36 * s, angle=ang, shadow=True, grupo="Foto con marco")
        r = math.radians(ang)
        D.photo(photos[0], fx + b * math.cos(r) - b * math.sin(r), fy + b * math.sin(r) + b * math.cos(r), pw, ph,
                radius=26 * s, angle=ang, grupo="Foto con marco")
    if mail:
        D.rect(m, py, pill_w, pill_h, DARK, "Píldora mail", radius=pill_h / 2)
        fs, ln = _fit_lines(mail, "subtitle", pill_w - 60 * s, pill_h * 0.6, int(40 * s), int(20 * s), 1.0, max_lines=1)
        D.text("subtitle", "", m, py + (pill_h - fs) / 2 - 2 * s, pill_w, WHITE, fs, 1.0, lines=ln, align="center", name="Mail")
        py += pill_h + 40 * s
    D.rect(m + 10 * s, py, pill_w - 10 * s, pill_h, "rgba(0,0,0,0)", "Píldora web", radius=pill_h / 2, stroke=ORANGE, stroke_width=5 * s)
    fs, ln = _fit_lines(web, "subtitle", pill_w - 70 * s, pill_h * 0.6, int(40 * s), int(20 * s), 1.0, max_lines=1)
    D.text("subtitle", "", m + 10 * s, py + (pill_h - fs) / 2 - 2 * s, pill_w - 10 * s, DARK, fs, 1.0, lines=ln, align="center", name="Web")
    return D


def tpl_mosaico(fmt, photos, c, first=True):
    """3 a 10 fotos con esquinas redondeadas en columnas, sobre naranja con textura y formas de marca."""
    D = Design(fmt, c, ORANGE)
    W, H, s = D.W, D.H, D.s
    D.texture(ORANGE, fuerte=True)
    ghost = "#ff7a2e"
    R = int(W * 0.36)
    for k, (cx, cy) in enumerate(((W * 0.15, H * 0.02), (W * 0.82, H * 0.5), (W * 0.2, H * 0.98)), 1):
        D.rect(cx - R, cy - R, 2 * R, 2 * R, "rgba(0,0,0,0)", f"Círculo de fondo {k}", radius=R, stroke=ghost, stroke_width=70 * s)
    top, bottom = _safe(fmt, H)
    m, g = int(46 * s), int(18 * s)
    y0 = m if fmt != "historia" else top - 60 * s
    if c.title and first:
        size, lines = _fit_lines(c.title, "title", W - 2 * m, H * 0.12, int(70 * s), int(36 * s), 1.05, upper=True)
        D.text("title", "", m, y0, W - 2 * m, WHITE, size, 1.05, hl_color=DARK, lines=lines, name="Título")
        y0 += len(lines) * size * 1.05 + 26 * s
    y1 = H - (m if fmt != "historia" else bottom - 80 * s)
    n = max(1, len(photos))
    cols = 1 if n == 1 else 2 if n <= 4 else 3
    colw = (W - 2 * m - (cols - 1) * g) / cols
    columnas = [[] for _ in range(cols)]
    for i, ph in enumerate(photos):
        columnas[i % cols].append(ph)
    r = int(24 * s)
    for ci, col in enumerate(columnas):
        if not col:
            continue
        # alturas desparejas (como un mosaico): se reparten según el formato de cada foto
        pesos = [min(1.6, max(0.6, ph.height / ph.width)) * (1.0 + 0.18 * ((ci + k) % 2)) for k, ph in enumerate(col)]
        alto = y1 - y0 - g * (len(col) - 1)
        y = y0
        for ph, wgt in zip(col, pesos):
            hh = alto * wgt / sum(pesos)
            D.photo(ph, m + ci * (colw + g), y, colw, hh, radius=r)
            y += hh + g
    return D


def tpl_patron(fmt, photos, c, first=True):
    """Banda de patrón DER arriba (como elemento: se puede cambiar o mover) y el texto abajo."""
    D = Design(fmt, c, WHITE)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    pats = brand.list_patrones()
    band_h = 0
    if pats:
        k = (sum(map(ord, c.title or "")) % len(pats))
        pat = pats[k]
        im = Image.open(brand.PATRONES_DIR / pat)
        band_h = W * im.height / im.width
        D.image(f"/patron/{pat}", 0, 0, W, band_h, "Patrón DER")
    m = 90 * s
    box_w = W - 2 * m
    y = max(band_h + 80 * s, top)
    avail = H - bottom - y - 140 * s
    block = D.measure(box_w, avail, 104)
    y += max(0, (avail - block - 50 * s) * 0.4)   # el texto, algo arriba del centro del espacio libre
    D.bar(m, y)
    D.text_block(m, y + 50 * s, box_w, avail, DARK, ORANGE, DARK, title_size=104)
    D.logo("on_light", 170 * s, m, H - bottom, "lb")
    D.tag(W - m, H - bottom, DARK, align="right")
    return D


# --- Plantillas desde referencias editoriales (nov 2026), con la paleta DER ---------------------

N2, GRIS, NEGRO = "#f58b22", "#8a8889", "#1b1b1b"


def _renglones(c) -> list[str]:
    return [ln.strip() for ln in (c.body or "").splitlines() if ln.strip()]


def tpl_marco_tarjeta(fmt, photos, c, first=True):
    """Tarjeta naranja con degradé, foto en una ventana redondeada, pestañas de logo y fecha, textos grandes abajo."""
    D = Design(fmt, c, DARK)
    W, H, s = D.W, D.H, D.s
    m = 36 * s
    D.rect(m, m, W - 2 * m, H - 2 * m, ORANGE, "Tarjeta", radius=48 * s, gradient={"a": ORANGE, "b": "#ffb066", "ang": 90})
    pad = 52 * s
    wx, wy = m + pad, m + pad
    ww = W - 2 * m - 2 * pad
    wh = (H - 2 * m) * (0.66 if fmt == "historia" else 0.6 if fmt == "post" else 0.52)
    D.photo(photos[0], wx, wy, ww, wh, "Foto", radius=42 * s)
    # pestañas que "muerden" la ventana (como en la pieza de referencia)
    tab_w, tab_h = 400 * s, 140 * s
    D.rect(m, m, tab_w, tab_h, ORANGE, "Pestaña logo", radius=44 * s)
    D.logo("on_orange", 170 * s, m + 70 * s, m + 32 * s)
    if c.subtitle:
        dy = wy + wh * 0.56
        fs, ln = _fit_lines(c.subtitle, "title", 400 * s, 170 * s, int(64 * s), int(30 * s), 1.05, upper=True, max_lines=2)
        th = len(ln) * fs * 1.05 + 70 * s
        D.rect(m, dy, 470 * s, th, "#ff7a26", "Pestaña fecha", radius=44 * s)
        D.text("title", "", m + 58 * s, dy + 35 * s, 400 * s, DARK, fs, 1.05, lines=ln, name="Fecha")
    y0 = wy + wh + 46 * s
    hb = H - m - 40 * s - y0
    if c.title:
        fs, ln = _fit_lines(c.title, "title", ww * 0.56, hb, int(150 * s), int(50 * s), 0.98, upper=True, max_lines=3)
        D.text("title", "", wx, y0, ww * 0.56, DARK, fs, 0.98, hl_color=WHITE, lines=ln, name="Título")
    r = _renglones(c)
    if r:
        D.text("subtitle", r[0].upper(), wx + ww * 0.5, y0 + 10 * s, ww * 0.5, DARK, int(46 * s), 1.1, align="right", name="Nombre")
    if len(r) > 1:
        fs, ln = _fit_lines(r[1], "title", ww * 0.46, hb * 0.6, int(130 * s), int(44 * s), 1.0, upper=True, max_lines=2)
        D.text("title", "", wx + ww * 0.54, H - m - 40 * s - len(ln) * fs, ww * 0.46, DARK, fs, 1.0, lines=ln, align="right", name="Palabra")
    return D


def tpl_bloques(fmt, photos, c, first=True):
    """Fondo claro con textura, fotos escalonadas, bloques naranjas, rayas, palabra con contorno vertical y datos."""
    D = Design(fmt, c, LIGHT)
    W, H, s = D.W, D.H, D.s
    D.texture("#efe7df")
    top, bottom = _safe(fmt, H)
    ph = (photos * 3)[:3]
    y0 = top if fmt == "historia" else 70 * s
    A = H * (0.40 if fmt == "historia" else 0.46 if fmt == "post" else 0.40)
    m = 110 * s
    # bloques y fotos
    D.rect(m, y0 + A * 0.08, 62 * s, A * 0.42, ORANGE, "Bloque")
    D.photo(ph[0], m + 80 * s, y0, W * 0.30, A * 0.55, "Foto 1")
    D.photo(ph[1], m + 80 * s + W * 0.30 + 20 * s, y0 + A * 0.12, W * 0.28, A * 0.55, "Foto 2")
    D.photo(ph[2], m, y0 + A * 0.58, W * 0.30 + 80 * s, A * 0.42, "Foto 3")
    D.element("rayas", m, y0 + A * 0.52, 200 * s, 54 * s, ORANGE, "Rayas")
    D.rect(m - 76 * s, y0 + A * 0.86, 62 * s, 62 * s, ORANGE, "Cuadrado")
    bx, by = m + 80 * s + W * 0.30 + 20 * s, y0 + A * 0.70
    bw, bh = W - m - bx, A * 0.30
    D.rect(bx, by, bw, bh, ORANGE, "Bloque datos")
    r = _renglones(c)
    if r:
        D.text("subtitle", r[0].upper(), bx + 40 * s, by + bh / 2 - 40 * s, bw - 80 * s, WHITE, int(40 * s), 1.1, name="Dato bloque")
    D.element("rayas", bx + bw - 230 * s, by - 70 * s, 230 * s, 54 * s, ORANGE, "Rayas")
    # palabra con contorno, en vertical sobre las fotos
    word = (c.title or "DER").split()[0].upper()
    D.text("title", word, m + 80 * s + W * 0.30 - 40 * s, y0 + A * 0.98, A * 0.95, "rgba(0,0,0,0)",
           int(min(170 * s, A * 0.95 / max(3, len(word)) * 1.6)), 1.0, name="Palabra vertical", angle=-90, stroke=WHITE, stroke_width=5 * s)
    # título y datos
    ty = y0 + A + 60 * s
    if c.title:
        fs, ln = _fit_lines(c.title, "title", W - 2 * m + 40 * s, H * 0.18, int(150 * s), int(50 * s), 0.98, upper=True, max_lines=2)
        D.text("title", "", m - 20 * s, ty, W - 2 * m + 40 * s, "#3a2310" if False else DARK, fs, 0.98, hl_color=ORANGE, lines=ln, name="Título")
        ty += len(ln) * fs * 0.98 + 30 * s
    lx, lw = m - 20 * s, W * 0.42
    yy = ty
    if c.subtitle:
        D.text("title", c.subtitle.upper(), lx, yy, lw, DARK, int(62 * s), 1.0, name="Fecha")
        yy += 90 * s
    if len(r) > 1:
        fs, ln = _fit_lines(r[1], "subtitle", lw - 48 * s, 120 * s, int(36 * s), int(22 * s), 1.1, max_lines=2)
        hh = len(ln) * fs * 1.1 + 44 * s
        D.rect(lx, yy, lw, hh, ORANGE, "Recuadro naranja")
        D.text("subtitle", "", lx + 24 * s, yy + 22 * s, lw - 48 * s, WHITE, fs, 1.1, lines=ln, name="Dato naranja")
        yy += hh
    if len(r) > 2:
        D.rect(lx, yy, lw, 80 * s, DARK, "Recuadro oscuro")
        D.text("title", r[2].upper(), lx, yy + 18 * s, lw, N2, int(44 * s), 1.0, align="center", name="Dato oscuro")
    rx, ry = W * 0.55, ty
    for k, ln in enumerate(r[3:7]):
        D.text("subtitle", ln, rx, ry, W - m - rx, DARK, int(40 * s), 1.15, name=f"Dato {k + 1}")
        ry += 76 * s
    D.element("rayas", lx + lw - 120 * s, min(H - bottom - 40 * s, yy + 110 * s), 160 * s, 50 * s, ORANGE, "Rayas")
    D.logo("on_light", 120 * s, W - m, y0, "rt")
    return D


def tpl_galeria(fmt, photos, c, first=True):
    """Fotos en blanco y negro desparramadas, cuadrados naranjas translúcidos, título gigante y columna de datos."""
    D = Design(fmt, c, WHITE)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    k = H / 1920 if fmt == "historia" else H / 1350 * 0.72 if fmt == "post" else H / 1080 * 0.58
    oy = top - 150 * s if fmt == "historia" else 40 * s
    Y = lambda f: oy + f * 1920 * k  # noqa: E731  (posiciones pensadas para historia, se comprimen en post)
    D.rect(0, Y(0.42), W * 0.66, Y(0.74) - Y(0.42), "#ececec", "Bloque gris")
    D.rect(W * 0.62, Y(0.05), W * 0.38, Y(0.33) - Y(0.05), "#f2f2f2", "Bloque gris")
    slots = [(0.40, 0.12, 0.27, 0.23), (0.13, 0.24, 0.21, 0.16), (0.05, 0.42, 0.33, 0.13), (0.44, 0.38, 0.22, 0.16),
             (0.69, 0.38, 0.25, 0.10), (0.69, 0.50, 0.25, 0.06), (0.43, 0.58, 0.22, 0.10)]
    for i, (ph, (fx, fy, fw, fh)) in enumerate(zip(photos, slots), 1):
        D.photo(ph, W * fx, Y(fy), W * fw, Y(fy + fh) - Y(fy), f"Foto {i}", filtro="bn")
    for i, (fx, fy, fw, fh) in enumerate([(0.62, 0.08, 0.14, 0.07), (0.05, 0.30, 0.21, 0.035), (0.61, 0.35, 0.07, 0.05),
                                          (0.08, 0.50, 0.15, 0.11), (0.48, 0.63, 0.18, 0.05)], 1):
        D.rect(W * fx, Y(fy), W * fw, Y(fy + fh) - Y(fy), ORANGE, f"Cuadrado {i}", opacity=0.72)
    D.logo("on_light", 150 * s, W * 0.13, Y(0.07))
    cx = W * 0.70
    if c.subtitle:
        parts = c.subtitle.upper().split()
        fs = int(76 * s)
        for j, part in enumerate(parts[:3]):
            D.text("title", part, cx, Y(0.13) + j * fs * 1.02, W - cx - 40 * s, ORANGE if j == len(parts[:3]) - 1 else DARK, fs, 1.0,
                   name=f"Fecha {j + 1}")
    ry = Y(0.62)
    for j, ln in enumerate(_renglones(c)[:3 if fmt == "cuadrado" else 5]):
        fs, lns = _fit_lines(ln.upper(), "subtitle", W - cx - 10 * s, 90 * s, int(34 * s), int(22 * s), 1.08, max_lines=2)
        D.text("subtitle", "", cx - 20 * s, ry, W - cx - 10 * s, DARK, fs, 1.08, lines=lns, name=f"Dato {j + 1}")
        ry += len(lns) * fs * 1.08 + 24 * s
    words = (c.title or "GALERÍA DER").upper().split()
    w1, w2 = (words[0], " ".join(words[1:])) if len(words) > 1 else (words[0], "")
    ty = Y(0.70)
    fs1, ln1 = _fit_lines(w1, "title", W * 0.58, Y(0.82) - ty, int(230 * s), int(60 * s), 0.95, max_lines=1)
    D.text("title", "", W * 0.05, ty, W * 0.6, ORANGE, fs1, 0.95, lines=ln1, name="Título 1")
    y2 = ty + fs1 * 1.0
    if w2:
        fs2, ln2 = _fit_lines(w2, "title", W * 0.62, H * 0.2, min(fs1, int(230 * s)), int(60 * s), 0.95, max_lines=1)
        D.text("title", "", W * 0.33, y2, W * 0.65, ORANGE, fs2, 0.95, lines=ln2, name="Título 2")
        y2 += fs2
    D.tag(W * 0.05, y2 - 30 * s, DARK)
    return D


def tpl_escenario(fmt, photos, c, first=True):
    """Fondo oscuro, fotos en tarjetas de colores con el nombre de cada uno, ondas, formas DER grandes y pie con fecha."""
    D = Design(fmt, c, NEGRO)
    W, H, s = D.W, D.H, D.s
    top, bottom = _safe(fmt, H)
    m, g = 110 * s, 16 * s
    y0 = top if fmt == "historia" else 60 * s
    D.element("ondas", 0, H * 0.28, W * 0.45, H * 0.16, ORANGE, "Ondas", opacity=0.7, cols=9, g=3)
    D.element("ondas", W * 0.55, H * 0.44, W * 0.45, H * 0.16, ORANGE, "Ondas", opacity=0.7, cols=9, g=3)
    colores = [ORANGE, GRIS, N2, "#5a5a5a"]
    n = max(1, len(photos))
    chicas, grande = (photos[:-1], photos[-1]) if n > 1 else ([], photos[0])
    area_h = (H - y0 - bottom) * (0.70 if fmt == "historia" else 0.66)
    filas = max(1, -(-len(chicas) // 2))
    big_h = area_h * (0.42 if chicas else 1.0)
    cell_h = (area_h - big_h - g * filas) / filas if chicas else 0
    cw = (W - 2 * m - g) / 2
    nombres = _renglones(c)
    for i, ph in enumerate(chicas):
        x = m + (i % 2) * (cw + g)
        y = y0 + (i // 2) * (cell_h + g)
        D.rect(x, y, cw, cell_h, colores[i % 4], f"Tarjeta {i + 1}")
        D.photo(ph, x, y + cell_h * 0.16, cw, cell_h * 0.84, f"Foto {i + 1}")
        if i < len(nombres):
            D.text("subtitle", nombres[i].upper(), x + cw * 0.45, y + 14 * s, cw * 0.52, WHITE, int(24 * s), 1.1, align="right", name=f"Nombre {i + 1}")
    by = y0 + filas * (cell_h + g) if chicas else y0
    D.rect(m, by, W - 2 * m, big_h, colores[len(chicas) % 4], "Tarjeta grande")
    D.photo(grande, m, by + big_h * 0.12, W - 2 * m, big_h * 0.88, "Foto grande")
    if len(nombres) > len(chicas):
        D.text("subtitle", nombres[len(chicas)].upper(), m + (W - 2 * m) * 0.55, by + 14 * s, (W - 2 * m) * 0.42, WHITE, int(26 * s), 1.1,
               align="right", name="Nombre grande")
    # formas DER grandes (como el monograma de la referencia)
    sz = min(300 * s, big_h * 0.7)
    D.element("modulo", W - m - sz * 1.45, by + big_h - sz, sz * 0.75, sz, ORANGE, "Forma DER", forma="triangulo")
    D.element("modulo", W - m - sz * 0.7, by + big_h - sz * 0.7, sz * 0.7, sz * 0.7, N2, "Forma DER", forma="cuarto")
    # título y pie
    ty = by + big_h + 60 * s
    for k in range(4):
        D.rect(m + k * 14 * s, ty + 6 * s, 5 * s, 130 * s, ORANGE, "Línea título")
    if c.title:
        fs, ln = _fit_lines(c.title, "title", W - 2 * m - 80 * s, 180 * s, int(110 * s), int(40 * s), 1.0, upper=True, max_lines=2)
        D.text("title", "", m + 80 * s, ty, W - 2 * m - 80 * s, LIGHT, fs, 1.0, hl_color=ORANGE, lines=ln, name="Título")
    fy = H - bottom + (40 * s if fmt == "historia" else -30 * s)
    D.rect(m, fy - 30 * s, W - 2 * m, 2 * s, GRIS, "Línea pie")
    D.logo("on_dark", 110 * s, m, fy - 10 * s)
    if c.subtitle:
        D.text("title", c.subtitle.upper(), W * 0.35, fy, W * 0.65 - m, LIGHT, int(38 * s), 1.0, align="right", name="Fecha y horario")
    return D


RENDERERS = {
    "impacto": tpl_impacto,
    "marco": tpl_marco,
    "banda": tpl_banda,
    "collage": tpl_collage,
    "texto": tpl_texto,
    "naranja": tpl_naranja,
    "cita": tpl_cita,
    "dato": tpl_dato,
    "lista": tpl_lista,
    "comparar": tpl_comparar,
    "agenda": tpl_agenda,
    "cinta": tpl_cinta,
    "hablemos": tpl_hablemos,
    "mosaico": tpl_mosaico,
    "patron": tpl_patron,
    "marco_tarjeta": tpl_marco_tarjeta,
    "bloques": tpl_bloques,
    "galeria": tpl_galeria,
    "escenario": tpl_escenario,
}


def relayout(origen: dict, fmt: str, fotos_dir: Path) -> "Design":
    """La misma pieza (plantilla, fotos y textos) armada en otro formato."""
    photos = [load_photo(fotos_dir / n) for n in origen.get("fotos", [])]
    return RENDERERS[origen["plantilla"]](fmt, photos, Content(**origen["contenido"]), first=origen.get("principal", True))


# Plantillas que hacen una pieza por foto
PER_PHOTO = {"impacto", "marco", "banda", "cinta", "marco_tarjeta"}
# Diapositivas siguientes de un carrusel para las plantillas de texto: misma onda, una por foto
CONTINUATION = {"texto": "impacto", "naranja": "banda", "cita": "marco", "lista": "marco",
                "dato": "impacto", "agenda": "impacto", "hablemos": "marco", "patron": "marco"}


def _chunks(items: list, size: int) -> list[list]:
    """Reparte en grupos parejos de hasta `size` (9 fotos de a 4 -> 3, 3, 3)."""
    n = -(-len(items) // size)
    base, extra = divmod(len(items), n)
    out, k = [], 0
    for g in range(n):
        m = base + (1 if g < extra else 0)
        out.append(items[k:k + m])
        k += m
    return out


def slides(template: str, photos: list) -> list[tuple[str, list, bool]]:
    """Diapositivas del carrusel: (plantilla, fotos, es_la_principal)."""
    if template in PER_PHOTO:
        return [(template, [p], True) for p in photos]
    if template == "collage":
        return [("collage", g, True) for g in _chunks(photos, 4)]
    if template == "mosaico":
        return [("mosaico", g, True) for g in _chunks(photos, 10)]
    if template in ("galeria", "escenario", "bloques"):
        size = {"galeria": 7, "escenario": 5, "bloques": 3}[template]
        return [(template, g, True) for g in _chunks(photos, size)]
    if template == "comparar":
        out = [("comparar", photos[k:k + 2], True) for k in range(0, len(photos) - 1, 2)]
        if len(photos) % 2:
            out.append(("impacto", photos[-1:], False))
        return out
    lead = photos[:1] if template in ("dato", "agenda", "hablemos") else []
    rest = photos[len(lead):]
    return [(template, lead, True)] + [(CONTINUATION[template], [p], False) for p in rest]


def generate(template: str, formats: list[str], photo_paths: list[Path], content: Content,
             out_dir: Path, carousel_text_first_only: bool = True) -> list[dict]:
    """Genera los diseños (base + capas JSON). Con varias fotos arma un carrusel en cualquier plantilla."""
    out_dir.mkdir(parents=True, exist_ok=True)
    photos = [load_photo(p) for p in photo_paths]
    if template in PHOTO_TEMPLATES and not photos:
        raise ValueError("Esta plantilla necesita al menos una foto.")
    if template == "comparar" and len(photos) < 2:
        raise ValueError("Antes / después necesita 2 fotos: la primera es ANTES y la segunda DESPUÉS.")
    if len(photos) > 20:
        raise ValueError("Instagram permite hasta 20 diapositivas por carrusel. Subí 20 fotos o menos.")
    designs = []
    for fmt in formats:
        plan = slides(template, list(range(len(photos))))   # índices: así cada pieza sabe qué fotos usó
        for i, (tpl, idxs, main) in enumerate(plan, 1):
            first = i == 1 or not carousel_text_first_only
            principal = first and (main or not carousel_text_first_only)
            d = RENDERERS[tpl](fmt, [photos[k] for k in idxs], content, first=principal)
            name = f"DER-{template}-{fmt}" + (f"-{i:02d}" if len(plan) > 1 else "")
            base_file = d.save_base(out_dir / name)
            # origen: con esto se puede rehacer la pieza en otro formato (como el "redimensionar" de Canva)
            origen = {"plantilla": tpl, "fotos": [Path(photo_paths[k]).name for k in idxs],
                      "contenido": content.__dict__.copy(), "principal": principal}
            data = {"name": name, "base_file": base_file, **d.to_dict(), "origen": origen}
            (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            designs.append(data)
    return designs
