"""Recursos audiovisuales: tarjetas visuales, subtítulos, miniaturas y búsqueda
de material con licencia en repositorios libres.

Solo se consultan servicios gratuitos y sin clave (Openverse, Wikimedia Commons,
Internet Archive) y siempre se guarda autor, licencia y fecha de consulta.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import textwrap
import time
import urllib.parse
import urllib.request
from pathlib import Path

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
    """Tarjeta visual generada localmente (se etiqueta como tal, no es foto histórica)."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    font = font_path()
    palette = PALETTES.get(kind, PALETTES["documental"])
    color = palette[abs(hash(title)) % len(palette)]
    title_size = max(34, int(width * 0.045))
    sub_size = max(20, int(width * 0.022))
    title_lines = wrap(title, max(12, int(width / (title_size * 0.58))), 2)
    sub_lines = wrap(subtitle, max(16, int(width / (sub_size * 0.56))), 2)

    filters = [f"drawbox=x=0:y=0:w=iw:h=ih:color={color}@1:t=fill"]
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
    cmd = [
        ffmpeg(), "-y", "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}",
        "-vf", ",".join(filters), "-frames:v", "1", str(out_png),
    ]
    proc = run(cmd, timeout=120)
    if not out_png.exists():
        raise RuntimeError(f"No se pudo generar la tarjeta visual: {proc.stderr.decode('utf-8', 'ignore')[:300]}")
    return out_png


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


def search_openverse(query: str, limit: int = 12) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "page_size": limit,
            "license_type": "all-cc",
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
                "license_url": "",
            }
        )
    return out


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
