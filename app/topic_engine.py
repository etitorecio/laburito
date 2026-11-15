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
import xml.etree.ElementTree as ET

from . import db

API = "https://es.wikipedia.org/w/api.php"
UA = "Laburito/1.0 (automatic topic research; contact: local project)"
TRENDS_RSS = "https://trends.google.com/trending/rss?geo=AR"
_TREND_STOPWORDS = {"de", "del", "la", "el", "los", "las", "en", "por", "para", "con", "y", "a", "un", "una", "the"}


def trending_searches() -> list[dict]:
    """Lee el RSS público de Google Trends Argentina; si falla, sigue la investigación normal."""
    request = urllib.request.Request(TRENDS_RSS, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            root = ET.fromstring(response.read())
        items = []
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            items.append({
                "title": title[:240],
                "published_at": (item.findtext("pubDate") or "").strip(),
                "url": (item.findtext("link") or "").strip(),
            })
        return items[:10]
    except Exception:
        # Las tendencias son una señal adicional, nunca una dependencia crítica.
        return []


def _relevant_trends(niche: str, pillars: str, trends: list[dict]) -> list[dict]:
    scope = set(_normal(" ".join([niche or "", pillars or ""])).split()) - _TREND_STOPWORDS
    if not scope:
        return []
    relevant = []
    for trend in trends:
        words = set(_normal(trend.get("title") or "").split()) - _TREND_STOPWORDS
        if scope & words:
            relevant.append(trend)
    return relevant[:3]


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


def _openalex_abstracts(title: str, limit: int = 4) -> list[dict]:
    """Recupera resúmenes académicos abiertos de OpenAlex, sin API key."""
    params = urllib.parse.urlencode({
        "search": title,
        "per-page": limit,
        "select": "id,doi,title,publication_year,type,abstract_inverted_index,authorships,primary_location",
    })
    request = urllib.request.Request(
        "https://api.openalex.org/works?" + params,
        headers={"User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []

    results = []
    for work in payload.get("results", []):
        index = work.get("abstract_inverted_index") or {}
        if not index:
            continue
        words = []
        for word, positions in index.items():
            for position in positions:
                words.append((int(position), word))
        abstract = " ".join(word for _, word in sorted(words))
        abstract = re.sub(r"\s+", " ", abstract).strip()
        if len(abstract) < 450:
            continue
        authors = []
        for item in (work.get("authorships") or [])[:3]:
            name = ((item.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        doi = work.get("doi") or ""
        location = work.get("primary_location") or {}
        landing = ((location.get("landing_page") or {}).get("url") or "").strip()
        url = doi or landing or work.get("id") or ""
        results.append({
            "title": (work.get("title") or "Publicación académica")[:240],
            "url": url,
            "abstract": abstract[:10000],
            "author": ", ".join(authors) or "Autores de la publicación",
            "year": work.get("publication_year"),
            "provider": "OpenAlex",
            "license": "Resumen bibliográfico de OpenAlex; consultar la publicación original",
        })
    return results


def choose_topic(
    niche: str,
    previous_topics: list[str],
    content_pillars: str = "",
    avoid_topics: str = "",
) -> dict:
    niche = (niche or "").strip()
    if not niche:
        raise ValueError("Configurá un nicho antes de iniciar el Autopiloto.")
    niche_key = _normal(niche)
    pillars = [part.strip() for part in re.split(r"[,;\n]+", content_pillars or "") if part.strip()]
    excluded = [_normal(part) for part in re.split(r"[,;\n]+", avoid_topics or "") if part.strip()]
    trend_signals = _relevant_trends(niche, content_pillars, trending_searches())
    search_terms = [niche] + [f"{niche} {pillar}" for pillar in pillars[:8]] + [niche + " historia", niche + " casos", niche + " descubrimientos"]
    # Solo suma tendencias que comparten palabras del nicho o sus pilares; no fuerza temas virales ajenos.
    search_terms += [f"{niche} {item['title']}" for item in trend_signals]
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
            if (
                not title or key in seen or key == niche_key
                or _is_duplicate(title, previous_topics)
                or any(term and term in _normal(title) for term in excluded)
            ):
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
            "trend_signals": trend_signals,
        }
    raise RuntimeError(
        "No encontré un tema nuevo y documentado para este nicho. "
        "No voy a repetir un tema ni inventar una investigación."
    )


def research_topic(
    niche: str,
    previous_topics: list[str],
    content_pillars: str = "",
    avoid_topics: str = "",
) -> dict:
    result = choose_topic(niche, previous_topics, content_pillars, avoid_topics)
    note_ids = []
    note_ids.append(db.execute(
        "INSERT INTO research_notes(niche, claim, evidence_level, source_url, accessed_at, methodology, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            niche, result["summary"], "orientación", result["url"], db.now(),
            "Extracto de Wikipedia recuperado automáticamente; usar como orientación y contrastar con publicaciones independientes.",
            db.now(),
        ),
    ))
    academic = _openalex_abstracts(result["title"])
    for item in academic:
        note_ids.append(db.execute(
            "INSERT INTO research_notes(niche, claim, evidence_level, source_url, accessed_at, methodology, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                niche, item["abstract"], "resumen académico", item["url"], db.now(),
                "Resumen bibliográfico recuperado de OpenAlex. No equivale al texto completo; comprobar alcance y metodología en la publicación original.",
                db.now(),
            ),
        ))
    result["academic_sources"] = academic
    result["note_ids"] = note_ids
    return result
