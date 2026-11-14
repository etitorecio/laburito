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
    used = {_normal(x) for x in previous_topics if x}
    niche_key = _normal(niche)
    search_terms = [niche, niche + " historia", niche + " casos", niche + " descubrimientos"]
    candidates = []
    seen = set()
    for term in search_terms:
        data = _get({
            "action": "query", "list": "search", "srsearch": term,
            "srnamespace": 0, "srlimit": 50, "format": "json",
        })
        for item in data.get("query", {}).get("search", []):
            title = (item.get("title") or "").strip()
            key = _normal(title)
            if not title or key in seen or key == niche_key or key in used:
                continue
            seen.add(key)
            candidates.append(title)

    for title in candidates:
        summary = _get({
            "action": "query", "prop": "extracts|info", "explaintext": 1,
            "inprop": "url", "titles": title, "format": "json",
        })
        pages = summary.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
        if len(extract) < 650:
            continue
        return {
            "title": title,
            "topic": title,
            "summary": extract[:12000],
            "extract": extract[:12000],
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
            "Extracto del artículo de Wikipedia recuperado automáticamente. Es una fuente secundaria de orientación; requiere contraste con fuentes primarias antes de publicar.",
            db.now(),
        ),
    )
    return result
