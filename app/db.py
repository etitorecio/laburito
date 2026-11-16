"""Capa de persistencia SQLite: esquema, migraciones y utilidades.

Todo el estado de AITuber Libre vive en un único archivo SQLite (WAL) dentro de
``data/``. No se usan servicios externos ni credenciales.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AITUBER_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "aitubel.sqlite3"
MEDIA_DIR = DATA_DIR / "media"
RENDER_DIR = DATA_DIR / "renders"
EXPORT_DIR = DATA_DIR / "exports"
MUSIC_DIR = DATA_DIR / "music"
TMP_DIR = DATA_DIR / "tmp"

_WRITE_LOCK = threading.RLock()

SCHEMA_VERSION = 10

_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """CREATE TABLE IF NOT EXISTS channels(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            topic TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'es',
            audience TEXT NOT NULL DEFAULT '',
            tone TEXT NOT NULL DEFAULT '',
            visual_identity TEXT NOT NULL DEFAULT '',
            formats TEXT NOT NULL DEFAULT 'documental,short',
            cadence TEXT NOT NULL DEFAULT 'semanal',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER REFERENCES channels(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            topic TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'documentary',
            aspect TEXT NOT NULL DEFAULT '16:9',
            status TEXT NOT NULL DEFAULT 'borrador',
            duration_target_sec INTEGER NOT NULL DEFAULT 600,
            voice TEXT NOT NULL DEFAULT 'es',
            speed INTEGER NOT NULL DEFAULT 150,
            pitch INTEGER NOT NULL DEFAULT 45,
            notes TEXT NOT NULL DEFAULT '',
            quality_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS scenes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            narration TEXT NOT NULL DEFAULT '',
            visual_query TEXT NOT NULL DEFAULT '',
            visual_path TEXT NOT NULL DEFAULT '',
            visual_kind TEXT NOT NULL DEFAULT '',
            visual_license TEXT NOT NULL DEFAULT '',
            visual_author TEXT NOT NULL DEFAULT '',
            visual_url TEXT NOT NULL DEFAULT '',
            audio_path TEXT NOT NULL DEFAULT '',
            audio_sec REAL NOT NULL DEFAULT 0,
            transition TEXT NOT NULL DEFAULT 'fundido',
            status TEXT NOT NULL DEFAULT 'pendiente',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id, idx)",
        """CREATE TABLE IF NOT EXISTS sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            scene_id INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            license TEXT NOT NULL DEFAULT '',
            accessed_at TEXT NOT NULL DEFAULT '',
            attribution TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'referencia',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS research_notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche TEXT NOT NULL DEFAULT '',
            claim TEXT NOT NULL DEFAULT '',
            evidence_level TEXT NOT NULL DEFAULT 'indicio',
            source_url TEXT NOT NULL DEFAULT '',
            accessed_at TEXT NOT NULL DEFAULT '',
            methodology TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS niches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            demand INTEGER NOT NULL DEFAULT 0,
            competition INTEGER NOT NULL DEFAULT 0,
            trend TEXT NOT NULL DEFAULT 'estable',
            difficulty INTEGER NOT NULL DEFAULT 0,
            copyright_risk TEXT NOT NULL DEFAULT 'medio',
            monetization TEXT NOT NULL DEFAULT '',
            series_potential INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS calendar_entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER REFERENCES channels(id) ON DELETE CASCADE,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            scheduled_for TEXT NOT NULL,
            format TEXT NOT NULL DEFAULT 'documental',
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planificado',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'en_cola',
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            attempts INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, id)",
        """CREATE TABLE IF NOT EXISTS assets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            scene_id INTEGER REFERENCES scenes(id) ON DELETE SET NULL,
            kind TEXT NOT NULL DEFAULT 'otro',
            path TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            license TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            bytes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS analytics(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
            channel_id INTEGER REFERENCES channels(id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT '',
            impressions INTEGER NOT NULL DEFAULT 0,
            views INTEGER NOT NULL DEFAULT 0,
            ctr REAL NOT NULL DEFAULT 0,
            retention REAL NOT NULL DEFAULT 0,
            avg_duration_sec REAL NOT NULL DEFAULT 0,
            interactions INTEGER NOT NULL DEFAULT 0,
            subscribers INTEGER NOT NULL DEFAULT 0,
            published_at TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'csv',
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            scope TEXT NOT NULL DEFAULT 'app',
            message TEXT NOT NULL DEFAULT '',
            data_json TEXT NOT NULL DEFAULT '{}'
        )""",
        """CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )""",
    ],
    2: [
        "ALTER TABLE projects ADD COLUMN template TEXT NOT NULL DEFAULT 'shorts'",
        "ALTER TABLE projects ADD COLUMN caption_style TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE projects ADD COLUMN transition_default TEXT NOT NULL DEFAULT 'fundido'",
        "ALTER TABLE projects ADD COLUMN resolution TEXT NOT NULL DEFAULT '1080p'",
        "ALTER TABLE projects ADD COLUMN fps INTEGER NOT NULL DEFAULT 25",
        "ALTER TABLE projects ADD COLUMN music TEXT NOT NULL DEFAULT 'auto'",
        "ALTER TABLE projects ADD COLUMN music_volume REAL NOT NULL DEFAULT 0.12",
    ],
    3: [
        "ALTER TABLE projects ADD COLUMN visual_style TEXT NOT NULL DEFAULT 'automatico'",
        "ALTER TABLE projects ADD COLUMN video_type TEXT NOT NULL DEFAULT 'moving_images'",
    ],
    4: [
        "ALTER TABLE scenes ADD COLUMN sfx_path TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE scenes ADD COLUMN sfx_volume REAL NOT NULL DEFAULT 0.8",
        "ALTER TABLE scenes ADD COLUMN sfx_start_sec REAL NOT NULL DEFAULT 0",
    ],
    5: [
        "ALTER TABLE scenes ADD COLUMN visual_trim_start_sec REAL NOT NULL DEFAULT 0",
        "ALTER TABLE scenes ADD COLUMN visual_trim_end_sec REAL NOT NULL DEFAULT 0",
    ],
    6: [
        "ALTER TABLE scenes ADD COLUMN visual_source_duration_sec REAL NOT NULL DEFAULT 0",
    ],
    7: [
        """CREATE TABLE IF NOT EXISTS timeline_overlays(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'image',
            path TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            start_sec REAL NOT NULL DEFAULT 0,
            duration_sec REAL NOT NULL DEFAULT 5,
            x REAL NOT NULL DEFAULT 0.62,
            y REAL NOT NULL DEFAULT 0.62,
            width REAL NOT NULL DEFAULT 0.32,
            opacity REAL NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_timeline_overlays_project ON timeline_overlays(project_id, start_sec, id)",
    ],
    8: [
        "ALTER TABLE timeline_overlays ADD COLUMN volume REAL NOT NULL DEFAULT 1",
    ],
    9: [
        """CREATE TABLE IF NOT EXISTS editor_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            target TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            undone INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_editor_history_project ON editor_history(project_id, id)",
    ],
    10: [
        "ALTER TABLE timeline_overlays ADD COLUMN source_start_sec REAL NOT NULL DEFAULT 0",
        "ALTER TABLE timeline_overlays ADD COLUMN source_end_sec REAL NOT NULL DEFAULT 0",
        "ALTER TABLE timeline_overlays ADD COLUMN source_duration_sec REAL NOT NULL DEFAULT 0",
        "UPDATE timeline_overlays SET source_duration_sec=duration_sec WHERE kind IN ('video','audio') AND source_duration_sec=0",
    ],
}

DEFAULT_SETTINGS = {
    "default_language": "es",
    "default_voice": "es",
    "music_volume": "0.12",
    "caption_style": "documental",
    "default_template": "shorts",
    "default_resolution": "1080p",
    "default_transition": "fundido",
    "ollama_url": "",
    "auto_backup": "1",
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def ensure_dirs() -> None:
    for d in (DATA_DIR, MEDIA_DIR, RENDER_DIR, EXPORT_DIR, MUSIC_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


@contextmanager
def db():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | list = ()) -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: tuple | list = (), default=None):
    row = query_one(sql, params)
    if not row:
        return default
    return list(row.values())[0]


def execute(sql: str, params: tuple | list = ()) -> int:
    with _WRITE_LOCK, db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return int(cur.lastrowid or 0)


def execute_many(statements: list[tuple[str, tuple | list]]) -> None:
    with _WRITE_LOCK, db() as conn:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()


def log(level: str, scope: str, message: str, data: dict | None = None) -> None:
    try:
        execute(
            "INSERT INTO logs(ts, level, scope, message, data_json) VALUES(?,?,?,?,?)",
            (now(), level, scope, message[:2000], json.dumps(data or {}, ensure_ascii=False)),
        )
    except Exception:  # nunca romper el flujo por un log
        pass


def get_setting(key: str, default: str | None = None) -> str:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, default if default is not None else "")


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def init_db() -> None:
    ensure_dirs()
    with _WRITE_LOCK, db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        current = int(row["value"]) if row else 0
        for version in sorted(_MIGRATIONS):
            if version <= current:
                continue
            for statement in _MIGRATIONS[version]:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(version),),
            )
        conn.commit()
        existing = {r["key"] for r in conn.execute("SELECT key FROM settings").fetchall()}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing:
                conn.execute("INSERT INTO settings(key, value) VALUES(?,?)", (key, value))
        # Migración de preferencias heredadas: esta instalación trabaja solo en español.
        conn.execute("UPDATE settings SET value='es' WHERE key='default_language'")
        conn.execute("UPDATE settings SET value='es' WHERE key='default_voice' AND value NOT IN ('es','es-ar','es-es-piper','es-mx','es-masculino','es-agudo')")
        conn.execute("UPDATE channels SET language='es' WHERE language!='es'")
        conn.execute("UPDATE projects SET voice='es' WHERE voice NOT IN ('es','es-ar','es-es-piper','es-mx','es-masculino','es-agudo')")
        conn.commit()


def backup() -> str | None:
    """Copia de seguridad del archivo SQLite (rotación simple de 5)."""
    ensure_dirs()
    if not DB_PATH.exists():
        return None
    backups = DATA_DIR / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    target = backups / f"aitubel-{time.strftime('%Y%m%d-%H%M%S')}.sqlite3"
    try:
        with db() as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        files = sorted(backups.glob("aitubel-*.sqlite3"))
        for old in files[:-5]:
            old.unlink(missing_ok=True)
        return str(target)
    except Exception as exc:  # pragma: no cover - defensivo
        log("error", "db", f"Backup falló: {exc}")
        return None
