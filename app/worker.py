"""Worker en segundo plano con cola persistente en SQLite.

Un único hilo procesa tareas de a una (hardware modesto). Si el proceso se
reinicia, las tareas que estaban en ejecución vuelven a la cola y se reanudan
aprovechando las escenas ya cacheadas.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

from . import autopilot, db, persistence, publish, render

_stop = threading.Event()
_thread: threading.Thread | None = None
_wake = threading.Event()


def enqueue(project_id: int | None, kind: str, payload: dict | None = None) -> int:
    import json

    if kind == "publish_project" and project_id is not None:
        wanted_payload = payload or {}
        existing_jobs = db.query(
            "SELECT id, payload_json FROM jobs WHERE project_id=? AND kind=? AND status IN ('en_cola','ejecutando') ORDER BY id DESC",
            (int(project_id), kind),
        )
        for existing in existing_jobs:
            try:
                existing_payload = json.loads(existing.get("payload_json") or "{}")
            except (TypeError, ValueError):
                existing_payload = {}
            if existing_payload == wanted_payload:
                return int(existing["id"])
    job_id = db.execute(
        "INSERT INTO jobs(project_id, kind, status, progress, message, payload_json, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (project_id, kind, "en_cola", 0, "En cola", json.dumps(payload or {}), db.now(), db.now()),
    )
    _wake.set()
    return job_id


def recover_stale_jobs() -> int:
    """Devuelve a la cola las tareas interrumpidas por un cierre."""
    rows = db.query("SELECT id FROM jobs WHERE status='ejecutando'")
    for row in rows:
        db.execute(
            "UPDATE jobs SET status='en_cola', message=?, attempts=attempts+1, updated_at=? WHERE id=?",
            ("Reanudada tras reinicio", db.now(), row["id"]),
        )
    return len(rows)


def _claim_next() -> dict | None:
    rows = db.query("SELECT * FROM jobs WHERE status='en_cola' ORDER BY id LIMIT 1")
    if not rows:
        return None
    job = rows[0]
    db.execute(
        "UPDATE jobs SET status='ejecutando', attempts=attempts+1, started_at=?, message=?, updated_at=? WHERE id=? AND status='en_cola'",
        (db.now(), "Iniciando", db.now(), job["id"]),
    )
    current = db.query_one("SELECT * FROM jobs WHERE id=?", (job["id"],))
    return current if current and current["status"] == "ejecutando" else None


def _is_cancelled(job_id: int) -> bool:
    row = db.query_one("SELECT status FROM jobs WHERE id=?", (job_id,))
    return bool(row and row["status"] == "cancelado")


def _set_progress(job_id: int, pct: int, message: str) -> None:
    db.execute(
        "UPDATE jobs SET progress=?, message=?, updated_at=? WHERE id=?",
        (int(pct), message[:400], db.now(), job_id),
    )


def _auto_publish_blocker(render_result: dict) -> str:
    """Evita subir automáticamente un MP4 que quedó sin narración."""
    quality = render_result.get("quality") or {}
    engines = quality.get("tts_engines") or []
    if not engines or "silencio" in engines:
        return "Publicación automática retenida: el render quedó sin narración de voz. Revisá el motor TTS."
    return ""


def _validate_render_result(result: dict) -> dict:
    """No marca un render como terminado si el MP4 final no existe o está roto."""
    raw_path = result.get("video")
    if not raw_path:
        raise RuntimeError("El render no devolvió la ruta del MP4 final.")
    video = Path(raw_path)
    if not video.is_file() or video.stat().st_size < 1024:
        raise RuntimeError("El render terminó sin generar un MP4 final válido.")
    info = render.media.probe_video(video)
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    duration = float(info.get("duration") or 0)
    if width < 1 or height < 1 or duration <= 0:
        raise RuntimeError("El MP4 final no pasó la validación de ffprobe.")
    return {"path": str(video), "width": width, "height": height, "duration": duration}


def _scheduled_publish_settings(project_id: int) -> dict:
    """Permite entregas locales automáticas, pero nunca publica en YouTube sin revisión humana."""
    row = db.query_one(
        "SELECT auto_publish, destination, privacy FROM autopilot_rules WHERE last_project_id=? ORDER BY id DESC LIMIT 1",
        (project_id,),
    )
    if not row or not bool(row.get("auto_publish")) or (row.get("destination") or "youtube") == "youtube":
        return {"enabled": False, "destination": "youtube", "privacy": "unlisted"}
    destination = row.get("destination") or "youtube"
    if destination not in ("youtube", "entrega"):
        destination = "youtube"
    return {
        "enabled": True,
        "destination": destination,
        "privacy": row.get("privacy") or "unlisted",
    }


def run_job(job: dict) -> None:
    import json

    job_id = job["id"]
    project_id = job.get("project_id")
    try:
        if job["kind"] == "render_project":
            render_payload = json.loads(job.get("payload_json") or "{}")
            result = render.render_project(
                int(project_id),
                should_cancel=lambda: _is_cancelled(job_id),
                on_progress=lambda pct, msg: _set_progress(job_id, pct, msg),
            )
            result["validation"] = _validate_render_result(result)
            settings = _scheduled_publish_settings(int(project_id))
            blocker = _auto_publish_blocker(result) if settings["enabled"] else ""
            # Guardar el MP4 final en Storage también cuando queda para revisión
            # manual: de otro modo SQLite conservaría una ruta a un archivo efímero.
            video_backup_error = ""
            if persistence.configured():
                try:
                    persistence.sync_pending_video(int(project_id), result["video"])
                except Exception as exc:
                    video_backup_error = str(exc)
                    db.log("error", "persistence", f"No se pudo respaldar el MP4 final: {exc}",
                           {"project_id": int(project_id)})
            if settings["enabled"] and video_backup_error and not blocker:
                blocker = f"Publicación automática retenida: no se pudo respaldar el MP4 en almacenamiento persistente ({video_backup_error})."
            if settings["enabled"] and not blocker:
                destination = settings["destination"]
                publish_job_id = enqueue(
                    int(project_id),
                    "publish_project",
                    {"destination": destination, "calendar_id": None, "privacy": settings["privacy"]},
                )
                approval_message = f"Render validado. Publicación automática en cola (tarea #{publish_job_id})."
            elif blocker:
                approval_message = blocker + " El video quedó disponible para revisión manual."
            else:
                approval_message = "Render terminado y validado. Revisá el video y usá Publicar cuando quieras."
                if persistence.configured() and not video_backup_error:
                    approval_message += " Copia del MP4 guardada en almacenamiento persistente."
                elif video_backup_error:
                    approval_message += " ATENCIÓN: el MP4 no pudo respaldarse; descargalo antes de reemplazar el contenedor."
            db.execute(
                "UPDATE jobs SET message=?, updated_at=? WHERE id=?",
                (approval_message, db.now(), job_id),
            )
            db.log("info", "worker", approval_message, {"project_id": project_id})
            # El trabajo de publicación queda encolado antes de cerrar el render;
            # un reinicio no deja un MP4 terminado sin su siguiente paso.
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False), db.now(), db.now(), job_id),
            )
        elif job["kind"] == "publish_project":
            payload = json.loads(job.get("payload_json") or "{}")
            persistence.restore_pending_video(int(project_id))
            published = publish.publish(
                int(project_id),
                destination=payload.get("destination", "entrega"),
                calendar_id=payload.get("calendar_id"),
                privacy=payload.get("privacy", "unlisted"),
                on_progress=lambda pct, msg: _set_progress(job_id, pct, msg),
            )
            final_job_status = "error" if published.get("status") == "procesamiento_fallido" else "completado"
            db.execute(
                "UPDATE jobs SET status=?, progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                (
                    final_job_status,
                    (published.get("message") or f"Publicado en {published['destination']}")[:400],
                    json.dumps({
                        "url": published["url"],
                        "external_id": published["external_id"],
                        "destination": published["destination"],
                        "published_at": db.now(),
                        "verification": published.get("verification", "upload_api_confirmed"),
                    }, ensure_ascii=False),
                    db.now(),
                    db.now(),
                    job_id,
                ),
            )
            db.execute(
                "UPDATE autopilot_rules SET last_error=CASE WHEN ?='procesamiento_fallido' THEN ? WHEN destination='youtube' AND ?!='youtube' THEN last_error ELSE '' END, updated_at=? WHERE last_project_id=?",
                (
                    published.get("status", "publicado"),
                    (published.get("message") or "YouTube rechazó el procesamiento")[:500],
                    published["destination"],
                    db.now(),
                    int(project_id),
                ),
            )
        elif job["kind"] == "export_project":
            path = render.export_project(int(project_id))
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                ("Exportación lista", json.dumps({"zip": str(path)}), db.now(), db.now(), job_id),
            )
        elif job["kind"] == "install_piper_voice":
            from . import tts
            model_path = tts.install_piper_voice(
                on_progress=lambda pct, msg: _set_progress(job_id, pct, msg)
            )
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                ("Voz neural española instalada", json.dumps({"model": model_path}), db.now(), db.now(), job_id),
            )
        elif job["kind"] == "cleanup":
            removed = render.cleanup_temporaries(int(project_id))
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, finished_at=?, updated_at=? WHERE id=?",
                (f"Temporales eliminados: {removed}", db.now(), db.now(), job_id),
            )
        elif job["kind"] == "backup":
            path = db.backup()
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                ("Backup creado" if path else "No se pudo crear el backup",
                 json.dumps({"path": path}), db.now(), db.now(), job_id),
            )
        else:
            raise ValueError(f"Tipo de tarea desconocido: {job['kind']}")
    except render.Cancelled:
        db.execute(
            "UPDATE jobs SET status='cancelado', message=?, finished_at=?, updated_at=? WHERE id=?",
            ("Cancelada por el usuario", db.now(), db.now(), job_id),
        )
    except Exception as exc:
        attempt = int(job.get("attempts") or 1)
        retry = attempt < 3
        db.log(
            "warn" if retry else "error",
            "worker",
            f"Tarea {job_id} falló: {exc}" + (f" — reintento {attempt}/3" if retry else " — máximo de intentos alcanzado"),
            {"trace": traceback.format_exc()[-2000:], "attempt": attempt},
        )
        if project_id is not None and job.get("kind") in ("render_project", "publish_project"):
            db.execute(
                "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE last_project_id=?",
                (str(exc)[:500], db.now(), int(project_id)),
            )
        if retry:
            # Reintentos acotados para errores transitorios de red, TTS o FFmpeg.
            time.sleep(min(2 ** attempt, 8))
            db.execute(
                "UPDATE jobs SET status='en_cola', progress=0, message=?, finished_at=NULL, updated_at=? WHERE id=?",
                (f"Falló el intento {attempt}; reintentando automáticamente ({attempt}/3)", db.now(), job_id),
            )
            _wake.set()
        else:
            db.execute(
                "UPDATE jobs SET status='error', message=?, finished_at=?, updated_at=? WHERE id=?",
                (str(exc)[:400], db.now(), db.now(), job_id),
            )


def _loop() -> None:
    last_tick = 0.0
    last_persistence_sync = 0.0
    while not _stop.is_set():
        try:
            now = time.time()
            if now - last_persistence_sync >= 900:
                last_persistence_sync = now
                if persistence.configured():
                    try:
                        persistence.sync_backup()
                    except Exception as exc:
                        db.log("error", "persistence", f"No se pudo sincronizar la copia externa: {exc}")
            job = _claim_next()
            if job:
                run_job(job)
                if persistence.configured():
                    try:
                        persistence.sync_backup()
                        if job.get("kind") == "publish_project" and job.get("project_id") is not None:
                            current = db.query_one("SELECT status FROM jobs WHERE id=?", (job["id"],))
                            payload = json.loads(job.get("payload_json") or "{}")
                            if current and current.get("status") == "completado" and payload.get("destination") == "youtube":
                                try:
                                    persistence.delete_pending_video(int(job["project_id"]))
                                except Exception as exc:
                                    db.log("warn", "persistence", f"No se pudo limpiar el MP4 pendiente: {exc}",
                                           {"project_id": job.get("project_id")})
                    except Exception as exc:
                        db.log("error", "persistence", f"No se pudo respaldar después de la tarea: {exc}")
                continue
            # Piloto automático: revisa reglas vencidas como máximo una vez por minuto.
            if now - last_tick > 60:
                last_tick = now
                fired = autopilot.tick()
                if fired and persistence.configured():
                    try:
                        persistence.sync_backup()
                    except Exception as exc:
                        db.log("error", "persistence", f"No se pudo respaldar después del Autopiloto: {exc}")
        except Exception as exc:  # nunca matar el hilo
            db.log("error", "worker", f"Bucle del worker: {exc}")
        _wake.wait(timeout=2.0)
        _wake.clear()


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    db.init_db()
    publish.ensure_schema()
    autopilot.ensure_schema()
    recovered = recover_stale_jobs()
    if recovered:
        db.log("info", "worker", f"{recovered} tarea(s) reanudadas tras reinicio")
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="aitubel-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    _wake.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=5)


def status() -> dict:
    return {
        "worker_alive": bool(_thread and _thread.is_alive()),
        "queued": db.scalar("SELECT COUNT(*) FROM jobs WHERE status='en_cola'", default=0),
        "running": db.scalar("SELECT COUNT(*) FROM jobs WHERE status='ejecutando'", default=0),
        "done": db.scalar("SELECT COUNT(*) FROM jobs WHERE status='completado'", default=0),
        "failed": db.scalar("SELECT COUNT(*) FROM jobs WHERE status='error'", default=0),
    }
