import os
from pathlib import Path

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

def load_dotenv(dotenv_path=None):
    """Simple built-in .env parser to avoid strict dependency on python-dotenv."""
    if dotenv_path is None:
        dotenv_path = BASE_DIR / ".env"
    else:
        dotenv_path = Path(dotenv_path)

    if not dotenv_path.is_file():
        return

    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val

# Load .env
load_dotenv()

class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    # Bot execution intervals & limits
    CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
    MIN_DISCOUNT_PERCENT = int(os.getenv("MIN_DISCOUNT_PERCENT", "15"))
    MAX_DEALS_PER_RUN = int(os.getenv("MAX_DEALS_PER_RUN", "5"))

    # Mercado Livre Affiliate Settings
    ML_AFFILIATE_TAG = os.getenv("ML_AFFILIATE_TAG", "").strip()
    ML_AFFILIATE_URL_TEMPLATE = os.getenv("ML_AFFILIATE_URL_TEMPLATE", "").strip()
    ML_CATEGORIES = [
        c.strip() for c in os.getenv(
            "ML_CATEGORIES",
            "tecnologia,eletrodomesticos,casa-e-decoracao,beleza-e-cuidado-pessoal,ferramentas,mais-vendidos"
        ).split(",") if c.strip()
    ]

    # Shopee Affiliate Settings
    SHOPEE_APP_ID = os.getenv("SHOPEE_APP_ID", "").strip()
    SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET", "").strip()
    SHOPEE_AFFILIATE_TAG = os.getenv("SHOPEE_AFFILIATE_TAG", "sub_id=telegram").strip()
    SHOPEE_UNIVERSAL_LINK = os.getenv("SHOPEE_UNIVERSAL_LINK", "").strip()

    # AI (Gemini) for custom contextual product phrases
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

    # Public web server URL (used for WhatsApp rich image link previews + redirect)
    # Render automatically populates RENDER_EXTERNAL_URL
    PUBLIC_BASE_URL = (
        os.getenv("PUBLIC_BASE_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
    ).rstrip("/")

    # Database
    DB_PATH = BASE_DIR / "deals.db"

    @classmethod
    def validate_telegram(cls):
        return bool(cls.TELEGRAM_BOT_TOKEN and cls.TELEGRAM_CHAT_ID)
