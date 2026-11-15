"""Catálogo único de opciones de creación (equivalente funcional a aituber.app).

Este módulo es intencionalmente puro (sin dependencias de db/media) para que la
API y el render compartan exactamente las mismas definiciones.

No incluye planes, créditos ni pagos: la app es libre y gratuita.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Formatos y resolución
# --------------------------------------------------------------------------- #

ASPECTS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

RESOLUTIONS: dict[str, float] = {"720p": 2 / 3, "1080p": 1.0, "1440p": 4 / 3, "2160p": 2.0}

RESOLUTION_INFO = [
    {"id": "720p", "label": "720p (HD)", "note": "Más rápido para equipos modestos; recomendado para probar."},
    {"id": "1080p", "label": "1080p (Full HD)", "note": "Recomendado para la publicación final."},
    {"id": "1440p", "label": "1440p (2K)", "note": "Intermedio. Más nitidez, ~1.8x tiempo de render."},
    {"id": "2160p", "label": "2160p (4K)", "note": "Máxima calidad. ~4x tiempo de render en 1 vCPU."},
]

FPS_OPTIONS = [25, 30]


def dimensions(aspect: str, resolution: str) -> tuple[int, int]:
    """Devuelve (ancho, alto) pares para el aspecto y la resolución pedidos."""
    base_w, base_h = ASPECTS.get(aspect, ASPECTS["16:9"])
    factor = RESOLUTIONS.get(resolution, 1.0)
    width = int(round(base_w * factor / 2) * 2)
    height = int(round(base_h * factor / 2) * 2)
    return width, height


# --------------------------------------------------------------------------- #
# Estilos de subtítulos (13 estilos, todos implementados con drawtext)
# --------------------------------------------------------------------------- #

_BASE = {
    "max_words": 9,
    "max_chars": 96,
    "max_lines": 3,
    "font_ratio": 0.024,
    "y_from_bottom": 0.13,
    "box": True,
    "box_alpha": "0.55",
    "boxcolor": "black",
    "fontcolor": "white",
    "outline": 0,
    "uppercase": False,
}

CAPTION_STYLES: dict[str, dict] = {
    "documental": {**_BASE},
    "documental_min": {**_BASE, "max_words": 7, "max_chars": 78, "y_from_bottom": 0.09, "box": False, "outline": 5},
    "short_pop": {**_BASE, "max_words": 4, "max_chars": 34, "max_lines": 2, "font_ratio": 0.062,
                  "y_from_bottom": 0.30, "box_alpha": "0.45", "uppercase": True},
    "short_min": {**_BASE, "max_words": 4, "max_chars": 32, "max_lines": 2, "font_ratio": 0.058,
                  "y_from_bottom": 0.22, "box": False, "outline": 7},
    "karaoke": {**_BASE, "max_words": 4, "max_chars": 30, "max_lines": 2, "font_ratio": 0.066,
                "y_from_bottom": 0.34, "box": False, "outline": 6, "fontcolor": "yellow", "uppercase": True},
    "caja_amarilla": {**_BASE, "max_words": 5, "max_chars": 40, "max_lines": 2, "font_ratio": 0.05,
                      "y_from_bottom": 0.26, "boxcolor": "yellow", "fontcolor": "black", "box_alpha": "0.92",
                      "uppercase": True},
    "caja_roja": {**_BASE, "max_words": 5, "max_chars": 40, "max_lines": 2, "font_ratio": 0.05,
                  "y_from_bottom": 0.26, "boxcolor": "red", "fontcolor": "white", "box_alpha": "0.9",
                  "uppercase": True},
    "banner_superior": {**_BASE, "max_words": 8, "max_chars": 60, "max_lines": 2, "font_ratio": 0.038,
                        "y_from_bottom": 0.86, "box_alpha": "0.7"},
    "banner_inferior": {**_BASE, "max_words": 8, "max_chars": 60, "max_lines": 2, "font_ratio": 0.038,
                        "y_from_bottom": 0.06, "box_alpha": "0.75"},
    "contorno": {**_BASE, "max_words": 6, "max_chars": 46, "max_lines": 2, "font_ratio": 0.05,
                 "y_from_bottom": 0.20, "box": False, "outline": 9, "uppercase": True},
    "grande_centrado": {**_BASE, "max_words": 3, "max_chars": 24, "max_lines": 2, "font_ratio": 0.085,
                        "y_from_bottom": 0.5, "box": False, "outline": 10, "uppercase": True},
    "serif_cine": {**_BASE, "max_words": 10, "max_chars": 110, "max_lines": 3, "font_ratio": 0.03,
                   "y_from_bottom": 0.10, "box": False, "outline": 4, "fontcolor": "#F2E9DC"},
    "cita": {**_BASE, "max_words": 7, "max_chars": 52, "max_lines": 3, "font_ratio": 0.052,
             "y_from_bottom": 0.5, "box": False, "outline": 8, "fontcolor": "white"},
}

CAPTION_LABELS = {
    "documental": "Documental (bloque con caja)",
    "documental_min": "Documental minimal (contorno)",
    "short_pop": "Short pop (grande, mayúsculas)",
    "short_min": "Short minimal (solo contorno)",
    "karaoke": "Karaoke (palabra por palabra, amarillo)",
    "caja_amarilla": "Caja amarilla (texto negro)",
    "caja_roja": "Caja roja (texto blanco)",
    "banner_superior": "Banner superior",
    "banner_inferior": "Banner inferior",
    "contorno": "Contorno grueso",
    "grande_centrado": "Grande centrado",
    "serif_cine": "Cine (tono cálido, caja suave)",
    "cita": "Cita centrada",
}


# --------------------------------------------------------------------------- #
# Transiciones (todas reales, aplicadas por FFmpeg escena a escena)
# --------------------------------------------------------------------------- #

TRANSITIONS = [
    {"id": "corte", "label": "Corte directo"},
    {"id": "fundido", "label": "Fundido a negro"},
    {"id": "fundido_blanco", "label": "Fundido a blanco (destello)"},
    {"id": "zoom_in", "label": "Zoom de acercamiento"},
    {"id": "zoom_out", "label": "Zoom de alejamiento"},
    {"id": "paneo_izq", "label": "Paneo a la izquierda"},
    {"id": "paneo_der", "label": "Paneo a la derecha"},
    {"id": "kenburns", "label": "Ken Burns (zoom + paneo)"},
]

TRANSITION_IDS = {t["id"] for t in TRANSITIONS}


# --------------------------------------------------------------------------- #
# Música de fondo
# --------------------------------------------------------------------------- #

MUSIC_BEDS = [
    {"id": "padsuave", "label": "Pad suave", "freqs": [196, 294, 392],
     "chain": "lowpass=f=2200,volume='0.35+0.12*sin(2*PI*t/14)':eval=frame,aecho=0.8:0.6:300:0.25"},
    {"id": "ambiente", "label": "Ambiente oscuro", "freqs": [110, 164, 220],
     "chain": "lowpass=f=900,volume='0.4+0.10*sin(2*PI*t/20)':eval=frame,aecho=0.8:0.7:500:0.3"},
    {"id": "epico", "label": "Épico", "freqs": [110, 165, 220, 330],
     "chain": "lowpass=f=3200,volume='0.30+0.15*sin(2*PI*t/8)':eval=frame"},
    {"id": "lofi", "label": "Lo-fi", "freqs": [174, 261, 349],
     "chain": "lowpass=f=1400,volume='0.35+0.08*sin(2*PI*t/10)':eval=frame,aecho=0.8:0.5:250:0.2"},
]

MUSIC_IDS = {m["id"] for m in MUSIC_BEDS}


# --------------------------------------------------------------------------- #
# Plantillas de vídeo
# --------------------------------------------------------------------------- #

TEMPLATES = [
    {
        "id": "shorts",
        "label": "Shorts / Reels verticales",
        "description": "Vídeo vertical corto con subtítulos grandes y ritmo rápido.",
        "kind": "short",
        "aspect": "9:16",
        "script": "short",
        "caption_style": "short_pop",
        "durations": [15, 20, 30, 45, 60, 90, 120, 180],
        "default_duration": 30,
        "available": True,
    },
    {
        "id": "longform",
        "label": "Documental largo (hasta 20 min)",
        "description": "Formato horizontal con capítulos narrativos y subtítulos documentales.",
        "kind": "documentary",
        "aspect": "16:9",
        "script": "documentary",
        "caption_style": "documental",
        "durations": [180, 300, 600, 900, 1200],
        "default_duration": 600,
        "available": True,
    },
    {
        "id": "listicle",
        "label": "Top N / Lista rápida",
        "description": "Cuenta regresiva o lista numerada, un punto por escena.",
        "kind": "short",
        "aspect": "9:16",
        "script": "listicle",
        "caption_style": "caja_amarilla",
        "durations": [30, 45, 60, 90, 120, 180],
        "default_duration": 45,
        "available": True,
    },
    {
        "id": "pov",
        "label": "POV / Historia en primera persona",
        "description": "Relato inmersivo en segunda persona con giro final.",
        "kind": "short",
        "aspect": "9:16",
        "script": "pov",
        "caption_style": "karaoke",
        "durations": [30, 45, 60, 90],
        "default_duration": 45,
        "available": True,
    },
    {
        "id": "explainer",
        "label": "Explicador educativo",
        "description": "Pregunta, respuesta por pasos y resumen final.",
        "kind": "documentary",
        "aspect": "16:9",
        "script": "explainer",
        "caption_style": "banner_inferior",
        "durations": [180, 300, 600, 900],
        "default_duration": 300,
        "available": True,
    },
    {
        "id": "quote",
        "label": "Cita / frase inspiradora",
        "description": "Frase potente con desarrollo breve y cierre reflexivo.",
        "kind": "short",
        "aspect": "9:16",
        "script": "quote",
        "caption_style": "cita",
        "durations": [15, 20, 30, 45],
        "default_duration": 20,
        "available": True,
    },
    {
        "id": "cuadrado",
        "label": "Cuadrado para feed (1:1)",
        "description": "Publicación cuadrada para Facebook, Instagram y LinkedIn.",
        "kind": "short",
        "aspect": "1:1",
        "script": "short",
        "caption_style": "short_min",
        "durations": [15, 30, 45, 60],
        "default_duration": 30,
        "available": True,
    },
    {
        "id": "vertical_45",
        "label": "Vertical 4:5 (feed)",
        "description": "Formato 4:5 que ocupa más pantalla en el feed de Instagram.",
        "kind": "short",
        "aspect": "4:5",
        "script": "short",
        "caption_style": "short_pop",
        "durations": [15, 30, 45, 60],
        "default_duration": 30,
        "available": True,
    },
]

# Plantillas de aituber.app que dependen de un proveedor externo de generación.
# Se listan para dejar el inventario completo y transparente, pero no se pueden
# producir localmente sin claves de terceros.
EXTERNAL_TEMPLATES = [
    {"id": "avatar", "label": "Talking head / UGC con avatar",
     "requires": "Generación de vídeo con avatar (proveedor externo de IA de vídeo)."},
    {"id": "music_video", "label": "Vídeo musical con voz cantada",
     "requires": "Síntesis de voz cantada y música generada (proveedor externo)."},
    {"id": "clips", "label": "AI Video Clips (clips de vídeo reales)",
     "requires": "Generación de clips de vídeo (proveedor externo); localmente se usan imágenes y tarjetas."},
    {"id": "objects", "label": "Talking objects / Skeleton (3D)",
     "requires": "Render 3D con malla y animación (motor 3D externo)."},
]

# --------------------------------------------------------------------------- #
# Tipos de video y estilos visuales locales (sin servicios de generación)
# --------------------------------------------------------------------------- #

VIDEO_TYPES = [
    {"id": "moving_images", "label": "Imágenes con movimiento", "description": "Fotos de archivo con paneo y zoom, procesadas localmente.", "available": True},
    {"id": "full_motion_ai", "label": "Video IA de movimiento completo", "description": "Generación de clips IA; no hay un modelo local viable para este equipo todavía.", "available": False},
    {"id": "skeleton", "label": "Esqueleto animado", "description": "Skeleton Video 2.5D generado localmente; sin IA ni créditos.", "available": True},
    {"id": "stock_footage", "label": "Videos de archivo", "description": "Cinco clips reales de archivo propios o autorizados, alternados automáticamente.", "available": False},
    {"id": "minecraft", "label": "Gameplay de Minecraft", "description": "Biblioteca de clips propios o autorizados; requiere cinco clips para rotación.", "available": False},
    {"id": "subway", "label": "Gameplay de Subway Surfers", "description": "Biblioteca de clips propios o autorizados; requiere cinco clips para rotación.", "available": False},
]
VIDEO_TYPE_IDS = {item["id"] for item in VIDEO_TYPES}

VISUAL_STYLES = [
    {"id": "automatico", "label": "Automático", "description": "Sin tratamiento adicional; conserva los colores de la imagen."},
    {"id": "cinematico", "label": "Cinematográfico", "description": "Contraste suave, color profundo y viñeta."},
    {"id": "realista", "label": "Realista", "description": "Nitidez moderada y color natural."},
    {"id": "anime", "label": "Color anime (filtro)", "description": "Saturación y bordes más intensos; conserva la foto, no la redibuja."},
    {"id": "pixel_art", "label": "Pixel art", "description": "Pixelado visible por reducción y ampliación por bloques."},
    {"id": "noir", "label": "Cine noir", "description": "Blanco y negro de alto contraste."},
    {"id": "vintage", "label": "Vintage", "description": "Tono sepia y viñeta suave."},
    {"id": "cyberpunk", "label": "Cyberpunk", "description": "Saturación alta y dominante fría."},
    {"id": "acuarela", "label": "Suavizado tipo acuarela", "description": "Suavizado leve y color pastel; no convierte la foto en una pintura."},
    {"id": "comic", "label": "Cómic (filtro)", "description": "Contraste y bordes marcados; no reemplaza una ilustración."},
]
VISUAL_STYLE_IDS = {item["id"] for item in VISUAL_STYLES}

TEMPLATE_IDS = {t["id"] for t in TEMPLATES}
SCRIPT_TEMPLATES = ["documentary", "short", "listicle", "pov", "explainer", "quote"]

DEFAULT_TEMPLATE = "shorts"


def template(template_id: str | None) -> dict:
    """Devuelve la plantilla pedida o la de shorts por defecto."""
    for item in TEMPLATES:
        if item["id"] == template_id:
            return item
    return TEMPLATES[0]


def caption_style(project: dict) -> dict:
    """Estilo de subtítulos efectivo del proyecto (con respaldo por plantilla)."""
    chosen = (project.get("caption_style") or "").strip()
    if chosen in CAPTION_STYLES:
        return CAPTION_STYLES[chosen]
    return CAPTION_STYLES.get(template(project.get("template")).get("caption_style"), CAPTION_STYLES["documental"])


def resolve_defaults(payload: dict) -> dict:
    """Completa las opciones de un proyecto a partir de su plantilla."""
    tpl = template(payload.get("template"))
    aspect = payload.get("aspect") or tpl["aspect"]
    if aspect not in ASPECTS:
        aspect = tpl["aspect"]
    resolution = payload.get("resolution") if payload.get("resolution") in RESOLUTIONS else "1080p"
    caption = payload.get("caption_style") if payload.get("caption_style") in CAPTION_STYLES else tpl["caption_style"]
    transition = payload.get("transition_default")
    if transition not in TRANSITION_IDS:
        transition = "fundido"
    fps = payload.get("fps") if payload.get("fps") in FPS_OPTIONS else 25
    music = payload.get("music") or "auto"
    return {
        "template": tpl["id"],
        "kind": tpl["kind"],
        "aspect": aspect,
        "resolution": resolution,
        "caption_style": caption,
        "transition_default": transition,
        "fps": fps,
        "music": music,
    }
