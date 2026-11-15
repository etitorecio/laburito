"""AITuber Libre — API local (FastAPI) que sirve también la interfaz web."""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import secrets
import urllib.error
import urllib.parse
import urllib.request
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import autopilot, db, media, options, persistence, publish, render, script_gen, skeleton, tts, worker

APP_VERSION = "1.1.0"
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Restaurar la base antes de que init_db cree un SQLite vacío en un contenedor nuevo.
    persistence.restore_if_available()
    db.init_db()
    worker.start()
    db.log("info", "app", "AITuber Libre iniciado", {"version": APP_VERSION})
    yield
    worker.stop()


app = FastAPI(title="AITuber Libre", version=APP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def persist_successful_changes(request: Request, call_next):
    response = await call_next(request)
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path.startswith("/api/")
        and response.status_code < 400
        and persistence.configured()
    ):
        try:
            persistence.sync_backup()
        except Exception as exc:
            db.log("error", "persistence", f"No se pudo guardar el cambio de API en Supabase: {exc}",
                   {"path": request.url.path, "method": request.method})
    return response


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

class ChannelIn(BaseModel):
    name: str
    topic: str = ""
    language: str = "es"
    audience: str = ""
    tone: str = ""
    visual_identity: str = ""
    formats: str = "documental,short"
    cadence: str = "semanal"


class ProjectIn(BaseModel):
    title: str
    topic: str = ""
    kind: str = "documentary"
    channel_id: int | None = None
    duration_target_sec: int | None = None
    voice: str = "es"
    speed: int = 150
    pitch: int = 45
    visual_style: str = "automatico"
    video_type: str = "moving_images"
    aspect: str = ""
    notes: str = ""
    template: str = options.DEFAULT_TEMPLATE
    caption_style: str = ""
    transition_default: str = ""
    resolution: str = ""
    fps: int | None = None
    music: str = "auto"
    music_volume: float | None = None


class ProjectPatch(BaseModel):
    title: str | None = None
    topic: str | None = None
    channel_id: int | None = None
    duration_target_sec: int | None = None
    voice: str | None = None
    speed: int | None = None
    pitch: int | None = None
    visual_style: str | None = None
    video_type: str | None = None
    title_style: str | None = None
    custom_tags: str | None = None
    aspect: str | None = None
    notes: str | None = None
    status: str | None = None
    template: str | None = None
    caption_style: str | None = None
    transition_default: str | None = None
    resolution: str | None = None
    fps: int | None = None
    music: str | None = None
    music_volume: float | None = None


class ScenePatch(BaseModel):
    title: str | None = None
    narration: str | None = None
    visual_query: str | None = None
    transition: str | None = None


class NicheIn(BaseModel):
    name: str
    demand: int = 0
    competition: int = 0
    trend: str = "estable"
    difficulty: int = 0
    copyright_risk: str = "medio"
    monetization: str = ""
    series_potential: int = 0
    notes: str = ""


class NoteIn(BaseModel):
    niche: str = ""
    claim: str
    evidence_level: str = "indicio"
    source_url: str = ""
    methodology: str = ""


class SourceIn(BaseModel):
    project_id: int | None = None
    scene_id: int | None = None
    title: str = ""
    url: str = ""
    author: str = ""
    license: str = ""
    attribution: str = ""
    kind: str = "referencia"
    notes: str = ""


class CalendarIn(BaseModel):
    channel_id: int
    scheduled_for: str
    title: str = ""
    format: str = "documental"
    project_id: int | None = None


class SearchIn(BaseModel):
    query: str
    provider: str = "all"


class VisualIn(BaseModel):
    url: str
    license: str = ""
    author: str = ""
    page: str = ""
    title: str = ""


class SettingsIn(BaseModel):
    values: dict[str, str]


class AutopilotIn(BaseModel):
    name: str = ""
    niche: str = ""
    channel_id: int | None = None
    template: str = "shorts"
    duration_target_sec: int | None = None
    voice: str = "es"
    speed: int = 150
    pitch: int = 45
    visual_style: str = "automatico"
    video_type: str = "moving_images"
    title_style: str = "automatico"
    custom_tags: str = ""
    aspect: str | None = None
    caption_style: str | None = None
    transition_default: str | None = None
    resolution: str | None = None
    fps: int | None = None
    music: str | None = None
    music_volume: float | None = None
    cadence_hours: int = 24
    videos_per_period: int = 1
    period_days: int = 1
    schedule_time: str = "10:00"
    timezone: str = "America/Argentina/Buenos_Aires"
    audience: str = "Público general"
    tone: str = "Dinámico y cercano"
    hook_style: str = "Dato sorprendente"
    cta: str = "Hacé una pregunta concreta al final"
    content_pillars: str = ""
    avoid_topics: str = ""
    enabled: bool = True
    destination: str = "youtube"
    privacy: str = "public"
    auto_publish: bool = True


class AutopilotPatch(BaseModel):
    name: str | None = None
    niche: str | None = None
    channel_id: int | None = None
    template: str | None = None
    duration_target_sec: int | None = None
    voice: str | None = None
    speed: int | None = None
    pitch: int | None = None
    visual_style: str | None = None
    video_type: str | None = None
    title_style: str | None = None
    custom_tags: str | None = None
    aspect: str | None = None
    caption_style: str | None = None
    transition_default: str | None = None
    resolution: str | None = None
    fps: int | None = None
    music: str | None = None
    music_volume: float | None = None
    cadence_hours: int | None = None
    videos_per_period: int | None = None
    period_days: int | None = None
    schedule_time: str | None = None
    timezone: str | None = None
    audience: str | None = None
    tone: str | None = None
    hook_style: str | None = None
    cta: str | None = None
    content_pillars: str | None = None
    avoid_topics: str | None = None
    enabled: bool | None = None
    destination: str | None = None
    privacy: str | None = None
    auto_publish: bool | None = None


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def _project_full(project_id: int) -> dict:
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    project["scenes"] = db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx, id", (project_id,))
    project["sources"] = db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (project_id,))
    try:
        project["quality"] = json.loads(project.get("quality_json") or "{}")
    except json.JSONDecodeError:
        project["quality"] = {}
    project["jobs"] = db.query(
        "SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 5", (project_id,)
    )
    return project


def _touch_project(project_id: int) -> None:
    db.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now(), project_id))

def _validate_video_type(video_type: str) -> None:
    if video_type not in options.VIDEO_TYPE_IDS:
        raise HTTPException(400, "Tipo de video desconocido")
    if video_type == "moving_images":
        return
    if video_type == "full_motion_ai":
        raise HTTPException(400, "La generación de video IA completo no tiene un modelo local viable para este equipo.")
    if video_type == "skeleton":
        return
    required = 5
    folder = db.DATA_DIR / "background_clips" / video_type
    count = len(list(folder.glob("*.mp4"))) if folder.exists() else 0
    if count < required:
        raise HTTPException(400, f"Este formato necesita {required} clip(s) propios o autorizados. Hay {count} cargados.")



# --------------------------------------------------------------------------- #
# Salud, metadatos y diagnóstico
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    # El endpoint de despertar también reanima el hilo si se detuvo inesperadamente.
    if not worker.status()["worker_alive"]:
        worker.start()
    return {
        "ok": True,
        "app": "Laburito Shorts Autopilot",
        "version": APP_VERSION,
        "time": db.now(),
        "worker": worker.status(),
        "persistence": persistence.status(),
    }


@app.post("/api/music/upload")
async def upload_music(file: UploadFile = File(...)):
    """Guarda una pista propia para usarla como música de fondo en los videos."""
    allowed = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
    original = Path(file.filename or "musica").name
    extension = Path(original).suffix.lower()
    if extension not in allowed:
        raise HTTPException(400, "Formato no admitido. Usá MP3, WAV, OGG, M4A o FLAC.")
    content = await file.read(25 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(400, "El archivo está vacío.")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "La pista supera el límite de 25 MB.")
    stem = "".join(ch for ch in Path(original).stem if ch.isalnum() or ch in "-_")[:48] or "musica"
    db.MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{stem}-{time.time_ns()}{extension}"
    target = db.MUSIC_DIR / filename
    target.write_bytes(content)
    return {"filename": filename, "music_library": sorted(p.name for p in db.MUSIC_DIR.iterdir() if p.is_file())}


CLIP_CATEGORIES = {"stock_footage", "minecraft", "subway"}
MAX_BACKGROUND_CLIP_BYTES = 150 * 1024 * 1024


def _background_clip_folder(category: str) -> Path:
    if category not in CLIP_CATEGORIES:
        raise HTTPException(404, "Biblioteca de clips desconocida")
    folder = db.DATA_DIR / "background_clips" / category
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@app.get("/api/background-clips")
def list_background_clips():
    result = {}
    for category in sorted(CLIP_CATEGORIES):
        folder = _background_clip_folder(category)
        result[category] = [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "url": f"/api/background-clips/{category}/{path.name}",
            }
            for path in sorted(folder.glob("*.mp4"))
            if path.is_file()
        ]
    return result


@app.post("/api/background-clips")
async def upload_background_clip(
    category: str,
    rights_confirmed: bool = False,
    file: UploadFile = File(...),
):
    if not rights_confirmed:
        raise HTTPException(400, "Confirmá que tenés derechos o permiso para usar este clip.")
    folder = _background_clip_folder(category)
    if len(list(folder.glob("*.mp4"))) >= 5:
        raise HTTPException(400, "Esta biblioteca ya tiene cinco clips. Quitá uno antes de agregar otro.")
    original = Path(file.filename or "clip.mp4").name
    extension = Path(original).suffix.lower()
    if extension not in {".mp4", ".mov", ".webm", ".mkv"}:
        raise HTTPException(400, "Usá un video MP4, MOV, WebM o MKV.")
    content = await file.read(MAX_BACKGROUND_CLIP_BYTES + 1)
    if not content:
        raise HTTPException(400, "El video está vacío.")
    if len(content) > MAX_BACKGROUND_CLIP_BYTES:
        raise HTTPException(400, "El clip supera el límite de 150 MB.")
    stem = "".join(ch for ch in Path(original).stem if ch.isalnum() or ch in "-_")[:48] or "clip"
    filename = f"{stem}-{time.time_ns()}.mp4"
    temp_dir = db.TMP_DIR / "background_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    source = temp_dir / f"{time.time_ns()}{extension}"
    target = folder / filename
    source.write_bytes(content)
    try:
        proc = media.run([
            media.ffmpeg(), "-y", "-i", str(source),
            "-vf", "scale='min(1280,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(target),
        ], timeout=300)
        if proc.returncode != 0 or not target.exists() or target.stat().st_size < 1000:
            message = (proc.stderr or b"").decode("utf-8", "ignore")[-700:]
            raise HTTPException(400, "No se pudo convertir el clip a MP4 H.264: " + message)
        sidecar = target.with_suffix(".json")
        sidecar.write_text(json.dumps({
            "original_filename": original,
            "rights_confirmed": True,
            "category": category,
            "uploaded_at": db.now(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"filename": filename, "size": target.stat().st_size}
    finally:
        source.unlink(missing_ok=True)


@app.get("/api/background-clips/{category}/{filename}")
def get_background_clip(category: str, filename: str):
    folder = _background_clip_folder(category)
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".mp4"):
        raise HTTPException(404, "Clip inexistente")
    target = folder / safe_name
    if not target.exists():
        raise HTTPException(404, "Clip inexistente")
    return FileResponse(target, media_type="video/mp4")


@app.delete("/api/background-clips/{category}/{filename}")
def delete_background_clip(category: str, filename: str):
    folder = _background_clip_folder(category)
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.lower().endswith(".mp4"):
        raise HTTPException(404, "Clip inexistente")
    target = folder / safe_name
    if not target.exists():
        raise HTTPException(404, "Clip inexistente")
    target.unlink()
    target.with_suffix(".json").unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/meta")
def meta():
    tts_status = tts.status()
    return {
        # El producto está deliberadamente limitado al español: no se ofrecen
        # idiomas que el guionista y la estrategia editorial no van a producir.
        "language": "es",
        "voices": [{**v, "available": tts_status["available"] and (v["id"] != "es-es-piper" or tts_status["piper_available"])} for v in tts_status["voices"] if v.get("language") == "es"],
        "aspects": list(render.ASPECTS.keys()),
        "resolutions": options.RESOLUTION_INFO,
        "fps_options": options.FPS_OPTIONS,
        "templates": options.TEMPLATES,
        "external_templates": options.EXTERNAL_TEMPLATES,
        "video_types": options.VIDEO_TYPES,
        "visual_styles": options.VISUAL_STYLES,
        "caption_styles": [
            {"id": key, "label": options.CAPTION_LABELS.get(key, key), **style}
            for key, style in options.CAPTION_STYLES.items()
        ],
        "transitions": options.TRANSITIONS,
        "music_beds": [{"id": m["id"], "label": m["label"]} for m in options.MUSIC_BEDS],
        "music_library": (
            sorted(p.name for p in db.MUSIC_DIR.iterdir() if p.is_file()) if db.MUSIC_DIR.exists() else []
        ),
        "script_templates": options.SCRIPT_TEMPLATES,
        "kinds": [
            {"id": "documentary", "label": "Documental (8-20 min)", "aspect": "16:9"},
            {"id": "short", "label": "Short vertical", "aspect": "9:16"},
        ],
        "evidence_levels": ["hecho", "indicio", "estimacion"],
        "settings": {
            **{k: db.get_setting(k) for k in db.DEFAULT_SETTINGS},
            "ollama_url": db.get_setting("ollama_url") or os.environ.get("OLLAMA_URL", ""),
        },
    }


@app.get("/api/caption-preview/{style_id}")
def caption_style_preview(style_id: str):
    if style_id not in options.CAPTION_STYLES:
        raise HTTPException(404, "Estilo de subtítulos inexistente")
    try:
        preview = render.caption_preview(style_id)
        return FileResponse(preview, media_type="image/png")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la vista previa: {exc}") from exc


@app.get("/api/visual-style-preview/{style_id}")
def visual_style_sample(style_id: str):
    if style_id not in options.VISUAL_STYLE_IDS:
        raise HTTPException(404, "Estilo visual inexistente")
    try:
        preview = render.visual_style_preview(style_id)
        return FileResponse(preview, media_type="image/png")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la muestra visual: {exc}") from exc


@app.get("/api/skeleton-preview/{action}")
def skeleton_sample_preview(action: str):
    if action not in skeleton.ACTIONS:
        raise HTTPException(404, "Animación de esqueleto inexistente")
    try:
        preview = skeleton.ensure_clip(action)
        return FileResponse(preview, media_type="video/mp4")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la muestra de esqueleto: {exc}") from exc


@app.get("/api/music-preview/{bed_id}")
def music_bed_preview(bed_id: str):
    if bed_id not in options.MUSIC_IDS:
        raise HTTPException(404, "Pista musical inexistente")
    try:
        preview = media.ensure_music_bed(bed_id)
        return FileResponse(preview, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la muestra musical: {exc}") from exc


@app.get("/api/music-file/{filename}")
def uploaded_music_preview(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or Path(safe_name).suffix.lower() not in {".mp3", ".wav", ".ogg", ".m4a", ".flac"}:
        raise HTTPException(404, "Pista musical inexistente")
    target = db.MUSIC_DIR / safe_name
    if not target.exists():
        raise HTTPException(404, "Pista musical inexistente")
    media_type = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".m4a": "audio/mp4", ".flac": "audio/flac",
    }.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type)


@app.get("/api/voice-preview/{voice_id}")
def voice_sample_preview(voice_id: str):
    if voice_id not in tts.VOICES:
        raise HTTPException(404, "Voz española inexistente")
    preview_dir = db.DATA_DIR / "voice_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"{voice_id}.wav"
    try:
        if not preview.exists() or preview.stat().st_size < 1000:
            tts.synthesize(
                "Hola. Esta es una muestra de voz en español para tus videos. "
                "Elegí la que mejor combine con el estilo de tu canal.",
                preview, voice=voice_id, speed=150,
                pitch=30 if voice_id == "es-masculino" else 65 if voice_id == "es-agudo" else 45,
            )
        return FileResponse(preview, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la muestra de voz: {exc}") from exc


@app.get("/api/transition-preview/{transition_id}")
def transition_effect_preview(transition_id: str):
    if transition_id not in options.TRANSITION_IDS:
        raise HTTPException(404, "Movimiento de escena inexistente")
    try:
        preview = render.transition_preview(transition_id)
        return FileResponse(preview, media_type="video/mp4")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la demostración: {exc}") from exc


@app.get("/api/diagnostics")
def diagnostics():
    disk = shutil.disk_usage(str(db.DATA_DIR))
    checks = {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "tts": tts.status()["available"],
        "fuente_subtitulos": bool(media.font_path()),
        "sqlite": db.DB_PATH.exists(),
        "worker": worker.status()["worker_alive"],
    }
    return {
        "version": APP_VERSION,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}",
        "data_dir": str(db.DATA_DIR),
        "data_writable": os.access(db.DATA_DIR, os.W_OK),
        "disk_free_mb": round(disk.free / (1024 * 1024), 1),
        "db_size_kb": round(db.DB_PATH.stat().st_size / 1024, 1) if db.DB_PATH.exists() else 0,
        "checks": checks,
        "tts": tts.status(),
        "font": media.font_path(),
        "ffmpeg_version": (media.run(["ffmpeg", "-version"], timeout=20).stdout or b"").decode().split("\n")[0],
        "render": media.capabilities(),
        "ollama": {
            "url": db.get_setting("ollama_url") or os.environ.get("OLLAMA_URL", ""),
            "available": script_gen.ollama_model_available(db.get_setting("ollama_url") or os.environ.get("OLLAMA_URL", ""), "qwen2.5:1.5b-instruct"),
            "model": "qwen2.5:1.5b-instruct",
            "optional": True,
        },
        "counts": {
            "canales": db.scalar("SELECT COUNT(*) FROM channels", default=0),
            "proyectos": db.scalar("SELECT COUNT(*) FROM projects", default=0),
            "escenas": db.scalar("SELECT COUNT(*) FROM scenes", default=0),
            "tareas": db.scalar("SELECT COUNT(*) FROM jobs", default=0),
            "fuentes": db.scalar("SELECT COUNT(*) FROM sources", default=0),
        },
        "worker": worker.status(),
        "persistence": persistence.status(),
        "note": "Render y TTS corren localmente; YouTube requiere OAuth. En AppJet Free configurá Supabase para conservar los datos entre reemplazos del contenedor.",
    }


@app.get("/api/logs")
def logs(limit: int = 80):
    return db.query("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (max(1, min(500, limit)),))


# --------------------------------------------------------------------------- #
# Canales
# --------------------------------------------------------------------------- #

@app.get("/api/channels")
def list_channels():
    rows = db.query("SELECT * FROM channels ORDER BY name COLLATE NOCASE")
    for row in rows:
        row["projects"] = db.scalar("SELECT COUNT(*) FROM projects WHERE channel_id=?", (row["id"],), 0)
        row["next_entry"] = db.query_one(
            "SELECT * FROM calendar_entries WHERE channel_id=? ORDER BY scheduled_for LIMIT 1", (row["id"],)
        )
    return rows


@app.post("/api/channels", status_code=201)
def create_channel(payload: ChannelIn):
    payload.language = "es"
    cid = db.execute(
        "INSERT INTO channels(name, topic, language, audience, tone, visual_identity, formats, cadence, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (payload.name, payload.topic, payload.language, payload.audience, payload.tone,
         payload.visual_identity, payload.formats, payload.cadence, db.now(), db.now()),
    )
    db.log("info", "channels", f"Canal creado: {payload.name}")
    return db.query_one("SELECT * FROM channels WHERE id=?", (cid,))


@app.patch("/api/channels/{channel_id}")
def update_channel(channel_id: int, payload: ChannelIn):
    if not db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,)):
        raise HTTPException(404, "Canal inexistente")
    payload.language = "es"
    db.execute(
        "UPDATE channels SET name=?, topic=?, language=?, audience=?, tone=?, visual_identity=?, formats=?, cadence=?, updated_at=? WHERE id=?",
        (payload.name, payload.topic, payload.language, payload.audience, payload.tone,
         payload.visual_identity, payload.formats, payload.cadence, db.now(), channel_id),
    )
    return db.query_one("SELECT * FROM channels WHERE id=?", (channel_id,))


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: int):
    db.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Proyectos y escenas
# --------------------------------------------------------------------------- #

@app.get("/api/projects")
def list_projects():
    rows = db.query(
        "SELECT p.*, c.name AS channel_name, "
        "(SELECT COUNT(*) FROM scenes s WHERE s.project_id=p.id) AS scenes_count "
        "FROM projects p LEFT JOIN channels c ON c.id=p.channel_id ORDER BY p.id DESC"
    )
    for row in rows:
        row["job"] = db.query_one(
            "SELECT id, status, progress, message FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
        )
    return rows


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectIn):
    data = payload.model_dump()
    spanish_voices = {"es", "es-ar", "es-es-piper", "es-mx", "es-masculino", "es-agudo"}
    if data.get("voice") not in spanish_voices:
        raise HTTPException(400, "Laburito genera contenido únicamente en español. Elegí una voz española.")
    if data.get("aspect") and data["aspect"] not in render.ASPECTS:
        raise HTTPException(400, "Formato no soportado (16:9, 9:16, 1:1 o 4:5)")
    if data.get("visual_style") not in options.VISUAL_STYLE_IDS:
        raise HTTPException(400, "Estilo visual desconocido")
    _validate_video_type(data.get("video_type") or "moving_images")
    resolved = options.resolve_defaults(data)
    tpl = options.template(resolved["template"])
    duration = int(data.get("duration_target_sec") or tpl["default_duration"])
    pid = db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, "
        "template, visual_style, video_type, caption_style, transition_default, resolution, fps, music, music_volume, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("channel_id"), payload.title, payload.topic or payload.title, resolved["kind"],
            resolved["aspect"], "borrador", duration, payload.voice, payload.speed, payload.pitch,
            payload.notes, resolved["template"], payload.visual_style, payload.video_type,
            resolved["caption_style"], resolved["transition_default"],
            resolved["resolution"], resolved["fps"], resolved["music"], data.get("music_volume"),
            db.now(), db.now(),
        ),
    )
    db.log("info", "projects", f"Proyecto creado: {payload.title}", {"id": pid})
    return _project_full(pid)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    return _project_full(project_id)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: int, payload: ProjectPatch):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    data = payload.model_dump(exclude_none=True)
    spanish_voices = {"es", "es-ar", "es-es-piper", "es-mx", "es-masculino", "es-agudo"}
    if "voice" in data and data["voice"] not in spanish_voices:
        raise HTTPException(400, "Laburito genera contenido únicamente en español. Elegí una voz española.")
    if "aspect" in data and data["aspect"] not in render.ASPECTS:
        raise HTTPException(400, "Formato no soportado")
    if "template" in data and data["template"] not in options.TEMPLATE_IDS:
        raise HTTPException(400, "Plantilla desconocida")
    if "caption_style" in data and data["caption_style"] not in options.CAPTION_STYLES:
        raise HTTPException(400, "Estilo de subtítulos desconocido")
    if "visual_style" in data and data["visual_style"] not in options.VISUAL_STYLE_IDS:
        raise HTTPException(400, "Estilo visual desconocido")
    if "video_type" in data:
        _validate_video_type(data["video_type"])
    if "transition_default" in data and data["transition_default"] not in options.TRANSITION_IDS:
        raise HTTPException(400, "Transición desconocida")
    if "resolution" in data and data["resolution"] not in options.RESOLUTIONS:
        raise HTTPException(400, "Resolución no soportada")
    if "fps" in data and data["fps"] not in options.FPS_OPTIONS:
        raise HTTPException(400, "FPS no soportado")
    if "music_volume" in data:
        data["music_volume"] = max(0.0, min(1.0, float(data["music_volume"])))
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        db.execute(f"UPDATE projects SET {sets}, updated_at=? WHERE id=?", (*data.values(), db.now(), project_id))
    return _project_full(project_id)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int):
    db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return {"ok": True}


@app.post("/api/projects/{project_id}/script")
def generate_script(project_id: int, replace: bool = True):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    notes = db.query("SELECT * FROM research_notes ORDER BY id DESC")
    sources = db.query("SELECT * FROM sources WHERE project_id=?", (project_id,))
    script = script_gen.generate_script(project, notes, sources)
    if replace:
        db.execute("DELETE FROM scenes WHERE project_id=?", (project_id,))
    base = 0 if replace else db.scalar("SELECT COALESCE(MAX(idx), -1) FROM scenes WHERE project_id=?", (project_id,), -1) + 1
    statements = []
    for scene in script["scenes"]:
        statements.append(
            (
                "INSERT INTO scenes(project_id, idx, title, narration, visual_query, transition, status, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, base + scene["idx"], scene["title"], scene["narration"], scene["visual_query"],
                 scene["transition"], "borrador", db.now(), db.now()),
            )
        )
    db.execute_many(statements)
    _touch_project(project_id)
    db.log("info", "script", f"Guion generado para proyecto {project_id}", {"scenes": len(script["scenes"])})
    return {"ok": True, "warnings": script["warnings"], "project": _project_full(project_id)}


@app.patch("/api/scenes/{scene_id}")
def patch_scene(scene_id: int, payload: ScenePatch):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    data = payload.model_dump(exclude_none=True)
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        db.execute(f"UPDATE scenes SET {sets}, updated_at=? WHERE id=?", (*data.values(), db.now(), scene_id))
        _touch_project(scene["project_id"])
    return db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))


@app.post("/api/scenes/{scene_id}/regenerate")
def regenerate(scene_id: int, variant: int = 0):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    project = db.query_one("SELECT * FROM projects WHERE id=?", (scene["project_id"],))
    result = script_gen.regenerate_scene(scene, project or {}, variant)
    db.execute(
        "UPDATE scenes SET narration=?, status=?, updated_at=? WHERE id=?",
        (result["narration"], result["status"], db.now(), scene_id),
    )
    _touch_project(scene["project_id"])
    return {"ok": True, "note": result["note"], "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))}


@app.post("/api/scenes/{scene_id}/visual")
def set_scene_visual(scene_id: int, payload: VisualIn):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    project_id = scene["project_id"]
    try:
        stored = media.download_asset(payload.url, db.MEDIA_DIR / "library" / str(project_id))
    except Exception as exc:
        raise HTTPException(400, f"No se pudo descargar el recurso: {exc}") from exc
    db.execute(
        "UPDATE scenes SET visual_path=?, visual_kind='recurso', visual_license=?, visual_author=?, visual_url=?, updated_at=? WHERE id=?",
        (stored["path"], payload.license, payload.author, payload.page or payload.url, db.now(), scene_id),
    )
    db.execute(
        "INSERT INTO assets(project_id, scene_id, kind, path, label, license, author, url, bytes, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (project_id, scene_id, "imagen", stored["path"], payload.title or "Recurso descargado",
         payload.license, payload.author, payload.page or payload.url, stored["bytes"], db.now()),
    )
    if payload.title or payload.page:
        db.execute(
            "INSERT INTO sources(project_id, scene_id, title, url, author, license, accessed_at, attribution, kind, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (project_id, scene_id, payload.title or "Recurso", payload.page or payload.url, payload.author,
             payload.license, db.now(), f"{payload.author} · {payload.license}", "imagen", db.now()),
        )
    return {"ok": True, "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))}


@app.post("/api/projects/{project_id}/scenes/order")
def reorder_scenes(project_id: int, ids: list[int] = Body(..., embed=True)):
    existing = {row["id"] for row in db.query("SELECT id FROM scenes WHERE project_id=?", (project_id,))}
    if set(ids) != existing:
        raise HTTPException(400, "La lista de escenas no coincide con el proyecto")
    db.execute_many(
        [("UPDATE scenes SET idx=?, updated_at=? WHERE id=?", (i, db.now(), scene_id)) for i, scene_id in enumerate(ids)]
    )
    return {"ok": True, "scenes": db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx", (project_id,))}


@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id: int):
    db.execute("DELETE FROM scenes WHERE id=?", (scene_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Render, exportación y cola
# --------------------------------------------------------------------------- #

@app.post("/api/projects/{project_id}/render", status_code=202)
def start_render(project_id: int):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    if not db.scalar("SELECT COUNT(*) FROM scenes WHERE project_id=?", (project_id,), 0):
        raise HTTPException(400, "El proyecto no tiene escenas: generá el guion primero")
    running = db.query_one(
        "SELECT id FROM jobs WHERE project_id=? AND kind='render_project' AND status IN ('en_cola','ejecutando')",
        (project_id,),
    )
    if running:
        return {"ok": True, "job_id": running["id"], "reused": True}
    job_id = worker.enqueue(project_id, "render_project")
    db.execute("UPDATE projects SET status='en_render', updated_at=? WHERE id=?", (db.now(), project_id))
    return {"ok": True, "job_id": job_id, "reused": False}


@app.post("/api/projects/{project_id}/export", status_code=202)
def start_export(project_id: int):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    job_id = worker.enqueue(project_id, "export_project")
    return {"ok": True, "job_id": job_id}


@app.post("/api/projects/{project_id}/cleanup")
def cleanup(project_id: int):
    job_id = worker.enqueue(project_id, "cleanup")
    return {"ok": True, "job_id": job_id}


@app.get("/api/projects/{project_id}/video")
def project_video(project_id: int):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    suffix = "short" if project.get("kind") == "short" else "documental"
    path = db.RENDER_DIR / str(project_id) / f"final_{suffix}.mp4"
    if not path.exists():
        raise HTTPException(404, "Todavía no hay vídeo renderizado")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/projects/{project_id}/download")
def project_download(project_id: int):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    assets = db.query(
        "SELECT path FROM assets WHERE project_id=? AND kind='export_zip' ORDER BY id DESC LIMIT 1", (project_id,)
    )
    path = Path(assets[0]["path"]) if assets else None
    if not path or not path.exists():
        try:
            path = render.export_project(project_id)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)


@app.get("/api/jobs")
def list_jobs(limit: int = 25):
    rows = db.query(
        "SELECT j.*, p.title AS project_title FROM jobs j LEFT JOIN projects p ON p.id=j.project_id "
        "ORDER BY j.id DESC LIMIT ?",
        (max(1, min(200, limit)),),
    )
    return rows


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "Tarea inexistente")
    if job["status"] in ("completado", "cancelado", "error"):
        return {"ok": True, "status": job["status"]}
    db.execute("UPDATE jobs SET status='cancelado', message=?, updated_at=? WHERE id=?",
               ("Cancelada por el usuario", db.now(), job_id))
    return {"ok": True, "status": "cancelado"}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int):
    job = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "Tarea inexistente")
    db.execute(
        "UPDATE jobs SET status='en_cola', progress=0, message=?, attempts=attempts+1, updated_at=? WHERE id=?",
        ("Reintentando", db.now(), job_id),
    )
    worker._wake.set()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Investigación de nichos y fuentes
# --------------------------------------------------------------------------- #

@app.get("/api/research/niches")
def list_niches():
    rows = db.query("SELECT * FROM niches ORDER BY demand DESC, competition ASC")
    for row in rows:
        row["opportunity"] = round(
            (row["demand"] * 0.5) + ((100 - row["competition"]) * 0.3) + (row["series_potential"] * 0.2)
            - (row["difficulty"] * 0.1),
            1,
        )
    return rows


@app.post("/api/research/niches", status_code=201)
def create_niche(payload: NicheIn):
    nid = db.execute(
        "INSERT INTO niches(name, demand, competition, trend, difficulty, copyright_risk, monetization, series_potential, notes, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (payload.name, payload.demand, payload.competition, payload.trend, payload.difficulty,
         payload.copyright_risk, payload.monetization, payload.series_potential, payload.notes, db.now(), db.now()),
    )
    return db.query_one("SELECT * FROM niches WHERE id=?", (nid,))


@app.delete("/api/research/niches/{niche_id}")
def delete_niche(niche_id: int):
    db.execute("DELETE FROM niches WHERE id=?", (niche_id,))
    return {"ok": True}


@app.get("/api/research/notes")
def list_notes(niche: str | None = None):
    if niche:
        return db.query("SELECT * FROM research_notes WHERE niche=? ORDER BY id DESC", (niche,))
    return db.query("SELECT * FROM research_notes ORDER BY id DESC")


@app.post("/api/research/notes", status_code=201)
def create_note(payload: NoteIn):
    if payload.evidence_level not in ("hecho", "indicio", "estimacion"):
        raise HTTPException(400, "Nivel de evidencia inválido")
    nid = db.execute(
        "INSERT INTO research_notes(niche, claim, evidence_level, source_url, accessed_at, methodology, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (payload.niche, payload.claim, payload.evidence_level, payload.source_url, db.now(), payload.methodology, db.now()),
    )
    return db.query_one("SELECT * FROM research_notes WHERE id=?", (nid,))


@app.delete("/api/research/notes/{note_id}")
def delete_note(note_id: int):
    db.execute("DELETE FROM research_notes WHERE id=?", (note_id,))
    return {"ok": True}


@app.post("/api/research/search")
def research_search(payload: SearchIn):
    if not payload.query.strip():
        raise HTTPException(400, "Escribí una búsqueda")
    return media.search_media(payload.query.strip(), payload.provider)


@app.get("/api/sources")
def list_sources(project_id: int | None = None):
    if project_id:
        return db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (project_id,))
    return db.query("SELECT * FROM sources ORDER BY id DESC LIMIT 200")


@app.post("/api/sources", status_code=201)
def create_source(payload: SourceIn):
    sid = db.execute(
        "INSERT INTO sources(project_id, scene_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (payload.project_id, payload.scene_id, payload.title, payload.url, payload.author, payload.license,
         db.now(), f"{payload.author} · {payload.license}", payload.kind, payload.notes, db.now()),
    )
    return db.query_one("SELECT * FROM sources WHERE id=?", (sid,))


# --------------------------------------------------------------------------- #
# Calendario editorial
# --------------------------------------------------------------------------- #

@app.get("/api/calendar")
def list_calendar(channel_id: int | None = None):
    sql = (
        "SELECT e.*, c.name AS channel_name, p.title AS project_title FROM calendar_entries e "
        "LEFT JOIN channels c ON c.id=e.channel_id LEFT JOIN projects p ON p.id=e.project_id "
    )
    if channel_id:
        return db.query(sql + "WHERE e.channel_id=? ORDER BY e.scheduled_for", (channel_id,))
    return db.query(sql + "ORDER BY e.scheduled_for")


@app.post("/api/calendar", status_code=201)
def create_calendar(payload: CalendarIn):
    if not db.query_one("SELECT id FROM channels WHERE id=?", (payload.channel_id,)):
        raise HTTPException(404, "Canal inexistente")
    cid = db.execute(
        "INSERT INTO calendar_entries(channel_id, project_id, scheduled_for, format, title, status, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (payload.channel_id, payload.project_id, payload.scheduled_for, payload.format,
         payload.title, "planificado", db.now()),
    )
    return db.query_one("SELECT * FROM calendar_entries WHERE id=?", (cid,))


@app.delete("/api/calendar/{entry_id}")
def delete_calendar(entry_id: int):
    db.execute("DELETE FROM calendar_entries WHERE id=?", (entry_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Biblioteca multimedia
# --------------------------------------------------------------------------- #

@app.get("/api/library")
def library():
    return db.query(
        "SELECT a.*, p.title AS project_title FROM assets a LEFT JOIN projects p ON p.id=a.project_id "
        "ORDER BY a.id DESC LIMIT 300"
    )


@app.delete("/api/library/{asset_id}")
def delete_asset(asset_id: int):
    asset = db.query_one("SELECT * FROM assets WHERE id=?", (asset_id,))
    if not asset:
        raise HTTPException(404, "Recurso inexistente")
    path = Path(asset["path"] or "")
    if path.exists() and str(path).startswith(str(db.DATA_DIR)) and asset["kind"] in ("imagen", "video_escena"):
        path.unlink(missing_ok=True)
    db.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Analítica real (importación CSV o carga manual)
# --------------------------------------------------------------------------- #

FIELD_MAP = {
    "impressions": ("impressions", "impresiones", "impresiones_totales"),
    "views": ("views", "visualizaciones", "reproducciones"),
    "ctr": ("ctr", "ctr_%", "porcentaje_ctr"),
    "retention": ("retention", "retencion", "retención", "retencion_media"),
    "avg_duration_sec": ("avg_duration", "duracion_media", "duración_media", "avg_view_duration"),
    "interactions": ("interactions", "interacciones", "likes_comentarios"),
    "subscribers": ("subscribers", "suscriptores"),
    "title": ("title", "titulo", "título", "video"),
    "format": ("format", "formato"),
    "published_at": ("published_at", "fecha", "publicado"),
}


def _pick(row: dict, field: str, default=None):
    for key in FIELD_MAP[field]:
        for candidate, value in row.items():
            if candidate.strip().lower() == key:
                return value
    return default


def _num(value, default=0):
    try:
        text = str(value).replace("%", "").replace(".", "").replace(",", ".") if isinstance(value, str) else value
        return float(text)
    except (TypeError, ValueError):
        return default


@app.get("/api/analytics")
def analytics(limit: int = 200):
    return db.query("SELECT * FROM analytics ORDER BY id DESC LIMIT ?", (max(1, min(1000, limit)),))


@app.get("/api/analytics/summary")
def analytics_summary():
    rows = db.query("SELECT * FROM analytics")
    if not rows:
        return {"count": 0, "summary": None,
                "note": "Sin datos. Importá un CSV real de tu panel; la app no inventa métricas."}
    total_views = sum(r["views"] for r in rows)
    total_impressions = sum(r["impressions"] for r in rows)
    ctr = round(100 * total_views / total_impressions, 2) if total_impressions else 0
    retention = round(sum(r["retention"] for r in rows) / len(rows), 2)
    by_format: dict[str, list] = {}
    for row in rows:
        by_format.setdefault(row["format"] or "sin formato", []).append(row)
    formats = [
        {"format": fmt, "videos": len(items), "views": sum(i["views"] for i in items),
         "retention": round(sum(i["retention"] for i in items) / len(items), 2)}
        for fmt, items in by_format.items()
    ]
    best = max(rows, key=lambda r: r["views"])
    return {
        "count": len(rows),
        "summary": {
            "views": total_views,
            "impressions": total_impressions,
            "ctr": ctr,
            "retention": retention,
            "subscribers": sum(r["subscribers"] for r in rows),
            "formats": sorted(formats, key=lambda f: f["views"], reverse=True),
            "best": {"title": best["title"], "views": best["views"], "retention": best["retention"]},
        },
        "hypotheses": [
            "Los datos muestran correlaciones, no causas: para afirmar causalidad hace falta un experimento controlado.",
            f"El mejor vídeo registrado es «{best['title']}» con {best['views']} visualizaciones: probá una variante de título/miniatura y compará.",
        ],
    }


@app.post("/api/analytics/import")
async def analytics_import(file: UploadFile = File(...), channel_id: int | None = None):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(400, "El CSV supera 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", "ignore")
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    inserted = 0
    statements = []
    for row in reader:
        title = str(_pick(row, "title", "") or "").strip()
        if not title and not _pick(row, "views"):
            continue
        impressions = int(_num(_pick(row, "impressions", 0)))
        views = int(_num(_pick(row, "views", 0)))
        ctr = _num(_pick(row, "ctr", 0))
        if not ctr and impressions:
            ctr = round(100 * views / impressions, 2)
        statements.append(
            (
                "INSERT INTO analytics(project_id, channel_id, title, format, impressions, views, ctr, retention, "
                "avg_duration_sec, interactions, subscribers, published_at, origin, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (None, channel_id, title[:200], str(_pick(row, "format", "") or ""), impressions, views, ctr,
                 _num(_pick(row, "retention", 0)), _num(_pick(row, "avg_duration_sec", 0)),
                 int(_num(_pick(row, "interactions", 0))), int(_num(_pick(row, "subscribers", 0))),
                 str(_pick(row, "published_at", "") or ""), "csv", db.now()),
            )
        )
        inserted += 1
    if not statements:
        raise HTTPException(400, "No se reconocieron filas. Encabezados esperados: title, views, impressions, ctr, retention…")
    db.execute_many(statements)
    db.log("info", "analytics", f"Importadas {inserted} filas de métricas")
    return {"ok": True, "inserted": inserted}


# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Publicación y auto-subida
# --------------------------------------------------------------------------- #

@app.get("/api/publish/destinations")
def publish_destinations():
    publish.ensure_schema()
    return {"destinations": publish.destinations(), "auto_publish_available": True}


@app.post("/api/tts/piper/install", status_code=202)
def install_piper_voice():
    status = tts.status()
    if status["piper_available"]:
        return {"installed": True, "message": "La voz neural ya está instalada."}
    if not status.get("piper_installed"):
        raise HTTPException(503, "Piper todavía no está instalado. Esperá a que el servidor despliegue requirements.txt.")
    existing = db.query_one(
        "SELECT id FROM jobs WHERE kind='install_piper_voice' AND status IN ('en_cola','ejecutando') ORDER BY id DESC LIMIT 1"
    )
    job_id = int(existing["id"]) if existing else worker.enqueue(None, "install_piper_voice", {})
    return {"installed": False, "job_id": job_id, "message": "Descarga de la voz neural agregada a la cola."}


@app.post("/api/youtube/oauth/start")
def youtube_oauth_start(request: Request):
    """Inicia OAuth oficial; el estado es aleatorio, de un solo uso y vence en 10 minutos."""
    credentials = publish.youtube_credentials()
    if not credentials["client_id"] or not credentials["client_secret"]:
        raise HTTPException(400, "Faltan YOUTUBE_CLIENT_ID y/o YOUTUBE_CLIENT_SECRET en el servidor.")
    redirect_uri = (
        os.environ.get("YOUTUBE_REDIRECT_URI", "").strip()
        or str(request.base_url).rstrip("/") + "/api/youtube/callback"
    )
    state = secrets.token_urlsafe(32)
    db.set_setting("youtube_oauth_state", state)
    db.set_setting("youtube_oauth_state_created", str(time.time()))
    db.set_setting("youtube_oauth_redirect_uri", redirect_uri)
    params = {
        "client_id": credentials["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params),
        "redirect_uri": redirect_uri,
    }


@app.get("/api/youtube/callback")
def youtube_oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Recibe el código de Google y guarda el refresh token solo en SQLite del servidor."""
    if error:
        return HTMLResponse(
            "<h2>Conexión de YouTube cancelada</h2><p>No se autorizó el canal.</p><a href='/#/ajustes'>Volver a Laburito</a>",
            status_code=400,
        )
    expected = db.get_setting("youtube_oauth_state", "")
    created = db.get_setting("youtube_oauth_state_created", "")
    redirect_uri = db.get_setting("youtube_oauth_redirect_uri", "")
    try:
        age = time.time() - float(created)
    except (TypeError, ValueError):
        age = 999999
    if not code or not state or not expected or not hmac.compare_digest(state, expected) or age > 600:
        raise HTTPException(403, "La autorización venció o no coincide. Volvé a iniciar la conexión de YouTube.")
    db.set_setting("youtube_oauth_state", "")
    db.set_setting("youtube_oauth_state_created", "")
    credentials = publish.youtube_credentials()
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    request = urllib.request.Request(
        publish.YOUTUBE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            token_data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:250]
        raise HTTPException(400, f"Google rechazó la autorización ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(502, f"No se pudo contactar a Google: {exc.reason}") from exc
    refresh_token = token_data.get("refresh_token")
    if refresh_token:
        db.set_setting("youtube_refresh_token", refresh_token)
    elif not credentials["refresh_token"]:
        raise HTTPException(400, "Google no devolvió un refresh token. Revocá el acceso anterior y volvé a autorizar con consentimiento.")
    try:
        publish.youtube_account_status()
    except publish.PublishError as exc:
        raise HTTPException(400, f"El token se guardó, pero no se pudo verificar el canal: {exc}") from exc
    if persistence.configured():
        try:
            persistence.sync_backup()
        except Exception as exc:
            raise HTTPException(503, f"YouTube quedó autorizado, pero no se pudo guardar la credencial en el respaldo persistente: {exc}") from exc
    return RedirectResponse(url="/#/ajustes", status_code=303)


@app.get("/api/youtube/status")
def youtube_status():
    try:
        return publish.youtube_account_status()
    except publish.PublishError as exc:
        raise HTTPException(400, str(exc)) from exc

@app.post("/api/projects/{project_id}/publish", status_code=202)
def publish_project(project_id: int, payload: publish.PublishIn):
    publish.ensure_schema()
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, f"El proyecto {project_id} no existe.")
    if payload.destination not in ("entrega", "youtube"):
        raise HTTPException(400, "Destino inválido: usá 'entrega' o 'youtube'.")
    if not publish.video_path(project).exists():
        raise HTTPException(400, "Todavía no hay un MP4 renderizado: ejecutá el render antes de publicar.")
    job_id = worker.enqueue(
        project_id,
        "publish_project",
        {"destination": payload.destination, "calendar_id": payload.calendar_id, "privacy": payload.privacy},
    )
    return {"ok": True, "job_id": job_id, "destination": payload.destination}


@app.get("/api/publications")
def publish_publications(project_id: int | None = None, limit: int = 50):
    publish.ensure_schema()
    return {"publications": publish.list_publications(project_id, limit)}


@app.get("/api/projects/{project_id}/auto-publish")
def get_auto_publish(project_id: int):
    try:
        return publish.auto_publish_settings(project_id)
    except publish.PublishError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/projects/{project_id}/auto-publish")
def set_auto_publish_endpoint(project_id: int, payload: publish.AutoPublishIn):
    try:
        return publish.set_auto_publish(project_id, payload.enabled, payload.destination)
    except publish.PublishError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/autopilot")
def list_autopilot():
    publish.ensure_schema()
    return {
        "rules": autopilot.list_rules(),
        "cadences": autopilot.CADENCE_OPTIONS,
        "destinations": publish.destinations(),
        "niches": db.query("SELECT id, name FROM niches ORDER BY name COLLATE NOCASE"),
        "channels": db.query("SELECT id, name FROM channels ORDER BY name COLLATE NOCASE"),
        "templates": options.TEMPLATES,
        "resolutions": options.RESOLUTION_INFO,
        "caption_styles": [
            {"id": key, "label": options.CAPTION_LABELS.get(key, key)} for key in options.CAPTION_STYLES
        ],
        "transitions": options.TRANSITIONS,
        "fps_options": options.FPS_OPTIONS,
    }


@app.post("/api/autopilot", status_code=201)
def create_autopilot(payload: AutopilotIn):
    try:
        return autopilot.create_rule(payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.patch("/api/autopilot/{rule_id}")
def patch_autopilot(rule_id: int, payload: AutopilotPatch):
    try:
        rule = autopilot.update_rule(rule_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not rule:
        raise HTTPException(404, "Regla inexistente")
    return rule


@app.delete("/api/autopilot/{rule_id}")
def delete_autopilot(rule_id: int):
    autopilot.delete_rule(rule_id)
    return {"ok": True}


@app.post("/api/autopilot/{rule_id}/run", status_code=202)
def run_autopilot(rule_id: int):
    try:
        return autopilot.run_rule(rule_id, force=True)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/settings")
def get_settings():
    return {k: db.get_setting(k) for k in db.DEFAULT_SETTINGS}


@app.put("/api/settings")
def put_settings(payload: SettingsIn):
    spanish_voices = {"es", "es-ar", "es-es-piper", "es-mx", "es-masculino", "es-agudo"}
    for key, value in payload.values.items():
        if key not in db.DEFAULT_SETTINGS or key == "default_language":
            continue
        if key == "default_voice" and value not in spanish_voices:
            raise HTTPException(400, "La voz predeterminada debe ser una voz española.")
        db.set_setting(key, value)
    # Idioma fijo: todo el contenido y toda la narración salen en español.
    db.set_setting("default_language", "es")
    return {k: db.get_setting(k) for k in db.DEFAULT_SETTINGS}


@app.post("/api/backup")
def make_backup():
    job_id = worker.enqueue(None, "backup")
    return {"ok": True, "job_id": job_id}


# --------------------------------------------------------------------------- #
# Archivos locales (validación estricta de rutas)
# --------------------------------------------------------------------------- #

@app.get("/media/{file_path:path}")
def serve_media(file_path: str):
    candidate = (db.DATA_DIR / file_path).resolve()
    root = db.DATA_DIR.resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(403, "Ruta no permitida")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(404, "Archivo inexistente")
    return FileResponse(candidate)


# --------------------------------------------------------------------------- #
# Interfaz web
# --------------------------------------------------------------------------- #

if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
else:
    @app.get("/", response_class=HTMLResponse)
    def placeholder():
        return (
            "<h1>AITuber Libre</h1><p>API activa. El frontend no está compilado todavía "
            "(<code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>).</p>"
            "<p>API docs: <a href='/docs'>/docs</a></p>"
        )
