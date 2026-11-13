import os
import sqlite3
from datetime import datetime, timedelta, timezone
from config import Config

# ---------------------------------------------------------------------------
# Backend detection: use PostgreSQL if DATABASE_URL is set, otherwise SQLite
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Render sometimes provides postgres:// URLs but psycopg2 needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    try:
        import psycopg2
        import psycopg2.extras
        print("[DB] ✅ Conexão PostgreSQL configurada")
    except ImportError:
        print("[DB] ⚠️ psycopg2 não instalado, caindo para SQLite")
        USE_POSTGRES = False
else:
    print(f"[DB] 📁 Usando SQLite local: {Config.DB_PATH}")


# ---------------------------------------------------------------------------
# Connection & backend helpers
# ---------------------------------------------------------------------------

def _is_pg(conn) -> bool:
    return not isinstance(conn, sqlite3.Connection)


def _ph(conn) -> str:
    return "%s" if _is_pg(conn) else "?"


def _db_ts(conn, dt: datetime):
    """Formats a UTC datetime to match CURRENT_TIMESTAMP in each backend."""
    utc_dt = dt.astimezone(timezone.utc)
    if _is_pg(conn):
        return utc_dt.replace(tzinfo=None)
    return utc_dt.strftime("%Y-%m-%d %H:%M:%S")


def _init_sqlite_schema(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE NOT NULL,
            platform TEXT NOT NULL,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            original_price REAL,
            discount_percent INTEGER,
            url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_pid ON seen_deals(product_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_title ON seen_deals(title)")

    cursor.execute("PRAGMA table_info(seen_deals)")
    columns = [col[1] for col in cursor.fetchall()]
    if "telegram_message_id" not in columns:
        cursor.execute("ALTER TABLE seen_deals ADD COLUMN telegram_message_id INTEGER")
    if "end_time" not in columns:
        cursor.execute("ALTER TABLE seen_deals ADD COLUMN end_time INTEGER")
    if "is_active" not in columns:
        cursor.execute("ALTER TABLE seen_deals ADD COLUMN is_active INTEGER DEFAULT 1")
    if "image_url" not in columns:
        cursor.execute("ALTER TABLE seen_deals ADD COLUMN image_url TEXT DEFAULT ''")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()


def _connect_postgres():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as first_err:
        if "sslmode" not in DATABASE_URL:
            try:
                return psycopg2.connect(DATABASE_URL, sslmode="require")
            except Exception:
                pass
        raise first_err


def get_connection():
    global USE_POSTGRES
    if USE_POSTGRES:
        try:
            return _connect_postgres()
        except Exception as e:
            print(f"[DB] ⚠️ Falha ao conectar no PostgreSQL: {e}. Usando SQLite temporariamente.")
            USE_POSTGRES = False
            conn = sqlite3.connect(Config.DB_PATH)
            conn.row_factory = sqlite3.Row
            _init_sqlite_schema(conn)
            return conn
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fetchall_as_dicts(cursor, is_pg: bool):
    if is_pg:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]
    return [dict(row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    conn = get_connection()
    is_pg = _is_pg(conn)
    try:
        cursor = conn.cursor()

        if is_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_deals (
                    id SERIAL PRIMARY KEY,
                    product_id TEXT UNIQUE NOT NULL,
                    platform TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    original_price REAL,
                    discount_percent INTEGER,
                    url TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    telegram_message_id INTEGER,
                    end_time BIGINT,
                    is_active INTEGER DEFAULT 1,
                    image_url TEXT DEFAULT ''
                )
            """)
            cursor.execute("ALTER TABLE seen_deals ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT ''")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_pid ON seen_deals(product_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_title ON seen_deals(title)")
        else:
            _init_sqlite_schema(conn)

        defaults = [
            ("comments_enabled", "true"),
            ("check_interval", "10"),
            ("min_discount", str(Config.MIN_DISCOUNT_PERCENT)),
            ("max_deals_per_run", str(Config.MAX_DEALS_PER_RUN)),
            ("start_hour", "8"),
            ("end_hour", "22"),
            ("active_days", "todos"),
            ("repeat_days", "2"),
            ("bot_activated", "true"),
            ("super_deals_enabled", "true"),
            ("super_deal_min_discount", "60"),
        ]
        for key, value in defaults:
            if is_pg:
                cursor.execute(
                    "INSERT INTO bot_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (key, value)
                )
            else:
                cursor.execute(
                    "INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)",
                    (key, value)
                )

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    ph = _ph(conn)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT value FROM bot_settings WHERE key = {ph}", (key,))
        row = cursor.fetchone()
        return row[0] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str):
    conn = get_connection()
    is_pg = _is_pg(conn)
    try:
        cursor = conn.cursor()
        if is_pg:
            cursor.execute(
                "INSERT INTO bot_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, str(value))
            )
        else:
            cursor.execute(
                "INSERT INTO bot_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value))
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Deal deduplication
# ---------------------------------------------------------------------------

def is_deal_seen(product_id: str, title: str = "") -> bool:
    """
    Checks if a deal has been seen within the configured repeat_days window.
    1. Checks if the unique product_id was already sent within repeat_days.
    2. Checks if an identical title was already sent within repeat_days.
    """
    repeat_days = int(get_setting("repeat_days", "2"))
    conn = get_connection()
    ph = _ph(conn)
    cutoff = _db_ts(conn, datetime.now(timezone.utc) - timedelta(days=repeat_days))
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT 1 FROM seen_deals WHERE product_id = {ph} AND created_at >= {ph}",
            (product_id, cutoff)
        )
        if cursor.fetchone() is not None:
            return True

        if title:
            clean_title = title.strip().lower()
            cursor.execute(
                f"SELECT 1 FROM seen_deals WHERE LOWER(title) = {ph} AND created_at >= {ph}",
                (clean_title, cutoff)
            )
            if cursor.fetchone() is not None:
                return True

        return False
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Saving & retrieving deals
# ---------------------------------------------------------------------------

def save_deal(deal: dict, message_id: int = None):
    conn = get_connection()
    is_pg = _is_pg(conn)
    image_url = deal.get("image", "") or ""
    try:
        cursor = conn.cursor()
        if is_pg:
            cursor.execute("""
                INSERT INTO seen_deals (
                    product_id, platform, title, price, original_price, discount_percent, url,
                    telegram_message_id, end_time, is_active, image_url, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (product_id) DO UPDATE
                    SET price = EXCLUDED.price,
                        original_price = EXCLUDED.original_price,
                        discount_percent = EXCLUDED.discount_percent,
                        url = EXCLUDED.url,
                        image_url = EXCLUDED.image_url,
                        telegram_message_id = COALESCE(EXCLUDED.telegram_message_id, seen_deals.telegram_message_id),
                        end_time = EXCLUDED.end_time,
                        is_active = 1,
                        created_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (
                deal.get("id"),
                deal.get("platform"),
                deal.get("title", "").strip(),
                float(deal.get("current_price", 0.0)),
                float(deal.get("original_price", 0.0)),
                int(deal.get("discount_percent", 0)),
                deal.get("link"),
                message_id,
                int(deal.get("end_time", 0)),
                image_url,
            ))
            row = cursor.fetchone()
            deal_db_id = row[0] if row else None
        else:
            cursor.execute("""
                INSERT OR IGNORE INTO seen_deals (
                    product_id, platform, title, price, original_price, discount_percent, url,
                    telegram_message_id, end_time, is_active, image_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (
                deal.get("id"),
                deal.get("platform"),
                deal.get("title", "").strip(),
                float(deal.get("current_price", 0.0)),
                float(deal.get("original_price", 0.0)),
                int(deal.get("discount_percent", 0)),
                deal.get("link"),
                message_id,
                int(deal.get("end_time", 0)),
                image_url,
            ))
            cursor.execute("""
                UPDATE seen_deals
                SET price = ?,
                    original_price = ?,
                    discount_percent = ?,
                    url = ?,
                    image_url = ?,
                    telegram_message_id = COALESCE(?, telegram_message_id),
                    end_time = ?,
                    is_active = 1,
                    created_at = CURRENT_TIMESTAMP
                WHERE product_id = ?
            """, (
                float(deal.get("current_price", 0.0)),
                float(deal.get("original_price", 0.0)),
                int(deal.get("discount_percent", 0)),
                deal.get("link"),
                image_url,
                message_id,
                int(deal.get("end_time", 0)),
                deal.get("id"),
            ))
            cursor.execute("SELECT id FROM seen_deals WHERE product_id = ?", (deal.get("id"),))
            row = cursor.fetchone()
            deal_db_id = row[0] if row else None
        conn.commit()
        return deal_db_id
    except Exception as e:
        print(f"[DB Error] Error saving deal: {e}")
        return None
    finally:
        conn.close()


def delete_deal(product_id: str):
    conn = get_connection()
    ph = _ph(conn)
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM seen_deals WHERE product_id = {ph}", (product_id,))
        conn.commit()
    finally:
        conn.close()


def get_deal_for_redirect(deal_ref: str):
    """Fetches deal info by integer row id or product_id for OpenGraph preview & redirect."""
    conn = get_connection()
    is_pg = _is_pg(conn)
    ph = _ph(conn)
    try:
        cursor = conn.cursor()
        if str(deal_ref).isdigit():
            cursor.execute(
                f"SELECT id, product_id, platform, title, price, original_price, discount_percent, url, image_url FROM seen_deals WHERE id = {ph}",
                (int(deal_ref),)
            )
        else:
            cursor.execute(
                f"SELECT id, product_id, platform, title, price, original_price, discount_percent, url, image_url FROM seen_deals WHERE product_id = {ph}",
                (str(deal_ref),)
            )
        rows = _fetchall_as_dicts(cursor, is_pg)
        return rows[0] if rows else None
    except Exception as e:
        print(f"[DB Error] get_deal_for_redirect({deal_ref}): {e}")
        return None
    finally:
        conn.close()


def get_active_posted_deals():
    conn = get_connection()
    is_pg = _is_pg(conn)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_id, platform, telegram_message_id, end_time, title
            FROM seen_deals
            WHERE telegram_message_id IS NOT NULL AND is_active = 1
        """)
        return _fetchall_as_dicts(cursor, is_pg)
    finally:
        conn.close()


def mark_deal_inactive(product_id: str):
    conn = get_connection()
    ph = _ph(conn)
    try:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE seen_deals SET is_active = 0 WHERE product_id = {ph}", (product_id,))
        conn.commit()
    finally:
        conn.close()


def get_dagd_deals():
    """Returns all active deals that were posted with da.gd links."""
    conn = get_connection()
    is_pg = _is_pg(conn)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT product_id, telegram_message_id, url, title
            FROM seen_deals
            WHERE telegram_message_id IS NOT NULL 
              AND is_active = 1 
              AND url LIKE '%da.gd%'
        """)
        return _fetchall_as_dicts(cursor, is_pg)
    except Exception as e:
        print(f"[DB Error] get_dagd_deals: {e}")
        return []
    finally:
        conn.close()


def delete_dagd_deals():
    """Deletes deals with da.gd links from seen_deals so they can be re-scanned and re-posted."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM seen_deals WHERE url LIKE '%da.gd%'")
        conn.commit()
    except Exception as e:
        print(f"[DB Error] delete_dagd_deals: {e}")
    finally:
        conn.close()


def get_stats():
    conn = get_connection()
    ph = _ph(conn)
    today_start = _db_ts(conn, datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM seen_deals")
        total = cursor.fetchone()[0]

        cursor.execute(f"SELECT COUNT(*) FROM seen_deals WHERE created_at >= {ph}", (today_start,))
        today = cursor.fetchone()[0]

        cursor.execute("SELECT platform, COUNT(*) FROM seen_deals GROUP BY platform")
        by_platform = dict(cursor.fetchall())

        return {
            "total": total,
            "today": today,
            "by_platform": by_platform
        }
    finally:
        conn.close()


def cleanup_old_deals(days=None):
    if days is None:
        repeat_days = int(get_setting("repeat_days", "2"))
        # Retain deals for at least 90 days so shared WhatsApp redirect links remain valid
        days = max(repeat_days * 2, 90)

    conn = get_connection()
    ph = _ph(conn)
    cutoff = _db_ts(conn, datetime.now(timezone.utc) - timedelta(days=days))
    try:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM seen_deals WHERE created_at < {ph}", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


# Initialize database on import
init_db()
