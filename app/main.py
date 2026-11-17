"""AITuber Libre — API local (FastAPI) que sirve también la interfaz web."""
from __future__ import annotations

import csv
import io
import hmac
import hashlib
import json
import os
import platform
import secrets
import urllib.error
import urllib.parse
import urllib.request
import shutil
import time
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont, ImageStat

from . import autopilot, commands, db, media, options, persistence, publish, render, script_gen, skeleton, tts, worker, topic_engine

APP_VERSION = "1.1.0"
WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def _ensure_factory_channels() -> None:
    """Crea las dos fábricas internas si todavía no existen, sin duplicarlas."""
    factories = (
        ("Historias", "Historias originales estilo Reddit", "Intrigante y dinámico", "Gameplay vertical autorizado"),
        ("Frutinovelas", "Telenovelas de frutas por episodios", "Dramático, emotivo y divertido", "Personajes frutales recurrentes"),
    )
    for name, topic, tone, visual_identity in factories:
        existing = db.query_one("SELECT id FROM channels WHERE lower(trim(name))=lower(?) LIMIT 1", (name,))
        if existing:
            continue
        db.execute(
            "INSERT INTO channels(name,topic,language,audience,tone,visual_identity,formats,cadence,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (name, topic, "es", "Público general", tone, visual_identity, "short", "diario", db.now(), db.now()),
        )
        db.log("info", "channels", f"Fábrica interna creada automáticamente: {name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Restaurar la base antes de que init_db cree un SQLite vacío en un contenedor nuevo.
    persistence.restore_if_available()
    db.init_db()
    _ensure_factory_channels()
    worker.start()
    if not tts.status()["piper_available"]:
        pending_voice_job = db.query_one(
            "SELECT id FROM jobs WHERE kind='install_piper_voice' AND status IN ('en_cola','ejecutando') ORDER BY id DESC LIMIT 1"
        )
        if not pending_voice_job:
            worker.enqueue(None, "install_piper_voice", {})
            db.log("info", "tts", "Descarga automática de la voz neural española iniciada.")
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


class ChannelWatermarkIn(BaseModel):
    enabled: bool = True
    position: str = "bottom_right"
    scale: float = 0.12
    opacity: float = 0.85


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


class NaturalCreateIn(BaseModel):
    prompt: str
    channel_id: int | None = None


class ProjectDuplicateIn(BaseModel):
    title: str | None = None


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
    sfx_volume: float | None = None
    sfx_start_sec: float | None = None
    visual_trim_start_sec: float | None = None
    visual_trim_end_sec: float | None = None

class SceneIn(BaseModel):
    title: str = "Nueva escena"
    narration: str = ""
    visual_query: str = ""
    transition: str = "corte"


class SceneSplitIn(BaseModel):
    narration: str
    split_at: int


class TimelineOverlaySfxIn(BaseModel):
    effect: str
    start_sec: float = 0
    volume: float = 0.8


class TimelineOverlayMusicIn(BaseModel):
    bed_id: str
    start_sec: float = 0
    duration_sec: float = 45
    volume: float = 0.35


class TimelineOverlayVoiceIn(BaseModel):
    text: str
    start_sec: float = 0
    voice: str | None = None
    speed: int | None = None
    pitch: int | None = None
    volume: float = 1


class EditorHistoryIn(BaseModel):
    target: str
    target_id: int
    before: dict[str, object]
    after: dict[str, object]
    label: str = ""


class TimelineOverlayTextIn(BaseModel):
    text: str
    start_sec: float = 0
    duration_sec: float = 4
    x: float = 0.5
    y: float = 0.75
    width: float = 0.82
    opacity: float = 1


class TimelineOverlaySplitIn(BaseModel):
    at_sec: float


class TimelineOverlayPatch(BaseModel):
    title: str | None = None
    start_sec: float | None = None
    duration_sec: float | None = None
    source_start_sec: float | None = None
    source_end_sec: float | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    opacity: float | None = None
    volume: float | None = None


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


class IdeasIn(BaseModel):
    niche: str
    limit: int = 10


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
    auto_publish: bool = False


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
    project["timeline_overlays"] = db.query(
        "SELECT * FROM timeline_overlays WHERE project_id=? ORDER BY start_sec,id", (project_id,)
    )
    custom_thumbnail = db.query_one("SELECT path FROM assets WHERE project_id=? AND kind='thumbnail' ORDER BY id DESC LIMIT 1", (project_id,))
    project["thumbnail_path"] = custom_thumbnail.get("path") if custom_thumbnail else ""
    try:
        project["quality"] = json.loads(project.get("quality_json") or "{}")
    except json.JSONDecodeError:
        project["quality"] = {}
    project["jobs"] = db.query(
        "SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 5", (project_id,)
    )
    return project


def _touch_project(project_id: int) -> None:
    # Cualquier cambio en el guion, escenas o ajustes invalida el MP4 y el
    # informe anteriores: nunca mostrar un render viejo como si fuera actual.
    db.execute(
        "UPDATE projects SET updated_at=?, status='borrador', quality_json='{}' WHERE id=?",
        (db.now(), project_id),
    )

def _validate_video_type(video_type: str) -> None:
    if video_type not in options.VIDEO_TYPE_IDS:
        raise HTTPException(400, "Tipo de video desconocido")
    if video_type == "moving_images":
        return
    if video_type == "full_motion_ai":
        raise HTTPException(400, "La generación de video IA completo no tiene un modelo local viable para este equipo.")
    if video_type == "skeleton":
        return
    required = options.VIDEO_CLIP_MINIMUMS[video_type]
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


@app.post("/api/visual-style/analyze")
async def analyze_visual_style_reference(file: UploadFile = File(...)):
    """Extrae una descripción sencilla de paleta/iluminación de una imagen, sin servicios IA."""
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "Subí una imagen JPG, PNG o WebP.")
    raw = await file.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "La imagen de referencia no puede superar 8 MB.")
    try:
        opened = Image.open(io.BytesIO(raw))
        if opened.width * opened.height > 40_000_000:
            raise HTTPException(413, "La imagen tiene demasiados píxeles para analizarla.")
        image = opened.convert("RGB")
        image.thumbnail((96, 96))
        red, green, blue = ImageStat.Stat(image).mean[:3]
        brightness = (red + green + blue) / 3
        saturation = max(red, green, blue) - min(red, green, blue)
        contrast = ImageStat.Stat(image.convert("L")).stddev[0]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "No se pudo leer la imagen de referencia.") from exc

    if blue > red * 1.12 and blue > green * 1.04:
        palette = "paleta fría azulada"
    elif red > blue * 1.12 and red > green * 1.05:
        palette = "paleta cálida rojiza y dorada"
    elif green > red * 1.08 and green > blue * 1.04:
        palette = "paleta natural verde"
    else:
        palette = "paleta neutra equilibrada"
    light = "iluminación luminosa" if brightness > 165 else "iluminación oscura" if brightness < 90 else "iluminación media"
    contrast_text = "contraste alto" if contrast > 55 else "contraste suave" if contrast < 28 else "contraste medio"
    color_text = "colores intensos" if saturation > 75 else "colores apagados" if saturation < 28 else "saturación moderada"
    return {"visual_style_prompt": f"{palette}, {light}, {contrast_text}, {color_text}", "analysis": "Paleta y luz calculadas localmente; no se subió la imagen a ningún servicio externo."}


@app.post("/api/projects/{project_id}/thumbnail", status_code=201)
async def upload_project_thumbnail(project_id: int, file: UploadFile = File(...)):
    """Guarda una miniatura personalizada para el proyecto."""
    project = db.query_one("SELECT id, aspect, resolution FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    content_type = (file.content_type or "").lower()
    extension = Path(file.filename or "").suffix.lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"} and extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(400, "Subí una miniatura JPG, PNG o WebP.")
    raw = await file.read(12 * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(400, "La imagen está vacía.")
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(413, "La miniatura no puede superar 12 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 40_000_000:
                raise HTTPException(413, "La miniatura supera los 40 megapíxeles.")
            image = source.convert("RGB")
            image.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "El archivo no es una imagen válida.") from exc
    folder = db.MEDIA_DIR / "uploads" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"thumbnail-{time.time_ns()}.jpg"
    image.save(target, format="JPEG", quality=94, optimize=True)
    db.execute(
        "INSERT INTO assets(project_id,scene_id,kind,path,label,license,author,url,bytes,created_at) "
        "VALUES(?,NULL,'thumbnail',?,?,?,?,?,?,?)",
        (project_id, str(target), Path(file.filename or "Miniatura").name,
         "Imagen propia/autorizada por el usuario", "Usuario", "", target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return {"ok": True, "path": str(target)}


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
    existing_tracks = [path for path in db.MUSIC_DIR.iterdir() if path.is_file()]
    if len(existing_tracks) >= 5:
        raise HTTPException(400, "La biblioteca admite hasta cinco pistas. Quitá una antes de agregar otra.")
    filename = f"{stem}-{time.time_ns()}{extension}"
    target = db.MUSIC_DIR / filename
    target.write_bytes(content)
    return {"filename": filename, "music_library": sorted(p.name for p in db.MUSIC_DIR.iterdir() if p.is_file())}


@app.delete("/api/music/{filename}")
def delete_music(filename: str):
    """Permite reemplazar pistas propias sin borrar música usada por proyectos o reglas."""
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in {"", ".", ".."}:
        raise HTTPException(400, "Nombre de pista no válido.")
    target = db.MUSIC_DIR / safe_name
    if not target.is_file():
        raise HTTPException(404, "No se encontró la pista.")
    autopilot.ensure_schema()
    project_use = db.query_one("SELECT id FROM projects WHERE music=? LIMIT 1", (safe_name,))
    rule_use = db.query_one("SELECT id FROM autopilot_rules WHERE music=? LIMIT 1", (safe_name,))
    if project_use or rule_use:
        raise HTTPException(409, "La pista está asignada a un proyecto o Autopiloto. Cambiá esa selección antes de quitarla.")
    target.unlink()
    return {"deleted": safe_name, "music_library": sorted(p.name for p in db.MUSIC_DIR.iterdir() if p.is_file())}


CLIP_CATEGORIES = {"stock_footage", "minecraft", "subway", "background_video"}
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
    clip_limit = 1 if category == "background_video" else 5
    if len(list(folder.glob("*.mp4"))) >= clip_limit:
        raise HTTPException(400, f"Esta biblioteca ya tiene {clip_limit} clip(s). Quitá uno antes de agregar otro.")
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
        # Español e inglés están disponibles con síntesis local; Piper es solo español.
        "language": "es",
        "languages": [{"id": "es", "label": "Español"}, {"id": "en", "label": "English"}],
        "voices": [{**v, "available": tts_status["available"] and (v["id"] != "es-es-piper" or tts_status["piper_available"])} for v in tts_status["voices"]],
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
def voice_sample_preview(voice_id: str, speed: int = 150, pitch: int = 45):
    if voice_id not in tts.VOICES:
        raise HTTPException(404, "Voz inexistente")
    speed = max(80, min(300, int(speed)))
    pitch = max(0, min(99, int(pitch)))
    preview_dir = db.DATA_DIR / "voice_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"{voice_id}-{speed}-{pitch}.wav"
    try:
        if not preview.exists() or preview.stat().st_size < 1000:
            sample_text = (
                "Hello. This is an English voice sample for your videos. Choose the voice that best fits your channel."
                if tts.VOICES[voice_id].get("language") == "en"
                else "Hola. Esta es una muestra de voz en español para tus videos. Elegí la que mejor combine con tu canal."
            )
            tts.synthesize(sample_text, preview, voice=voice_id, speed=speed, pitch=pitch)
        return FileResponse(preview, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la muestra de voz: {exc}") from exc


@app.get("/api/scenes/{scene_id}/voice-preview")
def scene_voice_preview(scene_id: int):
    """Genera una muestra de la narración de una escena con la voz real del proyecto."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    narration = (scene.get("narration") or "").strip()
    if not narration:
        raise HTTPException(400, "Escribí la narración de la escena antes de escucharla.")
    project = db.query_one("SELECT voice,speed,pitch FROM projects WHERE id=?", (scene["project_id"],))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    voice = project.get("voice") or "es"
    speed = max(80, min(300, int(project.get("speed") or 150)))
    pitch = max(0, min(99, int(project.get("pitch") or 45)))
    signature = hashlib.sha256(
        f"{narration}|{voice}|{speed}|{pitch}".encode("utf-8")
    ).hexdigest()[:20]
    preview_dir = db.DATA_DIR / "voice_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview = preview_dir / f"scene-{scene_id}-{signature}.wav"
    try:
        if not preview.exists() or preview.stat().st_size < 1000:
            tts.synthesize(narration, preview, voice=voice, speed=speed, pitch=pitch)
        return FileResponse(preview, media_type="audio/wav")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la voz de esta escena: {exc}") from exc


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
        "note": "Render, voz y guiones funcionan localmente. Para conservar proyectos y archivos, ejecutá la app con el volumen ./data montado; YouTube requiere conectar la cuenta mediante OAuth.",
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


@app.post("/api/channels/{channel_id}/watermark", status_code=201)
async def upload_channel_watermark(channel_id: int, file: UploadFile = File(...)):
    channel = db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,))
    if not channel:
        raise HTTPException(404, "Canal inexistente")
    if file.content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(400, "El logo debe ser PNG, JPG o WebP.")
    raw = await file.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        raise HTTPException(400, "El logo supera el límite de 12 MB.")
    try:
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        image.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    except Exception as exc:
        raise HTTPException(400, "El archivo no es una imagen válida.") from exc
    folder = db.DATA_DIR / "channels" / str(channel_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "watermark.png"
    image.save(target, format="PNG", optimize=True)
    db.execute("UPDATE channels SET watermark_path=?, watermark_enabled=1, updated_at=? WHERE id=?",
               (str(target), db.now(), channel_id))
    return db.query_one("SELECT * FROM channels WHERE id=?", (channel_id,))


@app.put("/api/channels/{channel_id}/watermark")
def update_channel_watermark(channel_id: int, payload: ChannelWatermarkIn):
    if not db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,)):
        raise HTTPException(404, "Canal inexistente")
    positions = {"top_left", "top_right", "bottom_left", "bottom_right", "center"}
    if payload.position not in positions:
        raise HTTPException(400, "Posición de marca de agua inválida.")
    scale = max(0.04, min(0.35, float(payload.scale)))
    opacity = max(0.1, min(1.0, float(payload.opacity)))
    db.execute(
        "UPDATE channels SET watermark_enabled=?, watermark_position=?, watermark_scale=?, watermark_opacity=?, updated_at=? WHERE id=?",
        (int(payload.enabled), payload.position, scale, opacity, db.now(), channel_id),
    )
    return db.query_one("SELECT * FROM channels WHERE id=?", (channel_id,))


@app.delete("/api/channels/{channel_id}/watermark")
def delete_channel_watermark(channel_id: int):
    channel = db.query_one("SELECT watermark_path FROM channels WHERE id=?", (channel_id,))
    if not channel:
        raise HTTPException(404, "Canal inexistente")
    path = Path(channel.get("watermark_path") or "")
    if path.is_file():
        path.unlink(missing_ok=True)
    db.execute("UPDATE channels SET watermark_path='', watermark_enabled=0, updated_at=? WHERE id=?",
               (db.now(), channel_id))
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
        custom_thumbnail = db.query_one(
            "SELECT path FROM assets WHERE project_id=? AND kind='thumbnail' ORDER BY id DESC LIMIT 1",
            (row["id"],),
        )
        row["thumbnail_path"] = custom_thumbnail.get("path") if custom_thumbnail else ""
        row["job"] = db.query_one(
            "SELECT id, status, progress, message FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 1", (row["id"],)
        )
    return rows


@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectIn):
    data = payload.model_dump()
    if "voice" not in payload.model_fields_set:
        data["voice"] = db.get_setting("default_voice", "es")
    if data.get("template") in {"reddit_story", "frutinovela"} and not data.get("channel_id"):
        expected_name = "Frutinovelas" if data["template"] == "frutinovela" else "Historias"
        default_channel = db.query_one("SELECT id,name FROM channels WHERE lower(name)=?", (expected_name.lower(),))
        if not default_channel:
            raise HTTPException(400, f"No existe el canal interno {expected_name}.")
        data["channel_id"] = int(default_channel["id"])
    if data.get("channel_id"):
        selected_channel = db.query_one("SELECT name FROM channels WHERE id=?", (data["channel_id"],))
        if not selected_channel:
            raise HTTPException(404, "El canal interno seleccionado no existe.")
    if data.get("voice") not in tts.VOICES:
        raise HTTPException(400, "Elegí una voz disponible en español o inglés.")
    if data.get("aspect") and data["aspect"] not in render.ASPECTS:
        raise HTTPException(400, "Formato no soportado (16:9, 9:16, 1:1 o 4:5)")
    if data.get("visual_style") not in options.VISUAL_STYLE_IDS:
        raise HTTPException(400, "Estilo visual desconocido")
    _validate_video_type(data.get("video_type") or "moving_images")
    resolved = options.resolve_defaults(data)
    tpl = options.template(resolved["template"])
    duration = int(data.get("duration_target_sec") or tpl["default_duration"])
    duration = options.clamp_vertical_short_duration(resolved["template"], duration)
    pid = db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, "
        "template, visual_style, video_type, caption_style, transition_default, resolution, fps, music, music_volume, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("channel_id"), payload.title, payload.topic or payload.title, resolved["kind"],
            resolved["aspect"], "borrador", duration, data["voice"], payload.speed, payload.pitch,
            payload.notes, resolved["template"], payload.visual_style, payload.video_type,
            resolved["caption_style"], resolved["transition_default"],
            resolved["resolution"], resolved["fps"], resolved["music"],
            float(data["music_volume"]) if data.get("music_volume") is not None else 0.12,
            db.now(), db.now(),
        ),
    )
    db.log("info", "projects", f"Proyecto creado: {payload.title}", {"id": pid})
    return _project_full(pid)


@app.post("/api/create-from-prompt", status_code=202)
def create_from_prompt(payload: NaturalCreateIn):
    """Convierte una orden breve en un proyecto guionado y deja el render en la cola."""
    try:
        intent = commands.interpret_prompt(payload.prompt)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    channel_id = payload.channel_id
    if channel_id is not None:
        if not db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,)):
            raise HTTPException(404, "El canal seleccionado no existe.")
    else:
        if intent.get("channel_name"):
            channel = db.query_one(
                "SELECT id FROM channels WHERE lower(trim(name))=lower(?) LIMIT 1",
                (intent["channel_name"],),
            )
        else:
            channel = None
        if not channel:
            channel = db.query_one("SELECT id FROM channels ORDER BY id LIMIT 1")
        channel_id = int(channel["id"]) if channel else None

    project = create_project(ProjectIn(
        title=intent["title"],
        topic=intent["topic"],
        channel_id=channel_id,
        template=intent["template"],
        aspect=intent["aspect"],
        # Las voces reales pueden superar levemente la duración estimada; dejar
        # margen evita que una historia de 3 min falle por unos segundos al validar Shorts.
        duration_target_sec=100 if intent["template"] == "reddit_story" else None,
        notes=(
            "Orden original del usuario: " + intent["prompt"]
            + (
                "[LABURITO_META]" + json.dumps(
                    {"characters": "Manzana, Banana, Pera y Naranja"},
                    ensure_ascii=False,
                )
                if intent["template"] == "frutinovela" else ""
            )
        ),
    ))
    project_id = int(project["id"])
    try:
        script_result = generate_script(project_id, replace=True)
    except Exception as exc:
        db.log("error", "commands", f"No se pudo completar el guion de la orden: {exc}", {"project_id": project_id})
        raise HTTPException(
            503,
            f"El proyecto quedó guardado como borrador, pero no se pudo completar el guion: {exc}",
        ) from exc

    job_id = worker.enqueue(project_id, "render_project", {})
    db.log(
        "info", "commands", "Orden natural convertida en producción completa",
        {"project_id": project_id, "job_id": job_id, "template": intent["template"]},
    )
    return {
        "ok": True,
        "prompt": intent["prompt"],
        "interpretation": intent,
        "project_id": project_id,
        "job_id": job_id,
        "status": "en_cola",
        "warnings": script_result.get("warnings", []),
    }


@app.get("/api/projects/{project_id}/music-preview")
def project_music_preview(project_id: int):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    music_path = render._music_track(project)
    if not music_path or not Path(music_path).is_file():
        raise HTTPException(404, "Este proyecto no tiene una pista musical disponible.")
    suffix = Path(music_path).suffix.lower()
    media_type = {
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".m4a": "audio/mp4", ".flac": "audio/flac",
    }.get(suffix, "application/octet-stream")
    return FileResponse(music_path, media_type=media_type,
                        headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/projects/{project_id}")
def get_project(project_id: int):
    return _project_full(project_id)


@app.post("/api/projects/{project_id}/duplicate", status_code=201)
def duplicate_project(project_id: int, payload: ProjectDuplicateIn | None = None):
    """Duplica un proyecto editable, conservando guion, recursos y ajustes."""
    original = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not original:
        raise HTTPException(404, "Proyecto inexistente")
    stamp = db.now()
    project_data = {
        key: value for key, value in original.items()
        if key not in {"id"}
    }
    requested_title = (payload.title or "").strip() if payload else ""
    project_data["title"] = requested_title[:120] or (str(original.get("title") or "Video")[:110] + " (copia)")
    project_data["status"] = "borrador"
    project_data["quality_json"] = "{}"
    project_data["created_at"] = stamp
    project_data["updated_at"] = stamp
    project_columns = list(project_data)
    new_project_id = db.execute(
        "INSERT INTO projects(" + ",".join(project_columns) + ") VALUES(" +
        ",".join("?" for _ in project_columns) + ")",
        tuple(project_data[key] for key in project_columns),
    )

    scene_map: dict[int, int] = {}
    for scene in db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx,id", (project_id,)):
        scene_data = {key: value for key, value in scene.items() if key not in {"id"}}
        scene_data["project_id"] = new_project_id
        scene_data["audio_path"] = ""
        scene_data["audio_sec"] = 0
        scene_data["status"] = "borrador"
        scene_data["created_at"] = stamp
        scene_data["updated_at"] = stamp
        columns = list(scene_data)
        new_scene_id = db.execute(
            "INSERT INTO scenes(" + ",".join(columns) + ") VALUES(" +
            ",".join("?" for _ in columns) + ")",
            tuple(scene_data[key] for key in columns),
        )
        scene_map[int(scene["id"])] = new_scene_id

    for source in db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (project_id,)):
        source_data = {key: value for key, value in source.items() if key not in {"id"}}
        source_data["project_id"] = new_project_id
        source_data["scene_id"] = scene_map.get(int(source["scene_id"])) if source.get("scene_id") else None
        source_data["created_at"] = stamp
        columns = list(source_data)
        db.execute(
            "INSERT INTO sources(" + ",".join(columns) + ") VALUES(" +
            ",".join("?" for _ in columns) + ")",
            tuple(source_data[key] for key in columns),
        )

    for asset in db.query("SELECT * FROM assets WHERE project_id=? ORDER BY id", (project_id,)):
        asset_data = {key: value for key, value in asset.items() if key not in {"id"}}
        asset_data["project_id"] = new_project_id
        asset_data["scene_id"] = scene_map.get(int(asset["scene_id"])) if asset.get("scene_id") else None
        asset_data["created_at"] = stamp
        columns = list(asset_data)
        db.execute(
            "INSERT INTO assets(" + ",".join(columns) + ") VALUES(" +
            ",".join("?" for _ in columns) + ")",
            tuple(asset_data[key] for key in columns),
        )

    for overlay in db.query("SELECT * FROM timeline_overlays WHERE project_id=? ORDER BY start_sec,id", (project_id,)):
        overlay_data = {key: value for key, value in overlay.items() if key != "id"}
        if overlay.get("kind") == "text":
            source_path = Path(overlay.get("path") or "")
            if source_path.is_file():
                text_folder = db.MEDIA_DIR / "overlays" / str(new_project_id)
                text_folder.mkdir(parents=True, exist_ok=True)
                copied_text_path = text_folder / f"text-copy-{time.time_ns()}.png"
                shutil.copy2(source_path, copied_text_path)
                overlay_data["path"] = str(copied_text_path)
                db.execute(
                    "UPDATE assets SET path=?,bytes=? WHERE project_id=? AND path=? AND kind='capa_text'",
                    (str(copied_text_path), copied_text_path.stat().st_size, new_project_id, str(source_path)),
                )
        overlay_data["project_id"] = new_project_id
        overlay_data["created_at"] = stamp
        overlay_data["updated_at"] = stamp
        columns = list(overlay_data)
        db.execute(
            "INSERT INTO timeline_overlays(" + ",".join(columns) + ") VALUES(" +
            ",".join("?" for _ in columns) + ")",
            tuple(overlay_data[key] for key in columns),
        )

    db.log("info", "projects", f"Proyecto duplicado: {original.get('title')}", {
        "source_project_id": project_id, "project_id": new_project_id,
    })
    return _project_full(new_project_id)


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: int, payload: ProjectPatch):
    current_project = db.query_one("SELECT id, template, channel_id FROM projects WHERE id=?", (project_id,))
    if not current_project:
        raise HTTPException(404, "Proyecto inexistente")
    data = payload.model_dump(exclude_none=True)
    effective_template = data.get("template") or current_project.get("template")
    effective_channel_id = data.get("channel_id", current_project.get("channel_id"))
    if effective_template in {"reddit_story", "frutinovela"} and not effective_channel_id:
        expected_name = "Frutinovelas" if effective_template == "frutinovela" else "Historias"
        default_channel = db.query_one("SELECT id,name FROM channels WHERE lower(name)=?", (expected_name.lower(),))
        if not default_channel:
            raise HTTPException(400, f"No existe el canal interno {expected_name}.")
        effective_channel_id = int(default_channel["id"])
        data["channel_id"] = effective_channel_id
    if effective_channel_id:
        selected_channel = db.query_one("SELECT name FROM channels WHERE id=?", (effective_channel_id,))
        if not selected_channel:
            raise HTTPException(404, "El canal interno seleccionado no existe.")
    if effective_template in options.VERTICAL_SHORT_TEMPLATES:
        data["aspect"] = "9:16"
        if "duration_target_sec" in data:
            data["duration_target_sec"] = options.clamp_vertical_short_duration(effective_template, data["duration_target_sec"])
    if "voice" in data and data["voice"] not in tts.VOICES:
        raise HTTPException(400, "Elegí una voz disponible en español o inglés.")
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
    topic = (project.get("topic") or project.get("title") or "").strip()
    sources = db.query("SELECT * FROM sources WHERE project_id=?", (project_id,))
    # Cada proyecto investiga su propio tema; nunca reutilizar notas globales de otro video.
    notes = []
    research_warning = None
    is_fiction = project.get("template") in {"frutinovela", "reddit_story"}
    metadata_marker = "[LABURITO_META]"
    project_metadata = {}
    if metadata_marker in (project.get("notes") or ""):
        try:
            project_metadata = json.loads(project["notes"].split(metadata_marker, 1)[1].splitlines()[0])
            if project_metadata.get("characters"):
                project["content_pillars"] = project_metadata["characters"]
        except (TypeError, ValueError, json.JSONDecodeError):
            project_metadata = {}
    custom_script = str(project_metadata.get("script_text") or "").strip()
    if not custom_script and not is_fiction and not notes:
        try:
            research = topic_engine.research_specific_topic(topic)
            notes = research["notes"]
            for note in notes:
                db.execute(
                    "INSERT INTO research_notes(niche,claim,evidence_level,source_url,accessed_at,methodology,created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (topic, note["claim"], note["evidence_level"], note["source_url"], db.now(),
                     note["methodology"], db.now()),
                )
            known_urls = {source.get("url") or "" for source in sources}
            for note in notes:
                source_url = note.get("source_url") or ""
                if not source_url or source_url in known_urls:
                    continue
                is_academic = note.get("evidence_level") == "resumen académico"
                source_title = note.get("title") or research["source_title"]
                author = "OpenAlex / autores de la publicación" if is_academic else "Wikipedia contributors"
                license_text = "Resumen bibliográfico; consultar publicación original" if is_academic else "CC BY-SA 4.0"
                db.execute(
                    "INSERT INTO sources(project_id,title,url,author,license,accessed_at,attribution,kind,notes,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (project_id, source_title, source_url, author, license_text, db.now(),
                     author + " · " + license_text, "investigacion",
                     note.get("methodology") or "Fuente recuperada automáticamente para este guion.", db.now()),
                )
                known_urls.add(source_url)
            sources = db.query("SELECT * FROM sources WHERE project_id=?", (project_id,))
            db.log("info", "research", "Investigación automática integrada al guion", {
                "project_id": project_id, "academic_sources": len(research.get("academic_sources") or []),
            })
        except Exception as exc:
            research_warning = f"No se pudo completar la investigación automática: {exc}"
            db.log("warn", "research", research_warning, {"project_id": project_id})
    if project.get("template") == "frutinovela" and project.get("channel_id"):
        previous = db.query_one(
            "SELECT id,title,topic,notes FROM projects "
            "WHERE channel_id=? AND template='frutinovela' AND id<? "
            "AND EXISTS (SELECT 1 FROM scenes WHERE scenes.project_id=projects.id) "
            "ORDER BY id DESC LIMIT 1",
            (project["channel_id"], project_id),
        )
        episode_number = int(db.scalar(
            "SELECT COUNT(*) FROM projects WHERE channel_id=? AND template='frutinovela' AND id<? "
            "AND EXISTS (SELECT 1 FROM scenes WHERE scenes.project_id=projects.id)",
            (project["channel_id"], project_id), 0,
        )) + 1
        project["series_episode"] = episode_number
        if previous:
            if not project.get("content_pillars"):
                previous_notes = previous.get("notes") or ""
                if metadata_marker in previous_notes:
                    try:
                        previous_meta = json.loads(previous_notes.split(metadata_marker, 1)[1].splitlines()[0])
                        project["content_pillars"] = previous_meta.get("characters", "")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
            endings = db.query(
                "SELECT narration FROM scenes WHERE project_id=? ORDER BY idx DESC LIMIT 2",
                (previous["id"],),
            )
            ending_text = " ".join(row.get("narration", "") for row in reversed(endings))
            project["series_context"] = (
                f"Episodio {episode_number}. Continuación de {previous.get('title') or 'episodio anterior'}: "
                f"{previous.get('topic') or ''}. Últimas escenas: {ending_text}"
            )
    script = script_gen.script_from_text(project, custom_script) if custom_script else script_gen.generate_script(project, notes, sources)
    ollama_url = db.get_setting("ollama_url", "") or os.environ.get("OLLAMA_URL", "").strip()
    english_voice = str(project.get("voice") or "es").startswith("en")
    ollama_ready = bool(ollama_url and script_gen.ollama_model_available(ollama_url, "qwen2.5:1.5b-instruct"))
    if not custom_script and english_voice and not ollama_ready:
        raise HTTPException(
            503,
            "La redacción automática en inglés necesita Ollama/Qwen local. Iniciá Ollama o pegá un guion ya escrito en inglés.",
        )
    if not custom_script and ollama_ready:
        try:
            if english_voice:
                script = script_gen.translate_script_with_ollama(
                    ollama_url, "qwen2.5:1.5b-instruct", project, script
                )
                translated_title = script.get("translated_title") or project.get("title")
                if translated_title:
                    db.execute(
                        "UPDATE projects SET title=?, updated_at=? WHERE id=?",
                        (translated_title, db.now(), project_id),
                    )
                    project["title"] = translated_title
            elif project.get("template") in {"frutinovela", "reddit_story"}:
                script = script_gen.rewrite_fiction_with_ollama(
                    ollama_url, "qwen2.5:1.5b-instruct", project, script
                )
            elif any(note.get("source_url") and len((note.get("claim") or "")) >= 300 for note in notes):
                script = script_gen.rewrite_with_ollama(
                    ollama_url, "qwen2.5:1.5b-instruct", project, script, notes
                )
            db.log("info", "script", "Guion procesado con Ollama local", {"project_id": project_id})
        except Exception as exc:
            if english_voice:
                raise HTTPException(503, f"No se pudo traducir el guion automático al inglés: {exc}") from exc
            warning = f"Ollama no pudo reescribir el guion; se conserva el borrador local para que puedas editarlo: {exc}"
            db.log("warn", "script", warning, {"project_id": project_id})
            script.setdefault("warnings", []).append(warning)
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
    warnings = list(script.get("warnings") or [])
    if research_warning:
        warnings.append(research_warning)
    elif notes and not is_fiction and not custom_script:
        warnings.append("Investigación integrada al proyecto: las fuentes quedaron registradas automáticamente.")
    return {"ok": True, "warnings": warnings, "project": _project_full(project_id)}


@app.post("/api/projects/{project_id}/scenes", status_code=201)
def create_scene(project_id: int, payload: SceneIn):
    project = db.query_one("SELECT id FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    next_idx = int(db.scalar(
        "SELECT COALESCE(MAX(idx), -1) + 1 FROM scenes WHERE project_id=?",
        (project_id,), 0,
    ))
    if next_idx >= 400:
        raise HTTPException(400, "Un proyecto admite hasta 400 escenas.")
    scene_id = db.execute(
        "INSERT INTO scenes(project_id,idx,title,narration,visual_query,transition,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (project_id, next_idx, payload.title.strip() or f"Escena {next_idx + 1}",
         payload.narration, payload.visual_query, payload.transition, "borrador", db.now(), db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))


@app.patch("/api/scenes/{scene_id}")
def patch_scene(scene_id: int, payload: ScenePatch):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    data = payload.model_dump(exclude_none=True)
    if "narration" in data and data["narration"] != scene.get("narration"):
        data["audio_path"] = ""
        data["audio_sec"] = 0
    trim_start = float(data.get("visual_trim_start_sec", scene.get("visual_trim_start_sec") or 0))
    trim_end = float(data.get("visual_trim_end_sec", scene.get("visual_trim_end_sec") or 0))
    if trim_start < 0 or trim_end < 0:
        raise HTTPException(400, "Los puntos de recorte no pueden ser negativos.")
    if trim_end and trim_end <= trim_start:
        raise HTTPException(400, "El final del recorte debe ser posterior al inicio.")
    source_duration = float(scene.get("visual_source_duration_sec") or 0)
    if source_duration > 0 and (trim_start >= source_duration or (trim_end and trim_end > source_duration)):
        raise HTTPException(400, f"El recorte debe quedar dentro del video original ({source_duration:.1f} s).")
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        db.execute(f"UPDATE scenes SET {sets}, updated_at=? WHERE id=?", (*data.values(), db.now(), scene_id))
        _touch_project(scene["project_id"])
    return db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))


@app.post("/api/scenes/{scene_id}/duplicate", status_code=201)
def duplicate_scene(scene_id: int):
    """Duplica el clip completo: visual, efecto, transición y fuentes."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    stamp = db.now()
    db.execute(
        "UPDATE scenes SET idx=idx+1, updated_at=? WHERE project_id=? AND idx>?",
        (stamp, scene["project_id"], scene["idx"]),
    )
    scene_data = {key: value for key, value in scene.items() if key != "id"}
    scene_data.update({
        "idx": int(scene["idx"]) + 1,
        "title": (str(scene.get("title") or "Escena")[:100] + " (copia)"),
        "audio_path": "",
        "audio_sec": 0,
        "status": "borrador",
        "created_at": stamp,
        "updated_at": stamp,
    })
    columns = list(scene_data)
    new_scene_id = db.execute(
        "INSERT INTO scenes(" + ",".join(columns) + ") VALUES(" +
        ",".join("?" for _ in columns) + ")",
        tuple(scene_data[key] for key in columns),
    )
    for asset in db.query("SELECT * FROM assets WHERE scene_id=? ORDER BY id", (scene_id,)):
        asset_data = {key: value for key, value in asset.items() if key != "id"}
        asset_data["scene_id"] = new_scene_id
        asset_data["created_at"] = stamp
        asset_columns = list(asset_data)
        db.execute(
            "INSERT INTO assets(" + ",".join(asset_columns) + ") VALUES(" +
            ",".join("?" for _ in asset_columns) + ")",
            tuple(asset_data[key] for key in asset_columns),
        )
    for source in db.query("SELECT * FROM sources WHERE scene_id=? ORDER BY id", (scene_id,)):
        source_data = {key: value for key, value in source.items() if key != "id"}
        source_data["scene_id"] = new_scene_id
        source_data["created_at"] = stamp
        source_columns = list(source_data)
        db.execute(
            "INSERT INTO sources(" + ",".join(source_columns) + ") VALUES(" +
            ",".join("?" for _ in source_columns) + ")",
            tuple(source_data[key] for key in source_columns),
        )
    _touch_project(scene["project_id"])
    return db.query_one("SELECT * FROM scenes WHERE id=?", (new_scene_id,))


@app.post("/api/scenes/{scene_id}/split", status_code=201)
def split_scene(scene_id: int, payload: SceneSplitIn):
    """Divide una escena en dos en la posición de texto elegida en el editor."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    narration = (payload.narration or "").strip()
    cut = max(0, min(len(narration), int(payload.split_at)))
    if cut <= 20 or cut >= len(narration) - 20:
        raise HTTPException(400, "Elegí un punto dentro del texto, dejando al menos 20 caracteres a cada lado.")
    if cut < len(narration) and not narration[cut].isspace():
        before = max(narration.rfind(" ", max(0, cut - 40), cut), narration.rfind("\n", max(0, cut - 40), cut))
        after_space = narration.find(" ", cut, min(len(narration), cut + 40))
        candidates = [position for position in (before, after_space) if position > 0]
        if candidates:
            cut = min(candidates, key=lambda position: abs(position - cut))
    first_text = narration[:cut].strip()
    second_text = narration[cut:].strip()
    if len(first_text) < 20 or len(second_text) < 20:
        raise HTTPException(400, "La división debe dejar dos escenas con texto suficiente.")

    stamp = db.now()
    db.execute(
        "UPDATE scenes SET narration=?, audio_path='', audio_sec=0, status='borrador', updated_at=? WHERE id=?",
        (first_text, stamp, scene_id),
    )
    db.execute(
        "UPDATE scenes SET idx=idx+1, updated_at=? WHERE project_id=? AND idx>?",
        (stamp, scene["project_id"], scene["idx"]),
    )
    second_id = db.execute(
        "INSERT INTO scenes(project_id,idx,title,narration,visual_query,visual_path,visual_kind,visual_license,visual_author,visual_url,transition,status,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            scene["project_id"], int(scene["idx"]) + 1,
            (str(scene.get("title") or "Escena")[:100] + " (continuación)"),
            second_text, scene.get("visual_query") or "", scene.get("visual_path") or "",
            scene.get("visual_kind") or "", scene.get("visual_license") or "",
            scene.get("visual_author") or "", scene.get("visual_url") or "",
            scene.get("transition") or "corte", "borrador", stamp, stamp,
        ),
    )
    _touch_project(scene["project_id"])
    return {
        "ok": True,
        "first": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,)),
        "second": db.query_one("SELECT * FROM scenes WHERE id=?", (second_id,)),
    }


@app.post("/api/scenes/{scene_id}/regenerate")
def regenerate(scene_id: int, variant: int = 0):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    project = db.query_one("SELECT * FROM projects WHERE id=?", (scene["project_id"],))
    project = project or {}
    result = None
    ollama_url = db.get_setting("ollama_url", "") or os.environ.get("OLLAMA_URL", "").strip()
    if ollama_url and script_gen.ollama_model_available(ollama_url, "qwen2.5:1.5b-instruct"):
        try:
            result = script_gen.regenerate_scene_with_ollama(
                ollama_url, "qwen2.5:1.5b-instruct", project, scene, variant
            )
            db.log("info", "script", "Escena regenerada con Ollama local", {
                "project_id": scene["project_id"], "scene_id": scene_id,
            })
        except Exception as exc:
            db.log("warn", "script", f"Falló la regeneración local; se usa la variante de respaldo: {exc}", {
                "project_id": scene["project_id"], "scene_id": scene_id,
            })
    if result is None:
        result = script_gen.regenerate_scene(scene, project, variant)
    db.execute(
        "UPDATE scenes SET narration=?, status=?, updated_at=? WHERE id=?",
        (result["narration"], result["status"], db.now(), scene_id),
    )
    _touch_project(scene["project_id"])
    return {"ok": True, "note": result["note"], "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))}


@app.post("/api/scenes/{scene_id}/regenerate-visual")
def regenerate_scene_visual(scene_id: int, variant: int = 0):
    """Busca y asigna una imagen alternativa con licencia desde fuentes abiertas."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    query = (scene.get("visual_query") or scene.get("title") or "").strip()
    if not query:
        raise HTTPException(400, "La escena necesita una descripción visual.")
    found = media.search_media(query, "all")
    candidates = [
        item for item in (found.get("results") or [])
        if item.get("url") and item.get("license") and item.get("provider") in {"Openverse", "Wikimedia Commons"}
    ]
    current_url = scene.get("visual_url") or ""
    alternatives = [item for item in candidates if current_url not in {item.get("url") or "", item.get("page") or ""}]
    choices = alternatives or candidates
    if not choices:
        raise HTTPException(503, "No hay imágenes abiertas disponibles ahora. Probá con otra descripción o subí un recurso propio.")
    selected = choices[max(0, int(variant)) % len(choices)]
    try:
        stored = media.download_asset(selected["url"], db.MEDIA_DIR / "library" / str(scene["project_id"]))
    except Exception as exc:
        raise HTTPException(400, f"No se pudo descargar la alternativa visual: {exc}") from exc
    if not str(stored.get("content_type") or "").startswith("image/"):
        Path(stored["path"]).unlink(missing_ok=True)
        raise HTTPException(400, "La fuente devolvió un recurso que no es una imagen.")
    license_name = selected.get("license") or "Ver licencia original"
    author = selected.get("author") or "Desconocido"
    page = selected.get("page") or selected["url"]
    db.execute(
        "UPDATE scenes SET visual_path=?,visual_kind='recurso',visual_license=?,visual_author=?,visual_url=?,"
        "visual_source_duration_sec=0,visual_trim_start_sec=0,visual_trim_end_sec=0,updated_at=? WHERE id=?",
        (stored["path"], license_name, author, page, db.now(), scene_id),
    )
    db.execute(
        "INSERT INTO assets(project_id,scene_id,kind,path,label,license,author,url,bytes,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (scene["project_id"], scene_id, "imagen", stored["path"], selected.get("title") or "Visual alternativo",
         license_name, author, page, stored["bytes"], db.now()),
    )
    db.execute(
        "INSERT INTO sources(project_id,scene_id,title,url,author,license,accessed_at,attribution,kind,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (scene["project_id"], scene_id, selected.get("title") or "Visual alternativo", page, author,
         license_name, db.now(), f"{author} · {license_name}", "imagen", db.now()),
    )
    _touch_project(scene["project_id"])
    return {"ok": True, "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,)),
            "source": selected, "alternatives": len(choices)}


@app.post("/api/scenes/{scene_id}/image", status_code=201)
@app.post("/api/scenes/{scene_id}/media", status_code=201)
async def upload_scene_image(scene_id: int, file: UploadFile = File(...)):
    """Asigna una imagen o un clip de video propio/autorizado a una escena."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    content_type = (file.content_type or "").lower()
    extension = Path(file.filename or "").suffix.lower()
    image_types = {"image/jpeg", "image/png", "image/webp"}
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    video_types = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}
    video_exts = {".mp4", ".mov", ".webm", ".mkv"}
    is_image = content_type in image_types or extension in image_exts
    is_video = content_type in video_types or extension in video_exts
    if not is_image and not is_video:
        raise HTTPException(400, "Subí una imagen JPG/PNG/WebP o un video MP4/MOV/WebM/MKV.")
    limit = 12 * 1024 * 1024 if is_image else 250 * 1024 * 1024
    raw = await file.read(limit + 1)
    if not raw:
        raise HTTPException(400, "El archivo está vacío.")
    if len(raw) > limit:
        raise HTTPException(413, f"El archivo supera el límite de {limit // (1024 * 1024)} MB.")

    project_id = int(scene["project_id"])
    folder = db.MEDIA_DIR / "uploads" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    source_duration = 0.0
    if is_image:
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    raise HTTPException(413, "La imagen supera los 40 megapíxeles.")
                image = source.convert("RGB")
                image.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, "El archivo no es una imagen válida.") from exc
        target = folder / f"scene-{scene_id}-{stamp}.jpg"
        image.save(target, format="JPEG", quality=92, optimize=True)
        asset_kind = "imagen"
        visual_kind = "recurso"
        label = "Imagen propia/autorizada por el usuario"
    else:
        source_path = db.TMP_DIR / f"scene-{scene_id}-{stamp}{extension}"
        target = folder / f"scene-{scene_id}-{stamp}.mp4"
        db.TMP_DIR.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(raw)
        try:
            info = media.probe_video(source_path)
            source_duration = float(info.get("duration") or 0)
            if not info.get("width") or not info.get("height") or source_duration <= 0:
                raise HTTPException(400, "El archivo no contiene un video válido.")
            proc = media.run([
                media.ffmpeg(), "-y", "-i", str(source_path), "-map", "0:v:0",
                "-an", "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(target),
            ], timeout=300)
            if proc.returncode != 0 or not target.is_file() or target.stat().st_size < 1024:
                detail = (proc.stderr or b"").decode("utf-8", "ignore")[-500:]
                raise HTTPException(400, "No se pudo convertir el video: " + detail)
        finally:
            source_path.unlink(missing_ok=True)
        asset_kind = "video"
        visual_kind = "video_fondo"
        label = "Video propio/autorizado por el usuario"

    db.execute(
        "UPDATE scenes SET visual_path=?, visual_kind=?, visual_license=?, visual_author='Usuario', "
        "visual_url='archivo local subido', visual_source_duration_sec=?, visual_trim_start_sec=0, "
        "visual_trim_end_sec=0, updated_at=? WHERE id=?",
        (str(target), visual_kind, label, source_duration, db.now(), scene_id),
    )
    db.execute(
        "INSERT INTO assets(project_id,scene_id,kind,path,label,license,author,url,bytes,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (project_id, scene_id, asset_kind, str(target), Path(file.filename or label).name,
         label, "Usuario", "", target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return {"ok": True, "media_type": asset_kind, "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))}


@app.post("/api/scenes/{scene_id}/sound", status_code=201)
async def upload_scene_sound(scene_id: int, file: UploadFile = File(...)):
    """Carga un efecto de sonido local para una escena."""
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    content_type = (file.content_type or "").lower()
    extension = Path(file.filename or "").suffix.lower()
    allowed_types = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mp4", "audio/flac"}
    allowed_exts = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
    if content_type not in allowed_types and extension not in allowed_exts:
        raise HTTPException(400, "Subí un audio MP3, WAV, OGG, M4A o FLAC.")
    raw = await file.read(50 * 1024 * 1024 + 1)
    if not raw:
        raise HTTPException(400, "El audio está vacío.")
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(413, "El audio no puede superar 50 MB.")
    project_id = int(scene["project_id"])
    folder = db.MEDIA_DIR / "uploads" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    source_path = db.TMP_DIR / f"scene-{scene_id}-{stamp}{extension}"
    target = folder / f"scene-{scene_id}-sfx-{stamp}.wav"
    db.TMP_DIR.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(raw)
    try:
        probe = media.run([
            media.ffprobe(), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name", "-of", "json", str(source_path),
        ], timeout=60)
        try:
            audio_streams = json.loads(probe.stdout.decode("utf-8") or "{}").get("streams", [])
        except json.JSONDecodeError:
            audio_streams = []
        if probe.returncode != 0 or not audio_streams:
            raise HTTPException(400, "El archivo no contiene una pista de audio válida.")
        proc = media.run([
            media.ffmpeg(), "-y", "-i", str(source_path), "-vn", "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(target),
        ], timeout=180)
        if proc.returncode != 0 or not target.is_file() or target.stat().st_size < 1024:
            detail = (proc.stderr or b"").decode("utf-8", "ignore")[-400:]
            raise HTTPException(400, "No se pudo convertir el efecto de sonido: " + detail)
    finally:
        source_path.unlink(missing_ok=True)
    db.execute(
        "UPDATE scenes SET sfx_path=?, sfx_volume=0.8, sfx_start_sec=0, updated_at=? WHERE id=?",
        (str(target), db.now(), scene_id),
    )
    db.execute(
        "INSERT INTO assets(project_id,scene_id,kind,path,label,license,author,url,bytes,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (project_id, scene_id, "efecto_sonido", str(target), Path(file.filename or "Efecto de sonido").name,
         "Archivo propio/autorizado por el usuario", "Usuario", "", target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return {"ok": True, "scene": db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))}


@app.delete("/api/scenes/{scene_id}/sound")
def delete_scene_sound(scene_id: int):
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    db.execute("UPDATE scenes SET sfx_path='', updated_at=? WHERE id=?", (db.now(), scene_id))
    _touch_project(scene["project_id"])
    return {"ok": True}


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
        "UPDATE scenes SET visual_path=?, visual_kind='recurso', visual_license=?, visual_author=?, visual_url=?, "
        "visual_source_duration_sec=0, visual_trim_start_sec=0, visual_trim_end_sec=0, updated_at=? WHERE id=?",
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
    scene = db.query_one("SELECT * FROM scenes WHERE id=?", (scene_id,))
    if not scene:
        raise HTTPException(404, "Escena inexistente")
    db.execute("DELETE FROM editor_history WHERE project_id=? AND target='scene' AND target_id=?",
               (scene["project_id"], scene_id))
    db.execute("DELETE FROM scenes WHERE id=?", (scene_id,))
    _touch_project(scene["project_id"])
    return {"ok": True}


def _write_timeline_text_image(text: str, target: Path) -> None:
    text = " ".join((text or "").split())[:240]
    if not text:
        raise HTTPException(400, "Escribí el texto que querés superponer.")
    font_file = media.font_path()
    font = ImageFont.truetype(font_file, 58) if font_file else ImageFont.load_default()
    lines = textwrap.wrap(text, width=28, break_long_words=True)[:4]
    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    boxes = [probe.textbbox((0, 0), line, font=font, stroke_width=2) for line in lines]
    line_heights = [max(1, box[3] - box[1]) for box in boxes]
    text_width = max((box[2] - box[0] for box in boxes), default=1)
    padding = 36
    line_gap = 14
    height = sum(line_heights) + max(0, len(lines) - 1) * line_gap + padding * 2
    width = max(600, min(1600, text_width + padding * 2))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, width - 4, height - 4), radius=22, fill=(0, 0, 0, 190))
    y = padding
    for line, line_height in zip(lines, line_heights):
        draw.text((padding, y), line, font=font, fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 210))
        y += line_height + line_gap
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="PNG", optimize=True)


@app.post("/api/projects/{project_id}/timeline-overlays/sfx", status_code=201)
def create_timeline_sfx_overlay(project_id: int, payload: TimelineOverlaySfxIn):
    project = db.query_one("SELECT id FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    if not 0 <= payload.start_sec <= 3600 or not 0 <= payload.volume <= 2:
        raise HTTPException(400, "La posición o el volumen del efecto no son válidos.")
    presets = {
        "whoosh": ("Barrido", "anoisesrc=color=white:amplitude=0.32:duration=1.2",
                   "highpass=f=350,lowpass=f=6500,afade=t=in:d=0.12,afade=t=out:st=0.55:d=0.65"),
        "impact": ("Impacto", "anoisesrc=color=pink:amplitude=0.55:duration=0.9",
                   "lowpass=f=1300,afade=t=out:st=0.05:d=0.85,aecho=0.8:0.7:90:0.35"),
        "chime": ("Campanilla", "sine=frequency=880:duration=1.5",
                  "afade=t=out:st=0.2:d=1.3,aecho=0.8:0.8:220:0.3"),
        "click": ("Clic", "anoisesrc=color=white:amplitude=0.4:duration=0.14",
                  "highpass=f=2200,afade=t=out:st=0.01:d=0.13"),
        "riser": ("Subida", "anoisesrc=color=white:amplitude=0.2:duration=2.0",
                  "highpass=f=250,lowpass=f=9000,volume='0.15+0.75*t/2':eval=frame,afade=t=out:st=1.7:d=0.3"),
    }
    if payload.effect not in presets:
        raise HTTPException(400, "Ese efecto no está disponible.")
    label, source, filters = presets[payload.effect]
    folder = db.MEDIA_DIR / "overlays" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"sfx-{payload.effect}-{time.time_ns()}.wav"
    try:
        proc = media.run([
            media.ffmpeg(), "-y", "-f", "lavfi", "-i", source, "-af", filters,
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(target),
        ], timeout=60)
        if proc.returncode != 0 or not target.is_file() or target.stat().st_size < 1024:
            detail = (proc.stderr or b"").decode("utf-8", "ignore")[-300:]
            raise RuntimeError(detail or "FFmpeg no pudo crear el archivo.")
        duration = float(media.probe_audio(target).get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("El efecto generado no contiene audio.")
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(503, f"No se pudo generar el efecto local: {exc}") from exc
    overlay_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,source_start_sec,source_end_sec,source_duration_sec,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, "audio", str(target), label, payload.start_sec, duration, 0.62, 0.62, 0.32, 1.0,
         payload.volume, 0.0, 0.0, duration, db.now(), db.now()),
    )
    db.execute(
        "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "efecto_generado", str(target), label, target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.post("/api/projects/{project_id}/timeline-overlays/music", status_code=201)
def create_timeline_music_overlay(project_id: int, payload: TimelineOverlayMusicIn):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    if payload.bed_id not in options.MUSIC_IDS:
        raise HTTPException(400, "La cama musical seleccionada no existe.")
    if not 0 <= payload.start_sec <= 3600 or not 5 <= payload.duration_sec <= 3600 or not 0 <= payload.volume <= 2:
        raise HTTPException(400, "La posición, duración o volumen de la música no son válidos.")
    try:
        music_path = media.ensure_music_bed(payload.bed_id)
        duration = float(media.probe_audio(music_path).get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("La cama musical no contiene audio.")
    except Exception as exc:
        raise HTTPException(503, f"No se pudo generar la música local: {exc}") from exc
    bed = next((item for item in options.MUSIC_BEDS if item["id"] == payload.bed_id), options.MUSIC_BEDS[0])
    overlay_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,source_start_sec,source_end_sec,source_duration_sec,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, "audio", str(music_path), bed["label"], payload.start_sec,
         min(payload.duration_sec, 3600), 0.62, 0.62, 0.32, 1.0, payload.volume, 0.0, 0.0, duration, db.now(), db.now()),
    )
    db.execute(
        "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "musica_generada", str(music_path), bed["label"], music_path.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.post("/api/projects/{project_id}/timeline-overlays/voice", status_code=201)
def create_timeline_voice_overlay(project_id: int, payload: TimelineOverlayVoiceIn):
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise HTTPException(404, "Proyecto inexistente")
    text = " ".join((payload.text or "").split())[:12000]
    if not text:
        raise HTTPException(400, "Escribí el texto de la voz en off.")
    if not 0 <= payload.start_sec <= 3600 or not 0 <= payload.volume <= 2:
        raise HTTPException(400, "La posición o el volumen de la voz no son válidos.")
    folder = db.MEDIA_DIR / "overlays" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"voice-{time.time_ns()}.wav"
    try:
        tts.synthesize(
            text, target,
            voice=payload.voice or project.get("voice") or "es",
            speed=payload.speed if payload.speed is not None else (project.get("speed") or 150),
            pitch=payload.pitch if payload.pitch is not None else (project.get("pitch") or 45),
        )
        audio_info = media.probe_audio(target)
        duration = float(audio_info.get("duration") or 0)
        if not audio_info.get("codec") or duration <= 0:
            raise RuntimeError("El motor de voz no produjo un audio válido.")
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(503, f"No se pudo generar la voz en off local: {exc}") from exc
    title = (text[:72] + "…") if len(text) > 72 else text
    overlay_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,source_start_sec,source_end_sec,source_duration_sec,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, "audio", str(target), title, payload.start_sec, min(duration, 3600),
         0.62, 0.62, 0.32, 1.0, payload.volume, 0.0, 0.0, duration, db.now(), db.now()),
    )
    db.execute(
        "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "voz_en_off", str(target), title, target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.post("/api/projects/{project_id}/timeline-overlays/text", status_code=201)
def create_timeline_text_overlay(project_id: int, payload: TimelineOverlayTextIn):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    text = " ".join((payload.text or "").split())[:240]
    if not text:
        raise HTTPException(400, "Escribí el texto que querés superponer.")
    if payload.start_sec < 0 or not 0.1 <= payload.duration_sec <= 3600:
        raise HTTPException(400, "La posición o duración del texto no son válidas.")
    if not 0 <= payload.x <= 1 or not 0 <= payload.y <= 1 or not 0.05 <= payload.width <= 1 or not 0 <= payload.opacity <= 1:
        raise HTTPException(400, "La posición, tamaño u opacidad del texto no son válidos.")
    folder = db.MEDIA_DIR / "overlays" / str(project_id)
    target = folder / f"text-{time.time_ns()}.png"
    _write_timeline_text_image(text, target)
    overlay_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, "text", str(target), text, payload.start_sec, payload.duration_sec,
         payload.x, payload.y, payload.width, payload.opacity, 1.0, db.now(), db.now()),
    )
    db.execute(
        "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "capa_text", str(target), text[:120], target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.get("/api/projects/{project_id}/timeline-overlays")
def list_timeline_overlays(project_id: int):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    return db.query("SELECT * FROM timeline_overlays WHERE project_id=? ORDER BY start_sec,id", (project_id,))


@app.post("/api/projects/{project_id}/timeline-overlays/upload", status_code=201)
async def upload_timeline_overlay(project_id: int, file: UploadFile = File(...), start_sec: float = 0):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    extension = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    video_exts = {".mp4", ".mov", ".webm", ".mkv"}
    audio_exts = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
    if extension not in image_exts | video_exts | audio_exts:
        raise HTTPException(400, "La capa admite imágenes, videos o audio MP3/WAV/OGG/M4A/FLAC.")
    limit = 12 * 1024 * 1024 if extension in image_exts else 100 * 1024 * 1024 if extension in audio_exts else 250 * 1024 * 1024
    raw = await file.read(limit + 1)
    if not raw:
        raise HTTPException(400, "El archivo está vacío.")
    if len(raw) > limit:
        raise HTTPException(413, f"El archivo supera el límite de {limit // (1024 * 1024)} MB.")
    folder = db.MEDIA_DIR / "overlays" / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.time_ns()
    if extension in image_exts:
        try:
            with Image.open(io.BytesIO(raw)) as source:
                if source.width * source.height > 40_000_000:
                    raise HTTPException(413, "La imagen supera los 40 megapíxeles.")
                image = source.convert("RGBA")
                image.thumbnail((3840, 3840), Image.Resampling.LANCZOS)
                target = folder / f"overlay-{stamp}.png"
                image.save(target, format="PNG", optimize=True)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, "La imagen no es válida.") from exc
        kind = "image"
        duration = 5.0
    elif extension in video_exts:
        source = db.TMP_DIR / f"overlay-{stamp}{extension}"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(raw)
        try:
            info = media.probe_video(source)
            duration = float(info.get("duration") or 0)
            if not info.get("width") or not info.get("height") or duration <= 0:
                raise HTTPException(400, "El archivo no contiene un video válido.")
            target = folder / f"overlay-{stamp}.mp4"
            proc = media.run([
                media.ffmpeg(), "-y", "-i", str(source), "-map", "0:v:0", "-an",
                "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target),
            ], timeout=300)
            if proc.returncode != 0 or not target.is_file() or target.stat().st_size < 1024:
                detail = (proc.stderr or b"").decode("utf-8", "ignore")[-500:]
                raise HTTPException(400, "No se pudo convertir el video: " + detail)
        finally:
            source.unlink(missing_ok=True)
        kind = "video"
    else:
        source = db.TMP_DIR / f"overlay-{stamp}{extension}"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(raw)
        try:
            audio_info = media.probe_audio(source)
            duration = float(audio_info.get("duration") or 0)
            if not audio_info.get("codec") or duration <= 0:
                raise HTTPException(400, "El archivo no contiene un stream de audio válido.")
            target = folder / f"overlay-{stamp}{extension}"
            shutil.copy2(source, target)
        finally:
            source.unlink(missing_ok=True)
        kind = "audio"
    overlay_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,source_start_sec,source_end_sec,source_duration_sec,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, kind, str(target), Path(file.filename or "Capa").stem[:120],
         max(0.0, float(start_sec)), min(max(duration, 0.1), 3600.0), 0.62, 0.62, 0.32, 1.0, 1.0,
         0.0, 0.0, duration if kind in {"video", "audio"} else 0.0, db.now(), db.now()),
    )
    db.execute(
        "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "capa_" + kind, str(target), Path(file.filename or "Capa").name, target.stat().st_size, db.now()),
    )
    _touch_project(project_id)
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.post("/api/timeline-overlays/{overlay_id}/split", status_code=201)
def split_timeline_overlay(overlay_id: int, payload: TimelineOverlaySplitIn):
    overlay = db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))
    if not overlay:
        raise HTTPException(404, "Capa inexistente")
    at_sec = float(payload.at_sec)
    start = float(overlay.get("start_sec") or 0)
    duration = float(overlay.get("duration_sec") or 0)
    if not start < at_sec < start + duration:
        raise HTTPException(400, "El cabezal debe estar dentro del clip para dividirlo.")
    left_duration = at_sec - start
    right_duration = duration - left_duration
    source_start = float(overlay.get("source_start_sec") or 0)
    source_end = float(overlay.get("source_end_sec") or 0)
    source_duration = float(overlay.get("source_duration_sec") or 0)
    source_limit = source_end if source_end > source_start else source_duration
    source_window = source_limit - source_start if source_limit > source_start else 0
    right_source_start = source_start
    if overlay.get("kind") in {"video", "audio"} and source_window > 0:
        right_source_start = source_start + (left_duration % source_window)
    right_path = overlay["path"]
    if overlay.get("kind") == "text":
        source_path = Path(overlay["path"])
        text_folder = db.MEDIA_DIR / "overlays" / str(overlay["project_id"])
        text_folder.mkdir(parents=True, exist_ok=True)
        right_text_path = text_folder / f"text-split-{time.time_ns()}.png"
        shutil.copy2(source_path, right_text_path)
        right_path = str(right_text_path)
    db.execute(
        "UPDATE timeline_overlays SET duration_sec=?,updated_at=? WHERE id=?",
        (left_duration, db.now(), overlay_id),
    )
    new_id = db.execute(
        "INSERT INTO timeline_overlays(project_id,kind,path,title,start_sec,duration_sec,x,y,width,opacity,volume,source_start_sec,source_end_sec,source_duration_sec,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (overlay["project_id"], overlay["kind"], right_path, overlay["title"], at_sec, right_duration,
         overlay["x"], overlay["y"], overlay["width"], overlay["opacity"], overlay.get("volume", 1),
         right_source_start, source_end, source_duration, db.now(), db.now()),
    )
    if overlay.get("kind") == "text":
        db.execute(
            "INSERT INTO assets(project_id,kind,path,label,bytes,created_at) VALUES(?,?,?,?,?,?)",
            (overlay["project_id"], "capa_text", right_path, overlay["title"][:120],
             Path(right_path).stat().st_size, db.now()),
        )
    _touch_project(overlay["project_id"])
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (new_id,))


@app.patch("/api/timeline-overlays/{overlay_id}")
def patch_timeline_overlay(overlay_id: int, payload: TimelineOverlayPatch):
    overlay = db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))
    if not overlay:
        raise HTTPException(404, "Capa inexistente")
    data = payload.model_dump(exclude_none=True)
    candidate = {**overlay, **data}
    if float(candidate["start_sec"]) < 0 or not 0 < float(candidate["duration_sec"]) <= 3600:
        raise HTTPException(400, "La posición debe ser positiva y la duración debe estar entre 0 y 3600 segundos.")
    if not 0 <= float(candidate["x"]) <= 1 or not 0 <= float(candidate["y"]) <= 1:
        raise HTTPException(400, "La posición de la capa debe estar dentro del lienzo.")
    if not 0.05 <= float(candidate["width"]) <= 1 or not 0 <= float(candidate["opacity"]) <= 1:
        raise HTTPException(400, "El tamaño o la opacidad de la capa no son válidos.")
    if not 0 <= float(candidate.get("volume", 1)) <= 2:
        raise HTTPException(400, "El volumen de la capa de audio debe estar entre 0 y 200%.")
    source_start = float(candidate.get("source_start_sec") or 0)
    source_end = float(candidate.get("source_end_sec") or 0)
    source_duration = float(candidate.get("source_duration_sec") or 0)
    if source_start < 0 or source_end < 0 or (source_duration and source_start >= source_duration):
        raise HTTPException(400, "El inicio del recorte debe estar dentro del archivo original.")
    if source_end and (source_end <= source_start or (source_duration and source_end > source_duration + 0.05)):
        raise HTTPException(400, "El final del recorte debe ser posterior al inicio y no superar el archivo original.")
    if data:
        if overlay.get("kind") == "text" and "title" in data:
            text_path = Path(overlay["path"])
            _write_timeline_text_image(data["title"], text_path)
            db.execute(
                "UPDATE assets SET label=?,bytes=? WHERE project_id=? AND path=?",
                (data["title"][:120], text_path.stat().st_size, overlay["project_id"], str(text_path)),
            )
        sets = ", ".join(f"{key}=?" for key in data)
        db.execute(f"UPDATE timeline_overlays SET {sets},updated_at=? WHERE id=?", (*data.values(), db.now(), overlay_id))
        _touch_project(overlay["project_id"])
    return db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))


@app.get("/api/projects/{project_id}/history")
def get_editor_history(project_id: int):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    entries = db.query(
        "SELECT id,target,target_id,before_json,after_json,label,undone,created_at "
        "FROM editor_history WHERE project_id=? ORDER BY id",
        (project_id,),
    )
    cursor = sum(1 for entry in entries if not entry["undone"])
    return {
        "entries": entries,
        "cursor": cursor,
        "can_undo": cursor > 0,
        "can_redo": cursor < len(entries),
    }


@app.post("/api/projects/{project_id}/history", status_code=201)
def record_editor_history(project_id: int, payload: EditorHistoryIn):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    if payload.target not in {"scene", "overlay", "project"} or payload.target_id <= 0:
        raise HTTPException(400, "El destino del historial no es válido.")
    if not payload.before or not payload.after:
        raise HTTPException(400, "El historial necesita valores anteriores y nuevos.")
    if payload.target == "project" and payload.target_id != project_id:
        raise HTTPException(400, "El historial no puede modificar otro proyecto.")
    if payload.target == "scene" and not db.query_one(
        "SELECT id FROM scenes WHERE id=? AND project_id=?", (payload.target_id, project_id)
    ):
        raise HTTPException(404, "La escena del historial ya no existe.")
    if payload.target == "overlay" and not db.query_one(
        "SELECT id FROM timeline_overlays WHERE id=? AND project_id=?", (payload.target_id, project_id)
    ):
        raise HTTPException(404, "La capa del historial ya no existe.")
    db.execute("DELETE FROM editor_history WHERE project_id=? AND undone=1", (project_id,))
    history_id = db.execute(
        "INSERT INTO editor_history(project_id,target,target_id,before_json,after_json,label,undone,created_at) "
        "VALUES(?,?,?,?,?,?,0,?)",
        (project_id, payload.target, payload.target_id, json.dumps(payload.before, ensure_ascii=False),
         json.dumps(payload.after, ensure_ascii=False), payload.label[:160], db.now()),
    )
    db.execute(
        "DELETE FROM editor_history WHERE project_id=? AND id NOT IN "
        "(SELECT id FROM editor_history WHERE project_id=? ORDER BY id DESC LIMIT 100)",
        (project_id, project_id),
    )
    return db.query_one("SELECT * FROM editor_history WHERE id=?", (history_id,))


@app.post("/api/projects/{project_id}/history/undo")
def undo_editor_history(project_id: int):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    entry = db.query_one(
        "SELECT * FROM editor_history WHERE project_id=? AND undone=0 ORDER BY id DESC LIMIT 1",
        (project_id,),
    )
    if not entry:
        raise HTTPException(409, "No hay cambios para deshacer.")
    patch = json.loads(entry["before_json"])
    if entry["target"] == "scene":
        patch_scene(entry["target_id"], ScenePatch(**patch))
    elif entry["target"] == "overlay":
        patch_timeline_overlay(entry["target_id"], TimelineOverlayPatch(**patch))
    else:
        patch_project(project_id, ProjectPatch(**patch))
    db.execute("UPDATE editor_history SET undone=1 WHERE id=?", (entry["id"],))
    return {"ok": True, "entry_id": entry["id"], "label": entry["label"]}


@app.post("/api/projects/{project_id}/history/redo")
def redo_editor_history(project_id: int):
    if not db.query_one("SELECT id FROM projects WHERE id=?", (project_id,)):
        raise HTTPException(404, "Proyecto inexistente")
    entry = db.query_one(
        "SELECT * FROM editor_history WHERE project_id=? AND undone=1 ORDER BY id ASC LIMIT 1",
        (project_id,),
    )
    if not entry:
        raise HTTPException(409, "No hay cambios para rehacer.")
    patch = json.loads(entry["after_json"])
    if entry["target"] == "scene":
        patch_scene(entry["target_id"], ScenePatch(**patch))
    elif entry["target"] == "overlay":
        patch_timeline_overlay(entry["target_id"], TimelineOverlayPatch(**patch))
    else:
        patch_project(project_id, ProjectPatch(**patch))
    db.execute("UPDATE editor_history SET undone=0 WHERE id=?", (entry["id"],))
    return {"ok": True, "entry_id": entry["id"], "label": entry["label"]}


@app.delete("/api/timeline-overlays/{overlay_id}")
def delete_timeline_overlay(overlay_id: int):
    overlay = db.query_one("SELECT * FROM timeline_overlays WHERE id=?", (overlay_id,))
    if not overlay:
        raise HTTPException(404, "Capa inexistente")
    path = Path(overlay.get("path") or "")
    shared_overlays = db.scalar(
        "SELECT COUNT(*) FROM timeline_overlays WHERE path=? AND id<>?",
        (overlay.get("path") or "", overlay_id), 0,
    )
    shared_assets = db.scalar(
        "SELECT COUNT(*) FROM assets WHERE path=? AND project_id<>?",
        (overlay.get("path") or "", overlay["project_id"]), 0,
    )
    overlay_root = db.MEDIA_DIR / "overlays"
    if not shared_overlays and not shared_assets and path.is_file() and str(path).startswith(str(overlay_root)):
        path.unlink(missing_ok=True)
    db.execute("DELETE FROM editor_history WHERE project_id=? AND target='overlay' AND target_id=?",
               (overlay["project_id"], overlay_id))
    if not shared_overlays:
        db.execute("DELETE FROM assets WHERE project_id=? AND path=?", (overlay["project_id"], overlay.get("path") or ""))
    db.execute("DELETE FROM timeline_overlays WHERE id=?", (overlay_id,))
    _touch_project(overlay["project_id"])
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

@app.post("/api/ideas")
def suggest_video_ideas(payload: IdeasIn):
    """Busca ideas de video documentables con fuentes públicas gratuitas."""
    try:
        ideas = topic_engine.suggest_topics(payload.niche, payload.limit)
    except Exception as exc:
        raise HTTPException(503, f"No se pudieron buscar ideas ahora: {exc}") from exc
    return {
        "ideas": ideas,
        "source": "Wikipedia",
        "trend_note": "Las tendencias solo se incluyen cuando coinciden con el nicho.",
    }


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



@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    existing = db.query_one("SELECT id FROM sources WHERE id=?", (source_id,))
    if not existing:
        raise HTTPException(404, "Fuente inexistente")
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    return {"ok": True}


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


@app.get("/api/youtube/accounts")
def youtube_accounts(request: Request):
    publish.ensure_schema()
    channels = db.query("SELECT id,name,topic FROM channels ORDER BY name COLLATE NOCASE, id")
    linked = {int(row["channel_id"]): row for row in publish.youtube_accounts_status()}
    credentials = publish.youtube_credentials()
    missing_env = [
        name for name, value in (
            ("YOUTUBE_CLIENT_ID", credentials["client_id"]),
            ("YOUTUBE_CLIENT_SECRET", credentials["client_secret"]),
        ) if not value
    ]
    redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI", "").strip() or str(request.base_url).rstrip("/") + "/api/youtube/callback"
    return {
        "accounts": [{**channel, "account": linked.get(int(channel["id"]))} for channel in channels],
        "oauth_ready": not missing_env,
        "missing_env": missing_env,
        "redirect_uri": redirect_uri,
    }


@app.post("/api/youtube/oauth/start")
def youtube_oauth_start(request: Request, channel_id: int | None = None):
    """Inicia OAuth para un espacio existente o para importar directamente un canal real."""
    credentials = publish.youtube_credentials()
    if not credentials["client_id"] or not credentials["client_secret"]:
        raise HTTPException(400, "Faltan las credenciales OAuth de YouTube en el servidor.")
    if channel_id is not None and not db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,)):
        raise HTTPException(404, "El espacio de trabajo seleccionado no existe.")
    redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI", "").strip() or str(request.base_url).rstrip("/") + "/api/youtube/callback"
    state = secrets.token_urlsafe(32)
    # Cada intento tiene su propio registro: conectar dos canales en paralelo no
    # invalida el state del otro intento. Sin channel_id, el callback crea el espacio
    # desde el nombre e ID que devuelve la API oficial de YouTube.
    db.set_setting("youtube_oauth_attempt:" + state, json.dumps({
        "created": time.time(), "redirect_uri": redirect_uri, "channel_id": int(channel_id) if channel_id is not None else None
    }))
    params = {
        "client_id": credentials["client_id"], "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly",
        "access_type": "offline", "prompt": "select_account consent",
        "include_granted_scopes": "true", "state": state,
    }
    return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params), "redirect_uri": redirect_uri}


@app.get("/api/youtube/callback")
def youtube_oauth_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return HTMLResponse("<h2>Conexión de YouTube cancelada</h2><p>No se autorizó el canal.</p><a href='/#/cuentas'>Volver a Cuentas</a>", status_code=400)
    attempt_key = "youtube_oauth_attempt:" + state if state else ""
    raw_attempt = db.get_setting(attempt_key, "") if attempt_key else ""
    try:
        attempt = json.loads(raw_attempt)
        age = time.time() - float(attempt["created"])
        redirect_uri = str(attempt["redirect_uri"])
        channel_id = int(attempt["channel_id"]) if attempt.get("channel_id") is not None else None
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        attempt, age, redirect_uri, channel_id = {}, 999999, "", None
    if not code or not state or not attempt or age > 600:
        raise HTTPException(403, "La autorización venció o no coincide. Volvé a iniciar la conexión desde Cuentas.")
    # Consumir el intento antes del intercambio para impedir reutilización del callback.
    db.set_setting(attempt_key, "")
    if channel_id is not None and not db.query_one("SELECT id FROM channels WHERE id=?", (channel_id,)):
        raise HTTPException(404, "El espacio de trabajo asociado a esta autorización ya no existe.")
    credentials = publish.youtube_credentials()
    body = urllib.parse.urlencode({
        "code": code, "client_id": credentials["client_id"], "client_secret": credentials["client_secret"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode()
    request = urllib.request.Request(publish.YOUTUBE_TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            token_data = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:250]
        raise HTTPException(400, f"Google rechazó la autorización ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(502, f"No se pudo contactar a Google: {exc.reason}") from exc
    refresh_token = token_data.get("refresh_token") or publish.youtube_credentials(channel_id).get("refresh_token")
    if not refresh_token:
        raise HTTPException(400, "Google no devolvió un refresh token para esta cuenta. Volvé a autorizar con consentimiento.")
    try:
        account = publish.youtube_account_status(refresh_token_override=refresh_token)
        if channel_id is None:
            # Importar el canal real autorizado. No inventamos un canal de YouTube:
            # el nombre y el ID provienen de channels.list(mine=true).
            existing = db.query_one(
                "SELECT channel_id FROM youtube_accounts WHERE youtube_channel_id=?",
                (account["channel_id"],),
            )
            if existing:
                channel_id = int(existing["channel_id"])
            else:
                now = db.now()
                channel_name = (account.get("channel_title") or "Canal de YouTube").strip()[:100]
                duplicate_name = db.query_one("SELECT id FROM channels WHERE lower(name)=lower(?)", (channel_name,))
                if duplicate_name:
                    channel_name = f"{channel_name} · YouTube"
                channel_id = db.execute(
                    "INSERT INTO channels(name,topic,language,audience,tone,visual_identity,formats,cadence,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (channel_name, "", "es", "", "", "", "short,documental", "semanal", now, now),
                )
        publish.save_youtube_account(channel_id, refresh_token, account)
    except publish.PublishError as exc:
        raise HTTPException(400, f"No se pudo verificar la cuenta autorizada: {exc}") from exc
    if persistence.configured():
        try:
            persistence.sync_backup()
        except Exception as exc:
            raise HTTPException(503, f"La cuenta quedó autorizada, pero falló la sincronización del respaldo persistente: {exc}") from exc
    return RedirectResponse(url="/#/cuentas", status_code=303)


@app.post("/api/youtube/disconnect")
def youtube_disconnect(channel_id: int):
    credentials = publish.youtube_credentials(channel_id)
    refresh_token = credentials.get("refresh_token", "")
    if refresh_token:
        revoke = urllib.request.Request("https://oauth2.googleapis.com/revoke", data=urllib.parse.urlencode({"token": refresh_token}).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(revoke, timeout=20):
                pass
        except Exception as exc:
            db.log("warn", "youtube", f"No se pudo confirmar la revocación remota de YouTube: {exc}")
    publish.ensure_schema()
    db.execute("DELETE FROM youtube_accounts WHERE channel_id=?", (channel_id,))
    if persistence.configured():
        try:
            persistence.sync_backup()
        except Exception as exc:
            raise HTTPException(503, f"La cuenta se desconectó localmente, pero falló la sincronización del respaldo: {exc}") from exc
    return {"ok": True, "connected": False}


@app.get("/api/youtube/status")
def youtube_status(channel_id: int | None = None):
    try:
        if channel_id is None:
            linked = publish.youtube_accounts_status()
            if not linked:
                raise publish.PublishError("Todavía no hay cuentas de YouTube conectadas.")
            channel_id = int(linked[0]["channel_id"])
        return publish.youtube_account_status(channel_id)
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
    if payload.destination == "youtube":
        if not project.get("channel_id"):
            raise HTTPException(400, "Asigná el proyecto a Historias o Frutinovelas antes de publicar en YouTube.")
        try:
            publish.youtube_account_status(int(project["channel_id"]))
        except publish.PublishError as exc:
            raise HTTPException(400, "La cuenta de YouTube de este canal no está conectada o no se pudo verificar: " + str(exc)) from exc
    # Si el contenedor usa almacenamiento remoto, respaldar el MP4 antes
    # de encolar la publicación. SQLite no incluye los binarios del render.
    if persistence.configured():
        try:
            persistence.sync_pending_video(project_id, publish.video_path(project))
        except Exception as exc:
            raise HTTPException(503, f"No se pudo respaldar el MP4 antes de publicar: {exc}") from exc
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
    for key, value in payload.values.items():
        if key not in db.DEFAULT_SETTINGS:
            continue
        if key == "default_language" and value not in {"es", "en"}:
            raise HTTPException(400, "Elegí español o inglés como idioma predeterminado.")
        if key == "default_voice" and value not in tts.VOICES:
            raise HTTPException(400, "Elegí una voz disponible en español o inglés.")
        db.set_setting(key, value)
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
