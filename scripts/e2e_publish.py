"""Prueba end-to-end de publicación y auto-subida (sin mocks).

Cubre, sobre un directorio de datos temporal:
  canal -> proyecto -> guion -> render real -> publicación "entrega"
  -> verificación de archivos, URL, metadatos y registro en SQLite
  -> fallo explícito de YouTube cuando faltan credenciales (nunca éxito falso)
  -> activación de la auto-subida por proyecto
  -> error claro al publicar un proyecto sin render

Uso:  python3 scripts/e2e_publish.py
Sale con código 0 solo si todas las comprobaciones pasan.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="aitubel-pub-"))
os.environ["AITUBER_DATA_DIR"] = str(WORK)
for key in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
    os.environ.pop(key, None)
sys.path.insert(0, str(REPO))

from app import db, publish, render, script_gen  # noqa: E402

FAILURES: list[str] = []
NOTES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        FAILURES.append(f"{label} {detail}".strip())
        print(f"  FAIL {label} {detail}")


def create_project(title: str, topic: str, kind: str, aspect: str, target: int, render_it: bool = True) -> int:
    channel = db.execute(
        "INSERT INTO channels(name, topic, language, audience, tone, visual_identity, formats, cadence, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("Prueba publicación", topic, "es", "público general", "documental sobrio", "oscuro",
         "documental,short", "semanal", db.now(), db.now()),
    )
    project_id = db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (channel, title, topic, kind, aspect, "borrador", target, "es", 165, 45, "", db.now(), db.now()),
    )
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    script = script_gen.generate_script(project, [], [])
    db.execute_many(
        [
            (
                "INSERT INTO scenes(project_id, idx, title, narration, visual_query, transition, status, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, scene["idx"], scene["title"], scene["narration"], scene["visual_query"],
                 scene["transition"], "borrador", db.now(), db.now()),
            )
            for scene in script["scenes"]
        ]
    )
    if render_it:
        render.render_project(project_id)
    return project_id


def main() -> int:
    print(f"Datos de prueba en {WORK}")
    db.init_db()
    publish.ensure_schema()
    print(f"Tabla publicaciones: {bool(db.query('PRAGMA table_info(publicaciones)'))}")

    print("\n== Destinos disponibles")
    dests = publish.destinations()
    ids = {d["id"]: d for d in dests}
    check(set(ids) == {"entrega", "youtube"}, "destinos entrega + youtube", f"({list(ids)})")
    check(ids["entrega"]["available"] is True, "entrega siempre disponible (sin claves)")
    check(ids["youtube"]["available"] is False, "youtube marcado no disponible sin credenciales")
    check(
        set(ids["youtube"]["missing_env"]) == {"YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"},
        "youtube informa las variables faltantes",
        f"({ids['youtube']['missing_env']})",
    )

    print("\n== Proyecto con render -> publicación 'entrega'")
    project_id = create_project("Publicación E2E", "la caída de Tenochtitlan y el fin de un imperio", "short", "9:16", 30)
    video = publish.video_path(db.query_one("SELECT * FROM projects WHERE id=?", (project_id,)))
    check(video.exists() and video.stat().st_size > 50_000, "MP4 de partida existe",
          f"({video.stat().st_size if video.exists() else 0} bytes)")

    progress: list[int] = []
    result = publish.publish(project_id, "entrega", on_progress=lambda pct, _msg: progress.append(pct))
    check(result["status"] == "publicado", "estado publicado")
    check(bool(progress) and progress[-1] == 100, "progreso de publicación hasta 100", f"({progress})")

    url = result["url"]
    check(url.startswith("/media/publicados/") and url.endswith(".mp4"), "URL de entrega servida por /media", f"({url})")
    delivered = Path(db.MEDIA_DIR) / url.split("/media/", 1)[1]
    check(delivered.exists() and delivered.stat().st_size == video.stat().st_size,
          "MP4 entregado con el mismo tamaño", f"({delivered})")

    folder = delivered.parent
    names = {p.name for p in folder.iterdir()}
    check("metadatos.json" in names, "metadatos.json en la entrega", f"({sorted(names)})")
    check("publicacion.txt" in names, "texto de publicación en la entrega")
    check(any(n.endswith(".srt") for n in names), "subtítulos SRT copiados")

    meta = json.loads((folder / "metadatos.json").read_text(encoding="utf-8"))
    check(bool(meta.get("title")), "título en metadatos", f"({meta.get('title')})")
    check(len(meta.get("description", "")) > 20, "descripción en metadatos")
    check(isinstance(meta.get("tags"), list) and len(meta["tags"]) >= 1, "etiquetas en metadatos", f"({meta.get('tags')})")

    rows = publish.list_publications(project_id)
    check(len(rows) == 1 and rows[0]["status"] == "publicado", "registro en SQLite", f"({len(rows)})")
    check(rows[0]["url"] == url, "el registro guarda la URL entregada")

    print("\n== YouTube sin credenciales falla con mensaje claro")
    before = len(publish.list_publications(project_id))
    try:
        publish.publish(project_id, "youtube")
        check(False, "youtube sin credenciales debe fallar")
    except publish.PublishError as exc:
        message = str(exc)
        check("YOUTUBE_CLIENT_ID" in message, "el error nombra la variable faltante", f"({message[:120]})")
        check("Settings" in message, "el error indica dónde configurarla")
    check(len(publish.list_publications(project_id)) == before, "no se registra una publicación falsa")

    print("\n== Destino inválido y proyecto inexistente")
    try:
        publish.publish(project_id, "tiktok")
        check(False, "destino desconocido debe fallar")
    except publish.PublishError as exc:
        check("Destino desconocido" in str(exc), "destino desconocido rechazado", f"({exc})")
    try:
        publish.publish(999_999, "entrega")
        check(False, "proyecto inexistente debe fallar")
    except publish.PublishError as exc:
        check("no existe" in str(exc), "proyecto inexistente rechazado", f"({exc})")

    print("\n== Proyecto sin render")
    empty_id = create_project("Sin render", "tema sin renderizar", "short", "9:16", 20, render_it=False)
    try:
        publish.publish(empty_id, "entrega")
        check(False, "publicar sin render debe fallar")
    except publish.PublishError as exc:
        check("render" in str(exc).lower(), "error pide renderizar primero", f"({exc})")

    print("\n== Auto-subida por proyecto")
    check(publish.auto_publish_settings(project_id)["enabled"] is False, "auto-subida desactivada por defecto")
    state = publish.set_auto_publish(project_id, True, "entrega")
    check(state["enabled"] is True and state["destination"] == "entrega", "auto-subida activada", f"({state})")
    persisted = db.query_one("SELECT auto_publish, publish_destination FROM projects WHERE id=?", (project_id,))
    check(int(persisted["auto_publish"]) == 1 and persisted["publish_destination"] == "entrega",
          "auto-subida persistida en la base")
    off = publish.set_auto_publish(project_id, False, "youtube")
    check(off["enabled"] is False and off["destination"] == "youtube", "auto-subida desactivada con destino youtube")

    print("\n== Resumen")
    for note in NOTES:
        print(f"  nota: {note}")
    if FAILURES:
        print(f"FALLARON {len(FAILURES)} comprobaciones:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("Todas las comprobaciones de publicación pasaron.")
    return 0


if __name__ == "__main__":
    code = main()
    if code == 0:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(code)
