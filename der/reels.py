"""Generador de reels: une varios videos (y fotos), agrega música genérica,
título opcional con la marca y cierra con el logo de DER.

Usa el ffmpeg que viene con el paquete imageio-ffmpeg (no hace falta instalarlo aparte).
"""
from __future__ import annotations

import random
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import brand, graphics, music
from .brand import DARK, LIGHT, ORANGE, WHITE

W, H, FPS = 1080, 1920, 30
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


@dataclass
class ReelOptions:
    title: str = ""
    subtitle: str = ""
    max_clip_seconds: float = 6.0     # recorta cada clip a este máximo (0 = sin límite)
    photo_seconds: float = 3.0        # duración de cada foto incluida en el reel
    transition: str = "fade"          # fade | slideleft | none ...
    transition_seconds: float = 0.4
    music: str = "auto:energico"      # auto:<estilo> | <archivo en brand/music> | none
    music_volume: float = 0.9
    keep_original_audio: bool = False
    watermark: bool = True
    outro_seconds: float = 3.0
    logo: str = "auto"                # auto | nombre de archivo en brand/logos
    log: list[str] = field(default_factory=list)


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
        raise RuntimeError(f"ffmpeg falló:\n{proc.stderr[-2500:]}")


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


# --- Gráficos de marca para el reel ------------------------------------------

def render_outro(path: Path, logo_choice: str = "auto") -> Path:
    img = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(img)
    m = 120
    graphics.corner_brackets(d, (m, 560, W - m, H - 560), 120, 12, ORANGE, "all")
    lg = brand.logo_sized("on_dark", width=560, choice=logo_choice)
    if lg.height > 520:
        lg = brand.logo_sized("on_dark", height=520, choice=logo_choice)
    img.paste(lg, ((W - lg.width) // 2, (H - lg.height) // 2 - 40), lg)
    f = brand.font("subtitle", 44)
    d.text((W / 2, H / 2 + lg.height / 2 + 60), brand.WEBSITE.upper(), font=f, fill=LIGHT, anchor="mt")
    d.rectangle([W / 2 - 45, H / 2 + lg.height / 2 + 140, W / 2 + 45, H / 2 + lg.height / 2 + 150], fill=ORANGE)
    img.save(path)
    return path


def render_title_overlay(path: Path, title: str, subtitle: str) -> Path:
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # degradé inferior para legibilidad
    shade = Image.new("RGB", (W, H), brand.DARK_RGB)
    mask = Image.new("L", (1, H), 0)
    for y in range(int(H * 0.45), H):
        mask.putpixel((0, y), int(210 * ((y - H * 0.45) / (H * 0.55)) ** 1.3))
    img.paste(shade, (0, 0), mask.resize((W, H)))
    d = ImageDraw.Draw(img)
    c = graphics.Content(title=title, subtitle=subtitle)
    m = 80
    block = graphics.measure_block(c, W - 2 * m, H * 0.3, 1.0, title_size=100)
    y = H - 420 - block
    graphics.accent_bar(d, m, y - 44, 1.0)
    graphics.text_block(d, m, y, W - 2 * m, H * 0.3, c, 1.0, WHITE, ORANGE, LIGHT, title_size=100)
    img.save(path)
    return path


def render_watermark(path: Path, logo_choice: str = "auto") -> Path:
    lg = brand.logo_sized("on_dark", width=150, choice=logo_choice)
    if lg.height > 150:
        lg = brand.logo_sized("on_dark", height=150, choice=logo_choice)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(lg, (W - 70 - lg.width, 200), lg)
    alpha = canvas.getchannel("A").point(lambda a: int(a * 0.85))
    canvas.putalpha(alpha)
    canvas.save(path)
    return path


# --- Pipeline ---------------------------------------------------------------

def _normalize_video(src: Path, dst: Path, opts: ReelOptions, info: dict) -> float:
    dur = info["duration"]
    if opts.max_clip_seconds and dur > opts.max_clip_seconds:
        # tomar el tramo central, que suele ser el más interesante
        start = (dur - opts.max_clip_seconds) / 2
        dur = opts.max_clip_seconds
    else:
        start = 0.0
    landscape = info["w"] > info["h"] * 1.05
    if landscape:
        # video horizontal: va completo al centro con el mismo video desenfocado de fondo
        vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"boxblur=40:4,eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},format=yuv420p,setsar=1[v]")
    else:
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"fps={FPS},format=yuv420p,setsar=1[v]")
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src)]
    if not (opts.keep_original_audio and info["audio"]):
        cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
        amap = "1:a"
    else:
        amap = "0:a"
    cmd += ["-filter_complex", f"[0:v]{vf}", "-map", "[v]", "-map", amap,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(dst)]
    _run(cmd, opts.log)
    return probe(dst)["duration"]


def _photo_clip(src: Path, dst: Path, opts: ReelOptions, tmp: Path) -> float:
    """Foto -> clip con zoom lento (Ken Burns)."""
    img = graphics.cover(graphics.load_photo(src), W * 2, H * 2)
    still = tmp / f"{dst.stem}.jpg"
    img.save(still, quality=95)
    frames = int(opts.photo_seconds * FPS)
    zin = random.choice([True, False])
    z = "min(1+0.0009*on,1.15)" if zin else "max(1.15-0.0009*on,1)"
    vf = (f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
          f"format=yuv420p,setsar=1")
    _run(["ffmpeg", "-y", "-i", str(still), "-f", "lavfi", "-t", f"{opts.photo_seconds}",
          "-i", "anullsrc=r=44100:cl=stereo", "-vf", vf, "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-ar", "44100",
          "-ac", "2", "-shortest", str(dst)], opts.log)
    return probe(dst)["duration"]


def _outro_clip(dst: Path, opts: ReelOptions, tmp: Path) -> float:
    png = render_outro(tmp / "outro.png", opts.logo)
    frames = int(opts.outro_seconds * FPS)
    vf = (f"scale={W * 2}:{H * 2},zoompan=z='min(1+0.0006*on,1.06)':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p,setsar=1")
    _run(["ffmpeg", "-y", "-i", str(png), "-f", "lavfi", "-t", f"{opts.outro_seconds}",
          "-i", "anullsrc=r=44100:cl=stereo", "-vf", vf, "-frames:v", str(frames),
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-c:a", "aac", "-ar", "44100",
          "-ac", "2", "-shortest", str(dst)], opts.log)
    return probe(dst)["duration"]


def _join(clips: list[tuple[Path, float]], opts: ReelOptions, overlays: list[tuple[Path, float, float]],
          dst: Path) -> float:
    """Une los clips con transiciones y aplica superposiciones (título, marca de agua)."""
    T = opts.transition_seconds if opts.transition != "none" else 0
    T = min(T, *(d / 2 for _, d in clips)) if clips else 0
    cmd = ["ffmpeg", "-y"]
    for p, _ in clips:
        cmd += ["-i", str(p)]
    for png, _, _ in overlays:
        cmd += ["-loop", "1", "-i", str(png)]
    parts = []
    v_prev, a_prev = "[0:v]", "[0:a]"
    acc = clips[0][1]
    for i in range(1, len(clips)):
        dur = clips[i][1]
        if T > 0:
            parts.append(f"{v_prev}[{i}:v]xfade=transition={opts.transition}:duration={T:.3f}:"
                         f"offset={acc - T:.3f}[v{i}]")
            parts.append(f"{a_prev}[{i}:a]acrossfade=d={T:.3f}[a{i}]")
            acc += dur - T
        else:
            parts.append(f"{v_prev}{a_prev}[{i}:v][{i}:a]concat=n=2:v=1:a=1[v{i}][a{i}]")
            acc += dur
        v_prev, a_prev = f"[v{i}]", f"[a{i}]"
    n = len(clips)
    for k, (_, t0, t1) in enumerate(overlays):
        idx = n + k
        t1 = min(t1, acc)
        fades = f"fade=in:st={t0:.2f}:d=0.4:alpha=1"
        if t1 < acc - 0.05:
            fades += f",fade=out:st={t1 - 0.4:.2f}:d=0.4:alpha=1"
        parts.append(f"[{idx}:v]format=rgba,{fades}[ov{k}]")
        parts.append(f"{v_prev}[ov{k}]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})':shortest=1[vo{k}]")
        v_prev = f"[vo{k}]"
    if not parts:
        parts.append("[0:v]null[vout]")
        v_prev = "[vout]"
    cmd += ["-filter_complex", ";".join(parts), "-map", v_prev, "-map", a_prev if a_prev != "[0:a]" else "0:a",
            "-t", f"{acc:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)]
    _run(cmd, opts.log)
    return acc


def _add_music(src: Path, duration: float, opts: ReelOptions, tmp: Path, dst: Path) -> None:
    choice = opts.music or "none"
    if choice == "none":
        shutil.copy(src, dst)
        return
    if choice.startswith("auto"):
        style = choice.split(":", 1)[1] if ":" in choice else "energico"
        track = music.generate(duration + 0.5, tmp / "music.wav", style, seed=random.randint(0, 10**6))
        loop = []
    else:
        track = brand.MUSIC_DIR / Path(choice).name
        if not track.exists():
            raise FileNotFoundError(f"No encuentro el tema {choice} en brand/music")
        loop = ["-stream_loop", "-1"]
    fade_st = max(0, duration - 1.8)
    vol = opts.music_volume * (0.35 if opts.keep_original_audio else 1.0)
    mix = (f"[1:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,volume={vol:.2f},"
           f"afade=in:st=0:d=0.3,afade=out:st={fade_st:.2f}:d=1.8[m];"
           f"[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    _run(["ffmpeg", "-y", "-i", str(src), *loop, "-i", str(track), "-filter_complex", mix,
          "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", "-t", f"{duration:.3f}", str(dst)], opts.log)


def generate(inputs: list[Path], out_path: Path, opts: ReelOptions) -> Path:
    if not inputs:
        raise ValueError("Subí al menos un video o foto.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="der-reel-", ignore_cleanup_errors=True) as td:
        tmp = Path(td)
        clips: list[tuple[Path, float]] = []
        for i, src in enumerate(inputs):
            dst = tmp / f"clip{i:02d}.mp4"
            if src.suffix.lower() in IMAGE_EXT:
                clips.append((dst, _photo_clip(src, dst, opts, tmp)))
            else:
                clips.append((dst, _normalize_video(src, dst, opts, probe(src))))

        overlays = []
        if opts.watermark:
            overlays.append((render_watermark(tmp / "wm.png", opts.logo), 0.0, 10_000.0))
        if opts.title or opts.subtitle:
            overlays.append((render_title_overlay(tmp / "title.png", opts.title, opts.subtitle), 0.2, 3.6))
        body = tmp / "body.mp4"
        body_dur = _join(clips, opts, overlays, body)

        outro = tmp / "outro.mp4"
        outro_dur = _outro_clip(outro, opts, tmp)
        full = tmp / "full.mp4"
        total = _join([(body, body_dur), (outro, outro_dur)],
                      ReelOptions(transition="fade", transition_seconds=0.5, log=opts.log), [], full)
        _add_music(full, total, opts, tmp, out_path)
    return out_path
