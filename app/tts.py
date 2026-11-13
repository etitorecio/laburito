"""Voz local (cero coste): espeak-ng por defecto, Piper opcional.

Nunca se usan servicios pagos ni APIs con clave. Si el motor no está instalado
se informa con claridad y el render avanza con una advertencia de calidad.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import wave
from pathlib import Path

VOICES = {
    "es": {"engine_voice": "es", "label": "Español (neutro)"},
    "es-ar": {"engine_voice": "es-la", "label": "Español rioplatense"},
    "es-mx": {"engine_voice": "es-419", "label": "Español latinoamericano"},
    "en": {"engine_voice": "en-us", "label": "Inglés (EE. UU.)"},
    "pt": {"engine_voice": "pt-br", "label": "Portugués (Brasil)"},
}

SPEED_RANGE = (80, 300)
PITCH_RANGE = (0, 99)


def engine_path() -> str | None:
    for name in ("espeak-ng", "espeak"):
        found = shutil.which(name)
        if found:
            return found
    return None


def piper_path() -> str | None:
    return shutil.which("piper")


def status() -> dict:
    engine = engine_path()
    piper = piper_path()
    model = os.environ.get("PIPER_MODEL", "")
    return {
        "engine": Path(engine).name if engine else None,
        "available": bool(engine),
        "piper_available": bool(piper and model and Path(model).exists()),
        "piper_model": model or None,
        "voices": [{"id": k, "label": v["label"]} for k, v in VOICES.items()],
        "note": "espeak-ng es una voz sintética de calidad modesta pero 100% libre y offline. "
        "Piper (también libre) puede configurarse con PIPER_MODEL para una voz más natural.",
    }


def _clean(text: str) -> str:
    text = " ".join((text or "").split())
    # espeak-ng lee mal algunas marcas tipográficas: se normalizan.
    for src, dst in (("—", ", "), ("–", ", "), ("«", '"'), ("»", '"'), ("…", "..."), ("º", " grados")):
        text = text.replace(src, dst)
    return text


def synthesize(text: str, out_path: Path, voice: str = "es", speed: int = 150, pitch: int = 45) -> dict:
    """Genera un WAV con la narración. Devuelve metadatos del proceso."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spoken = _clean(text)
    if not spoken:
        raise ValueError("El texto de narración está vacío")

    speed = max(SPEED_RANGE[0], min(SPEED_RANGE[1], int(speed or 150)))
    pitch = max(PITCH_RANGE[0], min(PITCH_RANGE[1], int(pitch or 45)))

    piper = piper_path()
    model = os.environ.get("PIPER_MODEL", "")
    if piper and model and Path(model).exists():
        try:
            subprocess.run(
                [piper, "--model", model, "--output_file", str(out_path)],
                input=spoken.encode("utf-8"),
                check=True,
                timeout=300,
                capture_output=True,
            )
            return {"engine": "piper", "voice": voice, "speed": speed, "pitch": pitch, "chars": len(spoken)}
        except Exception:
            pass  # si Piper falla, se intenta espeak-ng

    engine = engine_path()
    if not engine:
        raise RuntimeError(
            "No hay motor TTS local instalado. Instalá espeak-ng (Debian/Ubuntu: "
            "sudo apt install espeak-ng · Alpine: apk add espeak-ng)."
        )

    engine_voice = VOICES.get(voice, {}).get("engine_voice", voice or "es")
    cmd = [
        engine,
        "-v", engine_voice,
        "-s", str(speed),
        "-p", str(pitch),
        "-w", str(out_path),
        "--stdin",
    ]
    proc = subprocess.run(cmd, input=spoken.encode("utf-8"), timeout=300, capture_output=True)
    if proc.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"espeak-ng falló: {proc.stderr.decode('utf-8', 'ignore')[:300]}")
    return {
        "engine": Path(engine).name,
        "voice": engine_voice,
        "speed": speed,
        "pitch": pitch,
        "chars": len(spoken),
    }


def silence_wav(out_path: Path, seconds: float, sample_rate: int = 24000) -> dict:
    """WAV de silencio: permite renderizar sin TTS y marcar la advertencia.

    Se escribe con la librería estándar, sin FFmpeg ni `-f lavfi`.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = max(0.5, seconds)
    frames = int(total * sample_rate)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)
    return {"engine": "silencio", "seconds": seconds}
