"""Worker en segundo plano con cola persistente en SQLite.

Un único hilo procesa tareas de a una (hardware modesto). Si el proceso se
reinicia, las tareas que estaban en ejecución vuelven a la cola y se reanudan
aprovechando las escenas ya cacheadas.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from . import autopilot, db, publish, render

_stop = threading.Event()
_thread: threading.Thread | None = None
_wake = threading.Event()


def enqueue(project_id: int | None, kind: str, payload: dict | None = None) -> int:
    import json

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
    if "silencio" in engines:
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
    """Recupera el destino de la regla si falla la lectura de la configuración del proyecto."""
    row = db.query_one(
        "SELECT auto_publish, destination, privacy FROM autopilot_rules WHERE last_project_id=? ORDER BY id DESC LIMIT 1",
        (project_id,),
    )
    if not row or not bool(row.get("auto_publish")):
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
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                ("Render terminado", json.dumps(result, ensure_ascii=False), db.now(), db.now(), job_id),
            )
            # Auto-subida: si el proyecto la tiene activada, se publica al terminar.
            try:
                auto = publish.auto_publish_settings(int(project_id))
            except publish.PublishError as exc:
                message = "Render terminado, pero no se pudo consultar la autopublicación: " + str(exc)
                db.execute(
                    "UPDATE jobs SET message=?, updated_at=? WHERE id=?",
                    (message[:400], db.now(), job_id),
                )
                db.execute(
                    "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE last_project_id=?",
                    (message[:500], db.now(), int(project_id)),
                )
                db.log("error", "worker", message, {"project_id": project_id})
                # La configuración del proyecto pudo fallar transitoriamente.
                # Recuperamos la intención desde la regla para no perder la publicación.
                auto = _scheduled_publish_settings(int(project_id))
                if not auto["enabled"]:
                    db.execute(
                        "UPDATE jobs SET message=?, updated_at=? WHERE id=?",
                        ((message + " — no se pudo recuperar una regla activa; requiere revisión.")[:400], db.now(), job_id),
                    )
            blocker = _auto_publish_blocker(result)
            if auto["enabled"] and auto["destination"] == "youtube" and blocker:
                db.execute(
                    "UPDATE jobs SET message=?, updated_at=? WHERE id=?",
                    (blocker[:400], db.now(), job_id),
                )
                db.execute(
                    "UPDATE autopilot_rules SET last_error=?, updated_at=? WHERE last_project_id=?",
                    (blocker[:500], db.now(), int(project_id)),
                )
                db.log("warn", "worker", blocker, {"project_id": project_id})
                # No se simula una autopublicación mediante una entrega local.
                # El MP4 permanece en el proyecto y el bloqueo queda visible.
                auto = {"enabled": False, "destination": "youtube"}
            if auto["enabled"]:
                publish_job = enqueue(
                    int(project_id),
                    "publish_project",
                    {
                        "destination": auto["destination"],
                        "privacy": render_payload.get("privacy", auto.get("privacy", "unlisted")),
                    },
                )
                db.log(
                    "info",
                    "worker",
                    f"Auto-subida encolada para el proyecto {project_id}",
                    {"destination": auto["destination"], "job": publish_job},
                )
        elif job["kind"] == "publish_project":
            payload = json.loads(job.get("payload_json") or "{}")
            published = publish.publish(
                int(project_id),
                destination=payload.get("destination", "entrega"),
                calendar_id=payload.get("calendar_id"),
                privacy=payload.get("privacy", "unlisted"),
                on_progress=lambda pct, msg: _set_progress(job_id, pct, msg),
            )
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                (
                    f"Publicado en {published['destination']}",
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
                "UPDATE autopilot_rules SET last_error=CASE WHEN destination='youtube' AND ?!='youtube' THEN last_error ELSE '' END, updated_at=? WHERE last_project_id=?",
                (published["destination"], db.now(), int(project_id)),
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
    while not _stop.is_set():
        try:
            job = _claim_next()
            if job:
                run_job(job)
                continue
            # Piloto automático: revisa reglas vencidas como máximo una vez por minuto.
            if time.time() - last_tick > 60:
                last_tick = time.time()
                autopilot.tick()
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
    }
