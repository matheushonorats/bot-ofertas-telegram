import sqlite3
from datetime import datetime, timedelta
from config import Config

def get_connection():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
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
        # Index on product_id and title for ultra fast duplicate checks
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_pid ON seen_deals(product_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_seen_deals_title ON seen_deals(title)")
        conn.commit()

def is_deal_seen(product_id: str, title: str = "") -> bool:
    """
    Double protection against duplicates:
    1. Checks if the unique product_id was already sent.
    2. Checks if an identical title was already sent in the last 48 hours.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # Check by product ID
        cursor.execute("SELECT 1 FROM seen_deals WHERE product_id = ?", (product_id,))
        if cursor.fetchone() is not None:
            return True

        # Check by Title (prevents re-listings of the same item)
        if title:
            clean_title = title.strip()
            cursor.execute("""
                SELECT 1 FROM seen_deals 
                WHERE title = ? AND created_at >= datetime('now', '-2 days')
            """, (clean_title,))
            if cursor.fetchone() is not None:
                return True

        return False

def save_deal(deal: dict):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO seen_deals (
                    product_id, platform, title, price, original_price, discount_percent, url
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                deal.get("id"),
                deal.get("platform"),
                deal.get("title", "").strip(),
                float(deal.get("current_price", 0.0)),
                float(deal.get("original_price", 0.0)),
                int(deal.get("discount_percent", 0)),
                deal.get("link")
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"[DB Error] Error saving deal: {e}")
            return False

def get_stats():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM seen_deals")
        total = cursor.fetchone()[0]

        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        cursor.execute("SELECT COUNT(*) FROM seen_deals WHERE created_at >= ?", (today_start,))
        today = cursor.fetchone()[0]

        cursor.execute("SELECT platform, COUNT(*) FROM seen_deals GROUP BY platform")
        by_platform = dict(cursor.fetchall())

        return {
            "total": total,
            "today": today,
            "by_platform": by_platform
        }

def cleanup_old_deals(days=7):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM seen_deals WHERE created_at < ?", (cutoff,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted

# Initialize database on import
init_db()
