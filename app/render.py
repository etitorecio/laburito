"""Render real con FFmpeg: documental horizontal (16:9) y Shorts verticales (9:16).

Diseño para hardware modesto:
- El vídeo se arma escena por escena y cada escena se cachea por hash de su
  contenido, así un render interrumpido se reanuda sin repetir trabajo.
- Un solo proceso FFmpeg por escena (subtítulos quemados con ventanas drawtext),
  sin modelos de IA ni GPU.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import time
import threading
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import db, media, options, tts

ASPECTS = options.ASPECTS


class Cancelled(Exception):
    """El usuario canceló la tarea."""


def _style(project: dict) -> dict:
    """Estilo de subtítulos del proyecto (13 opciones, ver app/options.py)."""
    return options.caption_style(project)

def _project_metadata(project: dict) -> dict:
    notes = str(project.get("notes") or "")
    marker = "[LABURITO_META]"
    if marker not in notes:
        return {}
    try:
        metadata = json.loads(notes.split(marker, 1)[1])
        return metadata if isinstance(metadata, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _captions_enabled(project: dict) -> bool:
    """Lee el interruptor opcional guardado por el Autopiloto; proyectos normales conservan subtítulos."""
    return bool(_project_metadata(project).get("captions_enabled", True))

def _thumbnail_enabled(project: dict) -> bool:
    """Las miniaturas están activadas por defecto y pueden desactivarse en la configuración."""
    return bool(_project_metadata(project).get("create_thumbnail", True))


def _custom_visual_style_id(project: dict) -> str:
    """Traduce una descripción libre a un filtro local aproximado, sin prometer generación IA."""
    fallback = project.get("visual_style") or "automatico"
    prompt = str(_project_metadata(project).get("visual_style_prompt") or "").lower()
    if not prompt:
        return fallback
    mappings = [
        (("cyberpunk", "neón", "neon", "futurista"), "cyberpunk"),
        (("anime", "manga", "japonés", "japones"), "anime"),
        (("pixel", "8-bit", "8 bit", "retro game"), "pixel_art"),
        (("acuarela", "watercolor", "pintura al agua"), "acuarela"),
        (("comic", "cómic", "historieta"), "comic"),
        (("noir", "blanco y negro", "monocromo"), "noir"),
        (("vintage", "retro", "película antigua"), "vintage"),
        (("cinemático", "cinematic", "cine"), "cinematico"),
        (("realista", "fotográfico", "fotografico"), "realista"),
    ]
    for keywords, style_id in mappings:
        if any(keyword in prompt for keyword in keywords):
            return style_id
    return fallback


def _size(project: dict) -> tuple[int, int]:
    aspect = project.get("aspect") or options.template(project.get("template"))["aspect"]
    return options.dimensions(aspect, project.get("resolution") or "1080p")


def _h(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:12]


def _workdir(project_id: int) -> Path:
    path = db.RENDER_DIR / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _audio_dir(project_id: int) -> Path:
    path = db.MEDIA_DIR / "audio" / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _visual_dir(project_id: int) -> Path:
    path = db.MEDIA_DIR / "visuals" / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _check_cancel(should_cancel) -> None:
    if should_cancel and should_cancel():
        raise Cancelled()


def _ff(args: list[str], timeout: int = 1200) -> None:
    proc = media.run([media.ffmpeg(), "-y", *args], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or b"").decode("utf-8", "ignore")[-1200:] or "FFmpeg falló")


def ensure_audio(project: dict, scene: dict) -> tuple[Path, float, dict]:
    """WAV por escena, cacheado por texto. Devuelve (ruta, duración, info)."""
    narration = (scene.get("narration") or "").strip()
    if not narration:
        raise ValueError(f"La escena «{scene.get('title')}» no tiene narración")
    tts_status = tts.status()
    cached_engine = (
        "piper" if (project.get("voice") or "es") == "es-es-piper" and tts_status.get("piper_available")
        else Path(tts_status["engine"]).name if tts_status.get("engine")
        else "silencio"
    )
    engine_signature = f"{cached_engine}|{tts_status.get('piper_model') or ''}"
    key = _h(f"{narration}|{project.get('voice')}|{project.get('speed')}|{project.get('pitch')}|{engine_signature}")
    wav = _audio_dir(int(project["id"])) / f"{key}.wav"
    metadata_path = wav.with_suffix(".json")
    info: dict = {}
    if wav.exists() and metadata_path.exists():
        try:
            info = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            info = {}
    if wav.exists() and info.get("engine") == "silencio":
        # No reutilizar una pista muda: volver a intentar si el motor ya se recuperó.
        wav.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
    if wav.exists():
        info["cached"] = True
        info.setdefault("engine", cached_engine)
    else:
        info = {"cached": False}
        try:
            info.update(
                tts.synthesize(
                    narration,
                    wav,
                    voice=project.get("voice") or "es",
                    speed=int(project.get("speed") or 150),
                    pitch=int(project.get("pitch") or 45),
                )
            )
        except Exception as exc:
            # El Short no se marcará como terminado si no hay narración real.
            words = max(1, len(narration.split()))
            tts.silence_wav(wav, seconds=words / 2.6)
            info.update({"engine": "silencio", "warning": str(exc)})
        metadata_path.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    duration = media.probe_duration(wav)
    if duration <= 0:
        words = max(1, len(narration.split()))
        duration = words / 2.6
    return wav, duration, info


def ensure_visual(project: dict, scene: dict) -> tuple[Path, str, dict]:
    """Resuelve imágenes o clips de fondo propios/autorizados."""
    width, height = _size(project)
    video_type = (project.get("video_type") or "moving_images").strip()
    if video_type == "skeleton":
        from . import skeleton
        action = skeleton.action_for(scene.get("title") or "", scene.get("narration") or "")
        clip = skeleton.ensure_clip(action)
        return clip, "skeleton_local", {
            "license": "Animación procedural original generada localmente",
            "author": "Laburito",
            "url": f"local://skeleton/{action}",
            "title": f"Esqueleto animado · {action}",
            "provider": "skeleton_local",
        }
    if video_type in {"stock_footage", "minecraft", "subway", "background_video"}:
        clip_dir = db.DATA_DIR / "background_clips" / video_type
        clips = sorted(clip_dir.glob("*.mp4")) if clip_dir.exists() else []
        required = options.VIDEO_CLIP_MINIMUMS[video_type]
        if len(clips) < required:
            raise RuntimeError(
                f"El formato {video_type} necesita {required} clip(s) propios o autorizados. "
                f"Hay {len(clips)} cargados."
            )
        scene_index = int(scene.get("idx") or 0)
        project_index = int(project.get("id") or 0)
        chosen = clips[0] if video_type == "background_video" else clips[(project_index + scene_index) % len(clips)]
        return chosen, "video_fondo", {
            "license": "Clip propio o autorizado; derechos confirmados al cargar",
            "author": "Biblioteca local del usuario",
            "url": f"local://background-clips/{video_type}/{chosen.name}",
            "title": chosen.name,
            "provider": "biblioteca_local",
            "mode": "reutilizar el mismo clip en cada escena" if video_type == "background_video" else "rotación de clips por escena",
        }
    existing = (scene.get("visual_path") or "").strip()
    if existing and Path(existing).exists() and Path(existing).suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        return Path(existing), scene.get("visual_kind") or "recurso", {
            "license": scene.get("visual_license") or "sin verificar",
            "author": scene.get("visual_author") or "desconocido",
            "url": scene.get("visual_url") or "",
        }

    if project.get("template") == "frutinovela":
        metadata = _project_metadata(project)
        cast = str(metadata.get("characters") or project.get("content_pillars") or "")
        fruit_key = _h(f"frutinovela|{scene.get('title')}|{cast}|{width}x{height}")
        fruit_card = _visual_dir(int(project["id"])) / f"frutinovela_{fruit_key}.png"
        if not fruit_card.exists():
            media.make_fruit_card(
                fruit_card,
                scene.get("title") or project.get("title") or "Un secreto inesperado",
                cast,
                width,
                height,
            )
        return fruit_card, "frutinovela_local", {
            "license": "Ilustración procedural original generada localmente",
            "author": "Laburito",
            "url": f"local://frutinovela/{fruit_key}",
            "title": scene.get("title") or "Escena de Frutinovela",
            "provider": "frutinovela_local",
        }

    key = _h(f"{scene.get('title')}|{scene.get('visual_query')}|{width}x{height}")
    folder = _visual_dir(int(project["id"]))
    query = (scene.get("visual_query") or project.get("topic") or "").strip()
    custom_style_prompt = str(_project_metadata(project).get("visual_style_prompt") or "").strip()
    if custom_style_prompt:
        query = f"{query} {custom_style_prompt}".strip()
    providers = () if os.environ.get("AITUBER_DISABLE_EXTERNAL_MEDIA", "").lower() in ("1", "true", "yes") else ("wikimedia", "openverse")
    for provider in providers:
        try:
            search = media.search_wikimedia if provider == "wikimedia" else media.search_openverse
            for item in search(query, limit=6):
                image_url = (item.get("url") or "").strip()
                if not image_url:
                    continue
                license_name = (item.get("license") or "").strip()
                license_key = license_name.lower().replace(" ", "").replace("-", "")
                if "nc" in license_key or "noncommercial" in license_key or "nd" in license_key or "noderivatives" in license_key:
                    continue
                if not (
                    license_key.startswith("ccby")
                    or license_key.startswith("cc0")
                    or "publicdomain" in license_key
                    or license_key in ("by", "bysa", "cc0")
                ):
                    continue
                try:
                    downloaded = media.download_asset(image_url, folder)
                    if downloaded.get("content_type", "").split(";")[0] not in (
                        "image/jpeg", "image/png", "image/webp", "image/gif"
                    ):
                        continue
                    return Path(downloaded["path"]), provider, {
                        "license": (item.get("license") or "consultar licencia") + (f" · {item.get('license_url')}" if item.get("license_url") else ""),
                        "author": item.get("author") or "desconocido",
                        "url": item.get("page") or image_url,
                        "title": item.get("title") or "",
                        "provider": item.get("provider") or provider,
                    }
                except Exception:
                    continue
        except Exception:
            continue

    card = folder / f"{key}.png"
    if not card.exists():
        media.make_card(
            card,
            scene.get("title") or project.get("title") or "Laburito",
            query or project.get("topic") or "",
            width,
            height,
            kind="short" if project.get("kind") == "short" else "documental",
        )
    return card, "tarjeta_generada", {
        "license": "generada localmente (no es material histórico)",
        "author": "Laburito",
        "url": "",
    }


def _drawtext_chain(cues: list[dict], font: str, width: int, height: int, style: dict) -> str:
    fontsize = max(20, int(width * style["font_ratio"]))
    y = int(height * (1 - style["y_from_bottom"]))
    line_spacing = max(6, fontsize // 6)
    parts = []
    for cue in cues:
        draw = (
            f"drawtext=fontfile={font}:textfile={cue['file']}:fontsize={fontsize}"
            f":fontcolor={style.get('fontcolor', 'white')}:line_spacing={line_spacing}"
            f":x=(w-text_w)/2:y={y}-th"
        )
        if int(style.get("outline") or 0) > 0:
            draw += f":borderw={int(style['outline'])}:bordercolor=black"
        if style.get("box"):
            draw += (
                f":box=1:boxcolor={style.get('boxcolor', 'black')}@{style.get('box_alpha', '0.55')}"
                f":boxborderw={max(10, fontsize // 3)}"
            )
        draw += f":enable='between(t,{cue['start']:.2f},{cue['end']:.2f})'"
        parts.append(draw)
    return ",".join(parts)


_PREVIEW_LOCK = threading.Lock()


def caption_preview(style_id: str) -> Path:
    with _PREVIEW_LOCK:
        return _caption_preview_unlocked(style_id)


def _caption_preview_unlocked(style_id: str) -> Path:
    """Genera una muestra PNG con el mismo filtro drawtext que usa el render."""
    if style_id not in options.CAPTION_STYLES:
        raise ValueError("Estilo de subtítulos desconocido")
    preview_dir = db.DATA_DIR / "caption_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / f"{style_id}.png"
    if output.exists() and output.stat().st_size > 500:
        return output

    style = options.CAPTION_STYLES[style_id]
    font = media.font_path()
    if not font:
        raise RuntimeError("No hay una fuente TTF instalada para generar la demostración")
    width, height = 480, 854
    sample = "Esta historia cambió todo y nadie lo vio venir."
    cues = media.caption_chunks(
        sample, 2.0, style["max_words"], style["max_chars"], style["max_lines"]
    )
    cue_dir = preview_dir / f"{style_id}_cues"
    cue_dir.mkdir(parents=True, exist_ok=True)
    for index, cue in enumerate(cues):
        lines = cue["lines"]
        if style.get("uppercase"):
            lines = [line.upper() for line in lines]
        text_file = cue_dir / f"{index}.txt"
        text_file.write_text("\n".join(lines), encoding="utf-8")
        cue["file"] = str(text_file)

    background = [
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x102a43:t=fill",
        "drawbox=x=iw*0.08:y=ih*0.18:w=iw*0.84:h=ih*0.34:color=0x2563eb@0.35:t=fill",
        "drawbox=x=iw*0.20:y=ih*0.52:w=iw*0.95:h=ih*0.26:color=0x0b132b@0.9:t=fill",
    ]
    background.append(_drawtext_chain(cues, font, width, height, style))
    _ff([
        "-f", "lavfi", "-i", f"color=c=0x0b132b:s={width}x{height}:d=2:r=1",
        "-vf", ",".join(background), "-frames:v", "1", str(output),
    ], timeout=60)
    if not output.exists() or output.stat().st_size < 500:
        raise RuntimeError("FFmpeg no pudo generar la demostración de subtítulos")
    return output


def _motion_filters(transition: str, width: int, height: int, duration: float, fps: int) -> list[str]:
    """Transición/movimiento real de la escena (8 opciones)."""
    kind = (transition or "corte").strip()
    if kind == "fundido" and duration > 1.5:
        return ["fade=t=in:st=0:d=0.45", f"fade=t=out:st={max(0.0, duration - 0.45):.2f}:d=0.45"]
    if kind == "fundido_blanco" and duration > 1.0:
        return [
            "fade=t=in:st=0:d=0.30:color=white",
            f"fade=t=out:st={max(0.0, duration - 0.30):.2f}:d=0.30:color=white",
        ]
    if kind in ("zoom_in", "zoom_out", "kenburns"):
        if kind == "zoom_in":
            zoom = "min(1.0+0.0012*on,1.12)"
            xexpr = "iw/2-(iw/zoom/2)"
        elif kind == "zoom_out":
            zoom = "max(1.12-0.0012*on,1.0)"
            xexpr = "iw/2-(iw/zoom/2)"
        else:
            zoom = "min(1.0+0.0009*on,1.10)"
            xexpr = "iw/2-(iw/zoom/2)+((iw-iw/zoom)/2)*on/240"
        return [f"zoompan=z='{zoom}':x='{xexpr}':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps}"]
    if kind in ("paneo_izq", "paneo_der"):
        span = f"{max(0.5, duration):.2f}"
        pos = "t" if kind == "paneo_der" else f"({span}-t)"
        return [
            f"scale={int(width * 1.15)}:{int(height * 1.15)}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}:x='(iw-ow)*{pos}/{span}':y='(ih-oh)/2'",
        ]
    return []


def transition_preview(transition_id: str) -> Path:
    with _PREVIEW_LOCK:
        return _transition_preview_unlocked(transition_id)


def _transition_preview_unlocked(transition_id: str) -> Path:
    """Genera un clip corto que muestra el efecto real aplicado por FFmpeg."""
    if transition_id not in options.TRANSITION_IDS:
        raise ValueError("Movimiento de escena desconocido")
    preview_dir = db.DATA_DIR / "transition_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / f"{transition_id}.mp4"
    if output.exists() and output.stat().st_size > 1000:
        return output

    width, height, duration, fps = 360, 640, 3.0, 20
    base = _visual_style_sample_base(preview_dir / "paisaje-demo.png")
    filters = _motion_filters(transition_id, width, height, duration, fps)
    filters.append("format=yuv420p")
    _ff([
        "-loop", "1", "-framerate", str(fps), "-i", str(base), "-t", str(duration),
        "-vf", ",".join(filters), "-an", "-c:v", "libx264", "-preset", "ultrafast",
        "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ], timeout=90)
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError("FFmpeg no pudo generar la demostración de movimiento")
    return output


def _visual_style_filters(style_id: str | None) -> list[str]:
    """Tratamientos visuales locales compartidos por render y demostraciones."""
    filters = {
        "automatico": [],
        "cinematico": ["eq=contrast=1.12:saturation=1.08:brightness=-0.015", "vignette=PI/5"],
        "realista": ["eq=contrast=1.03:saturation=1.05", "unsharp=5:5:0.4:5:5:0.0"],
        "anime": ["eq=contrast=1.15:saturation=1.6", "unsharp=5:5:0.7:5:5:0.0"],
        "pixel_art": ["scale=iw/8:ih/8:flags=neighbor", "scale=iw*8:ih*8:flags=neighbor"],
        "noir": ["hue=s=0", "eq=contrast=1.35:brightness=-0.03", "vignette=PI/4"],
        "vintage": [
            "colorchannelmixer=.393:.769:.189:.349:.686:.168:.272:.534:.131",
            "eq=contrast=1.05:saturation=0.85", "vignette=PI/5",
        ],
        "cyberpunk": [
            "eq=contrast=1.15:saturation=1.65",
            "colorbalance=rs=.08:gs=-.04:bs=.15",
        ],
        "acuarela": ["gblur=sigma=0.6", "eq=saturation=1.2:contrast=.95"],
        "comic": ["edgedetect=low=0.1:high=0.3", "eq=contrast=1.2:saturation=1.3"],
    }
    return filters.get((style_id or "automatico").strip(), [])


def visual_style_preview(style_id: str) -> Path:
    with _PREVIEW_LOCK:
        return _visual_style_preview_unlocked(style_id)


def _visual_style_sample_base(path: Path) -> Path:
    """Paisaje ilustrado original para comparar los tratamientos de color."""
    if path.exists() and path.stat().st_size > 1000:
        return path
    width, height = 480, 854
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    stops = [
        (0.0, (9, 24, 52)),
        (0.48, (43, 83, 112)),
        (0.68, (205, 129, 91)),
        (1.0, (13, 34, 49)),
    ]
    for y in range(height):
        t = y / max(1, height - 1)
        for index in range(len(stops) - 1):
            if stops[index][0] <= t <= stops[index + 1][0]:
                a, ca = stops[index]
                b, cb = stops[index + 1]
                mix = (t - a) / (b - a)
                color = tuple(int(ca[c] * (1 - mix) + cb[c] * mix) for c in range(3))
                break
        else:
            color = stops[-1][1]
        for x in range(width):
            pixels[x, y] = color

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((292, 175, 418, 301), fill=(255, 194, 125, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(34))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image)
    draw.ellipse((325, 208, 385, 268), fill=(255, 219, 161, 255))
    draw.polygon([(0, 520), (95, 350), (165, 475), (260, 320), (390, 480), (480, 375), (480, 660), (0, 660)],
                 fill=(64, 91, 104, 255))
    draw.polygon([(0, 610), (110, 455), (205, 585), (315, 430), (480, 600), (480, 730), (0, 730)],
                 fill=(29, 59, 73, 255))
    draw.polygon([(0, 680), (120, 610), (240, 690), (355, 600), (480, 680), (480, 854), (0, 854)],
                 fill=(11, 37, 51, 255))
    draw.polygon([(0, 725), (130, 700), (250, 738), (380, 690), (480, 725), (480, 854), (0, 854)],
                 fill=(19, 69, 84, 255))
    # Árboles y una silueta humana para dar escala a la escena.
    for x, base_y, size in ((40, 715, 1.0), (85, 704, .75), (425, 720, 1.05), (455, 705, .8)):
        draw.rectangle((x - 4, base_y - 45 * size, x + 4, base_y), fill=(7, 24, 34, 255))
        draw.polygon([(x, base_y - 110 * size), (x - 28 * size, base_y - 38 * size),
                      (x + 28 * size, base_y - 38 * size)], fill=(8, 29, 39, 255))
    draw.ellipse((238, 664, 252, 678), fill=(4, 15, 23, 255))
    draw.line((245, 678, 245, 720), fill=(4, 15, 23, 255), width=8)
    draw.line((245, 690, 228, 708), fill=(4, 15, 23, 255), width=6)
    draw.line((245, 690, 262, 708), fill=(4, 15, 23, 255), width=6)
    draw.line((245, 720, 232, 748), fill=(4, 15, 23, 255), width=7)
    draw.line((245, 720, 258, 748), fill=(4, 15, 23, 255), width=7)
    image.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def _visual_style_preview_unlocked(style_id: str) -> Path:
    """Muestra PNG generado con los mismos filtros que se aplican a las escenas."""
    if style_id not in options.VISUAL_STYLE_IDS:
        raise ValueError("Estilo visual desconocido")
    preview_dir = db.DATA_DIR / "visual_style_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / f"{style_id}.png"
    if output.exists() and output.stat().st_size > 500:
        return output
    base = _visual_style_sample_base(preview_dir / "paisaje-demo.png")
    filters = _visual_style_filters(style_id)
    filters.append("format=rgb24")
    _ff([
        "-i", str(base), "-vf", ",".join(filters),
        "-frames:v", "1", "-c:v", "png", str(output),
    ], timeout=60)
    if not output.exists() or output.stat().st_size < 500:
        raise RuntimeError("FFmpeg no pudo generar la demostración del estilo")
    return output


def _mix_scene_audio(
    voice_wav: Path,
    effect_path: Path,
    duration: float,
    volume: float,
    start_sec: float,
    output_path: Path,
) -> Path:
    """Mezcla un efecto opcional sin alterar ni reemplazar el audio de voz original."""
    if not effect_path.is_file() or volume <= 0:
        return voice_wav
    if not output_path.exists() or output_path.stat().st_size < 1024:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        delay_ms = int(max(0.0, min(duration, start_sec)) * 1000)
        delay_filter = f"adelay={delay_ms}|{delay_ms}" if delay_ms else "anull"
        _ff([
            "-i", str(voice_wav), "-i", str(effect_path),
            "-filter_complex",
            f"[1:a]volume={max(0.0, min(2.0, volume)):.3f},{delay_filter},atrim=0:{duration:.3f}[effect];"
            "[0:a][effect]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.95[mix]",
            "-map", "[mix]", "-t", f"{duration:.3f}", "-c:a", "pcm_s16le",
            str(output_path),
        ])
    if output_path.is_file() and output_path.stat().st_size > 1024:
        return output_path
    return voice_wav


def _trim_audio_source(
    audio: Path,
    workdir: Path,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    source_duration: float = 0.0,
) -> Path:
    """Materializa un fragmento de audio para poder repetirlo sin salir del rango elegido."""
    start = max(0.0, float(trim_start or 0))
    end = max(0.0, float(trim_end or 0))
    source = max(0.0, float(source_duration or 0))
    if start <= 0 and end <= 0:
        return audio
    window_end = end if end > start else source if source > start else 0
    try:
        stat = audio.stat()
        signature = f"{audio}:{stat.st_size}:{stat.st_mtime_ns}:{start:.3f}:{window_end:.3f}"
    except OSError:
        signature = f"{audio}:{start:.3f}:{window_end:.3f}"
    workdir.mkdir(parents=True, exist_ok=True)
    trimmed = workdir / f"audio-trim-{_h(signature)[:16]}.wav"
    if trimmed.is_file() and trimmed.stat().st_size > 1000:
        return trimmed
    args = []
    if start > 0:
        args.extend(["-ss", f"{start:.3f}"])
    args.extend(["-i", str(audio)])
    if window_end > start:
        args.extend(["-t", f"{window_end - start:.3f}"])
    args.extend(["-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(trimmed)])
    _ff(args)
    if not trimmed.is_file() or trimmed.stat().st_size <= 1000:
        trimmed.unlink(missing_ok=True)
        raise RuntimeError("No se pudo preparar el fragmento recortado del audio.")
    return trimmed


def _visual_input_args(visual: Path, fps: int) -> list[str]:
    """Prepara imágenes estáticas o clips ya recortados y listos para repetirse."""
    is_video = visual.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
    if not is_video:
        return ["-loop", "1", "-framerate", str(fps), "-i", str(visual)]
    return ["-stream_loop", "-1", "-i", str(visual)]


def _trim_visual_source(
    visual: Path,
    scene_dir: Path,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    source_duration: float = 0.0,
) -> Path:
    """Materializa el fragmento de video una vez para poder repetirlo durante toda la escena."""
    if visual.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        return visual
    start = max(0.0, float(trim_start or 0))
    end = max(0.0, float(trim_end or 0))
    source = max(0.0, float(source_duration or 0))
    if start <= 0 and end <= 0:
        return visual
    window_end = end if end > start else source if source > start else 0
    try:
        stat = visual.stat()
        signature = f"{visual}:{stat.st_size}:{stat.st_mtime_ns}:{start:.3f}:{window_end:.3f}"
    except OSError:
        signature = f"{visual}:{start:.3f}:{window_end:.3f}"
    trimmed = scene_dir / f"visual-trim-{_h(signature)[:16]}.mp4"
    if trimmed.is_file() and trimmed.stat().st_size > 1000:
        return trimmed
    args = []
    if start > 0:
        args.extend(["-ss", f"{start:.3f}"])
    args.extend(["-i", str(visual)])
    if window_end > start:
        args.extend(["-t", f"{window_end - start:.3f}"])
    args.extend([
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(trimmed),
    ])
    _ff(args)
    if not trimmed.is_file() or trimmed.stat().st_size <= 1000:
        trimmed.unlink(missing_ok=True)
        raise RuntimeError("No se pudo preparar el fragmento recortado del video.")
    return trimmed


def render_scene(
    project: dict,
    scene: dict,
    scene_dir: Path,
    should_cancel=None,
) -> dict:
    """Renderiza una escena o reutiliza su MP4 cacheado por contenido efectivo."""
    _check_cancel(should_cancel)
    width, height = _size(project)
    style = _style(project)
    fps = int(project.get("fps") or 25)
    transition = scene.get("transition") or project.get("transition_default") or "corte"
    narration = (scene.get("narration") or "").strip()

    # Resolver primero audio y visual: el primer render puede crear/asignar una
    # imagen y cambiar scene.visual_path. El hash debe usar el recurso efectivo
    # para que la segunda ejecución encuentre exactamente la misma caché.
    wav, duration, audio_info = ensure_audio(project, scene)
    sfx_path = Path(scene.get("sfx_path") or "")
    sfx_signature = ""
    if scene.get("sfx_path") and sfx_path.is_file():
        try:
            sfx_stat = sfx_path.stat()
            sfx_signature = f"{sfx_path}:{sfx_stat.st_size}:{sfx_stat.st_mtime_ns}"
        except OSError:
            sfx_signature = str(sfx_path)
    sfx_volume = max(0.0, min(2.0, float(scene.get("sfx_volume") or 0.0)))
    sfx_start = max(0.0, min(duration, float(scene.get("sfx_start_sec") or 0.0)))
    visual, visual_kind, visual_info = ensure_visual(project, scene)
    scene["visual_path"] = str(visual)
    visual_path = Path(visual)
    try:
        visual_stat = visual_path.stat()
        visual_signature = f"{visual_path}:{visual_stat.st_size}:{visual_stat.st_mtime_ns}"
    except OSError:
        visual_signature = str(visual_path)

    captions_enabled = _captions_enabled(project)
    font = media.font_path() if captions_enabled else ""
    if captions_enabled and not font:
        raise RuntimeError(
            "No hay ninguna fuente TTF instalada (instalá font-dejavu / fonts-dejavu). "
            "Los subtítulos necesitan una fuente del sistema."
        )

    style_signature = json.dumps(style, ensure_ascii=False, sort_keys=True, default=str)
    key = _h(
        f"{narration}|{visual_signature}|{duration:.3f}|{width}x{height}"
        f"|{project.get('kind')}|{style_signature}|{transition}|{fps}|{font}"
        f"|{project.get('visual_style') or 'automatico'}|{_project_metadata(project).get('visual_style_prompt', '')}|{project.get('video_type') or 'moving_images'}"
        f"|{scene.get('visual_query') or ''}|{sfx_signature}|{sfx_volume:.3f}|{sfx_start:.3f}"
        f"|trim:{float(scene.get('visual_trim_start_sec') or 0):.3f}:{float(scene.get('visual_trim_end_sec') or 0):.3f}"
    )
    seg_dir = scene_dir / key
    seg_dir.mkdir(parents=True, exist_ok=True)
    scene_mp4 = seg_dir / "scene.mp4"
    manifest = seg_dir / "manifest.json"

    # Los efectos de sonido se mezclan sobre la voz a nivel de escena y quedan cacheados.
    scene_wav = (
        _mix_scene_audio(wav, sfx_path, duration, sfx_volume, sfx_start, seg_dir / "scene-audio.wav")
        if sfx_signature else wav
    )

    cues = media.caption_chunks(
        narration,
        duration,
        style["max_words"],
        style["max_chars"],
        style["max_lines"],
    ) if captions_enabled else []
    caption_dir = seg_dir / "captions"
    caption_dir.mkdir(parents=True, exist_ok=True)
    for i, cue in enumerate(cues):
        text_file = caption_dir / f"{i}.txt"
        lines = cue["lines"]
        if style.get("uppercase"):
            lines = [line.upper() for line in lines]
        text_file.write_text("\n".join(lines), encoding="utf-8")
        cue["file"] = str(text_file)

    reused = scene_mp4.exists() and scene_mp4.stat().st_size > 1000
    if not reused:
        filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            "format=yuv420p",
        ]
        filters.extend(_visual_style_filters(_custom_visual_style_id(project)))
        filters.extend(_motion_filters(transition, width, height, duration, fps))
        if cues:
            filters.append(_drawtext_chain(cues, font, width, height, style))
        render_visual = _trim_visual_source(
            visual_path,
            seg_dir,
            scene.get("visual_trim_start_sec") or 0,
            scene.get("visual_trim_end_sec") or 0,
            scene.get("visual_source_duration_sec") or 0,
        )
        input_args = _visual_input_args(render_visual, fps)
        _ff(
            [
                *input_args,
                "-t", f"{duration:.2f}",
                "-vf", ",".join(filters),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-an",
                str(scene_mp4),
            ]
        )
        manifest.write_text(
            json.dumps(
                {
                    "scene": scene.get("title"),
                    "duration": duration,
                    "audio": audio_info,
                    "visual": visual_info,
                    "rendered_at": db.now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    return {
        "scene_mp4": scene_mp4,
        "wav": wav,
        "duration": media.probe_duration(scene_mp4) or duration,
        "cues": cues,
        "audio_info": audio_info,
        "visual_kind": visual_kind,
        "visual_info": visual_info,
        "visual_path": str(visual),
        "reused": reused,
    }


def _concat(list_file: Path, out_path: Path, extra: list[str] | None = None) -> None:
    _ff(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", *(extra or []), str(out_path)])


def _apply_timeline_overlays(
    base_video: Path,
    overlays: list[dict],
    output_path: Path,
    canvas_width: int,
    canvas_height: int,
    total_duration: float,
) -> Path:
    """Compone capas visuales y de audio independientes sobre el montaje principal."""
    usable = []
    for clip in overlays:
        path = Path(clip.get("path") or "")
        start = max(0.0, float(clip.get("start_sec") or 0))
        duration = max(0.0, float(clip.get("duration_sec") or 0))
        kind = str(clip.get("kind") or "").lower()
        if path.is_file() and duration > 0 and start < total_duration and kind in {"image", "video", "audio", "text"}:
            usable.append((clip, path, start, min(duration, total_duration - start), kind))
    if not usable:
        return base_video

    visual_clips = [item for item in usable if item[4] in {"image", "video", "text"}]
    audio_clips = [item for item in usable if item[4] == "audio"]
    args = ["-i", str(base_video)]
    filters = []
    current = "[0:v]"

    trim_dir = output_path.parent / "overlay-trims"
    for input_index, (clip, path, start, duration, kind) in enumerate(visual_clips, start=1):
        visual_source = _trim_visual_source(
            path, trim_dir,
            clip.get("source_start_sec") or 0,
            clip.get("source_end_sec") or 0,
            clip.get("source_duration_sec") or 0,
        ) if kind == "video" else path
        args.extend(
            ["-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(visual_source)]
            if kind == "video" else ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(path)]
        )
        layer_width = max(2, int(canvas_width * max(0.05, min(1.0, float(clip.get("width") or 0.32)))))
        layer_width -= layer_width % 2
        x = max(0.0, min(1.0, float(clip.get("x") or 0)))
        y = max(0.0, min(1.0, float(clip.get("y") or 0)))
        opacity = max(0.0, min(1.0, float(clip.get("opacity") if clip.get("opacity") is not None else 1)))
        end = start + duration
        filters.append(
            f"[{input_index}:v]scale={layer_width}:-2,format=rgba,"
            f"colorchannelmixer=aa={opacity:.3f},setpts=PTS-STARTPTS+{start:.3f}/TB[ov{input_index}]"
        )
        next_label = f"[v{input_index}]"
        filters.append(
            f"{current}[ov{input_index}]overlay="
            f"x='(main_w-overlay_w)*{x:.4f}':y='(main_h-overlay_h)*{y:.4f}':"
            f"enable='between(t,{start:.3f},{end:.3f})':eof_action=pass{next_label}"
        )
        current = next_label

    audio_labels = ["[0:a]"]
    for audio_index, (clip, path, start, duration, _kind) in enumerate(audio_clips):
        input_index = 1 + len(visual_clips) + audio_index
        audio_source = _trim_audio_source(
            path, trim_dir,
            clip.get("source_start_sec") or 0,
            clip.get("source_end_sec") or 0,
            clip.get("source_duration_sec") or 0,
        )
        args.extend(["-stream_loop", "-1", "-t", f"{duration:.3f}", "-i", str(audio_source)])
        volume = max(0.0, min(2.0, float(clip.get("volume") if clip.get("volume") is not None else 1)))
        delay_ms = max(0, int(start * 1000))
        label = f"[a{input_index}]"
        filters.append(
            f"[{input_index}:a]volume={volume:.3f},adelay={delay_ms}|{delay_ms}{label}"
        )
        audio_labels.append(label)

    if audio_clips:
        filters.append(
            "".join(audio_labels)
            + f"amix=inputs={len(audio_labels)}:duration=first:dropout_transition=0[aout]"
        )

    args.extend(["-filter_complex", ";".join(filters)])
    args.extend(["-map", current if visual_clips else "0:v"])
    args.extend(["-map", "[aout]" if audio_clips else "0:a?"])
    args.extend(["-t", f"{total_duration:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-pix_fmt", "yuv420p"])
    args.extend(["-c:a", "aac", "-b:a", "192k"] if audio_clips else ["-c:a", "copy"])
    args.extend(["-movflags", "+faststart", str(output_path)])
    _ff(args)
    if not output_path.is_file() or output_path.stat().st_size < 1024:
        raise RuntimeError("No se pudieron componer las capas de la línea de tiempo.")
    return output_path


def _music_track(project: dict | None = None) -> Path | None:
    """Música de fondo elegida en el proyecto (biblioteca, cama generada o ninguna)."""
    choice = ((project or {}).get("music") or "auto").strip()
    if choice in ("ninguna", "none", "sin_musica"):
        return None
    if choice in options.MUSIC_IDS:
        choice = "bed:" + choice
    if choice.startswith("bed:"):
        try:
            return media.ensure_music_bed(choice.split(":", 1)[1])
        except Exception:
            return None
    if choice not in ("", "auto"):
        candidate = db.MUSIC_DIR / Path(choice).name
        if candidate.exists():
            return candidate
    if choice in ("", "auto"):
        uploaded = []
        if db.MUSIC_DIR.exists():
            for ext in ("*.mp3", "*.wav", "*.ogg", "*.m4a", "*.flac"):
                uploaded.extend(sorted(db.MUSIC_DIR.glob(ext)))
        if uploaded:
            project_index = int((project or {}).get("id") or 0)
            return uploaded[project_index % len(uploaded)]
        beds = [item["id"] for item in options.MUSIC_BEDS]
        project_index = int((project or {}).get("id") or 0)
        try:
            return media.ensure_music_bed(beds[project_index % len(beds)])
        except Exception:
            return None
    return None


def _validate_vertical_short_render(project: dict, info: dict, results: list[dict]) -> None:
    """No marca como terminado un Short de fábrica horizontal, largo o sin narración."""
    if project.get("kind") != "short" or (project.get("template") or "") not in options.VERTICAL_SHORT_TEMPLATES:
        return
    width, height = int(info.get("width") or 0), int(info.get("height") or 0)
    duration = float(info.get("duration") or 0)
    if not width or not height or width >= height or abs((width / height) - (9 / 16)) > 0.025:
        raise RuntimeError("El render de esta fábrica debe ser vertical 9:16; no se guardó como terminado.")
    if duration <= 0 or duration > 180:
        raise RuntimeError(f"El Short quedó en {duration:.1f} segundos; el máximo permitido es 180. Acortá el guion y volvé a renderizar.")
    if any(result.get("audio_info", {}).get("engine") == "silencio" for result in results):
        raise RuntimeError("No se pudo generar la voz en una o más escenas. Instalá o recuperá el motor TTS antes de publicar.")

def _duration_target_warning(target_seconds: int | float, actual_seconds: int | float) -> str:
    """Explica cuando el audio real queda muy lejos de la duración solicitada."""
    target = max(0.0, float(target_seconds or 0))
    actual = max(0.0, float(actual_seconds or 0))
    if target <= 0 or actual >= target * 0.8:
        return ""
    return (
        f"La narración quedó en {actual / 60:.1f} min frente al objetivo de {target / 60:.1f} min. "
        "El video se renderizó con la duración real del guion; ampliá las escenas antes de publicar."
    )


def render_project(project_id: int, should_cancel=None, on_progress=None) -> dict:
    """Render completo. Devuelve artefactos, advertencias e informe de calidad."""
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise ValueError("Proyecto inexistente")
    scenes = db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx, id", (project_id,))
    if not scenes:
        raise ValueError("El proyecto no tiene escenas. Generá el guion primero.")

    def progress(pct: int, message: str) -> None:
        if on_progress:
            on_progress(max(0, min(100, int(pct))), message)

    width, height = _size(project)
    workdir = _workdir(project_id)
    scene_dir = workdir / "scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)

    progress(3, f"Preparando {len(scenes)} escenas ({width}x{height})")
    results: list[dict] = []
    warnings: list[str] = []
    total = len(scenes)

    for i, scene in enumerate(scenes):
        _check_cancel(should_cancel)
        progress(5 + int(70 * i / max(1, total)), f"Escena {i + 1}/{total}: {scene.get('title')}")
        try:
            result = render_scene(project, scene, scene_dir, should_cancel)
        except Cancelled:
            raise
        except Exception as exc:
            raise RuntimeError(f"Escena «{scene.get('title')}»: {exc}") from exc
        results.append(result)
        if result["audio_info"].get("warning"):
            warnings.append(f"Escena «{scene.get('title')}» sin voz: {result['audio_info']['warning']}")
        db.execute(
            "UPDATE scenes SET audio_path=?, audio_sec=?, visual_path=?, visual_kind=?, visual_license=?, visual_author=?, visual_url=?, status=?, updated_at=? WHERE id=?",
            (
                str(result["wav"]), round(result["duration"], 2), result["visual_path"],
                result["visual_kind"], result["visual_info"].get("license", ""),
                result["visual_info"].get("author", ""), result["visual_info"].get("url", ""),
                "renderizada", db.now(), scene["id"],
            ),
        )
        db.execute(
            "INSERT INTO assets(project_id, scene_id, kind, path, label, license, author, url, bytes, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                scene["id"],
                "video_escena",
                str(result["scene_mp4"]),
                scene.get("title") or "",
                result["visual_info"].get("license", ""),
                result["visual_info"].get("author", ""),
                result["visual_info"].get("url", ""),
                result["scene_mp4"].stat().st_size,
                db.now(),
            ),
        )

    actual_duration = sum(float(result.get("duration") or 0) for result in results)
    duration_warning = _duration_target_warning(project.get("duration_target_sec") or 0, actual_duration)
    if duration_warning:
        warnings.append(duration_warning)

    _check_cancel(should_cancel)
    progress(78, "Uniendo escenas")
    video_list = workdir / "video_concat.txt"
    video_list.write_text(
        "\n".join(f"file '{r['scene_mp4'].as_posix()}'" for r in results), encoding="utf-8"
    )
    silent = workdir / "video_silencioso.mp4"
    _concat(video_list, silent)

    progress(84, "Uniendo narración")
    audio_list = workdir / "audio_concat.txt"
    audio_list.write_text("\n".join(f"file '{r['wav'].as_posix()}'" for r in results), encoding="utf-8")
    voice = workdir / "narracion.wav"
    _concat(audio_list, voice)

    progress(88, "Mezclando audio")
    mixed = workdir / "audio_mezcla.m4a"
    music = _music_track(project)
    volume = project.get("music_volume")
    if volume is None:
        volume = db.get_setting("music_volume", "0.12")
    volume = float(volume or 0.12)
    if music:
        _ff(
            [
                "-i", str(voice), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                f"[1:a]volume={volume}[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(mixed),
            ]
        )
    else:
        _ff(
            [
                "-i", str(voice), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a", "aac", "-b:a", "192k", str(mixed),
            ]
        )

    progress(93, "Montando vídeo final")
    suffix = "short" if project.get("kind") == "short" else "documental"
    final = workdir / f"final_{suffix}.mp4"
    _ff(
        [
            "-i", str(silent), "-i", str(mixed),
            "-c:v", "copy", "-c:a", "copy", "-shortest",
            "-movflags", "+faststart", str(final),
        ]
    )

    overlay_clips = db.query("SELECT * FROM timeline_overlays WHERE project_id=? ORDER BY start_sec,id", (project_id,))
    if overlay_clips:
        overlaid = workdir / f"final_{suffix}_overlays.mp4"
        _apply_timeline_overlays(final, overlay_clips, overlaid, width, height, float(actual_duration))
        final = overlaid

    progress(96, "Subtítulos y miniatura")
    cues_global: list[dict] = []
    offset = 0.0
    for result in results:
        for cue in result["cues"]:
            cues_global.append(
                {
                    "start": offset + cue["start"],
                    "end": offset + cue["end"],
                    "text": cue["text"],
                }
            )
        offset += result["duration"]

    srt = workdir / f"{suffix}.srt"
    vtt = workdir / f"{suffix}.vtt"
    srt.write_text(media.build_srt(cues_global), encoding="utf-8")
    vtt.write_text(media.build_vtt(cues_global), encoding="utf-8")

    thumb_w, thumb_h = options.dimensions(project.get("aspect") or "16:9", project.get("resolution") or "720p")
    thumb = workdir / f"miniatura_{suffix}.jpg"
    if _thumbnail_enabled(project):
        try:
            custom = db.query_one(
                "SELECT path FROM assets WHERE project_id=? AND kind='thumbnail' ORDER BY id DESC LIMIT 1",
                (project_id,),
            )
            custom_path = Path(custom["path"]) if custom and custom.get("path") else None
            if custom_path and custom_path.is_file():
                with Image.open(custom_path) as source:
                    ImageOps.fit(source.convert("RGB"), (thumb_w, thumb_h), method=Image.Resampling.LANCZOS).save(
                        thumb, format="JPEG", quality=94, optimize=True
                    )
            else:
                media.make_thumbnail(final, thumb, project.get("title") or "AITuber Libre", thumb_w, thumb_h)
        except Exception as exc:
            warnings.append(f"No se pudo preparar la miniatura: {exc}")
    else:
        if thumb.exists():
            thumb.unlink()
        db.execute("DELETE FROM assets WHERE project_id=? AND kind='miniatura'", (project_id,))

    info = media.probe_video(final)
    if not info.get("width"):
        raise RuntimeError("El MP4 final no se pudo validar con ffprobe")
    _validate_vertical_short_render(project, info, results)
    if not music and ((project.get("music") or "auto") not in ("ninguna", "none", "sin_musica")):
        warnings.append(
            "Sin música de fondo: elegí una cama en el proyecto o agregá archivos libres en data/music/."
        )
    if any(r["audio_info"].get("engine") == "silencio" for r in results):
        warnings.append("Al menos una escena se renderizó sin voz (motor TTS no disponible).")
    if any(r["visual_kind"] == "tarjeta_generada" for r in results):
        warnings.append(
            "Hay escenas con tarjetas visuales generadas localmente (no son fotografías históricas). "
            "Reemplazalas por material con licencia desde la Biblioteca para un documental final."
        )

    quality = {
        "generated_at": db.now(),
        "resolution": f"{info.get('width')}x{info.get('height')}",
        "duration_sec": round(info.get("duration", 0), 2),
        "bytes": info.get("bytes", 0),
        "scenes": len(results),
        "scenes_reused": sum(1 for r in results if r["reused"]),
        "subtitles": len(cues_global),
        "thumbnail_generated": bool(Path(thumb).exists()),
        "music": bool(music),
        "timeline_layers": {
            "visual": sum(1 for clip in overlay_clips if clip.get("kind") in {"image", "video", "text"}),
            "audio": sum(1 for clip in overlay_clips if clip.get("kind") == "audio"),
        },
        "warnings": warnings,
        "tts_engines": sorted({r["audio_info"].get("engine", "?") for r in results}),
        "visuals": {
            "generadas": sum(1 for r in results if r["visual_kind"] == "tarjeta_generada"),
            "recurso_externo": sum(1 for r in results if r["visual_kind"] == "recurso"),
        },
    }
    db.execute(
        "UPDATE projects SET status=?, quality_json=?, updated_at=? WHERE id=?",
        ("renderizado", json.dumps(quality, ensure_ascii=False), db.now(), project_id),
    )
    for kind, path, label in (
        ("video_final", final, "Vídeo final"),
        ("subtitulos_srt", srt, "Subtítulos SRT"),
        ("subtitulos_vtt", vtt, "Subtítulos VTT"),
        ("miniatura", thumb, "Miniatura"),
    ):
        if Path(path).exists():
            db.execute(
                "INSERT INTO assets(project_id, kind, path, label, bytes, created_at) VALUES(?,?,?,?,?,?)",
                (project_id, kind, str(path), label, Path(path).stat().st_size, db.now()),
            )
    progress(100, "Render terminado")
    db.log("info", "render", f"Proyecto {project_id} renderizado", {"quality": quality})
    return {
        "video": str(final),
        "srt": str(srt),
        "vtt": str(vtt),
        "thumbnail": str(thumb) if Path(thumb).exists() else "",
        "quality": quality,
    }


# --------------------------------------------------------------------------- #
# Exportación
# --------------------------------------------------------------------------- #

def project_script_md(project: dict, scenes: list[dict], sources: list[dict]) -> str:
    lines = [f"# {project.get('title')}", "", f"- Tipo: {project.get('kind')}",
             f"- Formato: {project.get('aspect')}",
             f"- Duración objetivo: {project.get('duration_target_sec')} s",
             f"- Voz: {project.get('voice')} · velocidad {project.get('speed')} · tono {project.get('pitch')}", ""]
    for i, scene in enumerate(scenes, start=1):
        lines.append(f"## {i}. {scene.get('title')}")
        lines.append("")
        lines.append(scene.get("narration") or "_(sin narración)_")
        lines.append("")
        if scene.get("visual_query"):
            lines.append(f"**Búsqueda visual:** {scene.get('visual_query')}")
            lines.append("")
    if sources:
        lines.append("## Fuentes y atribuciones")
        lines.append("")
        for src in sources:
            lines.append(
                f"- {src.get('title')} — {src.get('author')} — {src.get('license')} — {src.get('url')} "
                f"(consultado {src.get('accessed_at')})"
            )
    return "\n".join(lines)


def quality_md(project: dict, quality: dict, scenes: list[dict], sources: list[dict]) -> str:
    lines = [
        f"# Informe de calidad — {project.get('title')}",
        "",
        f"- Generado: {quality.get('generated_at')}",
        f"- Resolución: {quality.get('resolution')}",
        f"- Duración: {quality.get('duration_sec')} s",
        f"- Escenas: {quality.get('scenes')} (reutilizadas de caché: {quality.get('scenes_reused')})",
        f"- Subtítulos: {quality.get('subtitles')} bloques",
        f"- Música de fondo: {'sí' if quality.get('music') else 'no'}",
        f"- Motores TTS: {', '.join(quality.get('tts_engines') or [])}",
        f"- Visuales: {quality.get('visuals')}",
        "",
        "## Advertencias",
        "",
    ]
    warnings = quality.get("warnings") or []
    lines += [f"- {w}" for w in warnings] if warnings else ["- Sin advertencias registradas."]
    lines += ["", "## Escenas", "", "| # | Título | Duración (s) | Visual |", "|---|---|---|---|"]
    for i, scene in enumerate(scenes, start=1):
        lines.append(
            f"| {i} | {scene.get('title')} | {scene.get('audio_sec') or 0} | {scene.get('visual_kind') or 'generada'} |"
        )
    lines += [
        "",
        "## Licencias",
        "",
        "Este ZIP solo redistribuye material generado localmente (tarjetas, voz sintética, subtítulos). "
        "Los recursos de terceros se listan con su licencia y enlace; verificá cada licencia antes de publicar.",
        "",
        f"Fuentes registradas: {len(sources)}",
    ]
    return "\n".join(lines)


def export_project(project_id: int) -> Path:
    project = db.query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not project:
        raise ValueError("Proyecto inexistente")
    scenes = db.query("SELECT * FROM scenes WHERE project_id=? ORDER BY idx, id", (project_id,))
    sources = db.query("SELECT * FROM sources WHERE project_id=? ORDER BY id", (project_id,))
    quality = {}
    try:
        quality = json.loads(project.get("quality_json") or "{}")
    except json.JSONDecodeError:
        quality = {}
    assets = db.query("SELECT * FROM assets WHERE project_id=? ORDER BY id", (project_id,))

    workdir = _workdir(project_id)
    suffix = "short" if project.get("kind") == "short" else "documental"
    final = workdir / f"final_{suffix}.mp4"
    if not final.exists():
        raise RuntimeError("Todavía no hay vídeo renderizado para exportar. Ejecutá el render primero.")

    db.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (project.get("title") or "proyecto"))
    zip_path = db.EXPORT_DIR / f"{safe_title.strip().replace(' ', '_')[:60]}-{time.strftime('%Y%m%d-%H%M')}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        written: set[str] = set()
        zf.write(final, f"{suffix}/video_final.mp4")
        written.add(f"{suffix}/video_final.mp4")
        for name, arc in ((f"{suffix}.srt", "subtitulos/subtitulos.srt"), (f"{suffix}.vtt", "subtitulos/subtitulos.vtt")):
            path = workdir / name
            if path.exists():
                zf.write(path, arc)
        thumb = workdir / f"miniatura_{suffix}.jpg"
        if thumb.exists():
            zf.write(thumb, "miniaturas/miniatura.jpg")
        zf.writestr("guion/guion.md", project_script_md(project, scenes, sources))

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["titulo", "url", "autor", "licencia", "consultado", "atribucion", "tipo"])
        for src in sources:
            writer.writerow(
                [src.get("title"), src.get("url"), src.get("author"), src.get("license"),
                 src.get("accessed_at"), src.get("attribution"), src.get("kind")]
            )
        zf.writestr("fuentes/fuentes.csv", buffer.getvalue())
        zf.writestr(
            "metadatos/metadatos.json",
            json.dumps(
                {
                    "proyecto": project,
                    "escenas": scenes,
                    "fuentes": sources,
                    "calidad": quality,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
        zf.writestr("informe_calidad.md", quality_md(project, quality, scenes, sources))
        zf.writestr(
            "README.md",
            "# Exportación de AITuber Libre\n\n"
            f"Contenido: vídeo final, subtítulos, guion, fuentes con licencia, {'miniatura' if thumb.exists() else 'sin miniatura'}, metadatos e informe de calidad.\\n\\n"
            "Antes de publicar: verificá cada licencia en `fuentes/fuentes.csv`, revisá el guion y confirmá que las "
            "imágenes no se presenten como fotografías históricas si fueron generadas localmente.\n",
        )
        # Recursos propios (tarjetas generadas) redistribuibles sin restricción.
        for asset in assets:
            path = Path(asset.get("path") or "")
            if asset.get("kind") not in ("video_escena",):
                continue
            if not path.exists() or path.stat().st_size >= 40 * 1024 * 1024:
                continue
            arc = f"escenas/{path.parent.name}.mp4"
            if arc in written:
                continue
            written.add(arc)
            zf.write(path, arc)

    db.execute(
        "INSERT INTO assets(project_id, kind, path, label, bytes, created_at) VALUES(?,?,?,?,?,?)",
        (project_id, "export_zip", str(zip_path), "Paquete exportado", zip_path.stat().st_size, db.now()),
    )
    db.log("info", "export", f"Proyecto {project_id} exportado", {"zip": str(zip_path)})
    return zip_path


def cleanup_temporaries(project_id: int) -> int:
    """Elimina temporales de render no esenciales (conserva vídeo y subtítulos)."""
    workdir = _workdir(project_id)
    removed = 0
    for name in ("video_concat.txt", "audio_concat.txt", "video_silencioso.mp4", "narracion.wav", "audio_mezcla.m4a"):
        path = workdir / name
        if path.exists():
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed
