"""Descripción (caption) para posteos y reels con Gemini, en el plan gratis.

La clave se toma de GEMINI_API_KEY o del archivo .claves/gemini (fuera del repo). Si un modelo
gratis está saturado (429/503) o no existe más (404), se prueba el siguiente: nunca se pasa a
una API paga.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAVE_FILE = ROOT / ".claves" / "gemini"
MODELOS = ("gemini-flash-lite-latest", "gemini-3.1-flash-lite", "gemini-flash-latest")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

LARGOS = {"corta": "2 o 3 renglones", "media": "un párrafo corto y un segundo párrafo de 1 o 2 renglones",
          "larga": "3 párrafos cortos"}
REDES = {"instagram": "Instagram", "linkedin": "LinkedIn", "tiktok": "TikTok"}

REGLAS = """Sos Franco, director de SOMOS DER, una productora de eventos de Buenos Aires.
Escribís la descripción de una publicación de {red} de DER ({formato}).

Cómo escribe Franco:
- Como se lo contaría a un colega: «nos tocó», «la verdad», «de ahí no paramos más». Primera persona del plural.
- Español rioplatense (vos), simple y directo. Datos concretos sueltos en la frase, no en viñetas.
- NUNCA: frases de efecto, aforismos, contrastes armados («no es X, es Y»), moralejas, molde «Qué hicimos:» + viñetas,
  guion largo (—), signos de apertura ¿ ¡, emojis decorativos (como mucho 🧡 o 🙌, una vez).
- DER es una PRODUCTORA, nunca «agencia».
- No inventes nada: ni cifras, ni clientes, ni lugares, ni fechas, ni roles que no estén en el contexto.
  Si falta un dato, no lo pongas. No digas que DER organizó o produjo el evento completo si el contexto no lo dice.
- Cerrá simple: agradecer al equipo, o «Si tenés algo así, hablemos» (sin links inventados).

Largo: {largo}.
{idioma}
{hashtags}
Devolvé SOLO el texto de la descripción, listo para pegar. Sin comillas, sin títulos, sin explicaciones."""


def clave() -> str:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if not k and CLAVE_FILE.exists():
        k = CLAVE_FILE.read_text(encoding="utf-8").strip()
    return k


def guardar_clave(k: str) -> None:
    CLAVE_FILE.parent.mkdir(exist_ok=True)
    CLAVE_FILE.write_text(k.strip(), encoding="utf-8")
    CLAVE_FILE.chmod(0o600)


def contexto_lote(lote: Path) -> list[str]:
    """Los textos que ya tiene lo generado (títulos de las piezas, textos del reel), sin repetir."""
    vistos: list[str] = []
    def sumar(t):
        t = re.sub(r"\s+", " ", str(t or "")).strip()
        if t and t.lower() not in (v.lower() for v in vistos) and t.lower() not in ("somosder.ar", "somos der"):
            vistos.append(t)
    proyecto = lote / "proyecto.json"
    if proyecto.exists():
        for t in json.loads(proyecto.read_text(encoding="utf-8")).get("textos", []):
            sumar(t.get("texto"))
    for j in sorted(lote.glob("DER-*.json")):
        try:
            d = json.loads(j.read_text(encoding="utf-8"))
        except ValueError:
            continue
        objs = (d.get("fabric") or {}).get("objects")
        for o in objs if objs else d.get("layers", []):
            if o.get("type") in ("text", "textbox", "i-text", "curvedText"):
                sumar(o.get("text"))
    return vistos[:12]


def _pedir(modelo: str, k: str, prompt: str) -> str:
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.9, "maxOutputTokens": 900}}).encode()
    req = urllib.request.Request(URL.format(m=modelo), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": k})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read())
    if isinstance(data, list):  # el modelo liviano a veces responde dentro de una lista
        data = data[0] if data else {}
    partes = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in partes).strip()


def _limpiar(t: str) -> str:
    t = t.strip().strip('"«»').strip()
    t = t.replace(" — ", ", ").replace("—", ", ").replace("¿", "").replace("¡", "")
    return re.sub(r"\n{3,}", "\n\n", t)


# Servicio der-textos (solo en el servidor de DER, 127.0.0.1:5061): escribe con Claude, con la voz de Franco
# (voz.md) y con el expediente del evento que busca en trabajo/proyectos-historial. Si no está (por ejemplo en
# una compu sin ese servicio) o falla, se usa Gemini como respaldo. NO sacar: es lo que pidió Franco el 04/11/2026.
DER_TEXTOS = os.environ.get("DER_TEXTOS_URL", "http://127.0.0.1:5061/")


def _claude(tema, textos, red, formato, largo, idioma, hashtags, anterior):
    body = json.dumps({"tema": tema, "textos": textos, "red": red, "formato": formato, "largo": largo,
                       "idioma": idioma, "hashtags": hashtags, "anterior": anterior}).encode()
    req = urllib.request.Request(DER_TEXTOS, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=170) as r:
        data = json.loads(r.read().decode())
    t = (data.get("texto") or "").strip()
    if not t:
        raise RuntimeError("der-textos sin texto")
    print("descripcion: claude, expediente", data.get("expediente"), flush=True)
    return t


def con_claude() -> bool:
    """True si el servicio der-textos responde (entonces no hace falta la clave de Gemini)."""
    try:
        urllib.request.urlopen(urllib.request.Request(DER_TEXTOS, method="GET"), timeout=2)
    except urllib.error.HTTPError:
        return True  # responde, aunque sea con error de método
    except Exception:  # noqa: BLE001
        return False
    return True


def generar(tema: str, textos: list[str], red: str = "instagram", formato: str = "posteo",
            largo: str = "media", idioma: str = "es", hashtags: bool = True, anterior: str = "") -> str:
    try:
        return _limpiar(_claude(tema, textos, red, formato, largo, idioma, hashtags, anterior))
    except Exception as e:  # noqa: BLE001  (sin servicio, timeout o error de Claude: respaldo con Gemini)
        print(f"descripcion: claude no disponible ({type(e).__name__}: {str(e)[:120]}), uso Gemini", flush=True)
    if red == "todas":
        red = "instagram"
    k = clave()
    if not k:
        raise RuntimeError("SIN_CLAVE")
    prompt = REGLAS.format(
        red=REDES.get(red, "Instagram"), formato=formato, largo=LARGOS.get(largo, LARGOS["media"]),
        idioma="Escribila en inglés neutro, con el mismo tono cercano." if idioma == "en" else "Escribila en español.",
        hashtags="Al final, en un renglón aparte, 4 a 6 hashtags relevantes (siempre #SomosDER)." if hashtags
        else "Sin hashtags.")
    prompt += "\n\nDe qué se trata (lo escribió Franco):\n" + (tema.strip() or "(no escribió nada, usá los textos de las piezas)")
    if textos:
        prompt += "\n\nTextos que ya aparecen en las piezas:\n- " + "\n- ".join(textos)
    if anterior:
        prompt += "\n\nYa le mostraste esta versión y quiere OTRA distinta (otra forma de arrancar y otra estructura):\n" + anterior
    errores = []
    for m in MODELOS:
        try:
            t = _pedir(m, k, prompt)
            if t:
                return _limpiar(t)
            errores.append(f"{m}: vacío")
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                raise RuntimeError("CLAVE_MALA") from e
            errores.append(f"{m}: {e.code}")
        except Exception as e:  # noqa: BLE001  (timeout, red)
            errores.append(f"{m}: {type(e).__name__}")
    raise RuntimeError("Gemini está saturado ahora (plan gratis). Probá de nuevo en un minuto. [" + ", ".join(errores) + "]")
