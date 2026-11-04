"""Compone en el servidor la pieza terminada (base + color de fondo + capas), igual que el editor.

Así las piezas se terminan aunque el celular salga de la app: el navegador ya no tiene que
dibujarlas. El editor (Fabric.js) se sigue usando para editar; esto replica su forma de
ubicar el texto:
  - interlineado = tamaño × lineGap
  - línea base = arriba + n.º de línea × interlineado + tamaño × 1,13 × (1 − 0,222)
    (_fontSizeMult y _fontSizeFraction de Fabric)
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageDraw

from . import brand, graphics

FS_MULT, FS_FRACTION = 1.13, 0.222
BASELINE = FS_MULT * (1 - FS_FRACTION)


def _image_for(src: str) -> Image.Image:
    """Resuelve en el servidor las mismas URLs que usa el editor (logos y elementos)."""
    u = urlparse(src)
    if u.path.startswith("/logos/ver/"):
        kind, _, value = unquote(u.path[len("/logos/ver/"):]).partition(":")
        return brand.logo_file(value) if kind == "file" else brand.logo(value or "on_dark")
    if u.path.startswith("/elemento/"):
        return graphics.element_from_query(Path(u.path).stem, {k: v[0] for k, v in parse_qs(u.query).items()})
    if u.path.startswith("/patron/"):
        return Image.open(brand.PATRONES_DIR / Path(u.path).name).convert("RGBA")
    raise ValueError(f"No sé componer la imagen {src}")


def _text(d: ImageDraw.ImageDraw, layer: dict) -> None:
    size = int(layer["size"])
    f = brand.font(layer["font"], size)
    line_h = size * float(layer["lineGap"])
    box_w = layer["w"] + int(-(-size * 0.15 // 1))  # mismo ancho que el Textbox del editor
    styles = layer.get("styles") or {}
    for li, line in enumerate(layer["text"].split("\n")):
        line_w = f.getlength(line)
        align = layer.get("align", "left")
        x = layer["x"] + ((box_w - line_w) / 2 if align == "center" else (box_w - line_w) if align == "right" else 0)
        y = layer["y"] + li * line_h + size * BASELINE
        st = styles.get(str(li)) or {}
        if not st:
            d.text((x, y), line, font=f, fill=layer["color"], anchor="ls")
            continue
        # tramos con el mismo color (palabras resaltadas)
        start = 0
        while start < len(line):
            color = (st.get(str(start)) or {}).get("fill", layer["color"])
            end = start + 1
            while end < len(line) and (st.get(str(end)) or {}).get("fill", layer["color"]) == color:
                end += 1
            d.text((x + f.getlength(line[:start]), y), line[start:end], font=f, fill=color, anchor="ls")
            start = end


def _place(img: Image.Image, tile: Image.Image, x: float, y: float, angle: float = 0, opacity: float = 1.0) -> Image.Image:
    """Pega `tile` en (x, y) girado `angle` grados alrededor de su esquina superior izquierda (como Fabric)."""
    import math
    tile = tile.convert("RGBA")
    if opacity < 1:
        tile.putalpha(tile.getchannel("A").point(lambda a: int(a * opacity)))
    if angle:
        w, h = tile.size
        r = math.radians(angle)
        pts = [(px * math.cos(r) - py * math.sin(r), px * math.sin(r) + py * math.cos(r)) for px, py in ((0, 0), (w, 0), (w, h), (0, h))]
        tile = tile.rotate(-angle, expand=True, resample=Image.BICUBIC)
        x, y = x + min(p[0] for p in pts), y + min(p[1] for p in pts)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    layer.paste(tile, (round(x), round(y)), tile)
    return Image.alpha_composite(img, layer)


def _photo(layer: dict, lote: Path) -> Image.Image:
    """Recorte de la foto igual que el editor: llena el cuadro, centrada (o hacia arriba/abajo)."""
    from PIL import ImageOps
    src = Image.open(lote / layer["src_rel"]).convert("RGB")
    w, h = max(1, round(layer["w"])), max(1, round(layer["h"]))
    py = layer.get("py", 0.0)
    out = ImageOps.fit(src, (w, h), Image.LANCZOS, centering=(0.5, 0.5 + 0.5 * py)).convert("RGBA")
    if layer.get("radius"):
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=layer["radius"], fill=255)
        out.putalpha(mask)
    return out


def compose(design: dict, base_path: Path) -> Image.Image:
    """Devuelve la pieza terminada (RGB) a tamaño completo."""
    W, H = design["W"], design["H"]
    img = Image.new("RGBA", (W, H), design.get("bg") or brand.LIGHT)
    base = Image.open(base_path).convert("RGBA")
    if base.size != (W, H):
        base = base.resize((W, H), Image.LANCZOS)
    img = Image.alpha_composite(img, base)
    d = ImageDraw.Draw(img)
    for layer in design["layers"]:
        t = layer["type"]
        if t == "text":
            _text(d, layer)
        elif t == "rect":
            w, h = max(1, round(layer["w"])), max(1, round(layer["h"]))
            sw = layer.get("strokeWidth", 0) or 0
            tile = Image.new("RGBA", (w + sw, h + sw), (0, 0, 0, 0))
            fill = None if str(layer["color"]).startswith("rgba(0,0,0,0") else layer["color"]
            ImageDraw.Draw(tile).rounded_rectangle([sw / 2, sw / 2, w - 1 + sw / 2, h - 1 + sw / 2], radius=layer.get("rx", 0),
                                                   fill=fill, outline=layer.get("stroke"), width=sw)
            if layer.get("shadow"):
                from PIL import ImageFilter
                sh = Image.new("RGBA", tile.size, (0, 0, 0, 0))
                sh.putalpha(tile.getchannel("A").point(lambda a: int(a * 0.3)))
                pad = 40
                big = Image.new("RGBA", (sh.width + 2 * pad, sh.height + 2 * pad), (0, 0, 0, 0))
                big.paste(sh, (pad, pad))
                img = _place(img, big.filter(ImageFilter.GaussianBlur(14)), layer["x"] - pad + 10, layer["y"] - pad + 16, layer.get("angle", 0))
            img = _place(img, tile, layer["x"] - sw / 2, layer["y"] - sw / 2, layer.get("angle", 0), layer.get("opacity", 1.0))
            d = ImageDraw.Draw(img)
        elif t == "photo":
            img = _place(img, _photo(layer, base_path.parent), layer["x"], layer["y"], layer.get("angle", 0), layer.get("opacity", 1.0))
            d = ImageDraw.Draw(img)
        else:
            el = _image_for(layer["src"]).convert("RGBA").resize((max(1, round(layer["w"])), max(1, round(layer["h"]))),
                                                                 Image.LANCZOS)
            img = _place(img, el, layer["x"], layer["y"], layer.get("angle", 0), layer.get("opacity", 1.0))
            d = ImageDraw.Draw(img)
    return img.convert("RGB")


def save_final(design: dict, out_dir: Path) -> Path:
    """Escribe <nombre>.jpg (la pieza que se descarga) junto a su base."""
    out = out_dir / f"{design['name']}.jpg"
    compose(design, out_dir / design["base_file"]).save(out, "JPEG", quality=93)
    return out
