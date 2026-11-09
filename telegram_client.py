import io
import json
import html
import urllib.parse
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

    def set_my_commands(self, commands: list) -> bool:
        """Registers the official command menu in Telegram."""
        try:
            resp = requests.post(f"{self.api_url}/setMyCommands", json={"commands": commands}, timeout=10)
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] Erro ao registrar comandos: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = "", show_alert: bool = False) -> bool:
        """Acknowledges an inline button click and optionally shows a popup notification."""
        try:
            resp = requests.post(
                f"{self.api_url}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert},
                timeout=10
            )
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] Erro em answerCallbackQuery: {e}")
            return False

    def edit_message_text(self, chat_id: str, message_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> bool:
        """Edits an existing text message."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(f"{self.api_url}/editMessageText", json=payload, timeout=12)
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] Erro em editMessageText: {e}")
            return False

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

    def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Deletes a message from Telegram chat."""
        try:
            resp = requests.post(
                f"{self.api_url}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=10
            )
            return resp.json().get("ok", False)
        except Exception as e:
            print(f"[Telegram] Erro ao deletar mensagem {message_id}: {e}")
            return False

    def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML", reply_markup: dict = None):
        """Sends a plain text message to the specified chat with optional buttons. Returns message_id or None."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            resp = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=12)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", {}).get("message_id")
            # Auto-handle supergroup migration
            migrated_id = data.get("parameters", {}).get("migrate_to_chat_id")
            if migrated_id:
                print(f"[Telegram] Grupo migrado para supergrupo. Novo ID: {migrated_id}")
                Config.TELEGRAM_CHAT_ID = str(migrated_id)
                payload["chat_id"] = str(migrated_id)
                retry_resp = requests.post(f"{self.api_url}/sendMessage", json=payload, timeout=12)
                retry_data = retry_resp.json()
                if retry_data.get("ok"):
                    return retry_data.get("result", {}).get("message_id")
            return None
        except Exception as e:
            print(f"[Telegram] Erro ao enviar mensagem: {e}")
            return None

    def send_photo(self, chat_id: str, photo: str, caption: str = "", parse_mode: str = "HTML", reply_markup: dict = None):
        """Sends a photo using URL or direct upload with optional buttons. Returns message_id or None."""
        # 1. Try sending by direct URL first
        try:
            payload = {
                "chat_id": chat_id,
                "photo": photo,
                "caption": caption,
                "parse_mode": parse_mode
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            resp = requests.post(f"{self.api_url}/sendPhoto", json=payload, timeout=15)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", {}).get("message_id")
            migrated_id = data.get("parameters", {}).get("migrate_to_chat_id")
            if migrated_id:
                Config.TELEGRAM_CHAT_ID = str(migrated_id)
                payload["chat_id"] = str(migrated_id)
                retry_resp = requests.post(f"{self.api_url}/sendPhoto", json=payload, timeout=15)
                retry_data = retry_resp.json()
                if retry_data.get("ok"):
                    return retry_data.get("result", {}).get("message_id")
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
                    "chat_id": Config.TELEGRAM_CHAT_ID or chat_id,
                    "caption": caption,
                    "parse_mode": parse_mode
                }
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)

                upload_resp = requests.post(f"{self.api_url}/sendPhoto", data=data, files=files, timeout=20)
                upload_data = upload_resp.json()
                if upload_data.get("ok"):
                    return upload_data.get("result", {}).get("message_id")
        except Exception as e:
            print(f"[Telegram] Erro ao carregar/enviar foto: {e}")

        # 3. Fallback: send as text message if photo completely fails
        return self.send_message(Config.TELEGRAM_CHAT_ID or chat_id, caption, parse_mode=parse_mode, reply_markup=reply_markup)

    def send_deal(self, chat_id: str, deal: dict) -> bool:
        """
        Sends the complete deal card to Telegram:
        - Product Photo
        - Interactive block ready for 1-click copy into WhatsApp
        - Instant 1-click [📲 Compartilhar no WhatsApp] button
        """
        target_chat = Config.TELEGRAM_CHAT_ID or chat_id
        wa_text = format_whatsapp_message(deal)
        tg_caption = format_telegram_caption(deal, wa_text)
        photo_url = deal.get("image", "")

        # Create 1-click WhatsApp share button
        wa_share_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_text)}"
        reply_markup = {
            "inline_keyboard": [
                [{"text": "📲 Compartilhar no WhatsApp", "url": wa_share_url}]
            ]
        }

        # Telegram photo caption limit is 1024 characters
        if len(tg_caption) <= 1024 and photo_url:
            return self.send_photo(target_chat, photo_url, caption=tg_caption, parse_mode="HTML", reply_markup=reply_markup)
        elif photo_url:
            # Send photo with short info, then send full copyable WhatsApp text with share button
            platform = deal.get("platform", "Oferta")
            short_caption = f"🎯 <b>Nova Oferta: {platform}</b>\n{html.escape(deal.get('title', ''))}"
            self.send_photo(target_chat, photo_url, caption=short_caption[:1024], parse_mode="HTML")
            return self.send_message(
                target_chat,
                f"📋 <b>Toque abaixo para copiar para o WhatsApp:</b>\n\n<code>{html.escape(wa_text)}</code>",
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            # No photo available, send as message with button
            return self.send_message(target_chat, tg_caption, parse_mode="HTML", reply_markup=reply_markup)
