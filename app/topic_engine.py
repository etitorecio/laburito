"""Descubrimiento temático gratuito basado en Wikipedia.

No inventa tendencias: propone temas documentados dentro del nicho y guarda
la página consultada como fuente de contexto. Si no hay conexión o candidatos
nuevos, falla explícitamente para evitar publicar un tema repetido.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from . import db

API = "https://es.wikipedia.org/w/api.php"
UA = "Laburito/1.0 (automatic topic research; contact: local project)"


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=18) as response:
        return json.loads(response.read().decode("utf-8"))


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def choose_topic(niche: str, previous_topics: list[str]) -> dict:
    niche = (niche or "").strip()
    if not niche:
        raise ValueError("Configurá un nicho antes de iniciar el Autopiloto.")
    data = _get({
        "action": "query", "list": "search", "srsearch": niche,
        "srnamespace": 0, "srlimit": 20, "format": "json",
    })
    used = {_normal(x) for x in previous_topics if x}
    candidates = data.get("query", {}).get("search", [])
    for item in candidates:
        title = item.get("title", "").strip()
        if not title or _normal(title) in used:
            continue
        summary = _get({
            "action": "query", "prop": "extracts|info", "explaintext": 1,
            "exintro": 1, "inprop": "url", "titles": title, "format": "json",
        })
        pages = summary.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
        if len(extract) < 180:
            continue
        return {
            "title": title,
            "topic": title,
            "summary": extract[:3500],
            "url": page.get("fullurl") or "https://es.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
            "source_title": title + " — Wikipedia",
        }
    raise RuntimeError(
        "No encontré un tema nuevo y documentado para este nicho. "
        "No voy a repetir un tema ni inventar una investigación."
    )


def research_topic(niche: str, previous_topics: list[str]) -> dict:
    result = choose_topic(niche, previous_topics)
    db.execute(
        "INSERT INTO research_notes(niche, claim, evidence_level, source_url, accessed_at, methodology, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            niche, result["summary"], "indicio", result["url"], db.now(),
            "Resumen introductorio recuperado automáticamente de Wikipedia. Requiere contraste con fuentes primarias antes de publicar.",
            db.now(),
        ),
    )
    return result
