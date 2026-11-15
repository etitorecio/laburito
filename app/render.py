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
import zipfile
from pathlib import Path

from . import db, media, options, tts

ASPECTS = options.ASPECTS


class Cancelled(Exception):
    """El usuario canceló la tarea."""


def _style(project: dict) -> dict:
    """Estilo de subtítulos del proyecto (13 opciones, ver app/options.py)."""
    return options.caption_style(project)


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
    key = _h(f"{narration}|{project.get('voice')}|{project.get('speed')}|{project.get('pitch')}")
    wav = _audio_dir(int(project["id"])) / f"{key}.wav"
    info: dict = {"cached": wav.exists()}
    if not wav.exists():
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
            # Sin motor TTS: el render sigue con silencio y advertencia explícita.
            words = max(1, len(narration.split()))
            tts.silence_wav(wav, seconds=words / 2.6)
            info.update({"engine": "silencio", "warning": str(exc)})
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
    if video_type in {"stock_footage", "minecraft", "subway"}:
        clip_dir = db.DATA_DIR / "background_clips" / video_type
        clips = sorted(clip_dir.glob("*.mp4")) if clip_dir.exists() else []
        required = 5
        if len(clips) < required:
            raise RuntimeError(
                f"El formato {video_type} necesita {required} clip(s) propios o autorizados. "
                f"Hay {len(clips)} cargados."
            )
        scene_index = int(scene.get("idx") or 0)
        project_index = int(project.get("id") or 0)
        chosen = clips[(project_index + scene_index) % len(clips)]
        return chosen, "video_fondo", {
            "license": "Clip propio o autorizado; derechos confirmados al cargar",
            "author": "Biblioteca local del usuario",
            "url": f"local://background-clips/{video_type}/{chosen.name}",
            "title": chosen.name,
            "provider": "biblioteca_local",
        }
    existing = (scene.get("visual_path") or "").strip()
    if existing and Path(existing).exists() and Path(existing).suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv"}:
        return Path(existing), scene.get("visual_kind") or "recurso", {
            "license": scene.get("visual_license") or "sin verificar",
            "author": scene.get("visual_author") or "desconocido",
            "url": scene.get("visual_url") or "",
        }

    key = _h(f"{scene.get('title')}|{scene.get('visual_query')}|{width}x{height}")
    folder = _visual_dir(int(project["id"]))
    query = (scene.get("visual_query") or project.get("topic") or "").strip()
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


def caption_preview(style_id: str) -> Path:
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
    """Genera un clip corto que muestra el efecto real aplicado por FFmpeg."""
    if transition_id not in options.TRANSITION_IDS:
        raise ValueError("Movimiento de escena desconocido")
    preview_dir = db.DATA_DIR / "transition_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / f"{transition_id}.mp4"
    if output.exists() and output.stat().st_size > 1000:
        return output

    width, height, duration, fps = 360, 640, 3.0, 20
    filters = _motion_filters(transition_id, width, height, duration, fps)
    filters.extend(["drawbox=x=iw*0.12:y=ih*0.22:w=iw*0.76:h=ih*0.18:color=0xf59e0b@0.35:t=fill", "format=yuv420p"])
    _ff([
        "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate={fps}:duration={duration}",
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
    """Muestra PNG generado con los mismos filtros que se aplican a las escenas."""
    if style_id not in options.VISUAL_STYLE_IDS:
        raise ValueError("Estilo visual desconocido")
    preview_dir = db.DATA_DIR / "visual_style_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / f"{style_id}.png"
    if output.exists() and output.stat().st_size > 500:
        return output
    filters = _visual_style_filters(style_id)
    filters.extend([
        "drawbox=x=iw*0.12:y=ih*0.20:w=iw*0.76:h=ih*0.22:color=0xf59e0b@0.32:t=fill",
        "format=rgb24",
    ])
    _ff([
        "-f", "lavfi", "-i", "testsrc2=size=480x854:rate=1:duration=1",
        "-vf", ",".join(filters), "-frames:v", "1", "-c:v", "png", str(output),
    ], timeout=60)
    if not output.exists() or output.stat().st_size < 500:
        raise RuntimeError("FFmpeg no pudo generar la demostración del estilo")
    return output


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
    visual, visual_kind, visual_info = ensure_visual(project, scene)
    scene["visual_path"] = str(visual)
    visual_path = Path(visual)
    try:
        visual_stat = visual_path.stat()
        visual_signature = f"{visual_path}:{visual_stat.st_size}:{visual_stat.st_mtime_ns}"
    except OSError:
        visual_signature = str(visual_path)

    font = media.font_path()
    if not font:
        raise RuntimeError(
            "No hay ninguna fuente TTF instalada (instalá font-dejavu / fonts-dejavu). "
            "Los subtítulos necesitan una fuente del sistema."
        )

    style_signature = json.dumps(style, ensure_ascii=False, sort_keys=True, default=str)
    key = _h(
        f"{narration}|{visual_signature}|{duration:.3f}|{width}x{height}"
        f"|{project.get('kind')}|{style_signature}|{transition}|{fps}|{font}"
        f"|{project.get('visual_style') or 'automatico'}|{project.get('video_type') or 'moving_images'}"
        f"|{scene.get('visual_query') or ''}"
    )
    seg_dir = scene_dir / key
    seg_dir.mkdir(parents=True, exist_ok=True)
    scene_mp4 = seg_dir / "scene.mp4"
    manifest = seg_dir / "manifest.json"

    cues = media.caption_chunks(
        narration,
        duration,
        style["max_words"],
        style["max_chars"],
        style["max_lines"],
    )
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
        filters.extend(_visual_style_filters(project.get("visual_style")))
        filters.extend(_motion_filters(transition, width, height, duration, fps))
        if cues:
            filters.append(_drawtext_chain(cues, font, width, height, style))
        is_video_background = visual_path.suffix.lower() in {".mp4", ".mov", ".webm", ".mkv"}
        input_args = (
            ["-stream_loop", "-1", "-i", str(visual)]
            if is_video_background
            else ["-loop", "1", "-framerate", str(fps), "-i", str(visual)]
        )
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


def _music_track(project: dict | None = None) -> Path | None:
    """Música de fondo elegida en el proyecto (biblioteca, cama generada o ninguna)."""
    choice = ((project or {}).get("music") or "auto").strip()
    if choice in ("ninguna", "none", "sin_musica"):
        return None
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

    thumb_w, thumb_h = options.dimensions(project.get("aspect") or "16:9", "1080p")
    thumb = workdir / f"miniatura_{suffix}.jpg"
    try:
        media.make_thumbnail(final, thumb, project.get("title") or "AITuber Libre", thumb_w, thumb_h)
    except Exception as exc:
        warnings.append(f"No se pudo generar la miniatura: {exc}")

    info = media.probe_video(final)
    if not info.get("width"):
        raise RuntimeError("El MP4 final no se pudo validar con ffprobe")
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
        "music": bool(music),
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
            "Contenido: vídeo final, subtítulos, guion, fuentes con licencia, miniaturas, metadatos e informe de calidad.\n\n"
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
