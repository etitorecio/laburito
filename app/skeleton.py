"""Animación procedural local de esqueleto 2.5D, sin modelos ni servicios externos."""
from __future__ import annotations

import math
import subprocess
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

WIDTH, HEIGHT, FPS, LOOP_SECONDS = 480, 854, 15, 4
ACTIONS = {"walk", "run", "dance", "point", "explain"}


def action_for(title: str = "", narration: str = "") -> str:
    text = f"{title} {narration}".lower()
    if any(word in text for word in ("correr", "huir", "perseguir", "escape", "rápido")):
        return "run"
    if any(word in text for word in ("bail", "música", "canción", "fiesta", "ritmo")):
        return "dance"
    if any(word in text for word in ("señal", "apuntar", "indicar", "mirá", "mira")):
        return "point"
    if any(word in text for word in ("caminar", "viaje", "recorrer", "llegó", "llego")):
        return "walk"
    return "explain"


def _background() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = image.load()
    for y in range(HEIGHT):
        t = y / max(1, HEIGHT - 1)
        color = (int(5 + 8 * t), int(13 + 14 * t), int(28 + 22 * t))
        for x in range(WIDTH):
            pixels[x, y] = color
    draw = ImageDraw.Draw(image, "RGBA")
    for x in range(35, WIDTH, 55):
        draw.line((x, 0, x, HEIGHT), fill=(45, 90, 130, 22), width=1)
    for y in range(60, HEIGHT, 55):
        draw.line((0, y, WIDTH, y), fill=(45, 90, 130, 18), width=1)
    draw.ellipse((150, 90, 330, 270), outline=(30, 170, 220, 35), width=2)
    draw.line((0, 750, WIDTH, 750), fill=(60, 180, 220, 90), width=2)
    return image


def _pose(action: str, phase: float) -> dict[str, tuple[float, float]]:
    sway = math.sin(phase) * 11
    bob = abs(math.sin(phase)) * (15 if action == "run" else 8)
    cx = WIDTH / 2 + sway
    head_y = 155 + bob
    shoulder_y = 252 + bob
    pelvis_y = 440 + bob
    swing = math.sin(phase * (2 if action == "run" else 1))
    if action == "dance":
        left_elbow = (cx - 95 + 14 * swing, shoulder_y - 82)
        right_elbow = (cx + 92 - 12 * swing, shoulder_y - 90)
        left_hand = (cx - 120 + 20 * swing, shoulder_y - 142)
        right_hand = (cx + 125 - 18 * swing, shoulder_y - 150)
        left_knee = (cx - 60 + 28 * swing, 585 + bob)
        right_knee = (cx + 58 - 28 * swing, 565 + bob)
    elif action == "point":
        left_elbow = (cx - 75, shoulder_y + 70)
        left_hand = (cx - 98, shoulder_y + 145)
        right_elbow = (cx + 92, shoulder_y - 25)
        right_hand = (cx + 180, shoulder_y - 22)
        left_knee = (cx - 58, 580 + bob)
        right_knee = (cx + 58, 580 + bob)
    elif action == "explain":
        left_elbow = (cx - 100, shoulder_y + 10 + 18 * swing)
        left_hand = (cx - 132, shoulder_y - 5 + 24 * swing)
        right_elbow = (cx + 100, shoulder_y + 12 - 18 * swing)
        right_hand = (cx + 132, shoulder_y - 2 - 24 * swing)
        left_knee = (cx - 58 + 16 * swing, 580 + bob)
        right_knee = (cx + 58 - 16 * swing, 580 + bob)
    else:
        amplitude = 42 if action == "run" else 28
        left_elbow = (cx - 85 + amplitude * swing, shoulder_y + 65)
        right_elbow = (cx + 85 - amplitude * swing, shoulder_y + 65)
        left_hand = (cx - 65 + amplitude * swing, shoulder_y + 135)
        right_hand = (cx + 65 - amplitude * swing, shoulder_y + 135)
        left_knee = (cx - 55 + amplitude * swing, 580 + bob + abs(swing) * 12)
        right_knee = (cx + 55 - amplitude * swing, 580 + bob + abs(swing) * 12)

    leg_swing = math.sin(phase + math.pi / 2)
    if action in {"walk", "run"}:
        left_knee = (cx - 55 + 48 * leg_swing, 575 + bob + abs(leg_swing) * 18)
        right_knee = (cx + 55 - 48 * leg_swing, 575 + bob + abs(leg_swing) * 18)
    left_ankle = (left_knee[0] - 10 + 18 * swing, 735 + bob)
    right_ankle = (right_knee[0] + 10 - 18 * swing, 735 + bob)
    return {
        "head": (cx, head_y),
        "neck": (cx, 220 + bob),
        "shoulder_l": (cx - 48, shoulder_y),
        "shoulder_r": (cx + 48, shoulder_y),
        "elbow_l": left_elbow,
        "elbow_r": right_elbow,
        "hand_l": left_hand,
        "hand_r": right_hand,
        "spine_top": (cx, shoulder_y + 8),
        "spine_mid": (cx + sway * .15, 345 + bob),
        "pelvis": (cx, pelvis_y),
        "hip_l": (cx - 42, pelvis_y + 8),
        "hip_r": (cx + 42, pelvis_y + 8),
        "knee_l": left_knee,
        "knee_r": right_knee,
        "ankle_l": left_ankle,
        "ankle_r": right_ankle,
        "foot_l": (left_ankle[0] - 25, 752 + bob),
        "foot_r": (right_ankle[0] + 25, 752 + bob),
    }


def _draw_bone(draw: ImageDraw.ImageDraw, glow: ImageDraw.ImageDraw,
               a: tuple[float, float], b: tuple[float, float], width: int = 8) -> None:
    p1 = (int(a[0]), int(a[1]))
    p2 = (int(b[0]), int(b[1]))
    glow.line((p1, p2), fill=(25, 190, 235, 105), width=width + 15)
    draw.line(((p1[0] + 3, p1[1] + 3), (p2[0] + 3, p2[1] + 3)),
              fill=(12, 25, 42, 255), width=width + 3)
    draw.line((p1, p2), fill=(218, 238, 246, 255), width=width)
    draw.line((p1, p2), fill=(255, 255, 255, 220), width=max(2, width // 3))


def _frame(background: Image.Image, action: str, frame_index: int, frame_count: int) -> Image.Image:
    phase = 2 * math.pi * frame_index / frame_count
    points = _pose(action, phase)
    image = background.convert("RGBA").copy()
    glow_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    draw = ImageDraw.Draw(image)

    bones = [
        ("neck", "spine_top"), ("spine_top", "spine_mid"), ("spine_mid", "pelvis"),
        ("shoulder_l", "shoulder_r"), ("shoulder_l", "elbow_l"), ("elbow_l", "hand_l"),
        ("shoulder_r", "elbow_r"), ("elbow_r", "hand_r"),
        ("pelvis", "hip_l"), ("pelvis", "hip_r"),
        ("hip_l", "knee_l"), ("knee_l", "ankle_l"), ("ankle_l", "foot_l"),
        ("hip_r", "knee_r"), ("knee_r", "ankle_r"), ("ankle_r", "foot_r"),
    ]
    for first, second in bones:
        _draw_bone(draw, glow_draw, points[first], points[second],
                   10 if first in {"spine_top", "spine_mid"} else 7)

    # Caja torácica, pelvis y cráneo: detalles que dan volumen al esqueleto.
    cx, top = points["spine_top"]
    rib_top = int(top + 10)
    for offset in (0, 20, 40, 60):
        box = (int(cx - 43 + offset * .1), rib_top + offset, int(cx + 43 - offset * .1), rib_top + offset + 26)
        draw.arc(box, 190, 350, fill=(225, 241, 248, 235), width=3)
        glow_draw.arc(box, 190, 350, fill=(25, 190, 235, 90), width=8)
    pelvis_box = (int(cx - 48), int(points["pelvis"][1] - 12),
                  int(cx + 48), int(points["pelvis"][1] + 45))
    draw.arc(pelvis_box, 5, 175, fill=(230, 242, 248, 255), width=6)
    head_x, head_y = points["head"]
    skull = (int(head_x - 33), int(head_y - 42), int(head_x + 33), int(head_y + 43))
    draw.ellipse(skull, outline=(235, 246, 250, 255), width=7)
    glow_draw.ellipse(skull, outline=(25, 190, 235, 100), width=14)
    draw.arc((int(head_x - 26), int(head_y + 5), int(head_x + 26), int(head_y + 45)),
             0, 180, fill=(235, 246, 250, 255), width=5)
    for eye_x in (head_x - 13, head_x + 13):
        draw.ellipse((int(eye_x - 5), int(head_y - 8), int(eye_x + 5), int(head_y + 4)),
                     fill=(15, 35, 55, 255))
        draw.ellipse((int(eye_x - 2), int(head_y - 5), int(eye_x + 2), int(head_y - 1)),
                     fill=(65, 225, 255, 255))

    # Articulaciones.
    joints = [points[key] for key in (
        "neck", "shoulder_l", "shoulder_r", "elbow_l", "elbow_r", "hand_l", "hand_r",
        "pelvis", "hip_l", "hip_r", "knee_l", "knee_r", "ankle_l", "ankle_r",
    )]
    for x, y in joints:
        radius = 8
        draw.ellipse((int(x-radius), int(y-radius), int(x+radius), int(y+radius)),
                     fill=(228, 242, 248, 255), outline=(40, 185, 225, 255), width=3)
        glow_draw.ellipse((int(x-radius-5), int(y-radius-5), int(x+radius+5), int(y+radius+5)),
                          outline=(25, 190, 235, 85), width=6)

    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(7))
    image = Image.alpha_composite(image, glow_layer)
    # Redibujar el esqueleto nítido sobre el resplandor.
    final = Image.alpha_composite(image, Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)))
    return final.convert("RGB")


_SKELETON_LOCK = threading.Lock()


def ensure_clip(action: str, output: Path | None = None) -> Path:
    with _SKELETON_LOCK:
        return _ensure_clip_unlocked(action, output)


def _ensure_clip_unlocked(action: str, output: Path | None = None) -> Path:
    """Genera una animación en bucle reutilizable para escenas de video."""
    from . import db, media

    action = action if action in ACTIONS else "explain"
    target = Path(output) if output else db.DATA_DIR / "skeleton_clips" / f"{action}.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1000:
        return target

    background = _background()
    with tempfile.TemporaryDirectory(prefix="skeleton-", dir=str(db.TMP_DIR)) as temp:
        temp_dir = Path(temp)
        frame_count = FPS * LOOP_SECONDS
        for index in range(frame_count):
            frame = _frame(background, action, index, frame_count)
            frame.save(temp_dir / f"frame-{index:04d}.png", optimize=False)
        proc = media.run([
            media.ffmpeg(), "-y", "-framerate", str(FPS),
            "-i", str(temp_dir / "frame-%04d.png"),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "25",
            "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(target),
        ], timeout=180)
        if proc.returncode != 0 or not target.exists() or target.stat().st_size < 1000:
            message = (proc.stderr or b"").decode("utf-8", "ignore")[-700:]
            raise RuntimeError("No se pudo generar el esqueleto animado: " + message)
    return target
