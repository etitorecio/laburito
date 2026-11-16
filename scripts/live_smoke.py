"""Prueba en vivo contra una instancia desplegada (sin mocks).

Ejercita el flujo real de la app para confirmar que el FFmpeg de la imagen
compilada cubre el pipeline completo (lavfi, drawtext, libx264, ffprobe):

  canal -> proyecto Short -> guion -> render en cola -> MP4 servido

Uso: python3 scripts/live_smoke.py https://mi-app.ejemplo.com
Sale con código 0 solo si el MP4 final se genera y se sirve.
"""
from __future__ import annotations

import io
import json
import sys
import time
import wave
import math
import struct
import subprocess
import tempfile
import os
import urllib.error
import urllib.request

from PIL import Image

BASE = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
if not BASE:
    print("Falta la URL base")
    raise SystemExit(2)

FAILS: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'} {label} {detail}".rstrip())
    if not ok:
        FAILS.append(f"{label} {detail}".strip())


def call(method: str, path: str, payload: dict | None = None, raw: bool = False):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AITuberLibre-Smoke/1.0 (+https://appjet.local)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read()
            if raw:
                return resp.status, body, resp.headers
            return resp.status, (json.loads(body) if body else None), resp.headers
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        return exc.code, {"error": detail}, exc.headers


def upload_media(path: str, filename: str, content_type: str, file_bytes: bytes):
    boundary = "----AITuberLibreSmokeBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + path,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
            "User-Agent": "AITuberLibre-Smoke/1.0 (+https://appjet.local)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
            return resp.status, (json.loads(payload) if payload else None), resp.headers
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        return exc.code, {"error": detail}, exc.headers


def main() -> int:
    print(f"Instancia: {BASE}")

    status, diag, _ = call("GET", "/api/diagnostics")
    check(status == 200, "diagnóstico responde", f"({status})")
    checks = (diag or {}).get("checks", {}) if isinstance(diag, dict) else {}
    check(bool(checks.get("ffmpeg")), "ffmpeg presente en la imagen")
    check(bool(checks.get("ffprobe")), "ffprobe presente en la imagen")
    check(bool(checks.get("fuente_subtitulos")), "fuente para subtítulos", str((diag or {}).get("font")))
    print(f"  info ffmpeg: {(diag or {}).get('ffmpeg_version')}")

    # Verifica las dos fábricas reales de la aplicación, no canales de YouTube ficticios.
    status, accounts, _ = call("GET", "/api/youtube/accounts")
    check(status == 200, "cuentas Google consultables", f"({status})")
    factory_rows = (accounts or {}).get("accounts", []) if isinstance(accounts, dict) else []
    factory_ids = {
        str(row.get("name", "")).strip().lower(): row.get("id")
        for row in factory_rows
        if str(row.get("name", "")).strip().lower() in {"historias", "frutinovelas"}
    }
    check(set(factory_ids) == {"historias", "frutinovelas"}, "existen exactamente las dos fábricas", str(sorted(factory_ids)))
    factory_projects: list[int] = []
    if set(factory_ids) == {"historias", "frutinovelas"}:
        for name, template, duration in (
            ("Historias", "reddit_story", 20),
            ("Frutinovelas", "frutinovela", 45),
        ):
            status, project, _ = call(
                "POST",
                "/api/projects",
                {
                    "title": f"Smoke {name}",
                    "topic": "Una historia breve con un giro inesperado",
                    "kind": "short",
                    "template": template,
                    "channel_id": factory_ids[name.lower()],
                    "duration_target_sec": duration,
                    "aspect": "9:16",
                    "voice": "es",
                    "video_type": "moving_images",
                    "visual_style": "automatico",
                    "music_volume": 0.12,
                    "notes": "[LABURITO_META]" + json.dumps({"characters": "Manzana, Banana y Pera"}) if template == "frutinovela" else "",
                },
            )
            check(status in (200, 201), f"proyecto {name} creado con su fábrica", f"({status})")
            project_id = (project or {}).get("id") if isinstance(project, dict) else None
            if not project_id:
                continue
            factory_projects.append(project_id)
            check(project.get("template") == template, f"plantilla correcta para {name}", str(project.get("template")))
            check(project.get("aspect") == "9:16", f"formato vertical para {name}", str(project.get("aspect")))
            status, generated, _ = call("POST", f"/api/projects/{project_id}/script")
            generated_scenes = ((generated or {}).get("project") or {}).get("scenes") or []
            check(status == 200 and len(generated_scenes) > 0, f"guion y escenas de {name}", f"({status}, {len(generated_scenes)} escenas)")
        for project_id in factory_projects:
            call("DELETE", f"/api/projects/{project_id}")

    status, channel, _ = call(
        "POST",
        "/api/channels",
        {
            "name": f"Prueba en vivo {int(time.time())}",
            "topic": "prueba automatizada de render",
            "language": "es",
            "audience": "prueba",
            "tone": "neutro",
            "visual_identity": "minimalista",
            "formats": "short",
            "cadence": "semanal",
        },
    )
    check(status in (200, 201), "canal creado", f"({status})")
    channel_id = (channel or {}).get("id")

    status, project, _ = call(
        "POST",
        "/api/projects",
        {
            "title": "Prueba en vivo de render",
            "topic": "por qué el cielo es azul",
            "kind": "short",
            "channel_id": channel_id,
            "duration_target_sec": 20,
            "aspect": "9:16",
            "voice": "es",
        },
    )
    check(status in (200, 201), "proyecto creado", f"({status})")
    project_id = (project or {}).get("id")
    if not project_id:
        print(json.dumps(project, ensure_ascii=False)[:400])
        return 1

    status, script, _ = call("POST", f"/api/projects/{project_id}/script")
    check(status == 200, "guion generado", f"({status})")
    scenes = ((script or {}).get("project") or {}).get("scenes") or []
    check(len(scenes) > 0, "escenas creadas", f"({len(scenes)})")
    if not scenes:
        return 1

    # Añade una imagen independiente superpuesta para comprobar el montaje multicapa real.
    overlay_buffer = io.BytesIO()
    Image.new("RGBA", (320, 180), (255, 190, 40, 220)).save(overlay_buffer, format="PNG")
    status, overlay, _ = upload_media(
        f"/api/projects/{project_id}/timeline-overlays/upload?start_sec=1.0",
        "smoke-overlay.png",
        "image/png",
        overlay_buffer.getvalue(),
    )
    check(status == 201 and bool((overlay or {}).get("id")), "capa visual independiente agregada", f"({status})")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_file:
        video_path = video_file.name
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=cyan:s=320x180:d=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", video_path],
            capture_output=True, timeout=30, check=True,
        )
        with open(video_path, "rb") as source_video:
            video_bytes = source_video.read()
        status, video_overlay, _ = upload_media(
            f"/api/projects/{project_id}/timeline-overlays/upload?start_sec=1.5",
            "smoke-video.mp4", "video/mp4", video_bytes,
        )
        check(status == 201 and (video_overlay or {}).get("kind") == "video", "capa de video independiente agregada", f"({status})")
        status, trimmed_overlay, _ = call(
            "PATCH", f"/api/timeline-overlays/{video_overlay['id']}",
            {"source_start_sec": 0.2, "source_end_sec": 1.8},
        )
        check(
            status == 200 and abs(float((trimmed_overlay or {}).get("source_start_sec") or 0) - 0.2) < 0.01,
            "recorte de fuente de capa de video guardado",
            f"({status})",
        )
        status, split_overlay, _ = call(
            "POST", f"/api/timeline-overlays/{video_overlay['id']}/split",
            {"at_sec": 2.5},
        )
        check(
            status == 201 and abs(float((split_overlay or {}).get("start_sec") or 0) - 2.5) < 0.01,
            "capa de video dividida en el cabezal",
            f"({status})",
        )
        scene_id = scenes[0]["id"]
        status, scene_video, _ = upload_media(
            f"/api/scenes/{scene_id}/media", "smoke-scene.mp4", "video/mp4", video_bytes,
        )
        check(status == 201, "video fuente de escena subido", f"({status})")
        status, trimmed_scene, _ = call(
            "PATCH", f"/api/scenes/{scene_id}",
            {"visual_trim_start_sec": 0.2, "visual_trim_end_sec": 1.8},
        )
        check(
            status == 200 and abs(float((trimmed_scene or {}).get("visual_source_duration_sec") or 0) - 2.0) < 0.5,
            "recorte de entrada/salida guardado contra la duración original",
            f"({status})",
        )
        status, history_entry, _ = call(
            "POST", f"/api/projects/{project_id}/history",
            {
                "target": "scene", "target_id": scene_id,
                "before": {"visual_trim_start_sec": 0, "visual_trim_end_sec": 0},
                "after": {"visual_trim_start_sec": 0.2, "visual_trim_end_sec": 1.8},
                "label": "Recorte de video",
            },
        )
        check(status == 201 and bool((history_entry or {}).get("id")), "historial persistente registrado", f"({status})")
        status, undone, _ = call("POST", f"/api/projects/{project_id}/history/undo")
        check(status == 200 and (undone or {}).get("ok"), "deshacer persistente", f"({status})")
        status, redone, _ = call("POST", f"/api/projects/{project_id}/history/redo")
        check(status == 200 and (redone or {}).get("ok"), "rehacer persistente", f"({status})")
        status, saved_history, _ = call("GET", f"/api/projects/{project_id}/history")
        check(status == 200 and (saved_history or {}).get("can_undo"), "historial restaurable", f"({status})")
    finally:
        os.unlink(video_path)

    audio_buffer = io.BytesIO()
    with wave.open(audio_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        frames = b"".join(
            struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * frame / 22050)))
            for frame in range(11025)
        )
        wav_file.writeframes(frames)
    status, audio_overlay, _ = upload_media(
        f"/api/projects/{project_id}/timeline-overlays/upload?start_sec=0.5",
        "smoke-audio.wav", "audio/wav", audio_buffer.getvalue(),
    )
    check(status == 201 and (audio_overlay or {}).get("kind") == "audio", "capa de audio independiente agregada", f"({status})")
    status, trimmed_audio, _ = call(
        "PATCH", f"/api/timeline-overlays/{audio_overlay['id']}",
        {"source_start_sec": 0.1, "source_end_sec": 0.4},
    )
    check(
        status == 200 and abs(float((trimmed_audio or {}).get("source_end_sec") or 0) - 0.4) < 0.01,
        "recorte de fuente de capa de audio guardado",
        f"({status})",
    )

    status, text_overlay, _ = call(
        "POST",
        f"/api/projects/{project_id}/timeline-overlays/text",
        {"text": "PRUEBA DE CAPAS", "start_sec": 1.2, "duration_sec": 2.0},
    )
    check(status == 201 and (text_overlay or {}).get("kind") == "text", "capa de texto independiente agregada", f"({status})")

    status, music_overlay, _ = call(
        "POST",
        f"/api/projects/{project_id}/timeline-overlays/music",
        {"bed_id": "ambiente", "start_sec": 0.2, "duration_sec": 5.0, "volume": 0.2},
    )
    check(status == 201 and (music_overlay or {}).get("kind") == "audio", "música local independiente generada", f"({status})")

    status, sfx_overlay, _ = call(
        "POST",
        f"/api/projects/{project_id}/timeline-overlays/sfx",
        {"effect": "chime", "start_sec": 0.8, "volume": 0.4},
    )
    check(status == 201 and (sfx_overlay or {}).get("kind") == "audio", "efecto local independiente generado", f"({status})")

    status, voice_overlay, _ = call(
        "POST",
        f"/api/projects/{project_id}/timeline-overlays/voice",
        {"text": "Esta es una prueba de voz en off local.", "start_sec": 1.0, "volume": 0.5},
    )
    check(status == 201 and (voice_overlay or {}).get("kind") == "audio", "voz en off local independiente generada", f"({status})")

    status, current_project, _ = call("GET", f"/api/projects/{project_id}")
    original_overlays = (current_project or {}).get("timeline_overlays") or []
    status, version, _ = call(
        "POST", f"/api/projects/{project_id}/duplicate",
        {"title": "Versión de prueba multicapa"},
    )
    version_overlays = (version or {}).get("timeline_overlays") or []
    check(
        status == 201 and (version or {}).get("title") == "Versión de prueba multicapa"
        and len(version_overlays) >= 5,
        "guardar versión conserva las capas independientes",
        f"({status}, {len(version_overlays)} capas)",
    )
    original_text = next((clip for clip in original_overlays if clip.get("kind") == "text"), None)
    copied_text = next((clip for clip in version_overlays if clip.get("kind") == "text"), None)
    if original_text and copied_text:
        check(original_text.get("path") != copied_text.get("path"), "la versión aísla sus capas de texto editables")

    status, job, _ = call("POST", f"/api/projects/{project_id}/render")
    check(status in (200, 202), "render encolado", f"({status})")
    job_id = (job or {}).get("id") or ((job or {}).get("job") or {}).get("id")

    deadline = time.time() + 460
    state = ""
    last = ""
    while time.time() < deadline:
        time.sleep(5)
        _, jobs, _ = call("GET", "/api/jobs")
        rows = jobs if isinstance(jobs, list) else (jobs or {}).get("jobs", [])
        row = None
        for candidate in rows:
            if candidate.get("project_id") == project_id:
                row = candidate
                break
        if row is None and job_id:
            row = next((c for c in rows if c.get("id") == job_id), None)
        if row:
            state = str(row.get("status") or "")
            msg = f"{state} {row.get('progress')}% {row.get('message') or ''}".strip()
            if msg != last:
                print(f"  ... {msg}")
                last = msg
            if state in {"listo", "error", "cancelado", "done", "failed", "completado"}:
                break
    check(state in {"listo", "done", "completado"}, "render terminó sin error", f"({state or 'sin estado'})")

    status, body, headers = call("GET", f"/api/projects/{project_id}/video", raw=True)
    check(status == 200, "MP4 servido", f"({status})")
    check(len(body) > 10_000, "MP4 con contenido", f"({len(body)} bytes)")
    if status == 200 and body[:4] == b"\x00\x00\x00\x18":
        print("  info contenedor MP4 válido (ftyp)")
    if status == 200:
        with open("/tmp/live_smoke.mp4", "wb") as fh:
            fh.write(body)

    _, _, _ = call("DELETE", f"/api/projects/{project_id}")
    call("DELETE", f"/api/channels/{channel_id}")

    if FAILS:
        print("\nFallos:")
        for item in FAILS:
            print(f"  - {item}")
        return 1
    print("\nFlujo en vivo correcto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
