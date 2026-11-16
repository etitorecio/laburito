"""Interpretación determinista de órdenes breves para crear videos sin pasar por el asistente de configuración.

No llama a servicios externos ni usa IA paga. La generación de guion/investigación sigue
delegada al pipeline existente de Laburito.
"""
from __future__ import annotations

import re


def interpret_prompt(prompt: str) -> dict:
    raw = re.sub(r"\s+", " ", str(prompt or "")).strip()
    if not raw:
        raise ValueError("Escribí qué video querés crear.")
    lowered = raw.casefold()

    if re.search(r"frutinovela|novela\s+de\s+frutas|telenovela\s+de\s+frutas", lowered):
        template = "frutinovela"
        channel_name = "Frutinovelas"
        default_topic = "Frutinovela original"
        title_prefix = "Frutinovela"
    elif re.search(r"\b(?:short|shorts|video\s+corto|vídeo\s+corto)\b", lowered):
        template = "shorts"
        channel_name = None
        default_topic = "Short original"
        title_prefix = "Short"
    elif re.search(r"documental|video\s+largo|vídeo\s+largo|long.?form", lowered):
        template = "longform"
        channel_name = None
        default_topic = "Documental original"
        title_prefix = "Documental"
    elif re.search(r"historia|relato|terror|miedo|reddit|confesión|confesion", lowered):
        template = "reddit_story"
        channel_name = "Historias"
        default_topic = "Historia original"
        title_prefix = "Historia"
    else:
        template = "shorts"
        channel_name = None
        default_topic = "Short original"
        title_prefix = "Short"

    subject = raw
    subject = re.sub(
        r"^(?:che[, ]*)?(?:haceme|hazme|armame|creame|créame|generame|genérame|crea|crear|generar|produce|producime|quiero|necesito)\s+",
        "",
        subject,
        flags=re.IGNORECASE,
    )
    subject = re.sub(
        r"^(?:(?:un|una|el|la)\s+)?(?:short|video|vídeo|documental|historia|relato|frutinovela)(?:\s+de\s+terror)?\s*",
        "",
        subject,
        flags=re.IGNORECASE,
    )
    subject = re.sub(r"^(?:sobre|acerca\s+de|de)\s+", "", subject, flags=re.IGNORECASE)
    subject = re.sub(r"\s+", " ", subject).strip(" .,:;!?")
    if subject.casefold() in {"terror", "miedo", "original", "frutas", "frutinovela"}:
        subject = ""

    if template == "frutinovela":
        topic = subject or default_topic
        title = f"{title_prefix} · {topic}" if subject else default_topic
    elif template == "reddit_story":
        topic = subject or default_topic
        title = f"{title_prefix} · {topic}"
    elif template == "longform":
        topic = subject or default_topic
        title = f"{title_prefix} · {topic}"
    else:
        topic = subject or default_topic
        title = f"{title_prefix} · {topic}"

    return {
        "prompt": raw,
        "template": template,
        "topic": topic[:300],
        "title": title[:180],
        "channel_name": channel_name,
        "aspect": "16:9" if template == "longform" else "9:16",
    }
