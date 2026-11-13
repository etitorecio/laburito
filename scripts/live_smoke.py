"""Prueba en vivo contra una instancia desplegada (sin mocks).

Ejercita el flujo real de la app para confirmar que el FFmpeg de la imagen
compilada cubre el pipeline completo (lavfi, drawtext, libx264, ffprobe):

  canal -> proyecto Short -> guion -> render en cola -> MP4 servido

Uso: python3 scripts/live_smoke.py https://mi-app.ejemplo.com
Sale con código 0 solo si el MP4 final se genera y se sirve.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

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
        headers={"Content-Type": "application/json", "Accept": "application/json"},
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


def main() -> int:
    print(f"Instancia: {BASE}")

    status, diag, _ = call("GET", "/api/diagnostics")
    check(status == 200, "diagnóstico responde", f"({status})")
    checks = (diag or {}).get("checks", {}) if isinstance(diag, dict) else {}
    check(bool(checks.get("ffmpeg")), "ffmpeg presente en la imagen")
    check(bool(checks.get("ffprobe")), "ffprobe presente en la imagen")
    check(bool(checks.get("fuente_subtitulos")), "fuente para subtítulos", str((diag or {}).get("font")))
    print(f"  info ffmpeg: {(diag or {}).get('ffmpeg_version')}")

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

    status, job, _ = call("POST", f"/api/projects/{project_id}/render")
    check(status in (200, 202), "render encolado", f"({status})")
    job_id = (job or {}).get("id") or ((job or {}).get("job") or {}).get("id")

    deadline = time.time() + 300
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
