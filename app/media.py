"""Recursos audiovisuales: tarjetas visuales, subtítulos, miniaturas y búsqueda
de material con licencia en repositorios libres.

Solo se consultan servicios gratuitos y sin clave (Openverse, Wikimedia Commons,
Internet Archive) y siempre se guarda autor, licencia y fecha de consulta.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
import textwrap
import time
import urllib.parse
import urllib.request
import zlib
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_CARD_ERROR = ""

FONT_CANDIDATES = [
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

USER_AGENT = "AITuberLibre/1.0 (proyecto local sin animo de lucro; contacto: usuario local)"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


def font_path() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe_duration(path: str | Path) -> float:
    proc = run(
        [
            ffprobe(), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        timeout=60,
    )
    try:
        return float((proc.stdout or b"0").decode().strip() or 0)
    except ValueError:
        return 0.0


def probe_video(path: str | Path) -> dict:
    proc = run(
        [
            ffprobe(), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate",
            "-show_entries", "format=duration,size",
            "-of", "json", str(path),
        ],
        timeout=60,
    )
    try:
        data = json.loads(proc.stdout.decode() or "{}")
    except json.JSONDecodeError:
        return {}
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "codec": stream.get("codec_name"),
        "fps": stream.get("r_frame_rate"),
        "duration": float(fmt.get("duration") or 0),
        "bytes": int(fmt.get("size") or 0),
    }


def wrap(text: str, width: int, max_lines: int = 3) -> list[str]:
    lines: list[str] = []
    for paragraph in (text or "").split("\n"):
        wrapped = textwrap.wrap(paragraph.strip(), width=width) or [""]
        lines.extend(wrapped)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + [lines[max_lines - 1][: max(0, width - 1)] + "…"]
    return lines


def caption_chunks(text: str, duration: float, max_words: int, max_chars: int, max_lines: int = 3) -> list[dict]:
    """Divide la narración en subtítulos con tiempos proporcionales a las palabras.

    Es una aproximación honesta: no hay alineación forzada (Whisper) en este
    entorno, por lo que el tiempo se reparte por cantidad de palabras.
    """
    words = (text or "").split()
    if not words:
        return []
    chunks: list[list[str]] = []
    current: list[str] = []
    for word in words:
        candidate = current + [word]
        if len(current) >= max_words or len(" ".join(candidate)) > max_chars:
            if current:
                chunks.append(current)
            current = [word]
        else:
            current = candidate
    if current:
        chunks.append(current)

    total_words = sum(len(c) for c in chunks) or 1
    chunks_out: list[dict] = []
    cursor = 0.0
    for i, chunk in enumerate(chunks):
        share = len(chunk) / total_words
        start = cursor
        end = duration if i == len(chunks) - 1 else cursor + share * duration
        cursor = end
        chunks_out.append(
            {
                "start": round(start, 2),
                "end": round(max(start + 0.4, end), 2),
                "text": " ".join(chunk),
                "lines": wrap(" ".join(chunk), max_chars // max(1, max_lines - 1) if max_lines > 1 else max_chars, max_lines),
            }
        )
    return chunks_out


def srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def vtt_time(seconds: float) -> str:
    return srt_time(seconds).replace(",", ".")


def build_srt(cues: list[dict]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['text']}\n")
    return "\n".join(blocks)


def build_vtt(cues: list[dict]) -> str:
    blocks = ["WEBVTT", ""]
    for i, cue in enumerate(cues, start=1):
        blocks.append(f"{i}\n{vtt_time(cue['start'])} --> {vtt_time(cue['end'])}\n{cue['text']}\n")
    return "\n".join(blocks)


PALETTES = {
    "documental": ["0x0d1b2a", "0x1b263b", "0x102a43", "0x0b132b"],
    "short": ["0x111827", "0x1f2937", "0x0f172a"],
}


def make_card(out_png: Path, title: str, subtitle: str, width: int, height: int, kind: str = "documental") -> Path:
    """Tarjeta visual generada localmente (se etiqueta como tal, no es foto histórica).

    La base se dibuja en PNG puro (sin FFmpeg) y el texto se superpone con
    drawtext sobre esa imagen. Así la tarjeta nunca depende de `-f lavfi` y, si
    el binario de FFmpeg no puede dibujar texto, queda una tarjeta de color
    válida en lugar de romper el render.
    """
    global _CARD_ERROR
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    font = font_path()
    palette = PALETTES.get(kind, PALETTES["documental"])
    color = palette[abs(hash(title)) % len(palette)]
    base = out_png.with_name(f"{out_png.stem}_base.png")
    _png_solid(base, width, height, _rgb(color))

    title_size = max(34, int(width * 0.045))
    sub_size = max(20, int(width * 0.022))
    title_lines = wrap(title, max(12, int(width / (title_size * 0.58))), 2)
    sub_lines = wrap(subtitle, max(16, int(width / (sub_size * 0.56))), 2)

    filters: list[str] = []
    if font:
        filters.append(
            f"drawbox=x=0:y=ih*0.30:w=iw:h=6:color=0x7dd3fc@0.9:t=fill"
        )
        y = int(height * 0.38)
        for line in title_lines:
            filters.append(
                f"drawtext=fontfile={font}:text='{_esc(line)}':fontcolor=white:fontsize={title_size}"
                f":x=(w-text_w)/2:y={y}"
            )
            y += int(title_size * 1.25)
        y = int(height * 0.72)
        for line in sub_lines:
            filters.append(
                f"drawtext=fontfile={font}:text='{_esc(line)}':fontcolor=0x94a3b8:fontsize={sub_size}"
                f":x=(w-text_w)/2:y={y}"
            )
            y += int(sub_size * 1.4)

    try:
        if filters:
            cmd = [
                ffmpeg(), "-y", "-i", str(base),
                "-vf", ",".join(filters), "-frames:v", "1", str(out_png),
            ]
            proc = run(cmd, timeout=120)
            if not out_png.exists() or out_png.stat().st_size == 0:
                raise RuntimeError(
                    "ffmpeg no generó la imagen: "
                    + (proc.stderr or b"").decode("utf-8", "ignore")[-400:]
                )
        else:
            shutil.copyfile(base, out_png)
    except Exception as exc:  # respaldo: tarjeta de color válida sin texto
        _CARD_ERROR = str(exc)[-400:]
        shutil.copyfile(base, out_png)
    finally:
        base.unlink(missing_ok=True)

    if not out_png.exists():
        raise RuntimeError(f"No se pudo generar la tarjeta visual: {_CARD_ERROR}")
    return out_png


def make_fruit_card(
    out_png: Path,
    title: str,
    cast_text: str,
    width: int,
    height: int,
) -> Path:
    """Ilustración procedural original con el mismo elenco frutal en cada escena."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (250, 241, 226))
    draw = ImageDraw.Draw(image)

    scale = max(0.5, min(width / 720, height / 1280))
    def font(size: int):
        path = font_path()
        try:
            return ImageFont.truetype(path, max(10, int(size * scale))) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    title_font = font(42)
    name_font = font(27)
    role_font = font(19)
    small_font = font(18)

    # Fondo tipo telenovela, dibujado localmente y sin recursos externos.
    draw.rounded_rectangle(
        (int(width * .035), int(height * .025), int(width * .965), int(height * .975)),
        radius=int(32 * scale), fill=(255, 250, 241), outline=(226, 173, 119), width=max(2, int(4 * scale)),
    )
    title_text = (title or "Un secreto entre frutas").strip()[:72]
    title_lines = textwrap.wrap(title_text, width=max(12, int(width / (42 * scale * .58))), break_long_words=True)[:2]
    title_y = height * .055
    for line in title_lines:
        title_box = draw.textbbox((0, 0), line, font=title_font)
        draw.text(((width - (title_box[2] - title_box[0])) / 2, title_y), line, font=title_font, fill=(75, 45, 58))
        title_y += int(52 * scale)

    raw_cast = [part.strip() for part in re.split(r"[,;\n]+", cast_text or "") if part.strip()]
    cast = []
    for part in raw_cast:
        name = re.sub(r"\s*\([^)]*\)", "", part).strip()
        role_match = re.search(r"\(([^)]*)\)", part)
        role = role_match.group(1).strip() if role_match else ""
        if name and all(item["name"].casefold() != name.casefold() for item in cast):
            cast.append({"name": name[:24], "role": role[:28]})
        if len(cast) >= 4:
            break
    if not cast:
        cast = [
            {"name": "Manzana", "role": "protagonista"},
            {"name": "Banana", "role": "pareja"},
            {"name": "Pera", "role": "rival"},
        ]

    styles = [
        ("manzana", (213, 65, 75)),
        ("banana", (248, 202, 58)),
        ("pera", (137, 190, 105)),
        ("naranja", (243, 145, 55)),
        ("frutilla", (224, 67, 92)),
        ("uva", (135, 95, 170)),
        ("limon", (237, 214, 75)),
        ("durazno", (241, 153, 127)),
        ("kiwi", (128, 166, 92)),
        ("mango", (241, 164, 54)),
        ("cereza", (174, 48, 67)),
        ("anana", (222, 178, 65)),
        ("piña", (222, 178, 65)),
        ("sandia", (95, 166, 104)),
        ("palta", (116, 157, 94)),
    ]
    count = len(cast)
    center_y = int(height * .47)
    spacing = width / (count + 1)
    radius = int(min(width * .13, height * .115))
    for index, character in enumerate(cast):
        name = character["name"]
        lowered = name.casefold()
        color = next((value for key, value in styles if key in lowered), (231, 119, 91))
        cx = int(spacing * (index + 1))
        cy = center_y
        # Sombra y cuerpo de fruta.
        draw.ellipse((cx - radius * .82, cy + radius * .72, cx + radius * .82, cy + radius * .96), fill=(222, 207, 187))
        if "pera" in lowered:
            body = [
                (cx, cy - radius), (cx + radius * .55, cy - radius * .35),
                (cx + radius * .75, cy + radius * .45), (cx + radius * .45, cy + radius * .9),
                (cx - radius * .45, cy + radius * .9), (cx - radius * .75, cy + radius * .45),
                (cx - radius * .55, cy - radius * .35),
            ]
            draw.polygon(body, fill=color, outline=(110, 88, 69))
        elif "banana" in lowered:
            body = [
                (cx - radius * .8, cy - radius * .45), (cx - radius * .35, cy - radius * .82),
                (cx + radius * .55, cy - radius * .52), (cx + radius * .8, cy + radius * .35),
                (cx + radius * .25, cy + radius * .78), (cx - radius * .35, cy + radius * .35),
            ]
            draw.polygon(body, fill=color, outline=(130, 99, 44))
        elif "frutilla" in lowered or "fresa" in lowered:
            body = [
                (cx - radius * .7, cy - radius * .35), (cx - radius * .35, cy - radius * .8),
                (cx + radius * .35, cy - radius * .8), (cx + radius * .7, cy - radius * .35),
                (cx + radius * .45, cy + radius * .5), (cx, cy + radius),
                (cx - radius * .45, cy + radius * .5),
            ]
            draw.polygon(body, fill=color, outline=(130, 65, 65))
        else:
            draw.ellipse((cx - radius * .72, cy - radius * .85, cx + radius * .72, cy + radius * .85), fill=color, outline=(110, 78, 66), width=max(2, int(3 * scale)))
        # Tallo y hoja.
        draw.line((cx, cy - radius * .78, cx + radius * .08, cy - radius * 1.08), fill=(91, 105, 62), width=max(3, int(6 * scale)))
        draw.ellipse((cx + radius * .02, cy - radius * 1.12, cx + radius * .52, cy - radius * .82), fill=(91, 157, 91), outline=(66, 113, 70))
        # Rostro sencillo y expresivo.
        eye_y = cy - radius * .08
        eye_dx = radius * .25
        eye_r = max(3, int(radius * .075))
        for eye_x in (cx - eye_dx, cx + eye_dx):
            draw.ellipse((eye_x - eye_r, eye_y - eye_r, eye_x + eye_r, eye_y + eye_r), fill=(54, 44, 48))
            draw.ellipse((eye_x - eye_r * .35, eye_y - eye_r * .55, eye_x, eye_y - eye_r * .1), fill=(255, 255, 255))
        mouth_box = (cx - radius * .2, cy + radius * .02, cx + radius * .2, cy + radius * .34)
        draw.arc(mouth_box, start=10, end=170, fill=(92, 42, 53), width=max(2, int(4 * scale)))

        name_box = draw.textbbox((0, 0), name, font=name_font)
        draw.text((cx - (name_box[2] - name_box[0]) / 2, cy + radius * 1.12), name, font=name_font, fill=(75, 45, 58))
        if character["role"]:
            role = character["role"]
            role_box = draw.textbbox((0, 0), role, font=role_font)
            draw.text((cx - (role_box[2] - role_box[0]) / 2, cy + radius * 1.12 + name_box[3] + 8), role, font=role_font, fill=(123, 91, 89))

    footer = "FRUTINOVELA  ·  HISTORIA ORIGINAL"
    footer_box = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(((width - (footer_box[2] - footer_box[0])) / 2, height * .89), footer, font=small_font, fill=(150, 103, 91))
    image.save(out_png, format="PNG", optimize=True)
    return out_png


def _rgb(color: str) -> tuple[int, int, int]:
    value = int(color, 16) if color.lower().startswith("0x") else int(color.lstrip("#"), 16)
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def _png_solid(out_png: Path, width: int, height: int, rgb: tuple[int, int, int]) -> Path:
    """PNG de un color sólido escrito con la librería estándar (sin FFmpeg)."""
    r, g, b = rgb
    row = b"\x00" + bytes((r, g, b)) * width
    raw = row * height

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    out_png.write_bytes(png)
    return out_png


@lru_cache(maxsize=1)
def capabilities() -> dict:
    """Qué puede hacer realmente el FFmpeg instalado (se calcula una vez)."""

    def probe(args: list[str]) -> bool:
        try:
            proc = run([ffmpeg(), "-hide_banner", *args], timeout=30)
        except Exception:
            return False
        text = ((proc.stdout or b"") + (proc.stderr or b"")).decode("utf-8", "ignore").lower()
        return bool(text) and "unknown" not in text and "not recognized" not in text

    info: dict = {
        "encoder_png": probe(["-h", "encoder=png"]),
        "filtro_drawtext": probe(["-h", "filter=drawtext"]),
        "filtro_drawbox": probe(["-h", "filter=drawbox"]),
        "encoder_libx264": probe(["-h", "encoder=libx264"]),
        "demuxer_lavfi": probe(["-h", "demuxer=lavfi"]),
    }
    with tempfile.TemporaryDirectory() as tmp:
        card = Path(tmp) / "card.png"
        try:
            make_card(card, "prueba de capacidad", "diagnóstico", 320, 180, "short")
            info["tarjeta_visual"] = card.exists() and card.stat().st_size > 100
        except Exception as exc:
            info["tarjeta_visual"] = False
            info["error_tarjeta"] = str(exc)[-300:]
    if _CARD_ERROR:
        info["ultimo_error_tarjeta"] = _CARD_ERROR
    return info


def _esc(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )


def make_thumbnail(source: Path, out_jpg: Path, title: str, width: int, height: int) -> Path:
    out_jpg = Path(out_jpg)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    font = font_path()
    size = max(40, int(width * 0.075))
    lines = wrap(title, max(12, int(width / (size * 0.56))), 3)
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "eq=brightness=-0.06:saturation=1.15",
    ]
    if font:
        y = int(height * 0.62)
        for line in lines:
            filters.append(
                f"drawtext=fontfile={font}:text='{_esc(line)}':fontcolor=white:fontsize={size}"
                f":box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y={y}"
            )
            y += int(size * 1.2)
    cmd = [
        ffmpeg(), "-y", "-ss", "1", "-i", str(source), "-vf", ",".join(filters),
        "-frames:v", "1", "-q:v", "3", str(out_jpg),
    ]
    proc = run(cmd, timeout=180)
    if not out_jpg.exists():
        # Fuente sin pista de vídeo suficiente: se genera tarjeta de respaldo.
        make_card(out_jpg.with_suffix(".png"), title, "miniatura generada", width, height)
        shutil.move(str(out_jpg.with_suffix(".png")), str(out_jpg))
    return out_jpg


# --------------------------------------------------------------------------- #
# Búsqueda de material con licencia (servicios gratuitos, sin clave)
# --------------------------------------------------------------------------- #

def _get_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


@lru_cache(maxsize=512)
def search_openverse(query: str, limit: int = 12) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "page_size": limit,
            "license_type": "commercial",
            "mature": "false",
        }
    )
    data = _get_json(f"https://api.openverse.org/v1/images/?{params}")
    out = []
    for item in (data.get("results") or [])[:limit]:
        out.append(
            {
                "provider": "Openverse",
                "title": (item.get("title") or "Sin título")[:160],
                "page": item.get("foreign_landing_url") or "",
                "url": item.get("url") or "",
                "thumb": item.get("thumbnail") or item.get("url") or "",
                "author": item.get("creator") or "desconocido",
                "license": f"CC {item.get('license', '').upper()} {item.get('license_version', '')}".strip(),
                "license_url": item.get("license_url") or "",
            }
        )
    return out


@lru_cache(maxsize=512)
def search_wikimedia(query: str, limit: int = 12) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrlimit": limit,
            "gsrnamespace": 6,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 1280,
        }
    )
    data = _get_json(f"https://commons.wikimedia.org/w/api.php?{params}")
    pages = ((data.get("query") or {}).get("pages") or {}).values()
    out = []
    for page in list(pages)[:limit]:
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = (meta.get("LicenseShortName") or {}).get("value", "ver licencia")
        author = (meta.get("Artist") or {}).get("value", "desconocido")
        author = _strip_html(author)[:120]
        out.append(
            {
                "provider": "Wikimedia Commons",
                "title": (page.get("title") or "").replace("File:", "")[:160],
                "page": info.get("descriptionurl") or "",
                "url": info.get("url") or "",
                "thumb": info.get("thumburl") or info.get("url") or "",
                "author": author or "desconocido",
                "license": license_name,
                "license_url": (meta.get("LicenseUrl") or {}).get("value", ""),
            }
        )
    return out


@lru_cache(maxsize=512)
def search_archive(query: str, limit: int = 10) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "fl[]": ["identifier", "title", "year", "licenseurl", "mediatype"],
            "rows": limit,
            "page": 1,
            "output": "json",
        },
        doseq=True,
    )
    data = _get_json(f"https://archive.org/advancedsearch.php?{params}")
    docs = ((data.get("response") or {}).get("docs") or [])[:limit]
    out = []
    for doc in docs:
        ident = doc.get("identifier") or ""
        out.append(
            {
                "provider": "Internet Archive",
                "title": (doc.get("title") or ident)[:160] if isinstance(doc.get("title"), str) else ident,
                "page": f"https://archive.org/details/{ident}",
                "url": "",
                "thumb": f"https://archive.org/services/img/{ident}",
                "author": "Internet Archive",
                "license": "ver licencia del ítem" if not doc.get("licenseurl") else doc["licenseurl"],
                "license_url": doc.get("licenseurl") or "",
            }
        )
    return out


def _strip_html(text: str) -> str:
    out, inside = [], False
    for ch in text or "":
        if ch == "<":
            inside = True
        elif ch == ">":
            inside = False
        elif not inside:
            out.append(ch)
    return " ".join("".join(out).split())


def search_media(query: str, provider: str = "all") -> dict:
    """Busca material con licencia; devuelve resultados y errores por proveedor."""
    results: list[dict] = []
    errors: dict[str, str] = {}
    providers = {
        "openverse": search_openverse,
        "wikimedia": search_wikimedia,
        "archive": search_archive,
    }
    selected = providers if provider in ("all", "", None) else {provider: providers.get(provider)}
    for name, fn in selected.items():
        if not fn:
            continue
        try:
            results.extend(fn(query))
        except Exception as exc:  # red bloqueada, límite de tasa, etc.
            errors[name] = f"{type(exc).__name__}: {exc}"
    return {
        "query": query,
        "results": results,
        "errors": errors,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "disclaimer": "Verificá la licencia en el enlace original antes de usar el material. "
        "Estos buscadores son gratuitos y sin clave; si el entorno no tiene salida a internet, "
        "la app sigue funcionando con tarjetas visuales generadas localmente.",
    }


def download_asset(url: str, out_dir: Path, max_bytes: int = MAX_DOWNLOAD_BYTES) -> dict:
    """Descarga un recurso a la biblioteca local con validación básica."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Solo se permiten URLs http/https")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        content_type = resp.headers.get("Content-Type", "")
        if not content_type.startswith(("image/", "video/", "audio/")):
            raise ValueError(f"Tipo de contenido no permitido: {content_type}")
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("El recurso supera el límite de 25 MB")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(
        content_type.split(";")[0], ".bin"
    )
    digest = hashlib.sha1(data).hexdigest()[:12]
    target = out_dir / f"{digest}{ext}"
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data), "sha1": digest, "content_type": content_type}


def ensure_music_bed(bed_id: str) -> Path:
    """Genera una cama musical local con FFmpeg (una sola vez, sin descargas)."""
    from . import db as _db
    from . import options as _options

    bed = next((m for m in _options.MUSIC_BEDS if m["id"] == bed_id), _options.MUSIC_BEDS[0])
    out_dir = _db.MUSIC_DIR / "beds"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{bed['id']}.wav"
    if out.exists() and out.stat().st_size > 20000:
        return out
    inputs: list[str] = []
    for freq in bed["freqs"]:
        inputs += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=45:sample_rate=44100"]
    graph = f"amix=inputs={len(bed['freqs'])},{bed['chain']}"
    proc = subprocess.run(
        [ffmpeg(), "-y", *inputs, "-filter_complex", graph, "-c:a", "pcm_s16le", str(out)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"No se pudo generar la música local: {proc.stderr[-300:]}")
    return out
