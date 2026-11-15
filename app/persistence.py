"""Copia de seguridad comprimida y persistencia externa opcional (solo HTTPS).

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
    bucket = (os.environ.get("SUPABASE_STORAGE_BUCKET") or "").strip() or "laburito-private-backups"
    return base, key, bucket


def configured() -> bool:
    base, key, _bucket = _settings()
    return bool(base.startswith("https://") and key)


def status() -> dict:
    base, key, bucket = _settings()
    return {
        "configured": bool(base and key),
        "provider": "Supabase Storage" if base and key else None,
        "bucket": bucket if base and key else None,
        "private": True,
        "note": (
            "Credenciales detectadas; verificá la primera sincronización en los logs."
            if base and key else
            "Sin almacenamiento persistente externo. En AppJet Free, los archivos del contenedor pueden perderse al reemplazarlo."
        ),
    }


def _request(method: str, path: str, body: bytes | None = None,
             content_type: str = "application/json", extra_headers: dict | None = None):
    base, key, _bucket = _settings()
    if not base.startswith("https://") or not key:
        raise RuntimeError("Configurá SUPABASE_URL con HTTPS y SUPABASE_SERVICE_ROLE_KEY.")
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


def _storage_object_path(name: str) -> str:
    _base, _key, bucket = _settings()
    return "/storage/v1/object/" + urllib.parse.quote(bucket, safe="") + "/" + urllib.parse.quote(name, safe="/")


def sync_pending_video(project_id: int, video_path: str | Path) -> bool:
    """Conserva el MP4 final hasta que YouTube confirme que lo recibió."""
    if not configured():
        return False
    video = Path(video_path)
    if not video.is_file() or video.stat().st_size < 1024:
        raise RuntimeError("No se puede respaldar el Short: el MP4 final no existe o está vacío.")
    _ensure_bucket()
    object_path = _storage_object_path(f"pending/{int(project_id)}.mp4")
    with _request(
        "POST", object_path, video.read_bytes(), "video/mp4",
        extra_headers={"x-upsert": "true"},
    ) as response:
        response.read()
    db.log("info", "persistence", "MP4 pendiente respaldado en Supabase Storage.",
           {"project_id": int(project_id), "bytes": video.stat().st_size})
    return True


def restore_pending_video(project_id: int) -> bool:
    """Restaura el MP4 si el contenedor fue reemplazado antes de publicar."""
    row = db.query_one(
        "SELECT path FROM assets WHERE project_id=? AND kind='video_final' ORDER BY id DESC LIMIT 1",
        (int(project_id),),
    )
    if not row or not row.get("path"):
        raise RuntimeError("No se encontró el MP4 final asociado al proyecto.")
    target = Path(row["path"])
    if target.is_file() and target.stat().st_size >= 1024:
        return True
    if not configured():
        raise RuntimeError("El MP4 final se perdió y no hay almacenamiento persistente configurado.")
    object_path = _storage_object_path(f"pending/{int(project_id)}.mp4")
    try:
        with _request("GET", object_path) as response:
            content = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError("No existe una copia persistente del MP4 para reintentar la publicación.") from exc
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"No se pudo restaurar el MP4 pendiente ({exc.code}): {detail}") from exc
    if len(content) < 1024:
        raise RuntimeError("La copia persistente del MP4 está vacía o incompleta.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".restore.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    db.log("info", "persistence", "MP4 pendiente restaurado desde Supabase Storage.",
           {"project_id": int(project_id)})
    return True


def delete_pending_video(project_id: int) -> bool:
    """Elimina el MP4 remoto solo después de completar la publicación."""
    if not configured():
        return False
    _ensure_bucket()
    _base, _key, bucket = _settings()
    path = f"pending/{int(project_id)}.mp4"
    payload = json.dumps({"prefixes": [path]}).encode()
    with _request(
        "DELETE", "/storage/v1/object/" + urllib.parse.quote(bucket, safe=""),
        payload, "application/json",
    ) as response:
        response.read()
    db.log("info", "persistence", "MP4 pendiente eliminado tras la publicación.",
           {"project_id": int(project_id)})
    return True


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
