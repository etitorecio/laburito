"""Prueba E2E del piloto programado hasta entrega local (sin mocks ni publicación externa).

Cubre:
  regla programada -> descubrimiento de episodio no repetido -> proyecto/guion
  -> render FFmpeg real -> MP4 validado -> entrega local automática
  -> segunda programación sin duplicar tema -> recuperación tras reinicio.

Uso: python scripts/e2e_autopilot.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="laburito-autopilot-e2e-"))
os.environ["AITUBER_DATA_DIR"] = str(WORK)
os.environ.setdefault("AITUBER_DISABLE_EXTERNAL_MEDIA", "1")
os.environ.setdefault("AITUBER_MUSIC_VOLUME", "0")
for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
    os.environ.pop(key, None)
sys.path.insert(0, str(REPO))

from app import autopilot, db, publish, worker  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        FAILURES.append(f"{label} {detail}".strip())
        print(f"  FAIL {label} {detail}")


def main() -> int:
    print(f"Datos de prueba en {WORK}")
    db.init_db()
    publish.ensure_schema()
    autopilot.ensure_schema()

    channel = db.query_one(
        "SELECT id FROM channels WHERE lower(name)=? ORDER BY id LIMIT 1",
        ("frutinovelas",),
    )
    check(bool(channel), "fábrica Frutinovelas disponible")
    if not channel:
        return 1
    channel_id = int(channel["id"])

    print("\n== Activar una regla programada")
    rule = autopilot.create_rule({
        "name": "Piloto E2E Frutinovela",
        "niche": "Historias originales de la familia frutal",
        "channel_id": channel_id,
        "template": "frutinovela",
        "duration_target_sec": 30,
        "voice": "es",
        "resolution": "720p",
        "music": "ninguna",
        "music_volume": 0,
        "destination": "entrega",
        "auto_publish": True,
        "enabled": True,
        "cadence_hours": 24,
    })
    rule_id = int(rule["id"])
    db.execute(
        "UPDATE autopilot_rules SET next_run_at=? WHERE id=?",
        ("2000-01-01T00:00:00+00:00", rule_id),
    )
    fired = autopilot.tick()
    check(fired == 1, "el scheduler dispara la regla vencida", f"({fired})")

    scheduled = autopilot.get_rule(rule_id) or {}
    project_id = int(scheduled.get("last_project_id") or 0)
    check(project_id > 0, "el piloto crea un proyecto")
    if not project_id:
        return 1
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,)) or {}
    check(project.get("template") == "frutinovela", "usa la plantilla de la fábrica")
    check(int(project.get("channel_id") or 0) == channel_id, "el proyecto queda aislado en su canal")
    check(bool(db.query("SELECT id FROM scenes WHERE project_id=? ORDER BY idx", (project_id,))),
          "el piloto escribe escenas antes del render")

    print("\n== Render real desde la cola")
    render_job = worker._claim_next()
    check(bool(render_job), "el worker reclama una tarea")
    if not render_job:
        return 1
    check(render_job.get("kind") == "render_project", "la tarea reclamada es de render")
    check(int(render_job.get("project_id") or 0) == project_id, "el render corresponde al proyecto programado")
    worker.run_job(render_job)
    render_state = db.query_one("SELECT status,message,result_json FROM jobs WHERE id=?", (render_job["id"],)) or {}
    check(render_state.get("status") == "completado", "el render termina sin error", str(render_state.get("message") or ""))
    if render_state.get("status") != "completado":
        return 1
    rendered = json.loads(render_state.get("result_json") or "{}")
    video = Path((rendered.get("validation") or {}).get("path") or "")
    check(video.is_file() and video.stat().st_size > 50_000, "MP4 final real validado", str(video))
    if not video.is_file():
        return 1

    settings = publish.auto_publish_settings(project_id)
    check(settings.get("enabled") is True, "el piloto conserva la entrega local automática")
    check(settings.get("destination") == "entrega", "el destino automático es local, no YouTube")

    print("\n== Entrega local automática")
    publish_job = worker._claim_next()
    check(bool(publish_job), "el render encola el siguiente paso")
    if not publish_job:
        return 1
    check(publish_job.get("kind") == "publish_project", "el siguiente paso es la entrega")
    check(int(publish_job.get("project_id") or 0) == project_id, "la entrega corresponde al mismo proyecto")
    payload = json.loads(publish_job.get("payload_json") or "{}")
    check(payload.get("destination") == "entrega", "la cola no contiene una subida externa")
    worker.run_job(publish_job)
    publish_state = db.query_one("SELECT status,message FROM jobs WHERE id=?", (publish_job["id"],)) or {}
    check(publish_state.get("status") == "completado", "la entrega local termina", str(publish_state.get("message") or ""))

    rows = publish.list_publications(project_id)
    check(len(rows) == 1 and rows[0].get("status") == "publicado", "la biblioteca registra una entrega local")
    check(rows and rows[0].get("destination") == "entrega", "el registro no apunta a YouTube")
    if rows:
        url = str(rows[0].get("url") or "")
        delivered = Path(db.MEDIA_DIR) / url.split("/media/", 1)[1] if url.startswith("/media/") else Path("")
        check(delivered.is_file() and delivered.stat().st_size > 50_000, "el MP4 entregado existe y tiene contenido", str(delivered))
    check(not db.query(
        "SELECT id FROM publicaciones WHERE project_id=? AND destination='youtube'",
        (project_id,),
    ), "no se crea ninguna publicación externa")

    print("\n== Segunda ejecución y prevención de repetidos")
    first_topic = str(project.get("topic") or "")
    db.execute(
        "UPDATE autopilot_rules SET next_run_at=? WHERE id=?",
        ("2000-01-01T00:00:00+00:00", rule_id),
    )
    fired_again = autopilot.tick()
    check(fired_again == 1, "el piloto vuelve a ejecutar la regla")
    scheduled_again = autopilot.get_rule(rule_id) or {}
    second_project_id = int(scheduled_again.get("last_project_id") or 0)
    second_project = db.query_one("SELECT * FROM projects WHERE id=?", (second_project_id,)) or {}
    check(second_project_id != project_id, "la segunda ejecución crea otro proyecto")
    check(str(second_project.get("topic") or "") != first_topic, "el segundo episodio no repite el tema")
    check(int(second_project.get("channel_id") or 0) == channel_id, "el segundo episodio sigue en el mismo canal")

    print("\n== Recuperación de tarea tras reinicio")
    stale_job = db.query_one(
        "SELECT * FROM jobs WHERE project_id=? AND kind='render_project' AND status='en_cola' ORDER BY id DESC LIMIT 1",
        (second_project_id,),
    )
    check(bool(stale_job), "la segunda producción queda programada en la cola")
    if stale_job:
        db.execute(
            "UPDATE jobs SET status='ejecutando', message=?, updated_at=? WHERE id=?",
            ("Simulación de cierre abrupto", db.now(), stale_job["id"]),
        )
        recovered = worker.recover_stale_jobs()
        restored = db.query_one("SELECT status,attempts,message FROM jobs WHERE id=?", (stale_job["id"],)) or {}
        check(recovered >= 1, "el worker detecta una tarea interrumpida")
        check(restored.get("status") == "en_cola", "la tarea vuelve a la cola tras reinicio")
        check("Reanudada" in str(restored.get("message") or ""), "la recuperación deja un mensaje claro")

    if FAILURES:
        print("\nFallos:")
        for failure in FAILURES:
            print(f"  - {failure}")
        print(f"Datos conservados para diagnóstico: {WORK}")
        return 1
    print("\nPiloto programado, render, entrega local, no repetición y recuperación: todo correcto.")
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
