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
        kind = Path(u.path).stem
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        return graphics.element_png(kind, corner=q.get("c", "tl"), size=int(q.get("l", 110)),
                                    thick=int(q.get("g", 10)), cols=int(q.get("cols", 6)),
                                    rows=int(q.get("rows", 4)), gap=int(q.get("gap", 28)),
                                    r=int(q.get("r", 4)), color="#" + q.get("color", "ff5c00"))
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
            d.rectangle([layer["x"], layer["y"], layer["x"] + layer["w"] - 1, layer["y"] + layer["h"] - 1],
                        fill=layer["color"])
        else:
            el = _image_for(layer["src"]).convert("RGBA").resize((max(1, round(layer["w"])), max(1, round(layer["h"]))),
                                                                 Image.LANCZOS)
            img.alpha_composite(el, (round(layer["x"]), round(layer["y"]))) if layer["x"] >= 0 and layer["y"] >= 0 \
                else img.paste(el, (round(layer["x"]), round(layer["y"])), el)
            d = ImageDraw.Draw(img)
    return img.convert("RGB")


def save_final(design: dict, out_dir: Path) -> Path:
    """Escribe <nombre>.jpg (la pieza que se descarga) junto a su base."""
    out = out_dir / f"{design['name']}.jpg"
    compose(design, out_dir / design["base_file"]).save(out, "JPEG", quality=93)
    return out
