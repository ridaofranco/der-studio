"""Música genérica de fondo, sintetizada en el momento (sin derechos de autor).

Si preferís tus propios temas libres de derechos, dejalos en brand/music/
y elegilos desde la app.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100

STYLES = {
    #             bpm  kick  hats  pad  pluck  bass
    "energico":   (124, True, True, 0.18, 0.22, 0.30),
    "corporativo": (108, True, True, 0.22, 0.30, 0.22),
    "suave":      (92, False, True, 0.30, 0.25, 0.15),
}

# Progresiones (grados en semitonos desde la tónica, acordes de 3 notas)
PROGRESSIONS = [
    [(0, 4, 7), (-3, 0, 4), (5, 9, 12), (7, 11, 14)],   # I vi IV V
    [(-3, 0, 4), (5, 9, 12), (0, 4, 7), (7, 11, 14)],   # vi IV I V
    [(0, 4, 7), (7, 11, 14), (-3, 0, 4), (5, 9, 12)],   # I V vi IV
]


def _hz(semitones: float, root: float) -> float:
    return root * 2 ** (semitones / 12)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e = np.ones(n)
    e[:min(a, n)] = np.linspace(0, 1, min(a, n))
    if r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _soft_lowpass(x: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return x
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")


def generate(duration: float, out_path: Path, style: str = "energico", seed: int | None = None) -> Path:
    rng = np.random.default_rng(seed)
    bpm, use_kick, use_hats, pad_gain, pluck_gain, bass_gain = STYLES.get(style, STYLES["energico"])
    beat = 60 / bpm
    bar = beat * 4
    root = _hz(rng.integers(-5, 3), 220.0)  # tónica entre Mi y Do
    prog = PROGRESSIONS[rng.integers(len(PROGRESSIONS))]

    total = int((duration + bar) * SR)
    L = np.zeros(total)
    R = np.zeros(total)
    t_bar = np.arange(int(bar * SR)) / SR

    n_bars = int(np.ceil(duration / bar)) + 1
    arp_pattern = rng.permutation([0, 1, 2, 1, 2, 0, 2, 1])
    for b in range(n_bars):
        chord = prog[b % len(prog)]
        start = int(b * bar * SR)
        seg = slice(start, min(total, start + len(t_bar)))
        n = seg.stop - seg.start
        if n <= 0:
            break
        tt = t_bar[:n]
        # Pad: sierra suavizada + leve desafinación estéreo
        pad_l = np.zeros(n)
        pad_r = np.zeros(n)
        for st in chord:
            f = _hz(st, root)
            for det, side in ((0.997, pad_l), (1.003, pad_r)):
                side += 2 * ((tt * f * det) % 1) - 1
        env = _env(n, 0.35, 0.4)
        pad_l = _soft_lowpass(pad_l, 18) * env / len(chord)
        pad_r = _soft_lowpass(pad_r, 18) * env / len(chord)
        L[seg] += pad_l * pad_gain
        R[seg] += pad_r * pad_gain

        # Bajo: fundamental en negras, una octava abajo
        f_bass = _hz(chord[0] - 12, root)
        for q in range(4):
            s0 = int(q * beat * SR)
            m = min(int(beat * SR * 0.9), n - s0)
            if m <= 0:
                continue
            tb = np.arange(m) / SR
            note = (np.sin(2 * np.pi * f_bass * tb) + 0.3 * np.sin(4 * np.pi * f_bass * tb)) * _env(m, 0.005, 0.12)
            L[start + s0:start + s0 + m] += note * bass_gain
            R[start + s0:start + s0 + m] += note * bass_gain

        # Pluck arpegiado en corcheas
        for e in range(8):
            s0 = int(e * beat / 2 * SR)
            m = min(int(beat / 2 * SR), n - s0)
            if m <= 0:
                continue
            tp = np.arange(m) / SR
            f = _hz(chord[arp_pattern[e]] + 12, root)
            note = np.sin(2 * np.pi * f * tp) * np.exp(-tp * 9)
            note += 0.25 * np.sin(4 * np.pi * f * tp) * np.exp(-tp * 14)
            pan = 0.35 if e % 2 else 0.65
            L[start + s0:start + s0 + m] += note * pluck_gain * (1 - pan) * 2
            R[start + s0:start + s0 + m] += note * pluck_gain * pan * 2

    # Batería
    n_beats = int(duration / beat) + 4
    kick_len = int(0.35 * SR)
    tk = np.arange(kick_len) / SR
    kick = np.sin(2 * np.pi * (45 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 9)
    hat_len = int(0.05 * SR)
    hat = np.diff(rng.standard_normal(hat_len + 1)) * np.exp(-np.arange(hat_len) / SR * 90) * 0.35
    clap_len = int(0.18 * SR)
    clap = rng.standard_normal(clap_len) * np.exp(-np.arange(clap_len) / SR * 22) * 0.25
    clap = _soft_lowpass(clap, 3)
    for i in range(n_beats):
        s0 = int(i * beat * SR)
        if use_kick and s0 + kick_len < total:
            L[s0:s0 + kick_len] += kick * 0.75
            R[s0:s0 + kick_len] += kick * 0.75
            if i % 2 == 1 and s0 + clap_len < total:
                L[s0:s0 + clap_len] += clap
                R[s0:s0 + clap_len] += clap
        if use_hats:
            h0 = int((i + 0.5) * beat * SR)
            if h0 + hat_len < total:
                L[h0:h0 + hat_len] += hat * 0.8
                R[h0:h0 + hat_len] += hat

    n_out = int(duration * SR)
    mix = np.stack([L[:n_out], R[:n_out]], axis=1)
    mix = np.tanh(mix * 1.2)  # saturación suave / limitador
    fade = int(min(2.0, duration / 4) * SR)
    mix[:int(0.3 * SR)] *= np.linspace(0, 1, int(0.3 * SR))[:, None]
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    mix /= max(1e-9, np.abs(mix).max()) / 0.89

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
    return out_path
