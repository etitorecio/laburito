"""Prueba de instalación y síntesis real de la voz Piper DaveFX."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["AITUBER_DATA_DIR"] = str(Path(tempfile.gettempdir()) / "laburito-piper-test")

from app import db, tts  # noqa: E402


def main() -> None:
    db.init_db()
    model = tts.install_piper_voice()
    output = Path(tempfile.gettempdir()) / "laburito-piper-test.wav"
    result = tts.synthesize(
        "Hola, esta es una prueba de la voz neural española de Laburito.",
        output,
        voice="es-es-piper",
    )
    if result.get("engine") != "piper" or not output.exists() or output.stat().st_size < 10000:
        raise SystemExit(f"La síntesis Piper no pasó la prueba: {result}")
    print(f"Piper OK: {model} · {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
