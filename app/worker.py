"""Worker en segundo plano con cola persistente en SQLite.

Un único hilo procesa tareas de a una (hardware modesto). Si el proceso se
reinicia, las tareas que estaban en ejecución vuelven a la cola y se reanudan
aprovechando las escenas ya cacheadas.
"""
from __future__ import annotations

import threading
import time
import traceback

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
        "UPDATE jobs SET status='ejecutando', started_at=?, message=?, updated_at=? WHERE id=? AND status='en_cola'",
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
            db.execute(
                "UPDATE jobs SET status='completado', progress=100, message=?, result_json=?, finished_at=?, updated_at=? WHERE id=?",
                ("Render terminado", json.dumps(result, ensure_ascii=False), db.now(), db.now(), job_id),
            )
            # Auto-subida: si el proyecto la tiene activada, se publica al terminar.
            try:
                auto = publish.auto_publish_settings(int(project_id))
            except publish.PublishError:
                auto = {"enabled": False, "destination": "entrega"}
            if auto["enabled"]:
                publish_job = enqueue(
                    int(project_id),
                    "publish_project",
                    {
                        "destination": auto["destination"],
                        "privacy": render_payload.get("privacy", "unlisted"),
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
                    json.dumps({"url": published["url"], "external_id": published["external_id"]}, ensure_ascii=False),
                    db.now(),
                    db.now(),
                    job_id,
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
        db.log("error", "worker", f"Tarea {job_id} falló: {exc}", {"trace": traceback.format_exc()[-2000:]})
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
