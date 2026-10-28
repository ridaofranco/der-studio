"""Carrusel mixto de Instagram: fotos y videos en el orden en que se suben.

- Fotos -> piezas de marca editables (misma plantilla para todas; el texto va en la primera foto).
- Videos -> MP4 en el formato del carrusel (4:5 o 1:1), con el logo chico arriba y el audio original.
  Los horizontales van completos sobre el mismo video desenfocado, como en los reels.

Instagram admite hasta 20 diapositivas y videos de hasta 60 segundos dentro de un carrusel.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from . import brand, graphics, reels

MAX_SLIDES = 20
MAX_VIDEO = 60.0
PHOTO_STYLES = {"impacto": "Foto a sangre", "marco": "Foto enmarcada", "banda": "Foto + banda naranja",
                "cinta": "Foto con cinta"}


def _watermark(path: Path, w: int, h: int, logo_choice: str) -> Path:
    s = w / 1080
    lg = brand.logo_sized("on_dark", width=int(140 * s), choice=logo_choice)
    if lg.height > 140 * s:
        lg = brand.logo_sized("on_dark", height=int(140 * s), choice=logo_choice)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(lg, (int(w - 60 * s - lg.width), int(60 * s)), lg)
    canvas.putalpha(canvas.getchannel("A").point(lambda a: int(a * 0.85)))
    canvas.save(path)
    return path


def video_slide(src: Path, dst: Path, fmt: str, max_seconds: float, logo_choice: str, tmp: Path,
                log: list[str]) -> float:
    """Un video del carrusel: recortado al formato, tramo central si es largo, logo chico arriba."""
    W, H = brand.FORMATS[fmt]
    info = reels.probe(src)
    dur = info["duration"]
    if dur <= 0:
        raise ValueError(f"No pude leer el video {src.name}.")
    limit = min(MAX_VIDEO, max_seconds or MAX_VIDEO)
    start = (dur - limit) / 2 if dur > limit else 0.0
    dur = min(dur, limit)
    wm = _watermark(tmp / f"wm-{fmt}.png", W, H, logo_choice)
    wide = info["w"] / max(1, info["h"]) > W / H * 1.15
    if wide:
        vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"boxblur=40:4,eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]")
    else:
        vf = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[v0]"
    vf += f";[v0][1:v]overlay=0:0,fps=30,format=yuv420p,setsar=1[v]"
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-loop", "1", "-i", str(wm)]
    if info["audio"]:
        maps = ["-map", "[v]", "-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]
    else:
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        maps = ["-map", "[v]", "-map", "2:a", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-filter_complex", vf, *maps, "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "20", "-movflags", "+faststart", "-shortest", str(dst)]
    reels._run(cmd, log)
    return dur


def generate(inputs: list[Path], out_dir: Path, fmt: str, style: str, content: graphics.Content,
             max_video: float, text_all: bool = False, log: list[str] | None = None) -> list[dict]:
    """Devuelve las diapositivas en orden: {"tipo": "foto", "diseno": {...}} o {"tipo": "video", "archivo": ...}."""
    import tempfile

    log = log if log is not None else []
    if not inputs:
        raise ValueError("Subí al menos una foto o un video.")
    if len(inputs) > MAX_SLIDES:
        raise ValueError(f"Instagram permite hasta {MAX_SLIDES} diapositivas por carrusel. Subiste {len(inputs)}.")
    if fmt not in ("post", "cuadrado"):
        fmt = "post"
    style = style if style in PHOTO_STYLES else "impacto"
    out_dir.mkdir(parents=True, exist_ok=True)
    slides, text_done = [], False
    with tempfile.TemporaryDirectory(prefix="der-carrusel-", ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        for i, src in enumerate(inputs, 1):
            name = f"DER-carrusel-{i:02d}"
            if src.suffix.lower() in reels.IMAGE_EXT:
                first = text_all or not text_done
                d = graphics.RENDERERS[style](fmt, [graphics.load_photo(src)], content, first=first)
                text_done = text_done or graphics._has_text(content)
                base_file = d.save_base(out_dir / name)
                data = {"name": name, "base_file": base_file, **d.to_dict()}
                (out_dir / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                slides.append({"tipo": "foto", "diseno": data})
            else:
                dst = out_dir / f"{name}.mp4"
                secs = video_slide(src, dst, fmt, max_video, content.logo, tmp, log)
                slides.append({"tipo": "video", "nombre": dst.name, "segundos": round(secs, 1)})
    return slides
