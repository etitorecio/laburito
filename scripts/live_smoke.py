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

    status, text_overlay, _ = call(
        "POST",
        f"/api/projects/{project_id}/timeline-overlays/text",
        {"text": "PRUEBA DE CAPAS", "start_sec": 1.2, "duration_sec": 2.0},
    )
    check(status == 201 and (text_overlay or {}).get("kind") == "text", "capa de texto independiente agregada", f"({status})")

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
