"""Piloto automático por nicho: crea, escribe, renderiza y publica solo.

Cada regla define un nicho (tema), una plantilla, la duración y una cadencia en
horas. El worker llama a `tick()` periódicamente; cuando una regla vence, la app
crea el proyecto con el guion ya escrito, encola el render y, si se pidió,
activa la auto-subida. Todo local: no intervienen servicios pagos.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import db, options

CADENCE_OPTIONS = [6, 12, 24, 48, 72, 168]
SHORT_TEMPLATE_IDS = {"shorts", "listicle", "pov", "quote"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS autopilot_rules(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    niche TEXT NOT NULL DEFAULT '',
    channel_id INTEGER,
    template TEXT NOT NULL DEFAULT 'shorts',
    duration_target_sec INTEGER,
    voice TEXT NOT NULL DEFAULT 'es',
    speed INTEGER NOT NULL DEFAULT 150,
    pitch INTEGER NOT NULL DEFAULT 45,
    visual_style TEXT NOT NULL DEFAULT '',
    title_style TEXT NOT NULL DEFAULT 'automatico',
    custom_tags TEXT NOT NULL DEFAULT '',
    aspect TEXT NOT NULL DEFAULT '9:16',
    caption_style TEXT NOT NULL DEFAULT 'short_pop',
    transition_default TEXT NOT NULL DEFAULT 'fundido',
    resolution TEXT NOT NULL DEFAULT '1080p',
    fps INTEGER NOT NULL DEFAULT 25,
    music TEXT NOT NULL DEFAULT 'auto',
    music_volume REAL NOT NULL DEFAULT 0.12,
    audience TEXT NOT NULL DEFAULT 'Público general',
    tone TEXT NOT NULL DEFAULT 'Dinámico y cercano',
    hook_style TEXT NOT NULL DEFAULT 'Dato sorprendente',
    cta TEXT NOT NULL DEFAULT 'Hacé una pregunta concreta al final',
    content_pillars TEXT NOT NULL DEFAULT '',
    avoid_topics TEXT NOT NULL DEFAULT '',
    cadence_hours INTEGER NOT NULL DEFAULT 24,
    cadence_minutes INTEGER NOT NULL DEFAULT 1440,
    videos_per_period INTEGER NOT NULL DEFAULT 1,
    period_days INTEGER NOT NULL DEFAULT 1,
    schedule_time TEXT NOT NULL DEFAULT '10:00',
    timezone TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
    enabled INTEGER NOT NULL DEFAULT 1,
    destination TEXT NOT NULL DEFAULT 'entrega',
    privacy TEXT NOT NULL DEFAULT 'unlisted',
    auto_publish INTEGER NOT NULL DEFAULT 0,
    next_run_at TEXT,
    last_run_at TEXT,
    last_project_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

FIELDS = [
    "name", "niche", "channel_id", "template", "duration_target_sec", "voice", "speed", "pitch", "visual_style", "title_style", "custom_tags", "aspect",
    "audience", "tone", "hook_style", "cta", "content_pillars", "avoid_topics",
    "caption_style", "transition_default", "resolution", "fps", "music", "music_volume",
    "cadence_hours", "cadence_minutes", "videos_per_period", "period_days", "schedule_time", "timezone", "enabled", "destination", "privacy", "auto_publish", "next_run_at",
]


def ensure_schema() -> None:
    db.execute(SCHEMA)
    columns = {row["name"] for row in db.query("PRAGMA table_info(autopilot_rules)")}
    migrations = {
        "last_error": "TEXT",
        "speed": "INTEGER NOT NULL DEFAULT 150",
        "pitch": "INTEGER NOT NULL DEFAULT 45",
        "visual_style": "TEXT NOT NULL DEFAULT ''",
        "title_style": "TEXT NOT NULL DEFAULT 'automatico'",
        "custom_tags": "TEXT NOT NULL DEFAULT ''",
        "videos_per_period": "INTEGER NOT NULL DEFAULT 1",
        "cadence_minutes": "INTEGER NOT NULL DEFAULT 1440",
        "period_days": "INTEGER NOT NULL DEFAULT 1",
        "schedule_time": "TEXT NOT NULL DEFAULT '10:00'",
        "timezone": "TEXT NOT NULL DEFAULT 'America/Argentina/Buenos_Aires'",
        "audience": "TEXT NOT NULL DEFAULT 'Público general'",
        "tone": "TEXT NOT NULL DEFAULT 'Dinámico y cercano'",
        "hook_style": "TEXT NOT NULL DEFAULT 'Dato sorprendente'",
        "cta": "TEXT NOT NULL DEFAULT 'Hacé una pregunta concreta al final'",
        "content_pillars": "TEXT NOT NULL DEFAULT ''",
        "avoid_topics": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in migrations.items():
        if name not in columns:
            db.execute(f"ALTER TABLE autopilot_rules ADD COLUMN {name} {definition}")
    # Migra reglas antiguas: el Autopiloto queda dedicado exclusivamente a Shorts.
    placeholders = ",".join("?" for _ in SHORT_TEMPLATE_IDS)
    db.execute(
        f"UPDATE autopilot_rules SET template='shorts', aspect='9:16', "
        "duration_target_sec=CASE WHEN duration_target_sec IS NULL THEN 30 "
        "WHEN duration_target_sec<15 THEN 15 WHEN duration_target_sec>180 THEN 180 "
        "ELSE duration_target_sec END "
        f"WHERE template NOT IN ({placeholders}) OR aspect!='9:16'",
        tuple(sorted(SHORT_TEMPLATE_IDS)),
    )


def _ts(offset_hours: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_hours * 3600))


def list_rules() -> list[dict]:
    ensure_schema()
    rows = db.query(
        "SELECT r.*, c.name AS channel_name, p.title AS last_project_title, p.status AS last_project_status, "
        "j.status AS last_job_status, j.message AS last_job_message, j.progress AS last_job_progress, j.kind AS last_job_kind "
        "FROM autopilot_rules r "
        "LEFT JOIN channels c ON c.id=r.channel_id "
        "LEFT JOIN projects p ON p.id=r.last_project_id "
        "LEFT JOIN jobs j ON j.id=(SELECT MAX(j2.id) FROM jobs j2 WHERE j2.project_id=p.id) "
        "ORDER BY r.id"
    )
    for row in rows:
        row["enabled"] = bool(row["enabled"])
        row["auto_publish"] = bool(row["auto_publish"])
    return rows


def get_rule(rule_id: int) -> dict | None:
    ensure_schema()
    row = db.query_one("SELECT * FROM autopilot_rules WHERE id=?", (rule_id,))
    if row:
        row["enabled"] = bool(row["enabled"])
        row["auto_publish"] = bool(row["auto_publish"])
    return row


def _clean(data: dict) -> dict:
    """Valida y normaliza los campos de una regla."""
    clean: dict = {}
    if "name" in data and data["name"] is not None:
        clean["name"] = str(data["name"]).strip()[:120]
    if "niche" in data and data["niche"] is not None:
        clean["niche"] = str(data["niche"]).strip()[:200]
        if not clean["niche"]:
            raise ValueError("El nicho no puede quedar vacío.")
    if "channel_id" in data:
        clean["channel_id"] = data["channel_id"]
    if "template" in data and data["template"] is not None:
        if data["template"] not in SHORT_TEMPLATE_IDS:
            raise ValueError("El Autopiloto de Laburito produce exclusivamente Shorts.")
        clean["template"] = data["template"]
    if "duration_target_sec" in data and data["duration_target_sec"] is not None:
        short_templates = SHORT_TEMPLATE_IDS
        if data.get("template", "shorts") in short_templates:
            clean["duration_target_sec"] = max(15, min(180, int(data["duration_target_sec"])))
        else:
            clean["duration_target_sec"] = max(5, min(3600, int(data["duration_target_sec"])))
    if "voice" in data and data["voice"] is not None:
        voice = str(data["voice"]).strip()
        spanish_voices = {"es", "es-ar", "es-es-piper", "es-mx", "es-masculino", "es-agudo"}
        if voice not in spanish_voices:
            raise ValueError("Laburito genera contenido únicamente en español. Elegí una voz española.") 
        clean["voice"] = voice
    if "speed" in data and data["speed"] is not None:
        clean["speed"] = max(80, min(300, int(data["speed"])))
    if "pitch" in data and data["pitch"] is not None:
        clean["pitch"] = max(0, min(99, int(data["pitch"])))
    if "visual_style" in data and data["visual_style"] is not None:
        clean["visual_style"] = str(data["visual_style"]).strip()[:180]
    if "title_style" in data and data["title_style"] is not None:
        if data["title_style"] not in ("automatico", "pregunta", "curiosidad", "directo", "misterio"):
            raise ValueError("Estilo de título no válido")
        clean["title_style"] = data["title_style"]
    if "custom_tags" in data and data["custom_tags"] is not None:
        clean["custom_tags"] = str(data["custom_tags"]).strip()[:300]
    if "aspect" in data and data["aspect"] is not None:
        if data["aspect"] != "9:16":
            raise ValueError("Los Shorts del Autopiloto deben ser verticales 9:16.")
        clean["aspect"] = "9:16"
    if "caption_style" in data and data["caption_style"] is not None:
        if data["caption_style"] not in options.CAPTION_STYLES:
            raise ValueError("Estilo de subtítulos desconocido")
        clean["caption_style"] = data["caption_style"]
    if "transition_default" in data and data["transition_default"] is not None:
        if data["transition_default"] not in options.TRANSITION_IDS:
            raise ValueError("Transición desconocida")
        clean["transition_default"] = data["transition_default"]
    if "resolution" in data and data["resolution"] is not None:
        if data["resolution"] not in options.RESOLUTIONS:
            raise ValueError("Resolución no soportada")
        clean["resolution"] = data["resolution"]
    if "fps" in data and data["fps"] is not None:
        if int(data["fps"]) not in options.FPS_OPTIONS:
            raise ValueError("FPS no soportado")
        clean["fps"] = int(data["fps"])
    if "music" in data and data["music"] is not None:
        music = str(data["music"]).strip()
        if music not in ("auto", "ninguna", "none", "sin_musica") and music not in options.MUSIC_IDS:
            custom_track = db.MUSIC_DIR / music
            if custom_track.name != music or not custom_track.is_file():
                raise ValueError("Pista musical no reconocida o archivo inexistente")
        clean["music"] = "bed:" + music if music in options.MUSIC_IDS else music
    if "music_volume" in data and data["music_volume"] is not None:
        clean["music_volume"] = max(0.0, min(1.0, float(data["music_volume"])))
    for key, limit in {
        "audience": 160, "tone": 120, "hook_style": 100, "cta": 180,
        "content_pillars": 500, "avoid_topics": 500,
    }.items():
        if key in data and data[key] is not None:
            clean[key] = str(data[key]).strip()[:limit]
    if "videos_per_period" in data and data["videos_per_period"] is not None:
        clean["videos_per_period"] = max(1, min(30, int(data["videos_per_period"])))
    if "period_days" in data and data["period_days"] is not None:
        clean["period_days"] = max(1, min(30, int(data["period_days"])))
    if "videos_per_period" in clean or "period_days" in clean:
        count = clean.get("videos_per_period", int(data.get("videos_per_period", 1) or 1))
        days = clean.get("period_days", int(data.get("period_days", 1) or 1))
        clean["cadence_minutes"] = max(30, min(43200, int(round(days * 1440 / count))))
        clean["cadence_hours"] = max(1, int(round(clean["cadence_minutes"] / 60)))
    elif "cadence_hours" in data and data["cadence_hours"] is not None:
        clean["cadence_hours"] = max(1, min(720, int(data["cadence_hours"])))
        clean["cadence_minutes"] = clean["cadence_hours"] * 60
    if "schedule_time" in data and data["schedule_time"] is not None:
        value = str(data["schedule_time"]).strip()
        if len(value) != 5 or value[2] != ":" or not value[:2].isdigit() or not value[3:].isdigit() or int(value[:2]) > 23 or int(value[3:]) > 59:
            raise ValueError("El horario debe tener formato HH:MM.")
        clean["schedule_time"] = value
    if "timezone" in data and data["timezone"] is not None:
        value = str(data["timezone"]).strip()[:80]
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Zona horaria no válida.")
        clean["timezone"] = value
    if "destination" in data and data["destination"] is not None:
        if data["destination"] not in ("entrega", "youtube"):
            raise ValueError("Destino inválido: usá 'entrega' o 'youtube'")
        clean["destination"] = data["destination"]
    if "privacy" in data and data["privacy"] is not None:
        if data["privacy"] not in ("public", "unlisted", "private"):
            raise ValueError("Privacidad inválida")
        clean["privacy"] = data["privacy"]
    if "enabled" in data and data["enabled"] is not None:
        clean["enabled"] = 1 if data["enabled"] else 0
    if "auto_publish" in data and data["auto_publish"] is not None:
        clean["auto_publish"] = 1 if data["auto_publish"] else 0
    if "next_run_at" in data and data["next_run_at"] is not None:
        clean["next_run_at"] = str(data["next_run_at"])[:40]
    return clean


def _next_run_at(rule: dict, after: datetime | None = None) -> str:
    """Calcula la próxima ejecución respetando la hora y zona horaria elegidas."""
    zone_name = rule.get("timezone") or "America/Argentina/Buenos_Aires"
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    now = after.astimezone(zone) if after else datetime.now(zone)
    clock = str(rule.get("schedule_time") or "10:00")
    hour, minute = int(clock[:2]), int(clock[3:])
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    interval_minutes = int(rule.get("cadence_minutes") or (int(rule.get("cadence_hours") or 24) * 60))
    step = timedelta(minutes=interval_minutes)
    while target <= now:
        target += step
    return target.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_auto_publish(clean: dict, current: dict | None = None) -> None:
    """No deja activar YouTube si la conexión todavía no está configurada."""
    merged = {**(current or {}), **clean}
    if not bool(merged.get("auto_publish")) or merged.get("destination", "entrega") != "youtube":
        return
    from . import publish
    try:
        publish.youtube_account_status()
    except publish.PublishError as exc:
        raise ValueError(
            "Antes de activar la publicación automática, conectá y verificá YouTube en Ajustes. " + str(exc)
        ) from exc


def create_rule(data: dict) -> dict:
    ensure_schema()
    clean = _clean(data)
    clean.setdefault("name", clean.get("niche") or "Piloto automático")
    clean.setdefault("template", "shorts")
    clean.setdefault("aspect", "9:16")
    clean.setdefault("destination", "youtube")
    clean.setdefault("privacy", "public")
    clean.setdefault("auto_publish", 1)
    _validate_auto_publish(clean)
    clean.setdefault("videos_per_period", 1)
    clean.setdefault("period_days", 1)
    clean.setdefault("schedule_time", "10:00")
    clean.setdefault("timezone", "America/Argentina/Buenos_Aires")
    clean.setdefault("cadence_hours", 24)
    clean.setdefault("next_run_at", _next_run_at(clean))
    clean["created_at"] = db.now()
    clean["updated_at"] = db.now()
    cols = ", ".join(clean)
    marks = ", ".join("?" for _ in clean)
    rid = db.execute(f"INSERT INTO autopilot_rules({cols}) VALUES({marks})", tuple(clean.values()))
    db.log("info", "autopilot", f"Regla de piloto automático creada: {clean.get('name')}", {"id": rid})
    return get_rule(rid) or {}


def update_rule(rule_id: int, data: dict) -> dict | None:
    ensure_schema()
    current = get_rule(rule_id)
    if not current:
        return None
    clean = _clean(data)
    _validate_auto_publish(clean, current)
    if clean:
        if clean.get("enabled") == 1 and not current.get("enabled"):
            clean["next_run_at"] = _ts(0)
        elif "niche" in clean and clean["niche"] != current.get("niche"):
            clean["next_run_at"] = _ts(0)
        elif any(key in clean for key in ("cadence_hours", "cadence_minutes", "videos_per_period", "period_days", "schedule_time", "timezone")):
            merged = {**current, **clean}
            clean["next_run_at"] = _next_run_at(merged)
        sets = ", ".join(f"{k}=?" for k in clean)
        db.execute(
            f"UPDATE autopilot_rules SET {sets}, updated_at=? WHERE id=?",
            (*clean.values(), db.now(), rule_id),
        )
    return get_rule(rule_id)


def delete_rule(rule_id: int) -> None:
    ensure_schema()
    db.execute("DELETE FROM autopilot_rules WHERE id=?", (rule_id,))


def _create_project(rule: dict) -> dict:
    """Descubre un tema no usado, registra una fuente y crea el proyecto."""
    from . import script_gen, topic_engine

    template_id = rule.get("template") if rule.get("template") in SHORT_TEMPLATE_IDS else "shorts"
    tpl = options.template(template_id)
    # Compatibilidad con reglas antiguas: nunca producir narración en otro idioma.
    rule["voice"] = rule.get("voice") if rule.get("voice") in {"es", "es-ar", "es-es-piper", "es-mx", "es-masculino", "es-agudo"} else "es"
    niche = (rule.get("niche") or "").strip()
    if not niche:
        raise ValueError("La regla necesita un nicho.")

    # El historial evita que el Autopiloto repita temas ya producidos.
    previous = db.query(
        "SELECT topic FROM projects WHERE channel_id IS ? ORDER BY id DESC LIMIT 250",
        (rule.get("channel_id"),),
    )
    previous_topics = [row.get("topic", "") for row in previous]
    research = topic_engine.research_topic(
        niche, previous_topics,
        content_pillars=rule.get("content_pillars") or "",
        avoid_topics=rule.get("avoid_topics") or "",
    )
    topic = research["topic"]
    title = topic
    duration = max(15, min(180, int(rule.get("duration_target_sec") or tpl.get("default_duration") or 30)))
    pid = db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, "
        "template, caption_style, transition_default, resolution, fps, music, music_volume, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rule.get("channel_id"), title, topic, "short",
            "9:16", "borrador", duration,
            rule.get("voice") or "es", int(rule.get("speed") or 150), int(rule.get("pitch") if rule.get("pitch") is not None else 45),
            f"Autopiloto: {rule.get('name') or niche}. Fuente inicial: {research['url']}. "
            "La fuente es introductoria y debe contrastarse antes de publicar. "
            "[LABURITO_META]" + json.dumps({
                "title_style": rule.get("title_style") or "automatico",
                "custom_tags": rule.get("custom_tags") or "",
            }, ensure_ascii=False),
            tpl["id"], rule.get("caption_style") or tpl.get("caption_style"),
            rule.get("transition_default") or "fundido", rule.get("resolution") or "1080p",
            int(rule.get("fps") or 25), rule.get("music") or "auto",
            float(rule.get("music_volume") if rule.get("music_volume") is not None else 0.12), db.now(), db.now(),
        ),
    )
    project = db.query_one("SELECT * FROM projects WHERE id=?", (pid,))
    project.update({
        "audience": rule.get("audience") or "Público general",
        "tone": rule.get("tone") or "Dinámico y cercano",
        "hook_style": rule.get("hook_style") or "Dato sorprendente",
        "cta": rule.get("cta") or "Hacé una pregunta concreta al final",
        "content_pillars": rule.get("content_pillars") or "",
        "avoid_topics": rule.get("avoid_topics") or "",
        "visual_style": rule.get("visual_style") or "",
    })
    db.execute(
        "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            pid, research.get("source_title") or topic, research["url"], "Wikipedia contributors",
            "CC BY-SA 4.0 https://creativecommons.org/licenses/by-sa/4.0/", db.now(),
            "Wikipedia contributors · CC BY-SA · " + research["url"],
            "investigacion",
            "Fuente de orientación automática; verificar los datos con fuentes independientes antes de publicar.",
            db.now(),
        ),
    )
    trend_signals = research.get("trend_signals") or []
    if trend_signals:
        trend_titles = [item.get("title", "") for item in trend_signals if item.get("title")]
        db.execute(
            "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                pid, "Señales de tendencia — Google Trends Argentina", topic_engine.TRENDS_RSS,
                "Google Trends", "RSS público de tendencias de búsqueda; señal orientativa, no prueba de demanda comercial",
                db.now(), "Google Trends Argentina · " + topic_engine.TRENDS_RSS,
                "tendencia", "Términos relacionados con el nicho: " + "; ".join(trend_titles),
                db.now(),
            ),
        )
    for reference_url in research.get("references", []):
        db.execute(
            "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                pid, "Referencia externa citada en Wikipedia", reference_url,
                "Referencia enlazada por Wikipedia", "Consultar licencia y contenido",
                db.now(), reference_url, "referencia",
                "Enlace citado en el artículo de Wikipedia; no fue verificado automáticamente.",
                db.now(),
            ),
        )
    for academic in research.get("academic_sources", []):
        db.execute(
            "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                pid, academic.get("title") or "Resumen académico",
                academic.get("url") or "", academic.get("author") or "Autores de la publicación",
                "Resumen bibliográfico; consultar licencia del texto completo",
                db.now(), f"{academic.get('author', 'Autores')} · {academic.get('title', '')} · {academic.get('url', '')}",
                "investigacion",
                "Resumen recuperado desde OpenAlex; no equivale al texto completo. Verificar publicación original.",
                db.now(),
            ),
        )
    if rule.get("voice") == "es-es-piper":
        from . import tts
        if tts.status().get("piper_available"):
            db.execute(
                "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    pid, "Piper DaveFX — voz neural española",
                    "https://huggingface.co/rhasspy/piper-voices/tree/cf910fb59f1d79ab3b625a63993a108751c6c25d/es/es_ES/davefx/medium",
                    "Piper voice contributors", "CC0",
                    db.now(), "Piper DaveFX (es_ES) · CC0 · https://huggingface.co/rhasspy/piper-voices/tree/cf910fb59f1d79ab3b625a63993a108751c6c25d",
                    "voz", "Modelo neural español instalado localmente; ficha de voz CC0.",
                    db.now(),
                ),
            )
    note_ids = [int(note_id) for note_id in research.get("note_ids", []) if note_id]
    if note_ids:
        placeholders = ",".join("?" for _ in note_ids)
        notes = db.query(
            f"SELECT * FROM research_notes WHERE id IN ({placeholders}) ORDER BY id DESC",
            tuple(note_ids),
        )
    else:
        notes = []
    project_sources = db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (pid,))
    script = script_gen.generate_script(project, notes, project_sources)
    ollama_url = db.get_setting("ollama_url", "")
    if ollama_url and script_gen.ollama_available(ollama_url):
        try:
            script = script_gen.rewrite_with_ollama(
                ollama_url, "llama3.2", project, script, notes
            )
            db.log("info", "autopilot", "Guion reescrito con Ollama local", {"project_id": pid})
        except Exception as exc:
            db.log("warn", "autopilot", f"Ollama no pudo reescribir el guion; se conserva el borrador basado en fuentes: {exc}")
    for scene in script["scenes"]:
        db.execute(
            "INSERT INTO scenes(project_id, idx, title, narration, visual_query, transition, status, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                pid, scene["idx"], scene["title"], scene["narration"], scene["visual_query"],
                scene["transition"], "borrador", db.now(), db.now(),
            ),
        )
    db.log(
        "info", "autopilot",
        f"Proyecto automático creado con tema descubierto: {title}",
        {"id": pid, "topic": topic, "source": research["url"], "scenes": len(script["scenes"])},
    )
    return {"project_id": pid, "script_writer": script.get("writer", "template"), "evidence_sources": int(script.get("evidence_sources", 0))}


def _next_after_run(rule: dict, force: bool = False, now: str | None = None) -> str:
    """Una ejecución manual no mueve una próxima fecha que todavía está en el futuro."""
    current_time = now or db.now()
    scheduled = rule.get("next_run_at")
    if force and scheduled and str(scheduled) > current_time:
        return str(scheduled)
    return _next_run_at(rule)


def run_rule(rule_id: int, force: bool = False) -> dict:
    """Ejecuta una regla ahora: crea el proyecto, escribe el guion y encola el render."""
    from . import publish, worker

    rule = get_rule(rule_id)
    if not rule:
        raise ValueError("Regla inexistente")
    # Verificar YouTube antes de consumir recursos creando y renderizando un Short.
    if rule.get("auto_publish") and (rule.get("destination") or "entrega") == "youtube":
        try:
            publish.youtube_account_status()
        except publish.PublishError as exc:
            message = "Autopublicación pausada: YouTube no está disponible. " + str(exc)
            db.execute(
                "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE id=?",
                (message[:500], db.now(), rule_id),
            )
            raise ValueError(message) from exc
    try:
        project_result = _create_project(rule)
        pid = int(project_result["project_id"])
        script_writer = project_result.get("script_writer", "template")
        evidence_sources = int(project_result.get("evidence_sources", 0))
    except Exception as exc:
        db.execute(
            "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE id=?",
            (str(exc)[:500], db.now(), rule_id),
        )
        raise
    publish_warning = ""
    if rule.get("auto_publish"):
        destination = rule.get("destination") or "entrega"
        # No exigir Ollama: el Autopiloto debe funcionar sin instalar un
        # modelo externo. Un guion basado en extractos recuperados es publicable
        # si cuenta con al menos un extracto de evidencia; los borradores sin
        # fuentes suficientes quedan retenidos para evitar publicar inventos.
        quality_ready = script_writer in ("source-extract", "ollama-local") and evidence_sources >= 1
        if destination == "youtube" and not quality_ready:
            publish_warning = (
                "Publicación automática en YouTube retenida: hace falta al menos un extracto "
                "de investigación y un guion basado en fuentes. El video queda generado para revisión."
            )
            db.log("warn", "autopilot", publish_warning, {"project_id": pid, "writer": script_writer})
            # No degradar silenciosamente una publicación de YouTube a una entrega local.
            # El MP4 queda disponible en el proyecto, pero el estado informa que no se publicó.
        else:
            try:
                publish.set_auto_publish(pid, True, destination)
            except publish.PublishError as exc:
                publish_warning = "Autopublicación no activada: " + str(exc)[:450]
                db.log("error", "autopilot", f"No se pudo activar la auto-subida: {exc}")
                # No cambiar el destino a entrega local: eso ocultaría el fallo de YouTube.
    job_id = worker.enqueue(pid, "render_project", {"privacy": rule.get("privacy") or "unlisted"})
    next_run = _next_after_run(rule, force=force)
    db.execute(
        "UPDATE autopilot_rules SET last_run_at=?, last_project_id=?, next_run_at=?, last_error=?, updated_at=? WHERE id=?",
        (db.now(), pid, next_run, publish_warning, db.now(), rule_id),
    )
    return {"rule_id": rule_id, "project_id": pid, "job_id": job_id, "next_run_at": next_run, "forced": force, "publish_warning": publish_warning or None}


def tick() -> int:
    """Dispara las reglas vencidas. Devuelve cuántas se ejecutaron."""
    ensure_schema()
    now = db.now()
    due = db.query(
        "SELECT id FROM autopilot_rules WHERE enabled=1 AND (next_run_at IS NULL OR next_run_at<=?) ORDER BY id",
        (now,),
    )
    fired = 0
    for row in due:
        try:
            run_rule(int(row["id"]))
            fired += 1
        except Exception as exc:  # una regla rota no debe frenar al worker
            rule = get_rule(int(row["id"])) or {}
            db.execute(
                "UPDATE autopilot_rules SET next_run_at=?, last_error=?, updated_at=? WHERE id=?",
                (_next_run_at(rule), str(exc)[:500], db.now(), row["id"]),
            )
            db.log("error", "autopilot", f"Regla {row['id']} falló: {exc}")
    return fired
