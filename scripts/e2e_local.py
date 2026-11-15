"""Prueba end-to-end real de AITuber Libre (sin HTTP, sin mocks).

Ejecuta el pipeline completo en un directorio de datos temporal:
  canal -> proyecto -> guion -> voz espeak-ng -> render FFmpeg (9:16 y 16:9)
  -> subtítulos -> exportación ZIP -> verificación con ffprobe.

Uso:  python3 scripts/e2e_local.py
Sale con código 0 solo si todas las comprobaciones pasan.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

WORK = Path(tempfile.mkdtemp(prefix="aitub_e2e_"))
os.environ["AITUBER_DATA_DIR"] = str(WORK)
os.environ.setdefault("AITUBER_MUSIC_VOLUME", "0")

from app import db, media, options, render, script_gen  # noqa: E402

FAILURES: list[str] = []
NOTES: list[str] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        FAILURES.append(f"{label} {detail}".strip())
        print(f"  FAIL {label} {detail}")


def create_project(title: str, topic: str, kind: str, aspect: str, target: int) -> int:
    channel = db.execute(
        "INSERT INTO channels(name, topic, language, audience, tone, visual_identity, formats, cadence, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        ("Prueba E2E", topic, "es", "público general", "documental sobrio", "oscuro", "documental,short", "semanal", db.now(), db.now()),
    )
    return db.execute(
        "INSERT INTO projects(channel_id, title, topic, kind, aspect, status, duration_target_sec, voice, speed, pitch, notes, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (channel, title, topic, kind, aspect, "borrador", target, "es", 165, 45, "", db.now(), db.now()),
    )


def write_scenes(project_id: int) -> list[dict]:
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    script = script_gen.generate_script(project, [], [])
    statements = []
    for scene in script["scenes"]:
        statements.append(
            (
                "INSERT INTO scenes(project_id, idx, title, narration, visual_query, transition, status, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, scene["idx"], scene["title"], scene["narration"], scene["visual_query"],
                 scene["transition"], "borrador", db.now(), db.now()),
            )
        )
    db.execute_many(statements)
    return script["scenes"]


def run_case(label: str, kind: str, aspect: str, target: int) -> None:
    print(f"\n== Caso {label} ({aspect}, objetivo {target}s)")
    pid = create_project(f"E2E {label}", "la caída de Tenochtitlan y el fin de un imperio", kind, aspect, target)
    scenes = write_scenes(pid)
    check(len(scenes) >= 3, f"{label}: guion con escenas", f"(generó {len(scenes)})")

    progress: list[float] = []
    result = render.render_project(pid, on_progress=lambda p, msg="": progress.append(p))
    video = Path(result["video"])
    check(video.exists() and video.stat().st_size > 50_000, f"{label}: MP4 real generado",
          f"({video.stat().st_size if video.exists() else 0} bytes)")
    check(len(progress) > 1 and progress[-1] >= 99, f"{label}: progreso reportado", f"({progress[:3]}…)")

    info = media.probe_video(video)
    width, height = int(info.get("width", 0)), int(info.get("height", 0))
    duration = float(info.get("duration", 0) or 0)
    expected = {"9:16": (1080, 1920), "16:9": (1920, 1080)}[aspect]
    check((width, height) == expected, f"{label}: resolución {expected[0]}x{expected[1]}", f"(obtuvo {width}x{height})")
    check(duration > 5, f"{label}: duración de audio/vídeo", f"({duration:.1f}s)")

    srt = Path(result["srt"])
    vtt = Path(result["vtt"])
    srt_text = srt.read_text(encoding="utf-8") if srt.exists() else ""
    check(srt.exists() and "-->" in srt_text, f"{label}: subtítulos SRT")
    check(vtt.exists() and vtt.read_text(encoding="utf-8").startswith("WEBVTT"), f"{label}: subtítulos VTT")

    quality = result["quality"]
    check(int(quality.get("scenes", 0)) == len(scenes), f"{label}: informe de calidad con escenas")
    check(quality.get("tts_engines"), f"{label}: motor de voz registrado", f"({quality.get('tts_engines')})")
    if any("silencio" in str(x) for x in quality.get("tts_engines", [])):
        NOTES.append(f"{label}: alguna escena quedó sin voz (motor TTS no disponible).")
    for warning in quality.get("warnings", []):
        NOTES.append(f"{label}: aviso del render — {warning}")

    # Reanudación: un segundo render debe reutilizar las escenas cacheadas.
    again = render.render_project(pid)
    check(int(again["quality"].get("scenes_reused", 0)) >= 1, f"{label}: render reanudable reutiliza escenas",
          f"(reutilizadas: {again['quality'].get('scenes_reused')})")

    # Exportación ZIP con todo el paquete de entrega.
    zip_path = render.export_project(pid)
    check(zip_path.exists() and zip_path.stat().st_size > 50_000, f"{label}: ZIP exportado",
          f"({zip_path.stat().st_size} bytes)")
    names = zipfile.ZipFile(zip_path).namelist()
    expected_paths = {
        "vídeo final": lambda n: n.endswith("video_final.mp4"),
        "subtítulos SRT": lambda n: n.endswith(".srt"),
        "subtítulos VTT": lambda n: n.endswith(".vtt"),
        "guion": lambda n: n.startswith("guion/"),
        "fuentes": lambda n: n.startswith("fuentes/"),
        "miniatura": lambda n: n.startswith("miniaturas/"),
        "metadatos": lambda n: n.startswith("metadatos/"),
        "informe de calidad": lambda n: n.startswith("informe_calidad"),
    }
    for expected_name, predicate in expected_paths.items():
        check(any(predicate(n) for n in names), f"{label}: ZIP incluye {expected_name}")
    check(len(names) == len(set(names)), f"{label}: ZIP sin entradas duplicadas",
          f"({len(names) - len(set(names))} repetidas)")
    print(f"  ZIP: {zip_path} -> {names}")


def main() -> int:
    print(f"Datos de prueba en {WORK}")
    db.init_db()
    diag_tts = __import__("app.tts", fromlist=["status"]).status()
    print(f"Motor de voz: {diag_tts.get('engine')} disponible={diag_tts.get('available')}")
    if not diag_tts.get("available"):
        NOTES.append("espeak-ng no está instalado: el render usa silencio y lo informa como aviso.")

    run_case("short-vertical", "short", "9:16", 45)
    run_case("documental-horizontal", "documental", "16:9", 60)

    print("\n== Demostraciones visuales de subtítulos")
    for style_id in options.CAPTION_STYLES:
        try:
            preview = render.caption_preview(style_id)
            check(preview.exists() and preview.stat().st_size > 500,
                  f"vista previa real del estilo {style_id}")
        except Exception as exc:
            check(False, f"vista previa real del estilo {style_id}", str(exc))

    print("\n== Persistencia")
    check(db.scalar("SELECT COUNT(*) FROM projects") == 2, "dos proyectos en SQLite")
    check(db.scalar("SELECT COUNT(*) FROM scenes") >= 6, "escenas persistidas")
    check(db.scalar("SELECT COUNT(*) FROM jobs") == 0, "sin trabajos residuales (prueba en proceso)")
    backup = db.backup()
    check(Path(backup).exists(), "copia de seguridad de la base")

    print("\n== Resumen")
    if NOTES:
        for note in NOTES:
            print(f"  nota: {note}")
    if FAILURES:
        print(f"FALLARON {len(FAILURES)} comprobaciones:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("Todas las comprobaciones pasaron.")
    return 0


if __name__ == "__main__":
    code = main()
    if code == 0:
        shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(code)
