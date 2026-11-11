import html
import os
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from database import get_deal_for_redirect

PREVIEW_BOT_TOKENS = (
    "whatsapp",
    "facebookexternalhit",
    "facebot",
    "telegrambot",
    "twitterbot",
    "discordbot",
    "slackbot",
    "linkedinbot",
    "pinterest",
    "applebot",
    "googlebot",
    "bingbot",
    "embedly",
    "skypeuripreview",
    "iframely",
    "vkshare",
)


def _format_brl(value) -> str:
    try:
        v = float(value or 0)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return ""


def _build_og_html(deal: dict, request_url: str) -> bytes:
    title = (deal.get("title") or "Oferta Imperdível").strip()
    platform = (deal.get("platform") or "Loja Oficial").strip()
    discount = int(deal.get("discount_percent") or 0)
    price = float(deal.get("price") or 0)
    orig_price = float(deal.get("original_price") or 0)
    image_url = (deal.get("image_url") or "").strip()
    target_url = (deal.get("url") or "").strip()

    if image_url.endswith(".webp") and "mlstatic.com" in image_url:
        image_url = image_url[:-5] + ".jpg"

    og_title = f"🔥 {discount}% OFF • {title}" if discount > 0 else f"🔥 {title}"

    desc_parts = []
    if price > 0:
        desc_parts.append(f"Por apenas {_format_brl(price)}")
    if orig_price > price > 0:
        desc_parts.append(f"(De {_format_brl(orig_price)})")
    desc_parts.append(f"em {platform}")
    og_desc = " ".join(desc_parts)

    esc_title = html.escape(og_title)
    esc_desc = html.escape(og_desc)
    esc_img = html.escape(image_url)
    esc_req_url = html.escape(request_url)
    esc_target = html.escape(target_url)

    image_tags = ""
    if esc_img:
        image_tags = (
            f'<meta property="og:image" content="{esc_img}">\n'
            f'  <meta property="og:image:secure_url" content="{esc_img}">\n'
            f'  <meta property="og:image:type" content="image/jpeg">\n'
            f'  <meta name="twitter:image" content="{esc_img}">\n'
        )

    doc = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>{esc_title}</title>
  <meta name="robots" content="noindex, nofollow">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="{html.escape(platform)}">
  <meta property="og:title" content="{esc_title}">
  <meta property="og:description" content="{esc_desc}">
  <meta property="og:url" content="{esc_req_url}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc_title}">
  <meta name="twitter:description" content="{esc_desc}">
  {image_tags}</head>
<body style="font-family:sans-serif;text-align:center;padding:32px;">
  <h2>{esc_title}</h2>
  <p>{esc_desc}</p>
  <p><a href="{esc_target}" style="display:inline-block;padding:12px 24px;background:#00a650;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold;">Abrir Oferta Agora</a></p>
</body>
</html>"""
    return doc.encode("utf-8")


class HealthHandler(BaseHTTPRequestHandler):
    def _is_preview_bot(self) -> bool:
        ua = (self.headers.get("User-Agent") or "").lower()
        return any(token in ua for token in PREVIEW_BOT_TOKENS)

    def _send_bytes(self, status: int, content_type: str, body: bytes, head_only: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if not head_only and body:
            self.wfile.write(body)

    def _handle_offer(self, deal_ref: str, head_only: bool = False):
        deal = get_deal_for_redirect(deal_ref)
        if not deal or not deal.get("url"):
            msg = "Oferta indisponivel ou expirada.".encode("utf-8")
            self._send_bytes(404, "text/plain; charset=utf-8", msg, head_only=head_only)
            return

        if self._is_preview_bot():
            host = self.headers.get("Host") or "bot-ofertas-telegram-8ysw.onrender.com"
            req_url = f"https://{host}/o/{deal_ref}"
            html_bytes = _build_og_html(deal, req_url)
            self._send_bytes(200, "text/html; charset=utf-8", html_bytes, head_only=head_only)
            return

        target_url = deal["url"]
        self.send_response(302)
        self.send_header("Location", target_url)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_HEAD(self):
        path = self.path.split("?")[0]
        if path.startswith("/o/") and len(path) > 3:
            self._handle_offer(path[3:].strip("/"), head_only=True)
            return
        self._send_bytes(200, "text/plain; charset=utf-8", b"OK", head_only=True)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith("/o/") and len(path) > 3:
            self._handle_offer(path[3:].strip("/"), head_only=False)
            return
        self._send_bytes(200, "text/plain; charset=utf-8", b"OK", head_only=False)

    def log_message(self, format, *args):
        # Mute http access logs to avoid clutter
        return


def start_health_server(port=None):
    if port is None:
        port = int(os.environ.get("PORT", "0"))

    if port <= 0:
        return

    try:
        server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"[Web Server] Servidor ativo na porta {port} (Keep-alive + Prévias WhatsApp)")
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
    except Exception as e:
        print(f"[Web Server] Erro ao iniciar servidor web: {e}")
