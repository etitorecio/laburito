"""Descubrimiento temático gratuito basado en Wikipedia.

No inventa tendencias: propone temas documentados dentro del nicho y guarda
la página consultada como fuente de contexto. Si no hay conexión o candidatos
nuevos, falla explícitamente para evitar publicar un tema repetido.
"""
from __future__ import annotations

import difflib
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
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"No se pudo consultar Wikipedia para investigar el tema: {exc}") from exc


def _normal(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _external_references(title: str) -> list[str]:
    try:
        data = _get({
            "action": "query", "prop": "extlinks", "ellimit": 50,
            "titles": title, "format": "json",
        })
        pages = data.get("query", {}).get("pages", {})
        urls = []
        trusted_domains = (
            "britannica.com", "nature.com", "science.org", "doi.org", "jstor.org",
            "unesco.org", "smithsonian.org", "nationalgeographic.com", "archive.org",
            "who.int", "un.org", "reuters.com", "apnews.com", "bbc.com",
        )
        for page in pages.values():
            for link in page.get("extlinks", []):
                url = (link.get("*") or "").strip()
                host = (urllib.parse.urlparse(url).hostname or "").lower()
                trusted_host = host.endswith(".gov") or host.endswith(".edu") or any(
                    host == domain or host.endswith("." + domain) for domain in trusted_domains
                )
                if url.startswith(("https://", "http://")) and trusted_host:
                    if url not in urls:
                        urls.append(url)
                if len(urls) >= 8:
                    return urls
        return urls
    except Exception:
        return []

def _is_duplicate(candidate: str, previous_topics: list[str]) -> bool:
    candidate_norm = _normal(candidate)
    candidate_tokens = set(candidate_norm.split())
    for previous in previous_topics:
        previous_norm = _normal(previous)
        if not previous_norm:
            continue
        if candidate_norm == previous_norm:
            return True
        if difflib.SequenceMatcher(None, candidate_norm, previous_norm).ratio() >= 0.84:
            return True
        previous_tokens = set(previous_norm.split())
        smaller = min(len(candidate_tokens), len(previous_tokens))
        if smaller and len(candidate_tokens & previous_tokens) / smaller >= 0.82:
            return True
    return False


def choose_topic(niche: str, previous_topics: list[str]) -> dict:
    niche = (niche or "").strip()
    if not niche:
        raise ValueError("Configurá un nicho antes de iniciar el Autopiloto.")
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
            if not title or key in seen or key == niche_key or _is_duplicate(title, previous_topics):
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
            "references": _external_references(title),
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
