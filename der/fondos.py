"""Fondos de marca para las piezas: que las plantillas de texto no queden en un color liso.

Cada fondo son capas (bloqueadas, al fondo de todo) que se adaptan al tono de la pieza: oscuro, claro
o naranja. Se eligen al generar («Fondo» en el formulario), y en el editor (pestaña Fondo → Fondos DER)
se cambian sobre cualquier pieza. Las capas se llaman «Fondo · …» para poder reemplazarlas.
"""
from __future__ import annotations

from PIL import Image

from . import brand
from .brand import DARK, LIGHT, ORANGE

FONDOS = {
    "auto": "Automático",
    "liso": "Liso",
    "papel": "Papel",
    "brillo": "Brillo naranja",
    "degrade": "Degradé",
    "modulos": "Módulos DER",
    "patron": "Patrón DER",
    "ondas": "Ondas",
    "grilla": "Grilla de puntos",
    "rayas": "Rayas",
}
# Con «Automático», cada plantilla de texto trae su fondo (las de foto quedan como están)
AUTO = {"texto": "brillo", "naranja": "degrade", "cita": "modulos", "dato": "grilla", "lista": "papel",
        "agenda": "brillo", "patron": "papel"}
PREFIJO = "Fondo · "
# Tono de fondo de cada plantilla (para mostrar las miniaturas de los fondos como van a quedar)
TONO_PLANTILLA = {"texto": "oscuro", "naranja": "naranja", "cita": "claro", "dato": "oscuro", "lista": "claro",
                  "agenda": "oscuro", "hablemos": "claro", "patron": "claro", "mosaico": "naranja", "bloques": "claro"}
COLOR_TONO = {"oscuro": DARK, "claro": LIGHT, "naranja": ORANGE}


def tono(bg: str) -> str:
    """oscuro | claro | naranja, según el color de fondo de la pieza."""
    c = (bg or "").lower()
    if c == ORANGE.lower():
        return "naranja"
    try:
        r, g, b = Image.new("RGB", (1, 1), c).getpixel((0, 0))
    except ValueError:
        return "oscuro"
    if r > 200 and 60 < g < 150 and b < 90:
        return "naranja"
    return "claro" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "oscuro"


def _url(kind: str, **q) -> str:
    from .graphics import element_url
    return element_url(kind, **q)


def capas(kind: str, W: int, H: int, bg: str) -> list[dict]:
    """Las capas del fondo `kind` para una pieza de W×H con fondo `bg`."""
    t = tono(bg)
    s = W / 1080
    nombre = PREFIJO + FONDOS.get(kind, kind)

    def img(src, x, y, w, h, opacity=1.0):
        layer = {"type": "image", "name": nombre, "src": src, "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                 "bloqueado": True}
        if opacity < 1:
            layer["opacity"] = opacity
        return layer

    def difu(forma, x, y, w, h, color, opacity):
        return img(_url("difuminado", forma=forma, w=max(8, round(w / 2)), h=max(8, round(h / 2)), color=color.lstrip("#")),
                   x, y, w, h, opacity)

    if kind == "papel":
        return [img(_url("textura", color=bg.lstrip("#"), w=W, h=H, forma="fuerte" if t == "naranja" else "papel"), 0, 0, W, H)]
    if kind == "brillo":
        if t == "naranja":
            return [difu("radial", -W * 0.7, -W * 0.7, W * 1.9, W * 1.9, "#ffc49a", 0.85),
                    difu("radial", W * 0.1, H - W * 1.0, W * 1.7, W * 1.7, "#8a3200", 0.6)]
        a = 0.95 if t == "oscuro" else 0.5
        return [difu("radial", -W * 0.1, -W * 0.8, W * 1.9, W * 1.9, ORANGE, a),
                difu("radial", -W * 0.75, H - W * 0.85, W * 1.7, W * 1.7, ORANGE, a * 0.65)]
    if kind == "degrade":
        a, b = {"oscuro": ("#1c1c1c", "#5a2e14"), "claro": (LIGHT, "#ffd8bf"), "naranja": ("#ff7a2e", "#b83f00")}[t]
        return [{"type": "rect", "name": nombre, "x": 0, "y": 0, "w": W, "h": H, "color": a, "bloqueado": True,
                 "gradient": {"a": a, "b": b, "ang": 120}}]
    if kind == "modulos":
        col = {"oscuro": "#3e3e3e", "claro": "#e2e2e2", "naranja": "#ff7d33"}[t]
        acento = {"oscuro": ORANGE, "claro": ORANGE, "naranja": DARK}[t]
        big = W * 0.62
        return [img(_url("modulo", forma="cuarto", w=round(big), h=round(big), color=col.lstrip("#")), W - big * 0.62, -big * 0.38,
                    big, big),
                img(_url("modulo", forma="circulo", w=round(W * 0.5), h=round(W * 0.5), color=col.lstrip("#")), -W * 0.2, H - W * 0.32,
                    W * 0.5, W * 0.5),
                img(_url("modulo", forma="triangulo", w=round(W * 0.16), h=round(W * 0.16), color=acento.lstrip("#")),
                    W * 0.3, H - W * 0.16, W * 0.16, W * 0.16, 0.9)]
    if kind == "patron":
        pats = brand.list_patrones()
        if not pats:
            return capas("modulos", W, H, bg)
        p = pats[sum(map(ord, bg)) % len(pats)]
        im = Image.open(brand.PATRONES_DIR / p)
        k = max(W / im.width, H / im.height)
        w, h = im.width * k, im.height * k
        return [img(f"/patron/{p}", (W - w) / 2, (H - h) / 2, w, h, {"oscuro": 0.38, "claro": 0.22, "naranja": 0.3}[t])]
    if kind == "ondas":
        col = {"oscuro": "#4a4a4a", "claro": "#dadada", "naranja": "#ff9050"}[t]
        h = H * 0.3
        return [img(_url("ondas", w=W, h=round(h), cols=7, g=max(3, round(4 * s)), color=col.lstrip("#")), 0, H - h - H * 0.04, W, h),
                img(_url("ondas", w=W, h=round(h * 0.6), cols=4, g=max(3, round(4 * s)), color=col.lstrip("#")), 0, H * 0.06, W,
                    h * 0.6, 0.6)]
    if kind == "grilla":
        col = {"oscuro": "#4d4d4d", "claro": "#d0d0d0", "naranja": "#ff9a5e"}[t]
        gap, r = round(46 * s), max(2, round(3 * s))
        cols, rows = W // gap + 1, H // gap + 1
        from .graphics import element_png
        im = element_png("puntos", cols=cols, rows=rows, gap=gap, r=r, color=col)
        return [img(_url("puntos", cols=cols, rows=rows, gap=gap, r=r, color=col.lstrip("#")),
                    (W - (im.width - 2 * r - 2)) / 2 - r - 1, (H - (im.height - 2 * r - 2)) / 2 - r - 1, im.width, im.height),
                *capas("brillo", W, H, bg)[:1]]
    if kind == "rayas":
        col = {"oscuro": ORANGE, "claro": ORANGE, "naranja": DARK}[t]
        h = round(26 * s)
        return [img(_url("textura", color=bg.lstrip("#"), w=W, h=H, forma="papel"), 0, 0, W, H),
                img(_url("rayas", w=W, h=h, color=col.lstrip("#")), 0, 0, W, h, 0.9),
                img(_url("rayas", w=W, h=h, color=col.lstrip("#")), 0, H - h, W, h, 0.9)]
    return []


def elegido(kind: str, plantilla: str, con_fotos: bool) -> str:
    if kind == "auto" or kind not in FONDOS:
        return "liso" if con_fotos and plantilla in ("dato", "agenda") else AUTO.get(plantilla, "liso")
    return kind


def aplicar(D, kind: str, plantilla: str, con_fotos: bool) -> None:
    """Pone el fondo debajo de todo lo que armó la plantilla (si ya traía textura, la reemplaza)."""
    k = elegido(kind, plantilla, con_fotos)
    if k == "liso":
        return
    nuevas = capas(k, D.W, D.H, D.bg)
    if not nuevas:
        return
    D.layers = [l for l in D.layers if not (l.get("name") == "Textura" and l.get("bloqueado"))]
    D.layers[:0] = nuevas
