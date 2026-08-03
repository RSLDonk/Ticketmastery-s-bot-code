import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict

from .config import (
    DB_FILE,
    DEFAULT_PANEL_DESCRIPTION,
    DEFAULT_PANEL_TITLE,
    DEFAULT_TICKET_DESCRIPTION,
    DEFAULT_TICKET_TITLE,
)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

@contextmanager
def db():
    """Reusable DB connection context manager."""
    conn = get_db_connection()
    try:
        yield connx
    finally:
        conn.close()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    old_panel_description = "Open a ticket using the buttons below."
    panel_description_default = DEFAULT_PANEL_DESCRIPTION.replace("'", "''")

    c.execute(f"""CREATE TABLE IF NOT EXISTS guild_configs (
        guild_id INTEGER PRIMARY KEY,
        tickets_created INTEGER DEFAULT 0,
        staff_role_id INTEGER,
        log_channel_id INTEGER,
        panel_title TEXT DEFAULT '🎫 Need Support?',
        panel_description TEXT DEFAULT '{panel_description_default}',
        panel_color INTEGER DEFAULT 5793266,
        ticket_title TEXT DEFAULT '🎫 Ticket Created',
        ticket_description TEXT,
        auto_close_enabled INTEGER DEFAULT 1,
        log_transcripts INTEGER DEFAULT 1,
        transcript_format TEXT DEFAULT 'txt',
        panel_channel_id INTEGER,
        panel_message_id INTEGER
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS ticket_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT NOT NULL,
        role_id INTEGER,
        position INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS open_tickets (
        guild_id INTEGER,
        channel_id INTEGER,
        owner_id INTEGER,
        num INTEGER,
        created_at INTEGER,
        last_activity INTEGER,
        reminded24 INTEGER DEFAULT 0,
        hold INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, channel_id)
    )""")

    # Add new columns to open_tickets if they don't exist
    c.execute("PRAGMA table_info(open_tickets)")
    columns = [col[1] for col in c.fetchall()]
    
    if 'assigned_to' not in columns:
        c.execute("ALTER TABLE open_tickets ADD COLUMN assigned_to INTEGER DEFAULT NULL")
    
    if 'category_id' not in columns:
        c.execute("ALTER TABLE open_tickets ADD COLUMN category_id INTEGER DEFAULT NULL")

    c.execute("PRAGMA table_info(guild_configs)")
    config_columns = [col[1] for col in c.fetchall()]

    if 'transcript_format' not in config_columns:
        c.execute("ALTER TABLE guild_configs ADD COLUMN transcript_format TEXT DEFAULT 'txt'")

    appearance_columns = {
        "panel_title": "TEXT",
        "panel_color": "INTEGER",
        "ticket_title": "TEXT",
        "ticket_description": "TEXT",
    }
    for column, column_type in appearance_columns.items():
        if column not in config_columns:
            c.execute(f"ALTER TABLE guild_configs ADD COLUMN {column} {column_type}")

    c.execute("UPDATE guild_configs SET transcript_format = 'txt'")

    c.execute(
        """
        UPDATE guild_configs
        SET panel_description = ?
        WHERE panel_description IS NULL OR panel_description = ?
        """,
        (DEFAULT_PANEL_DESCRIPTION, old_panel_description)
    )
    c.execute(
        """
        UPDATE guild_configs
        SET panel_title = COALESCE(panel_title, ?),
            panel_color = COALESCE(panel_color, ?),
            ticket_title = COALESCE(ticket_title, ?),
            ticket_description = COALESCE(ticket_description, ?)
        """,
        (
            DEFAULT_PANEL_TITLE,
            0x5865F2,
            DEFAULT_TICKET_TITLE,
            DEFAULT_TICKET_DESCRIPTION,
        ),
    )

    conn.commit()
    conn.close()

def get_gcfg(gid: int) -> Dict[str, Any]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM guild_configs WHERE guild_id = ?', (gid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "tickets_created": row["tickets_created"],
            "staff_role_id": row["staff_role_id"],
            "log_channel_id": row["log_channel_id"],
            "panel_title": row["panel_title"],
            "panel_description": row["panel_description"],
            "panel_color": row["panel_color"],
            "ticket_title": row["ticket_title"],
            "ticket_description": row["ticket_description"],
            "auto_close_enabled": bool(row["auto_close_enabled"]),
            "log_transcripts": bool(row["log_transcripts"]),
            "transcript_format": "txt",
            "panel_channel_id": row["panel_channel_id"],
            "panel_message_id": row["panel_message_id"]
        }
    default = {
        "tickets_created": 0,
        "staff_role_id": None,
        "log_channel_id": None,
        "panel_title": DEFAULT_PANEL_TITLE,
        "panel_description": DEFAULT_PANEL_DESCRIPTION,
        "panel_color": 0x5865F2,
        "ticket_title": DEFAULT_TICKET_TITLE,
        "ticket_description": DEFAULT_TICKET_DESCRIPTION,
        "auto_close_enabled": True,
        "log_transcripts": True,
        "transcript_format": "txt",
        "panel_channel_id": None,
        "panel_message_id": None
    }
    set_gcfg(gid, default)
    return default

def get_all_gcfg() -> Dict[str, Dict[str, Any]]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM guild_configs')
    rows = c.fetchall()
    conn.close()
    result = {}
    for row in rows:
        gid = str(row["guild_id"])
        result[gid] = {
            "tickets_created": row["tickets_created"],
            "staff_role_id": row["staff_role_id"],
            "log_channel_id": row["log_channel_id"],
            "panel_title": row["panel_title"],
            "panel_description": row["panel_description"],
            "panel_color": row["panel_color"],
            "ticket_title": row["ticket_title"],
            "ticket_description": row["ticket_description"],
            "auto_close_enabled": bool(row["auto_close_enabled"]),
            "log_transcripts": bool(row["log_transcripts"]),
            "transcript_format": "txt",
            "panel_channel_id": row["panel_channel_id"],
            "panel_message_id": row["panel_message_id"]
        }
    return result

def set_gcfg(gid: int, val: Dict[str, Any]):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO guild_configs 
        (guild_id, tickets_created, staff_role_id, log_channel_id, panel_title, panel_description, panel_color, ticket_title, ticket_description, auto_close_enabled, log_transcripts, transcript_format, panel_channel_id, panel_message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            gid,
            val["tickets_created"],
            val["staff_role_id"],
            val["log_channel_id"],
            val.get("panel_title") or DEFAULT_PANEL_TITLE,
            val["panel_description"],
            val.get("panel_color", 0x5865F2),
            val.get("ticket_title") or DEFAULT_TICKET_TITLE,
            val.get("ticket_description") or DEFAULT_TICKET_DESCRIPTION,
            int(val["auto_close_enabled"]),
            int(val["log_transcripts"]),
            "txt",
            val["panel_channel_id"],
            val["panel_message_id"],
        ))
    conn.commit()
    conn.close()

def get_categories(gid: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, role_id
        FROM ticket_categories
        WHERE guild_id = ?
        ORDER BY position ASC
    """, (gid,))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "role_id": r[2]} for r in rows]


def get_category(gid: int, category_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, role_id
        FROM ticket_categories
        WHERE guild_id = ? AND id = ?
    """, (gid, category_id))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "role_id": row[2]}
    return None


def add_category(gid: int, name: str, role_id: int | None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO ticket_categories (guild_id, name, role_id)
        VALUES (?, ?, ?)
    """, (gid, name, role_id))
    conn.commit()
    conn.close()


def clear_categories(gid: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM ticket_categories WHERE guild_id = ?", (gid,))
    conn.commit()
    conn.close()


def update_category(gid: int, category_id: int, name: str, role_id: int | None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE ticket_categories
        SET name = ?, role_id = ?
        WHERE guild_id = ? AND id = ?
    """, (name, role_id, gid, category_id))
    conn.commit()
    conn.close()


def remove_category(gid: int, category_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM ticket_categories WHERE guild_id = ? AND id = ?",
        (gid, category_id)
    )
    conn.commit()
    conn.close()


def add_open_ticket(gid: int, channel_id: int, owner_id: int, num: int, category_id: int = None):
    now = int(time.time())
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO open_tickets
        (guild_id, channel_id, owner_id, num, created_at, last_activity, category_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (gid, channel_id, owner_id, num, now, now, category_id))
    conn.commit()
    conn.close()

def remove_open_ticket(gid: int, channel_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM open_tickets WHERE guild_id=? AND channel_id=?",
        (gid, channel_id)
    )
    conn.commit()
    conn.close()

def get_open_ticket(gid: int, channel_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM open_tickets WHERE guild_id=? AND channel_id=?",
        (gid, channel_id)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "owner_id": row[2],
        "num": row[3],
        "created_at": row[4],
        "last_activity": row[5],
        "reminded24": bool(row[6]),
        "hold": bool(row[7]),
        "assigned_to": row[8] if len(row) > 8 else None,
        "category_id": row[9] if len(row) > 9 else None
    }


def get_open_ticket_by_owner(gid: int, owner_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM open_tickets WHERE guild_id=? AND owner_id=?",
        (gid, owner_id)
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "channel_id": row[1],
        "owner_id": row[2],
        "num": row[3],
        "created_at": row[4],
        "last_activity": row[5],
        "reminded24": bool(row[6]),
        "hold": bool(row[7]),
        "assigned_to": row[8] if len(row) > 8 else None,
        "category_id": row[9] if len(row) > 9 else None
    }


def assign_ticket(gid: int, channel_id: int, staff_id: int):
    """Assign a ticket to staff."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE open_tickets
        SET assigned_to = ?
        WHERE guild_id=? AND channel_id=?
    ''', (staff_id, gid, channel_id))
    conn.commit()
    conn.close()
