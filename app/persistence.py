"""Copia de seguridad cifrada en tránsito y persistencia externa opcional.

En AppJet Free el filesystem del contenedor es efímero. Si se configura un
bucket privado de Supabase Storage, se sincroniza una copia SQLite comprimida
y se restaura antes de inicializar la aplicación. No se expone la service key
al navegador.
"""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import db

OBJECT_NAME = "laburito.sqlite3.gz"


def _settings() -> tuple[str, str, str]:
    base = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    bucket = (os.environ.get("SUPABASE_STORAGE_BUCKET") or "laburito-private-backups").strip()
    return base, key, bucket


def configured() -> bool:
    base, key, _bucket = _settings()
    return bool(base and key)


def status() -> dict:
    base, key, bucket = _settings()
    return {
        "configured": bool(base and key),
        "provider": "Supabase Storage" if base and key else None,
        "bucket": bucket if base and key else None,
        "private": True,
        "note": (
            "Copia externa activa; última sincronización disponible en logs."
            if base and key else
            "Sin almacenamiento persistente externo. En AppJet Free, los archivos del contenedor pueden perderse al reemplazarlo."
        ),
    }


def _request(method: str, path: str, body: bytes | None = None,
             content_type: str = "application/json", extra_headers: dict | None = None):
    base, key, _bucket = _settings()
    if not base or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    if body is not None:
        headers["Content-Type"] = content_type
    headers.update(extra_headers or {})
    request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    return urllib.request.urlopen(request, timeout=90)


def _ensure_bucket() -> None:
    _base, _key, bucket = _settings()
    payload = json.dumps({"id": bucket, "name": bucket, "public": False}).encode()
    try:
        with _request("POST", "/storage/v1/bucket", payload):
            pass
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 409 or (exc.code == 400 and "already exists" in detail.lower()):
            return
        raise RuntimeError(f"No se pudo preparar el bucket privado de Supabase ({exc.code}): {detail}") from exc


def restore_if_available() -> bool:
    """Restaura la copia remota solo cuando todavía no existe una SQLite local."""
    if not configured():
        return False
    db.ensure_dirs()
    if db.DB_PATH.exists() and db.DB_PATH.stat().st_size > 0:
        return False
    _ensure_bucket()
    _base, _key, bucket = _settings()
    object_path = "/storage/v1/object/" + urllib.parse.quote(bucket, safe="") + "/" + OBJECT_NAME
    try:
        with _request("GET", object_path) as response:
            compressed = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"No se pudo recuperar la copia de Supabase ({exc.code}): {detail}") from exc

    temporary = db.DB_PATH.with_suffix(".restore.tmp")
    try:
        temporary.write_bytes(gzip.decompress(compressed))
        with sqlite3.connect(temporary) as connection:
            check = connection.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError("La copia remota de SQLite no pasó integrity_check.")
        os.replace(temporary, db.DB_PATH)
        for suffix in ("-wal", "-shm"):
            Path(str(db.DB_PATH) + suffix).unlink(missing_ok=True)
        db.log("info", "persistence", "Base SQLite restaurada desde Supabase Storage.")
        return True
    finally:
        temporary.unlink(missing_ok=True)


def sync_backup() -> bool:
    """Sube una copia consistente y comprimida a un bucket privado."""
    if not configured():
        return False
    _ensure_bucket()
    backup_path = db.backup()
    if not backup_path:
        raise RuntimeError("No se pudo crear la copia local de SQLite.")
    compressed = gzip.compress(Path(backup_path).read_bytes(), compresslevel=6)
    _base, _key, bucket = _settings()
    object_path = "/storage/v1/object/" + urllib.parse.quote(bucket, safe="") + "/" + OBJECT_NAME
    with _request(
        "POST", object_path, compressed, "application/gzip",
        extra_headers={"x-upsert": "true"},
    ) as response:
        response.read()
    db.log("info", "persistence", "Copia SQLite sincronizada con Supabase Storage.",
           {"compressed_bytes": len(compressed)})
    return True
