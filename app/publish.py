"""Publicación del render terminado: entrega verificable y auto-subida real.

Dos destinos, ambos reales (nunca se simula una subida correcta):

* ``entrega`` — copia el MP4, los subtítulos y los metadatos a
  ``media/publicados/<proyecto>/`` y devuelve el enlace servido por la propia
  app. No necesita claves, así que siempre es verificable.
* ``youtube`` — subida real a la YouTube Data API v3 con un refresh token
  OAuth. Si faltan las credenciales, la publicación falla con un mensaje que
  dice exactamente qué variable de entorno falta.

El estado de cada intento queda en la tabla ``publicaciones`` y la columna
``projects.auto_publish`` permite que el worker publique solo al terminar el
render (auto-subida sin intervención).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db, media, persistence

YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
PUBLICADOS_DIRNAME = "publicados"

router = APIRouter()


class PublishIn(BaseModel):
    destination: str = "entrega"
    calendar_id: int | None = None
    privacy: str = "unlisted"


class AutoPublishIn(BaseModel):
    enabled: bool = True
    destination: str = "entrega"


class PublishError(RuntimeError):
    """Error de publicación con un mensaje apto para mostrar al usuario."""


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _g(row, key: str, default: str = "") -> str:
    """Lee una clave de un dict o de una sqlite3.Row sin romper si no existe."""
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    if value is None:
        return default
    return value


def _slug(text: str, limit: int = 48) -> str:
    base = unicodedata.normalize("NFKD", text or "")
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:limit].strip("-")


def publicados_dir() -> Path:
    path = Path(db.MEDIA_DIR) / PUBLICADOS_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_schema() -> None:
    """Crea la tabla de publicaciones y las columnas de auto-subida si faltan."""
    Path(db.DATA_DIR).mkdir(parents=True, exist_ok=True)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS publicaciones(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            calendar_id INTEGER,
            destination TEXT NOT NULL DEFAULT 'entrega',
            status TEXT NOT NULL DEFAULT 'borrador',
            url TEXT NOT NULL DEFAULT '',
            external_id TEXT NOT NULL DEFAULT '',
            meta_json TEXT NOT NULL DEFAULT '{}',
            message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_publicaciones_project ON publicaciones(project_id, id)")
    columns = {_g(row, "name") for row in db.query("PRAGMA table_info(projects)")}
    if "auto_publish" not in columns:
        db.execute("ALTER TABLE projects ADD COLUMN auto_publish INTEGER NOT NULL DEFAULT 0")
    if "publish_destination" not in columns:
        db.execute("ALTER TABLE projects ADD COLUMN publish_destination TEXT NOT NULL DEFAULT 'entrega'")


def video_path(project) -> Path:
    """Ruta del MP4 final del proyecto (misma convención que el render)."""
    suffix = "short" if _g(project, "kind") == "short" else "documental"
    return Path(db.RENDER_DIR) / str(_g(project, "id")) / f"final_{suffix}.mp4"


def subtitles(project) -> list[Path]:
    folder = Path(db.RENDER_DIR) / str(_g(project, "id"))
    if not folder.exists():
        return []
    return sorted([p for p in folder.iterdir() if p.suffix.lower() in (".srt", ".vtt")])


def youtube_credentials() -> dict:
    return {
        "client_id": os.environ.get("YOUTUBE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip(),
        "refresh_token": (db.get_setting("youtube_refresh_token", "") or os.environ.get("YOUTUBE_REFRESH_TOKEN") or "").strip(),
    }


def destinations() -> list[dict]:
    credentials = youtube_credentials()
    missing = []
    if not credentials["client_id"]:
        missing.append("YOUTUBE_CLIENT_ID")
    if not credentials["client_secret"]:
        missing.append("YOUTUBE_CLIENT_SECRET")
    if not credentials["refresh_token"]:
        missing.append("Conectar cuenta YouTube (refresh token)")
    return [
        {
            "id": "entrega",
            "label": "Carpeta de entregas (sin claves)",
            "available": True,
            "missing_env": [],
            "note": "Copia el MP4, los subtítulos y los metadatos a media/publicados y devuelve el enlace para revisarlo.",
        },
        {
            "id": "youtube",
            "label": "YouTube (auto-subida OAuth)",
            "available": not missing,
            "missing_env": missing,
            "note": (
                "Subida real a la Data API v3. Necesita YOUTUBE_CLIENT_ID, "
                "YOUTUBE_CLIENT_SECRET y una cuenta conectada desde Ajustes (permisos youtube.upload y youtube.readonly)."
            ),
        },
    ]


def build_metadata(project, scenes) -> dict:
    """Metadatos reales del video a partir del proyecto, las escenas y las fuentes."""
    title = (_g(project, "title") or "Video sin título").strip()
    topic = (_g(project, "topic") or title).strip()
    metadata_config = {}
    notes_text = _g(project, "notes") or ""
    marker = "[LABURITO_META]"
    if marker in notes_text:
        try:
            metadata_config = json.loads(notes_text.split(marker, 1)[1].splitlines()[0])
        except (ValueError, TypeError, json.JSONDecodeError):
            metadata_config = {}
    title_style = metadata_config.get("title_style", "automatico")
    title_templates = {
        "pregunta": f"¿Qué hay detrás de {topic}?",
        "curiosidad": f"Lo que tenés que saber sobre {topic}",
        "directo": f"Qué es {topic} y por qué importa",
        "misterio": f"El misterio detrás de {topic}",
    }
    if title_style in title_templates and title == topic:
        title = title_templates[title_style]
    if len(title) > 95:
        title = title[:92].rstrip() + "…"
    hook = ""
    for scene in scenes:
        text = (_g(scene, "narration") or _g(scene, "text") or "").strip()
        if text:
            hook = text
            break
    language = _g(project, "language")
    if (_g(project, "notes") or "").startswith("Autopiloto:"):
        voice_id = (_g(project, "voice") or "es").strip()
        language = "es" if voice_id == "es-es-piper" else voice_id.split("-", 1)[0]
    elif not language and _g(project, "channel_id"):
        channel = db.query_one("SELECT language FROM channels WHERE id=?", (_g(project, "channel_id"),))
        language = _g(channel or {}, "language")
    if not language:
        voice_id = (_g(project, "voice") or "es").strip()
        language = "es" if voice_id == "es-es-piper" else voice_id.split("-", 1)[0]
    # Laburito produce exclusivamente en español, incluso al migrar proyectos antiguos.
    language = "es"
    manual_keywords = [k.strip() for k in re.split(r"[,;]", _g(project, "keywords") or "") if k.strip()]
    custom_tags = [k.strip().lstrip("#") for k in re.split(r"[,;]", str(metadata_config.get("custom_tags") or "")) if k.strip()]
    topic_keywords = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}", _g(project, "topic"))
    keywords = list(dict.fromkeys(manual_keywords + custom_tags + topic_keywords))[:15]

    credits: list[str] = []
    for scene in scenes:
        author = (_g(scene, "visual_author") or "").strip()
        license_name = (_g(scene, "visual_license") or "").strip()
        if author and author not in [c.split(" (")[0] for c in credits]:
            credits.append(f"- {author} ({license_name or 'licencia sin indicar'})")

    sources = db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (_g(project, "id"),))
    source_lines = [
        (
            f"- {_g(s, 'title') or _g(s, 'url')} "
            f"· {_g(s, 'author')} · {_g(s, 'license')} "
            f"· {_g(s, 'url')}"
        ).strip(" ·")
        for s in sources
    ]

    parts: list[str] = []
    if hook:
        parts.append(hook)
    parts.append(
        f"{len(scenes)} escenas · formato {_g(project, 'kind') or 'short'} · narración en {language}."
    )
    if keywords:
        parts.append("Temas: " + ", ".join(keywords[:12]))
    if credits:
        parts.append("Créditos visuales:\n" + "\n".join(credits[:25]))
    if source_lines:
        parts.append("Fuentes:\n" + "\n".join(source_lines[:15]))
    hashtags = " ".join("#" + re.sub(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", k) for k in keywords[:6] if k)
    if hashtags:
        parts.append(hashtags)

    tags = keywords[:15] + [language, _g(project, "kind") or "short"]
    return {
        "title": title,
        "description": "\n\n".join(parts),
        "tags": [t for t in dict.fromkeys(tags) if t],
        "language": language,
        "category_id": "27" if (_g(project, "kind") or "short") != "short" else "24",
        "hashtags": hashtags,
        "project_id": _g(project, "id"),
    }


# --------------------------------------------------------------------------- #
# Destinos
# --------------------------------------------------------------------------- #
def _deliver_local(project, meta: dict, report) -> dict:
    source = video_path(project)
    report(35, "Copiando el video a la carpeta de entregas")
    slug = _slug(meta["title"]) or f"proyecto-{_g(project, 'id')}"
    target = publicados_dir() / f"{_g(project, 'id')}-{slug}"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target / source.name)
    for sub in subtitles(project):
        shutil.copy2(sub, target / sub.name)
    thumbnails = db.query(
        "SELECT path FROM assets WHERE project_id=? AND kind='miniatura' ORDER BY id DESC LIMIT 1",
        (_g(project, "id"),),
    )
    if thumbnails:
        thumbnail_path = Path(thumbnails[0].get("path") or "")
        if thumbnail_path.is_file():
            shutil.copy2(thumbnail_path, target / "miniatura.jpg")
    (target / "metadatos.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (target / "publicacion.txt").write_text(
        meta["title"] + "\n\n" + meta["description"] + "\n", encoding="utf-8"
    )
    report(90, "Entrega escrita")
    return {
        "url": f"/media/{PUBLICADOS_DIRNAME}/{target.name}/{source.name}",
        "external_id": target.name,
        "message": f"Entregado en {target}",
    }


def _youtube_token() -> str:
    credentials = youtube_credentials()
    missing = [
        key for key, value in (("YOUTUBE_CLIENT_ID", credentials["client_id"]), ("YOUTUBE_CLIENT_SECRET", credentials["client_secret"]), ("refresh token", credentials["refresh_token"]))
        if not value
    ]
    if missing:
        raise PublishError("Falta configurar YouTube: " + ", ".join(missing) + ". Conectá la cuenta desde Ajustes y configurá las credenciales de OAuth.")
    body = urllib.parse.urlencode({
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "refresh_token": credentials["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    request = urllib.request.Request(
        YOUTUBE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise PublishError(f"YouTube rechazó las credenciales ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise PublishError(f"No se pudo contactar a YouTube: {exc.reason}") from exc
    token = data.get("access_token")
    if not token:
        raise PublishError("YouTube no devolvió un token de acceso; revisá la conexión OAuth.")
    return token


def youtube_account_status() -> dict:
    token = _youtube_token()
    url = "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode({
        "part": "snippet",
        "mine": "true",
    })
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise PublishError(f"YouTube no pudo verificar el canal ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise PublishError(f"No se pudo contactar a YouTube: {exc.reason}") from exc
    items = data.get("items") or []
    if not items:
        raise PublishError("Google autorizó la cuenta, pero no devolvió un canal de YouTube.")
    snippet = items[0].get("snippet") or {}
    return {
        "channel_id": items[0].get("id"),
        "channel_title": snippet.get("title") or "Canal de YouTube",
    }


def _validate_autopilot_short(project, source: Path) -> dict:
    """Valida el archivo final para que un autopiloto nunca suba un video largo."""
    notes = _g(project, "notes") or ""
    if not notes.startswith("Autopiloto:"):
        return {}
    if _g(project, "kind") != "short":
        raise PublishError("Publicación cancelada: el Autopiloto solo puede publicar proyectos tipo Short.")
    try:
        info = media.probe_video(source)
    except Exception as exc:
        raise PublishError(f"No se pudo validar el MP4 antes de publicar: {exc}") from exc
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    duration = float(info.get("duration") or 0)
    if not width or not height or height <= width:
        raise PublishError("Publicación cancelada: el archivo no es vertical. Los Shorts deben renderizarse en 9:16.")
    if duration <= 0 or duration > 180:
        raise PublishError(f"Publicación cancelada: duración inválida para un Short ({duration:.1f} s). El máximo es 180 segundos.")
    ratio = width / height
    if abs(ratio - (9 / 16)) > 0.025:
        raise PublishError(f"Publicación cancelada: proporción {width}x{height}; se esperaba 9:16.")
    return info


def _validate_autopilot_video(project, source: Path) -> dict:
    """Valida Shorts y documentales del Autopiloto antes de subirlos."""
    if not (_g(project, "notes") or "").startswith("Autopiloto:"):
        return {}
    if _g(project, "kind") == "short":
        return _validate_autopilot_short(project, source)
    if _g(project, "kind") != "documentary":
        raise PublishError("Publicación cancelada: tipo de video del Autopiloto no compatible.")
    try:
        info = media.probe_video(source)
    except Exception as exc:
        raise PublishError(f"No se pudo validar el MP4 antes de publicar: {exc}") from exc
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    duration = float(info.get("duration") or 0)
    if not width or not height or width <= height:
        raise PublishError("Publicación cancelada: el documental debe ser horizontal 16:9.")
    if duration < 180 or duration > 1200:
        raise PublishError(f"Publicación cancelada: duración inválida para un documental ({duration:.1f} s). El límite es 20 minutos.")
    ratio = width / height
    if abs(ratio - (16 / 9)) > 0.04:
        raise PublishError(f"Publicación cancelada: proporción {width}x{height}; se esperaba 16:9.")
    return info


def _youtube_upload(project, meta: dict, privacy: str, report) -> dict:
    source = video_path(project)
    _validate_autopilot_video(project, source)
    token = _youtube_token()
    report(40, "Credenciales de YouTube aceptadas")
    payload = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"][:4900],
            "tags": meta["tags"][:15],
            "categoryId": meta["category_id"],
            "defaultLanguage": meta["language"],
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    total = source.stat().st_size
    if total <= 0:
        raise PublishError("El MP4 está vacío; no se puede subir.")
    init = urllib.request.Request(
        f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(total),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(init, timeout=60) as response:
            location = response.headers.get("Location")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise PublishError(f"YouTube rechazó la sesión de subida ({exc.code}): {detail}") from exc
    if not location:
        raise PublishError("YouTube no devolvió la URL de subida.")

    report(60, "Subiendo el video a YouTube")
    chunk_size = 8 * 1024 * 1024
    offset = 0
    stalled_attempts = 0
    result = None
    try:
        with source.open("rb") as video:
            while offset < total:
                video.seek(offset)
                chunk = video.read(min(chunk_size, total - offset))
                if not chunk:
                    raise PublishError("La lectura del MP4 se interrumpió durante la subida.")
                end = offset + len(chunk) - 1
                next_offset = end + 1
                upload = urllib.request.Request(
                    location,
                    data=chunk,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{total}",
                    },
                    method="PUT",
                )
                try:
                    with urllib.request.urlopen(upload, timeout=180) as response:
                        if response.status in (200, 201):
                            result = json.loads(response.read().decode("utf-8", "replace"))
                except urllib.error.HTTPError as exc:
                    if exc.code != 308:
                        detail = exc.read().decode("utf-8", "replace")[:300]
                        raise PublishError(f"YouTube rechazó el bloque de subida ({exc.code}): {detail}") from exc
                    accepted = exc.headers.get("Range", "")
                    if accepted.startswith("bytes=0-"):
                        next_offset = int(accepted.rsplit("-", 1)[1]) + 1
                    else:
                        next_offset = offset
                if result:
                    offset = total
                else:
                    if next_offset <= offset:
                        stalled_attempts += 1
                        if stalled_attempts > 3:
                            raise PublishError("YouTube no confirmó el avance de la subida después de varios intentos.")
                    else:
                        stalled_attempts = 0
                    offset = next_offset
                report(60 + int(30 * offset / total), f"Subiendo video: {int(100 * offset / total)}%")
    except urllib.error.URLError as exc:
        raise PublishError(f"Se cortó la conexión durante la subida a YouTube: {exc.reason}") from exc
    video_id = (result or {}).get("id")
    if not video_id:
        raise PublishError("YouTube no devolvió el identificador del video subido.")

    # Confirmar que el ID ya aparece en la biblioteca del canal. La subida
    # puede estar aceptada aunque el procesamiento de YouTube siga en curso.
    verification = {
        "status": "pending",
        "upload_status": "unknown",
        "processing_status": "unknown",
    }
    verify_url = "https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode({
        "part": "status,processingDetails",
        "id": video_id,
    })
    verify_request = urllib.request.Request(
        verify_url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(verify_request, timeout=45) as response:
            verify_data = json.loads(response.read().decode("utf-8", "replace"))
        items = verify_data.get("items") or []
        if items and items[0].get("id") == video_id:
            status_data = items[0].get("status") or {}
            processing_data = items[0].get("processingDetails") or {}
            upload_status = status_data.get("uploadStatus") or "unknown"
            processing_status = processing_data.get("processingStatus") or "unknown"
            failed = upload_status in ("failed", "rejected") or processing_status in ("failed", "terminated")
            verification = {
                "status": "processing_failed" if failed else "verified",
                "upload_status": upload_status,
                "processing_status": processing_status,
            }
        else:
            db.log("warn", "publicacion", "YouTube aceptó la subida, pero el video todavía no aparece en videos.list.",
                   {"project_id": _g(project, "id"), "video_id": video_id})
    except Exception as exc:
        # No repetir la subida por un fallo de lectura posterior: el upload API
        # ya devolvió un ID válido y volver a subir podría crear un duplicado.
        db.log("warn", "publicacion", f"Subida aceptada; verificación posterior pendiente: {exc}",
               {"project_id": _g(project, "id"), "video_id": video_id})

    thumb_suffix = "short" if _g(project, "kind") == "short" else "documental"
    thumb = Path(db.RENDER_DIR) / str(_g(project, "id")) / f"miniatura_{thumb_suffix}.jpg"
    thumbnail_uploaded = False
    is_autopilot_short = (_g(project, "notes") or "").startswith("Autopiloto:")
    # YouTube no permite fijar por API la portada de un Short; se conserva el JPG local.
    if thumb.exists() and not is_autopilot_short:
        try:
            thumb_request = urllib.request.Request(
                "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId=" + urllib.parse.quote(video_id),
                data=thumb.read_bytes(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "image/jpeg",
                },
                method="POST",
            )
            with urllib.request.urlopen(thumb_request, timeout=90) as response:
                thumbnail_uploaded = response.status in (200, 201)
        except Exception as exc:
            db.log("warn", "publicacion", f"Video subido pero no se pudo adjuntar la miniatura: {exc}", {"project_id": _g(project, "id")})
    report(95, "Subida terminada")
    message = f"Subido a YouTube con privacidad {privacy}"
    if verification["status"] == "verified":
        message += " · ID confirmado en el canal"
        if verification["processing_status"] not in ("succeeded", "unknown"):
            message += " · procesamiento de YouTube en curso"
    elif verification["status"] == "processing_failed":
        message += " · YouTube informó un fallo de procesamiento"
    else:
        message += " · verificación posterior pendiente"
    if thumbnail_uploaded:
        message += " y miniatura personalizada"
    return {
        "url": f"https://youtu.be/{video_id}",
        "external_id": video_id,
        "message": message,
        "verification": verification,
    }

# --------------------------------------------------------------------------- #
# Publicación
# --------------------------------------------------------------------------- #
def _video_fingerprint(path: Path) -> str:
    """Huella del MP4 para que los reintentos no suban dos veces el mismo archivo."""
    digest = hashlib.sha256()
    with path.open("rb") as video:
        for chunk in iter(lambda: video.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish(project_id: int, destination: str = "entrega", calendar_id: int | None = None,
            privacy: str = "unlisted", on_progress=None) -> dict:
    """Publica el render del proyecto en el destino pedido y registra el intento."""
    report = on_progress or (lambda _pct, _msg: None)
    ensure_schema()
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise PublishError(f"El proyecto {project_id} no existe.")
    source = video_path(project)
    if not source.exists():
        raise PublishError("Todavía no hay un MP4 renderizado para este proyecto: ejecutá el render y volvé a publicar.")
    if destination == "youtube" and privacy not in ("public", "unlisted", "private"):
        raise PublishError("Privacidad inválida para YouTube. Elegí público, oculto o privado.")
    if destination == "youtube" and (_g(project, "notes") or "").startswith("Autopiloto:"):
        _validate_autopilot_video(project, source)
    if destination not in ("entrega", "youtube"):
        raise PublishError(f"Destino desconocido: {destination}. Usá 'entrega' o 'youtube'.")

    fingerprint = _video_fingerprint(source)
    previous = db.query_one(
        "SELECT * FROM publicaciones WHERE project_id=? AND destination=? AND status IN ('publicado','procesamiento_fallido') ORDER BY id DESC LIMIT 1",
        (project_id, destination),
    )
    if previous:
        try:
            previous_meta = json.loads(_g(previous, "meta_json", "{}") or "{}")
        except (TypeError, ValueError):
            previous_meta = {}
        if previous_meta.get("video_sha256") == fingerprint:
            report(100, "Este mismo video ya estaba publicado; no se volvió a subir")
            return {
                "ok": True,
                "destination": destination,
                "status": _g(previous, "status") or "publicado",
                "url": _g(previous, "url"),
                "external_id": _g(previous, "external_id"),
                "message": "Este mismo archivo ya estaba publicado. Se evitó una segunda subida.",
                "verification": previous_meta.get("youtube_verification"),
                "meta": previous_meta,
            }

    scenes = db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx", (project_id,))
    meta = build_metadata(project, scenes)
    meta["video_sha256"] = fingerprint
    report(15, "Metadatos generados")

    if destination == "entrega":
        result = _deliver_local(project, meta, report)
    elif destination == "youtube":
        result = _youtube_upload(project, meta, privacy, report)
    else:
        raise PublishError(f"Destino desconocido: {destination}. Usá 'entrega' o 'youtube'.")

    if result.get("verification"):
        meta["youtube_verification"] = result["verification"]
    verification = result.get("verification") or {}
    publication_status = (
        "procesamiento_fallido"
        if verification.get("status") == "processing_failed"
        else "publicado"
    )
    now = db.now()
    db.execute(
        "INSERT INTO publicaciones(project_id, calendar_id, destination, status, url, external_id, meta_json, message, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            project_id,
            calendar_id,
            destination,
            publication_status,
            result["url"],
            result["external_id"],
            json.dumps(meta, ensure_ascii=False),
            result["message"],
            now,
            now,
        ),
    )
    if calendar_id:
        db.execute(
            "UPDATE calendar_entries SET status=?, video_url=?, updated_at=? WHERE id=?",
            (publication_status, result["url"], now, calendar_id),
        )
    db.log("info", "publicacion", f"Resultado de publicación del proyecto {project_id}: {publication_status} en {destination}",
           {"url": result["url"], "external_id": result["external_id"]})
    report(100, "Procesamiento rechazado por YouTube" if publication_status == "procesamiento_fallido" else "Publicado")
    return {
        "ok": True,
        "destination": destination,
        "status": publication_status,
        "url": result["url"],
        "external_id": result["external_id"],
        "message": result["message"],
        "verification": result.get("verification"),
        "meta": meta,
    }


def list_publications(project_id: int | None = None, limit: int = 50) -> list[dict]:
    ensure_schema()
    if project_id:
        rows = db.query("SELECT * FROM publicaciones WHERE project_id=? ORDER BY id DESC LIMIT ?",
                        (project_id, limit))
    else:
        rows = db.query("SELECT * FROM publicaciones ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(row) for row in rows]


def auto_publish_settings(project_id: int) -> dict:
    ensure_schema()
    project = db.query_one("SELECT auto_publish, publish_destination FROM projects WHERE id=?", (project_id,))
    if not project:
        raise PublishError(f"El proyecto {project_id} no existe.")
    return {
        "enabled": bool(_g(project, "auto_publish", 0)),
        "destination": _g(project, "publish_destination", "entrega") or "entrega",
    }


def set_auto_publish(project_id: int, enabled: bool, destination: str = "entrega") -> dict:
    ensure_schema()
    if destination not in ("entrega", "youtube"):
        raise PublishError("Destino inválido: usá 'entrega' o 'youtube'.")
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise PublishError(f"El proyecto {project_id} no existe.")
    if enabled and destination == "youtube":
        if not persistence.durable_storage_available():
            raise PublishError(
                "La autopublicación necesita Supabase o un volumen local persistente para no perder el MP4 si el servidor se reinicia."
            )
        youtube_account_status()
    db.execute(
        "UPDATE projects SET auto_publish=?, publish_destination=?, updated_at=? WHERE id=?",
        (1 if enabled else 0, destination, db.now(), project_id),
    )
    return auto_publish_settings(project_id)


# --------------------------------------------------------------------------- #
# Rutas HTTP
# --------------------------------------------------------------------------- #
def _enqueue(project_id: int, destination: str, calendar_id: int | None, privacy: str) -> int:
    from . import worker  # import tardío: worker importa este módulo

    return worker.enqueue(
        project_id,
        "publish_project",
        {"destination": destination, "calendar_id": calendar_id, "privacy": privacy},
    )


@router.get("/api/publish/destinations")
def api_destinations():
    return {"destinations": destinations(), "auto_publish_available": True}


@router.post("/api/projects/{project_id}/publish", status_code=202)
def api_publish(project_id: int, payload: PublishIn):
    ensure_schema()
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, f"El proyecto {project_id} no existe.")
    if payload.destination not in ("entrega", "youtube"):
        raise HTTPException(400, "Destino inválido: usá 'entrega' o 'youtube'.")
    if not video_path(project).exists():
        raise HTTPException(400, "Todavía no hay un MP4 renderizado: ejecutá el render antes de publicar.")
    job_id = _enqueue(project_id, payload.destination, payload.calendar_id, payload.privacy)
    return {"ok": True, "job_id": job_id, "destination": payload.destination}


@router.get("/api/publications")
def api_publications(project_id: int | None = None, limit: int = 50):
    return {"publications": list_publications(project_id, limit)}


@router.get("/api/projects/{project_id}/auto-publish")
def api_get_auto_publish(project_id: int):
    try:
        return auto_publish_settings(project_id)
    except PublishError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/projects/{project_id}/auto-publish")
def api_set_auto_publish(project_id: int, payload: AutoPublishIn):
    try:
        return set_auto_publish(project_id, payload.enabled, payload.destination)
    except PublishError as exc:
        raise HTTPException(400, str(exc)) from exc
