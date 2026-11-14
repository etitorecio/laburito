"""Voz local (cero coste): espeak-ng por defecto, Piper opcional.

Nunca se usan servicios pagos ni APIs con clave. Si el motor no está instalado
se informa con claridad y el render avanza con una advertencia de calidad.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import urllib.request
import shutil
import subprocess
import wave
from pathlib import Path

from . import db

# Catálogo de voces del motor libre (espeak-ng). Cada entrada es una voz real:
# "engine_voice" es el idioma/variante que entiende el motor.
VOICES = {
    "es": {"engine_voice": "es", "label": "Español (neutro)", "gender": "neutro", "language": "es"},
    "es-ar": {"engine_voice": "es-la", "label": "Español rioplatense (espeak)", "gender": "neutro", "language": "es"},
    "es-es-piper": {"engine_voice": "es-la", "label": "Español neural (Piper DaveFX · España)", "gender": "masculino", "language": "es"},
    "es-mx": {"engine_voice": "es-419", "label": "Español latinoamericano", "gender": "neutro", "language": "es"},
    "es-masculino": {"engine_voice": "es", "label": "Español grave (masculino)", "gender": "masculino", "language": "es"},
    "es-agudo": {"engine_voice": "es", "label": "Español agudo (femenino)", "gender": "femenino", "language": "es"},
    "en": {"engine_voice": "en-us", "label": "Inglés (EE. UU.)", "gender": "neutro", "language": "en"},
    "en-gb": {"engine_voice": "en-gb", "label": "Inglés (Reino Unido)", "gender": "neutro", "language": "en"},
    "pt": {"engine_voice": "pt-br", "label": "Portugués (Brasil)", "gender": "neutro", "language": "pt"},
    "pt-pt": {"engine_voice": "pt", "label": "Portugués (Portugal)", "gender": "neutro", "language": "pt"},
    "it": {"engine_voice": "it", "label": "Italiano", "gender": "neutro", "language": "it"},
    "fr": {"engine_voice": "fr-fr", "label": "Francés", "gender": "neutro", "language": "fr"},
    "de": {"engine_voice": "de", "label": "Alemán", "gender": "neutro", "language": "de"},
    "ru": {"engine_voice": "ru", "label": "Ruso", "gender": "neutro", "language": "ru"},
    "uk": {"engine_voice": "uk", "label": "Ucraniano", "gender": "neutro", "language": "uk"},
    "nl": {"engine_voice": "nl", "label": "Neerlandés", "gender": "neutro", "language": "nl"},
    "pl": {"engine_voice": "pl", "label": "Polaco", "gender": "neutro", "language": "pl"},
    "sv": {"engine_voice": "sv", "label": "Sueco", "gender": "neutro", "language": "sv"},
    "tr": {"engine_voice": "tr", "label": "Turco", "gender": "neutro", "language": "tr"},
    "ar": {"engine_voice": "ar", "label": "Árabe", "gender": "neutro", "language": "ar"},
    "hi": {"engine_voice": "hi", "label": "Hindi", "gender": "neutro", "language": "hi"},
    "id": {"engine_voice": "id", "label": "Indonesio", "gender": "neutro", "language": "id"},
    "vi": {"engine_voice": "vi", "label": "Vietnamita", "gender": "neutro", "language": "vi"},
    "ja": {"engine_voice": "ja", "label": "Japonés", "gender": "neutro", "language": "ja"},
    "ko": {"engine_voice": "ko", "label": "Coreano", "gender": "neutro", "language": "ko"},
    "zh": {"engine_voice": "cmn", "label": "Chino mandarín", "gender": "neutro", "language": "zh"},
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
    model = os.environ.get("PIPER_MODEL") or db.get_setting("piper_model_path", "")
    piper_available = bool(piper and model and Path(model).exists())
    return {
        "engine": Path(engine).name if engine else None,
        "available": bool(engine),
        "piper_available": piper_available,
        "piper_installed": bool(piper),
        "piper_model": model or None,
        "voices": [
            {
                "id": k,
                "label": v["label"],
                "gender": v.get("gender", "neutro"),
                "language": v.get("language", k),
                "engine_voice": v["engine_voice"],
            }
            for k, v in VOICES.items()
        ],
        "note": "espeak-ng es una voz sintética de calidad modesta pero 100% libre y offline. "
        "Piper ofrece una voz neural española opcional, descargable sin claves ni pagos.",
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
    model = os.environ.get("PIPER_MODEL") or db.get_setting("piper_model_path", "")
    if piper and model and Path(model).exists() and voice == "es-es-piper":
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



def _md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def install_piper_voice(on_progress=None) -> str:
    """Descarga y verifica la voz española DaveFX de Piper desde el catálogo oficial."""
    if not piper_path():
        raise RuntimeError("El motor Piper no está instalado en este servidor. Revisá requirements.txt y reiniciá la app.")
    free_bytes = shutil.disk_usage(str(db.DATA_DIR)).free
    if free_bytes < 90 * 1024 * 1024:
        raise RuntimeError("No hay 90 MB libres para instalar la voz neural.")
    folder = db.DATA_DIR / "voices" / "es_ES-davefx-medium"
    folder.mkdir(parents=True, exist_ok=True)
    files = [
        (
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx",
            folder / "es_ES-davefx-medium.onnx",
            "dc515cd4ecc5f6f72fe14a941188fc9c",
            63201294,
        ),
        (
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json",
            folder / "es_ES-davefx-medium.onnx.json",
            "dd157b5eaf6930bf949cf416d9a9307a",
            4817,
        ),
        (
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/es/es_ES/davefx/medium/MODEL_CARD",
            folder / "MODEL_CARD",
            "5569c0fb20448308466216428b52f392",
            275,
        ),
    ]
    total_bytes = sum(item[3] for item in files)
    downloaded_total = 0
    for url, destination, expected_md5, expected_size in files:
        if destination.exists() and destination.stat().st_size == expected_size:
            digest = _md5_file(destination)
            if digest == expected_md5:
                downloaded_total += expected_size
                continue
        temporary = destination.with_suffix(destination.suffix + ".part")
        digest = hashlib.md5()
        size = 0
        request = urllib.request.Request(url, headers={"User-Agent": "Laburito/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    pct = 5 + int(85 * (downloaded_total + size) / total_bytes)
                    if on_progress:
                        on_progress(pct, f"Descargando voz neural española: {size // (1024 * 1024)} MB")
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"No se pudo descargar el modelo Piper: {exc}") from exc
        if size != expected_size or digest.hexdigest() != expected_md5:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"El archivo {destination.name} no pasó la verificación de integridad.")
        temporary.replace(destination)
        downloaded_total += size
    model_path = str(files[0][1])
    db.set_setting("piper_model_path", model_path)
    if on_progress:
        on_progress(100, "Voz neural española instalada y verificada")
    return model_path
