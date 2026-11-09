import io
import html
import requests
from config import Config
from formatter import format_whatsapp_message, format_telegram_caption

class TelegramClient:
    def __init__(self, token: str = None):
        self.token = token or Config.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    def get_me(self) -> dict:
        """Tests token and retrieves bot profile info."""
        try:
            resp = requests.get(f"{self.api_url}/getMe", timeout=10)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", {})
            print(f"[Telegram] Erro em getMe: {data.get('description')}")
        except Exception as e:
            print(f"[Telegram] Falha de conexão: {e}")
        return {}

    def get_updates(self, offset: int = None) -> list:
        """Polls for new messages sent to the bot."""
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset

        try:
            resp = requests.get(f"{self.api_url}/getUpdates", params=params, timeout=25)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception as e:
            print(f"[Telegram] Erro ao obter updates: {e}")
        return []

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
        """Sends a plain text message to the specified chat."""
        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": False
                },
                timeout=12
            )
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] Erro ao enviar mensagem: {e}")
            return False

    def send_photo(self, chat_id: str, photo: str, caption: str = "", parse_mode: str = "HTML") -> bool:
        """Sends a photo using URL or direct upload."""
        # 1. Try sending by direct URL first
        try:
            resp = requests.post(
                f"{self.api_url}/sendPhoto",
                json={
                    "chat_id": chat_id,
                    "photo": photo,
                    "caption": caption,
                    "parse_mode": parse_mode
                },
                timeout=15
            )
            data = resp.json()
            if data.get("ok"):
                return True
        except Exception:
            pass

        # 2. If direct URL failed (e.g. CDN restrictions), download image and upload binary
        try:
            img_resp = requests.get(
                photo,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=10
            )
            if img_resp.status_code == 200:
                files = {"photo": ("image.jpg", io.BytesIO(img_resp.content), "image/jpeg")}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": parse_mode
                }
                upload_resp = requests.post(f"{self.api_url}/sendPhoto", data=data, files=files, timeout=20)
                if upload_resp.json().get("ok"):
                    return True
        except Exception as e:
            print(f"[Telegram] Erro ao carregar/enviar foto: {e}")

        # 3. Fallback: send as text message if photo completely fails
        return self.send_message(chat_id, caption, parse_mode=parse_mode)

    def send_deal(self, chat_id: str, deal: dict) -> bool:
        """
        Sends the complete deal card to Telegram:
        - Product Photo
        - Interactive block ready for 1-click copy into WhatsApp
        """
        wa_text = format_whatsapp_message(deal)
        tg_caption = format_telegram_caption(deal, wa_text)
        photo_url = deal.get("image", "")

        # Telegram photo caption limit is 1024 characters
        if len(tg_caption) <= 1024 and photo_url:
            return self.send_photo(chat_id, photo_url, caption=tg_caption, parse_mode="HTML")
        elif photo_url:
            # Send photo with short info, then send full copyable WhatsApp text
            platform = deal.get("platform", "Oferta")
            short_caption = f"🎯 <b>Nova Oferta: {platform}</b>\n{html.escape(deal.get('title', ''))}"
            self.send_photo(chat_id, photo_url, caption=short_caption[:1024], parse_mode="HTML")
            return self.send_message(
                chat_id,
                f"📋 <b>Toque abaixo para copiar para o WhatsApp:</b>\n\n<code>{html.escape(wa_text)}</code>",
                parse_mode="HTML"
            )
        else:
            # No photo available, send as message
            return self.send_message(chat_id, tg_caption, parse_mode="HTML")
