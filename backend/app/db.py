"""Metadatos de versiones generadas (SQLite)."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator

from .config import settings
from .periods import now

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# Proceso que genera cada versión ("equipo:pid"). Al abrir la base solo se marcan como interrumpidas las
# versiones "en proceso" cuyo proceso ya no existe: un script o un segundo servidor no rompe una generación viva.
WORKER = f"{socket.gethostname()}:{os.getpid()}"
STALE_AFTER = timedelta(hours=2)  # en proceso por más de esto = abandonada (aunque el proceso siga vivo)
INTERRUPTED = "La generación se interrumpió por un reinicio del servidor. Puedes reintentar."

SCHEMA = """
CREATE TABLE IF NOT EXISTS report_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report TEXT NOT NULL,
    period TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,              -- processing | available | error
    filename TEXT,
    storage_key TEXT,
    size_bytes INTEGER,
    created_at TEXT NOT NULL,
    generated_at TEXT,
    generated_by TEXT NOT NULL,        -- correo o 'system'
    generated_by_name TEXT NOT NULL,   -- nombre visible ('Sistema')
    trigger TEXT NOT NULL,             -- schedule | manual | on_demand | catch_up
    error TEXT,                        -- mensaje para el usuario
    error_detail TEXT,                 -- detalle interno (no se expone)
    stats TEXT,                        -- JSON con conteos y advertencias
    UNIQUE (report, period, version)
);
CREATE INDEX IF NOT EXISTS ix_versions_report_period ON report_versions(report, period);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            cols = {r[1] for r in _conn.execute("PRAGMA table_info(report_versions)")}
            if "worker" not in cols:
                _conn.execute("ALTER TABLE report_versions ADD COLUMN worker TEXT")
            _mark_interrupted(_conn)
            _conn.commit()
        return _conn


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # acceso denegado → existe
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # en POSIX la señal 0 solo verifica que el proceso exista
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _is_orphan(row: sqlite3.Row) -> bool:
    try:
        created = datetime.fromisoformat(row["created_at"])
        if now() - created > STALE_AFTER:
            return True
    except (TypeError, ValueError):
        return True
    worker = row["worker"] or ""
    host, _, pid = worker.rpartition(":")
    if not worker or not pid.isdigit():
        return True  # versiones anteriores a este control
    if host != socket.gethostname():
        return False  # otro equipo: no se puede verificar; queda a cargo del plazo STALE_AFTER
    return not _pid_alive(int(pid))


def _mark_interrupted(conn: sqlite3.Connection) -> None:
    """Pasa a error las versiones "en proceso" cuyo proceso generador ya no existe."""
    rows = conn.execute("SELECT id, created_at, worker FROM report_versions WHERE status='processing'").fetchall()
    orphan = [r["id"] for r in rows if _is_orphan(r)]
    for vid in orphan:
        conn.execute("UPDATE report_versions SET status='error', error=?, generated_at=? WHERE id=?",
                     (INTERRUPTED, now().isoformat(), vid))


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    with _lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    d = dict(row)
    if d.get("stats"):
        try:
            d["stats"] = json.loads(d["stats"])
        except ValueError:
            d["stats"] = None
    return d


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    conn = connect()
    with _lock:
        return [row_to_dict(r) for r in conn.execute(sql, params).fetchall()]  # type: ignore[misc]


def query_one(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    conn = connect()
    with _lock:
        return row_to_dict(conn.execute(sql, params).fetchone())


def create_version(report: str, period: str, user_email: str, user_name: str, trigger: str) -> dict[str, Any]:
    with tx() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM report_versions WHERE report=? AND period=?",
            (report, period),
        ).fetchone()
        version = int(row[0])
        cur = conn.execute(
            """INSERT INTO report_versions (report, period, version, status, created_at, generated_by,
               generated_by_name, trigger, worker) VALUES (?,?,?,?,?,?,?,?,?)""",
            (report, period, version, "processing", now().isoformat(), user_email, user_name, trigger, WORKER),
        )
        vid = cur.lastrowid
    return get_version(vid)  # type: ignore[return-value]


def finish_version(vid: int, *, filename: str, storage_key: str, size_bytes: int, stats: dict) -> None:
    with tx() as conn:
        conn.execute(
            """UPDATE report_versions SET status='available', filename=?, storage_key=?, size_bytes=?,
               stats=?, generated_at=? WHERE id=?""",
            (filename, storage_key, size_bytes, json.dumps(stats, ensure_ascii=False), now().isoformat(), vid),
        )


def fail_version(vid: int, *, error: str, detail: str) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE report_versions SET status='error', error=?, error_detail=?, generated_at=? WHERE id=?",
            (error, detail[-4000:], now().isoformat(), vid),
        )


def get_version(vid: int) -> dict[str, Any] | None:
    return query_one("SELECT * FROM report_versions WHERE id=?", (vid,))


def versions_for(report: str, period: str | None = None) -> list[dict[str, Any]]:
    if period:
        return query(
            "SELECT * FROM report_versions WHERE report=? AND period=? ORDER BY version DESC", (report, period)
        )
    return query("SELECT * FROM report_versions WHERE report=? ORDER BY period DESC, version DESC", (report,))


def all_versions() -> list[dict[str, Any]]:
    return query("SELECT * FROM report_versions ORDER BY created_at DESC, id DESC")


def set_kv(key: str, value: str) -> None:
    with tx() as conn:
        conn.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key, value))


def get_kv(key: str) -> str | None:
    row = query_one("SELECT value FROM kv WHERE key=?", (key,))
    return row["value"] if row else None
