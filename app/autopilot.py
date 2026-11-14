"""Piloto automático por nicho: crea, escribe, renderiza y publica solo.

Cada regla define un nicho (tema), una plantilla, la duración y una cadencia en
horas. El worker llama a `tick()` periódicamente; cuando una regla vence, la app
crea el proyecto con el guion ya escrito, encola el render y, si se pidió,
activa la auto-subida. Todo local: no intervienen servicios pagos.
"""
from __future__ import annotations

import time

from . import db, options

CADENCE_OPTIONS = [6, 12, 24, 48, 72, 168]

SCHEMA = """
CREATE TABLE IF NOT EXISTS autopilot_rules(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '',
    niche TEXT NOT NULL DEFAULT '',
    channel_id INTEGER,
    template TEXT NOT NULL DEFAULT 'shorts',
    duration_target_sec INTEGER,
    voice TEXT NOT NULL DEFAULT 'es',
    aspect TEXT NOT NULL DEFAULT '9:16',
    caption_style TEXT NOT NULL DEFAULT 'short_pop',
    transition_default TEXT NOT NULL DEFAULT 'fundido',
    resolution TEXT NOT NULL DEFAULT '1080p',
    fps INTEGER NOT NULL DEFAULT 25,
    music TEXT NOT NULL DEFAULT 'auto',
    music_volume REAL NOT NULL DEFAULT 0.12,
    cadence_hours INTEGER NOT NULL DEFAULT 24,
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
    "name", "niche", "channel_id", "template", "duration_target_sec", "voice", "aspect",
    "caption_style", "transition_default", "resolution", "fps", "music", "music_volume",
    "cadence_hours", "enabled", "destination", "privacy", "auto_publish", "next_run_at",
]


def ensure_schema() -> None:
    db.execute(SCHEMA)
    columns = {row["name"] for row in db.query("PRAGMA table_info(autopilot_rules)")}
    if "last_error" not in columns:
        db.execute("ALTER TABLE autopilot_rules ADD COLUMN last_error TEXT")


def _ts(offset_hours: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset_hours * 3600))


def list_rules() -> list[dict]:
    ensure_schema()
    rows = db.query(
        "SELECT r.*, c.name AS channel_name, p.title AS last_project_title, p.status AS last_project_status, "
        "j.status AS last_job_status, j.message AS last_job_message "
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
    if "channel_id" in data:
        clean["channel_id"] = data["channel_id"]
    if "template" in data and data["template"] is not None:
        if data["template"] not in options.TEMPLATE_IDS:
            raise ValueError("Plantilla desconocida")
        clean["template"] = data["template"]
    if "duration_target_sec" in data and data["duration_target_sec"] is not None:
        clean["duration_target_sec"] = max(5, min(3600, int(data["duration_target_sec"])))
    if "voice" in data and data["voice"] is not None:
        clean["voice"] = str(data["voice"])[:40]
    if "aspect" in data and data["aspect"] is not None:
        if data["aspect"] not in options.ASPECTS:
            raise ValueError("Aspecto no soportado")
        clean["aspect"] = data["aspect"]
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
        music = str(data["music"])
        if music != "auto" and music not in options.MUSIC_IDS:
            raise ValueError("Pista musical no reconocida")
        clean["music"] = "bed:" + music if music in options.MUSIC_IDS else music
    if "music_volume" in data and data["music_volume"] is not None:
        clean["music_volume"] = max(0.0, min(1.0, float(data["music_volume"])))
    if "cadence_hours" in data and data["cadence_hours"] is not None:
        clean["cadence_hours"] = max(1, min(720, int(data["cadence_hours"])))
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


def create_rule(data: dict) -> dict:
    ensure_schema()
    clean = _clean(data)
    clean.setdefault("name", clean.get("niche") or "Piloto automático")
    clean.setdefault("next_run_at", _ts(0))
    clean["created_at"] = db.now()
    clean["updated_at"] = db.now()
    cols = ", ".join(clean)
    marks = ", ".join("?" for _ in clean)
    rid = db.execute(f"INSERT INTO autopilot_rules({cols}) VALUES({marks})", tuple(clean.values()))
    db.log("info", "autopilot", f"Regla de piloto automático creada: {clean.get('name')}", {"id": rid})
    return get_rule(rid) or {}


def update_rule(rule_id: int, data: dict) -> dict | None:
    ensure_schema()
    if not db.query_one("SELECT id FROM autopilot_rules WHERE id=?", (rule_id,)):
        return None
    clean = _clean(data)
    if clean:
        sets = ", ".join(f"{k}=?" for k in clean)
        db.execute(
            f"UPDATE autopilot_rules SET {sets}, updated_at=? WHERE id=?",
            (*clean.values(), db.now(), rule_id),
        )
    return get_rule(rule_id)


def delete_rule(rule_id: int) -> None:
    ensure_schema()
    db.execute("DELETE FROM autopilot_rules WHERE id=?", (rule_id,))


def _create_project(rule: dict) -> int:
    """Descubre un tema no usado, registra una fuente y crea el proyecto."""
    from . import script_gen, topic_engine

    tpl = options.template(rule.get("template"))
    niche = (rule.get("niche") or "").strip()
    if not niche:
        raise ValueError("La regla necesita un nicho.")

    # El historial evita que el Autopiloto repita temas ya producidos.
    previous = db.query(
        "SELECT topic FROM projects WHERE channel_id IS ? ORDER BY id DESC LIMIT 250",
        (rule.get("channel_id"),),
    )
    previous_topics = [row.get("topic", "") for row in previous]
    research = topic_engine.research_topic(niche, previous_topics)
    topic = research["topic"]
    title = topic
    duration = int(rule.get("duration_target_sec") or tpl.get("default_duration") or 30)
    pid = db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, "
        "template, caption_style, transition_default, resolution, fps, music, music_volume, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rule.get("channel_id"), title, topic, tpl.get("kind", "short"),
            rule.get("aspect") or tpl.get("aspect"), "borrador", duration,
            rule.get("voice") or "es", 150, 45,
            f"Autopiloto: {rule.get('name') or niche}. Fuente inicial: {research['url']}. "
            "La fuente es introductoria y debe contrastarse antes de publicar.",
            tpl["id"], rule.get("caption_style") or tpl.get("caption_style"),
            rule.get("transition_default") or "fundido", rule.get("resolution") or "1080p",
            int(rule.get("fps") or 25), rule.get("music") or "auto",
            float(rule.get("music_volume") if rule.get("music_volume") is not None else 0.12), db.now(), db.now(),
        ),
    )
    project = db.query_one("SELECT * FROM projects WHERE id=?", (pid,))
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
    if rule.get("voice") == "es-es-piper":
        from . import tts
        if tts.status().get("piper_available"):
            db.execute(
                "INSERT INTO sources(project_id, title, url, author, license, accessed_at, attribution, kind, notes, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    pid, "Piper DaveFX — voz neural española",
                    "https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/es/es_ES/davefx/medium",
                    "Piper voice contributors", "CC0",
                    db.now(), "Piper DaveFX (es_ES) · CC0 · https://huggingface.co/rhasspy/piper-voices",
                    "voz", "Modelo neural español instalado localmente; ficha de voz CC0.",
                    db.now(),
                ),
            )
    notes = db.query(
        "SELECT * FROM research_notes WHERE niche=? ORDER BY id DESC LIMIT 12",
        (niche,),
    )
    script = script_gen.generate_script(project, notes, [])
    ollama_url = (db.get_setting("ollama_url", "") or "").strip()
    if ollama_url and script_gen.ollama_available(ollama_url):
        try:
            script = script_gen.rewrite_with_ollama(ollama_url, "llama3.2", project, script, notes)
            db.log("info", "autopilot", "Guion reescrito con Ollama local", {"project_id": pid})
        except Exception as exc:
            db.log("warn", "autopilot", f"Ollama no pudo reescribir el guion; se conserva el guion basado en fuentes: {exc}", {"project_id": pid})
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
    return pid


def run_rule(rule_id: int, force: bool = False) -> dict:
    """Ejecuta una regla ahora: crea el proyecto, escribe el guion y encola el render."""
    from . import publish, worker

    rule = get_rule(rule_id)
    if not rule:
        raise ValueError("Regla inexistente")
    try:
        pid = _create_project(rule)
    except Exception as exc:
        db.execute(
            "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE id=?",
            (str(exc)[:500], db.now(), rule_id),
        )
        raise
    if rule.get("auto_publish"):
        try:
            publish.set_auto_publish(pid, True, rule.get("destination") or "entrega")
        except publish.PublishError as exc:
            db.log("warn", "autopilot", f"No se pudo activar la auto-subida: {exc}")
    job_id = worker.enqueue(pid, "render_project", {"privacy": rule.get("privacy") or "unlisted"})
    next_run = _ts(float(rule.get("cadence_hours") or 24))
    db.execute(
        "UPDATE autopilot_rules SET last_run_at=?, last_project_id=?, next_run_at=?, last_error=?, updated_at=? WHERE id=?",
        (db.now(), pid, next_run, "", db.now(), rule_id),
    )
    return {"rule_id": rule_id, "project_id": pid, "job_id": job_id, "next_run_at": next_run, "forced": force}


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
                (_ts(float(rule.get("cadence_hours") or 24)), str(exc)[:500], db.now(), row["id"]),
            )
            db.log("error", "autopilot", f"Regla {row['id']} falló: {exc}")
    return fired
