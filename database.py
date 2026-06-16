"""
database.py — SQLite persistence layer for Harar NID Bot
Drop-in replacement for the MongoDB version. No external service needed.
Data is stored in /app/data/harar_nid_bot.db (persistent on Railway/Fly.io).
"""

import os, json, sqlite3
from datetime import datetime, date
from threading import Lock

# ── connection ────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("SQLITE_PATH", "/app/data/harar_nid_bot.db")
_lock   = Lock()

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads
    return conn

def init_db():
    """Create tables and seed default officers if needed."""
    with _lock, get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS officers (
                name      TEXT PRIMARY KEY,
                kits      TEXT NOT NULL DEFAULT '[]',   -- JSON array
                chat_id   INTEGER,
                username  TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                date      TEXT NOT NULL,
                kit       TEXT NOT NULL,
                reg       INTEGER NOT NULL DEFAULT 0,
                uploaded  INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT,
                PRIMARY KEY (date, kit)
            );

            CREATE TABLE IF NOT EXISTS pending_users (
                chat_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                seen_at    TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '{}'   -- JSON
            );
        """)

        # Seed default officers only if table is empty
        count = conn.execute("SELECT COUNT(*) FROM officers").fetchone()[0]
        if count == 0:
            defaults = [
                ("Nardos",   ["EID1277"]),
                ("Lidiya",   ["EID1227"]),
                ("Hana",     ["EID1305"]),
                ("Ayehu",    ["EID1275"]),
                ("Mekdes",   ["EID1272"]),
                ("Eden",     ["EID1315"]),
                ("Makda",    ["EID1273"]),
                ("Ashebir",  ["EID1230"]),
                ("Amar",     ["EID1297"]),
                ("Ermias",   ["EID1260"]),
                ("Mustefa",  ["EID1271"]),
                ("Getachew", ["EID1306"]),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO officers (name, kits) VALUES (?, ?)",
                [(n, json.dumps(k)) for n, k in defaults]
            )

        # Seed default settings if missing
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('main', ?)",
            (json.dumps({
                "admin_usernames": ["gech_2721"],
                "admin_chat_ids":  [],
                "forward_groups":  [],
            }),)
        )

# Keep the old name so bot.py's `db.init_officers()` still works
def init_officers():
    init_db()

# ── helpers ───────────────────────────────────────────────────────────────────
def _row_to_officer(row) -> dict:
    return {
        "name":     row["name"],
        "kits":     json.loads(row["kits"]),
        "chat_id":  row["chat_id"],
        "username": row["username"],
    }

# ══════════════════════════════════════════════════════════════════════════════
# OFFICERS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_officers() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM officers ORDER BY name ASC").fetchall()
    return [_row_to_officer(r) for r in rows]

def get_officer_by_chat_id(chat_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM officers WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    return _row_to_officer(row) if row else None

def get_officer_by_name(name: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM officers WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
    return _row_to_officer(row) if row else None

def capture_officer_chat_id(name: str, chat_id: int, username: str = None):
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE officers SET chat_id = ?, username = ? WHERE name = ? COLLATE NOCASE",
            (chat_id, username, name)
        )

def add_officer(name: str, kits: list, chat_id: int = None, username: str = None):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO officers (name, kits, chat_id, username) VALUES (?, ?, ?, ?)",
            (name, json.dumps(kits), chat_id, username)
        )

def update_officer_name(old_name: str, new_name: str):
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE officers SET name = ? WHERE name = ? COLLATE NOCASE",
            (new_name, old_name)
        )

def update_officer_kits(name: str, kits: list):
    with _lock, get_conn() as conn:
        conn.execute(
            "UPDATE officers SET kits = ? WHERE name = ? COLLATE NOCASE",
            (json.dumps(kits), name)
        )

def assign_kit(name: str, kit: str):
    officer = get_officer_by_name(name)
    if officer:
        kits = officer["kits"]
        if kit not in kits:
            kits.append(kit)
            update_officer_kits(name, kits)

def delete_officer(name: str):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM officers WHERE name = ? COLLATE NOCASE", (name,))

# ══════════════════════════════════════════════════════════════════════════════
# PENDING USERS
# ══════════════════════════════════════════════════════════════════════════════

def upsert_pending_user(chat_id: int, username: str, first_name: str):
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT INTO pending_users (chat_id, username, first_name, seen_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                   username=excluded.username,
                   first_name=excluded.first_name,
                   seen_at=excluded.seen_at""",
            (chat_id, username, first_name, datetime.utcnow().isoformat())
        )

def get_pending_users() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pending_users ORDER BY seen_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]

def delete_pending_user(chat_id: int):
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM pending_users WHERE chat_id = ?", (chat_id,))

# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def today_str() -> str:
    return date.today().isoformat()

def save_report(date_iso: str, kit: str, reg: int, uploaded: int):
    with _lock, get_conn() as conn:
        conn.execute(
            """INSERT INTO reports (date, kit, reg, uploaded, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(date, kit) DO UPDATE SET
                   reg=excluded.reg,
                   uploaded=excluded.uploaded,
                   updated_at=excluded.updated_at""",
            (date_iso, kit, reg, uploaded, datetime.utcnow().isoformat())
        )

def get_reports_for_date(date_iso: str) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT kit, reg, uploaded FROM reports WHERE date = ?", (date_iso,)
        ).fetchall()
    return {r["kit"]: {"reg": r["reg"], "uploaded": r["uploaded"]} for r in rows}

def get_reports_range(start_iso: str, end_iso: str) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, kit, reg, uploaded FROM reports WHERE date >= ? AND date <= ?",
            (start_iso, end_iso)
        ).fetchall()
    result = {}
    for r in rows:
        d = r["date"]
        if d not in result:
            result[d] = {}
        result[d][r["kit"]] = {"reg": r["reg"], "uploaded": r["uploaded"]}
    return result

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

def _get_settings_raw() -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'main'"
        ).fetchone()
    return json.loads(row["value"]) if row else {}

def _save_settings(data: dict):
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('main', ?)",
            (json.dumps(data),)
        )

def get_settings() -> dict:
    return _get_settings_raw()

def add_admin_chat_id(chat_id: int):
    s = _get_settings_raw()
    ids = s.get("admin_chat_ids", [])
    if chat_id not in ids:
        ids.append(chat_id)
        s["admin_chat_ids"] = ids
        _save_settings(s)

def add_forward_group(group_id: int):
    s = _get_settings_raw()
    groups = s.get("forward_groups", [])
    if group_id not in groups:
        groups.append(group_id)
        s["forward_groups"] = groups
        _save_settings(s)

def remove_forward_group(group_id: int):
    s = _get_settings_raw()
    groups = s.get("forward_groups", [])
    s["forward_groups"] = [g for g in groups if g != group_id]
    _save_settings(s)

def is_admin(username: str, chat_id: int) -> bool:
    s = _get_settings_raw()
    admins = [a.lower() for a in s.get("admin_usernames", [])]
    return (username or "").lower() in admins or chat_id in s.get("admin_chat_ids", [])
