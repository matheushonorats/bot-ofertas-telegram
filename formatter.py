import html
import re
from comment_generator import get_relaxed_comment
from database import get_setting

DEFAULT_CTA_TEXT = "🛒 *Acesse e garanta a sua no link:*"
DEFAULT_FOOTER_TEXT = "⚠️ _Preço e estoque sujeitos a alteração a qualquer momento!_"
DEFAULT_CUSTOM_HEADER = "🔥 *{desconto}% OFF* • *{produto}*"

HEADER_STYLES = {
    "direct": "🔥 Desconto + Produto",
    "price_first": "💥 Produto + Preço",
    "alert": "🚨 Achadinho + Desconto",
    "custom": "✍️ Personalizado",
}


def _render_header_line(deal: dict, style: str, custom_header: str) -> str:
    """Renders the first notification line according to the selected style."""
    title = deal.get("title", "").strip()
    platform = deal.get("platform", "Promoção")
    curr_price = deal.get("current_price_str", "0,00")
    orig_price = deal.get("original_price_str", "") or curr_price
    discount = int(deal.get("discount_percent", 0) or 0)

    if style == "custom" and custom_header.strip():
        template = custom_header.strip()
        if discount <= 0:
            template = re.sub(
                r"\*?\{desconto\}\s*%?\s*(?:OFF)?\*?\s*[•:\-|]?\s*",
                "",
                template,
                flags=re.IGNORECASE,
            ).strip()
        tokens = {
            "desconto": str(discount),
            "produto": title,
            "preco": curr_price,
            "preco_de": orig_price,
            "loja": platform,
        }
        rendered = re.sub(
            r"\{(desconto|produto|preco|preco_de|loja)\}",
            lambda m: tokens[m.group(1)],
            template,
        ).strip()
        if rendered:
            return rendered

    if style == "price_first":
        if discount > 0:
            return f"💥 *{title}* por *R$ {curr_price}* ({discount}% OFF)"
        return f"💥 *{title}* por *R$ {curr_price}*"

    if style == "alert":
        if discount > 0:
            return f"🚨 *ACHADINHO {discount}% OFF:* *{title}*"
        return f"🚨 *ACHADINHO:* *{title}*"

    # Default ("direct"): discount + product first so lock-screen previews vary per deal
    if discount > 0:
        return f"🔥 *{discount}% OFF* • *{title}*"
    return f"🔥 *{title}*"


def format_whatsapp_message(deal: dict) -> str:
    """
    Formats a WhatsApp message leading directly with customizable product-first lines
    so mobile lock-screen notifications show the actual product instead of generic text.
    """
    platform = deal.get("platform", "Promoção")
    title = deal.get("title", "").strip()
    category = deal.get("category", "")
    curr_price = deal.get("current_price_str", "0,00")
    orig_price = deal.get("original_price_str", "")
    link = deal.get("link", "")

    comments_active = get_setting("comments_enabled", "true") == "true"
    comment = get_relaxed_comment(title, category, platform=platform) if comments_active else ""

    header_style = get_setting("msg_header_style", "direct")
    custom_header = get_setting("msg_custom_header", "")
    cta_text = get_setting("msg_cta_text", DEFAULT_CTA_TEXT).strip() or DEFAULT_CTA_TEXT
    show_platform = get_setting("msg_show_platform", "true") == "true"
    show_footer = get_setting("msg_show_footer", "true") == "true"
    show_coupon = get_setting("msg_show_coupon", "true") == "true"
    footer_text = get_setting("msg_footer_text", DEFAULT_FOOTER_TEXT).strip() or DEFAULT_FOOTER_TEXT

    detected_coupon = (deal.get("coupon") or "").strip()
    plat_low = platform.lower()
    if "mercado livre" in plat_low:
        store_coupon = get_setting("coupon_ml", "").strip()
    elif "shopee" in plat_low:
        store_coupon = get_setting("coupon_shopee", "").strip()
    else:
        store_coupon = ""

    first_line = _render_header_line(deal, header_style, custom_header)
    lines = [first_line]

    if comment:
        lines.append(f"_{comment}_")

    lines.append("")

    if orig_price and orig_price != curr_price:
        lines.append(f"❌ De: ~R$ {orig_price}~")

    price_line = f"✅ Por apenas: *R$ {curr_price}*"
    if show_platform:
        price_line += f" _({platform})_"
    lines.append(price_line)

    if show_coupon:
        if detected_coupon:
            if "com cupom" in detected_coupon.lower() or "na página" in detected_coupon.lower():
                lines.append(f"🎟️ *Cupom na página:* *{detected_coupon}* _(ative direto no link abaixo)_")
            else:
                lines.append(f"🎟️ *Cupom do produto:* *{detected_coupon}* _(aplique após abrir o link)_")
        if store_coupon:
            lines.append(f"🎟️ *Cupom {platform}:* *{store_coupon}* _(aplique no carrinho após abrir o link)_")

    lines.extend([
        "",
        cta_text,
        f"👉 {link}",
    ])

    if show_footer and footer_text:
        lines.extend(["", footer_text])

    return "\n".join(lines)

def format_telegram_caption(deal: dict, whatsapp_text: str) -> str:
    """
    Formats the message sent to Telegram.
    Leads with discount and product title for clear lock-screen previews,
    and places the WhatsApp text inside a <code> block for 1-tap copy.
    """
    platform = deal.get("platform", "Oferta")
    title = deal.get("title", "").strip()
    discount = deal.get("discount_percent", 0)
    disc_prefix = f"{discount}% OFF — " if discount else ""

    escaped_title = html.escape(title)
    escaped_platform = html.escape(platform)
    escaped_wa = html.escape(whatsapp_text)

    caption = (
        f"🔥 <b>{disc_prefix}{escaped_title}</b>\n"
        f"🏷️ <i>{escaped_platform}</i>\n\n"
        f"📋 <b>Toque no bloco abaixo para copiar para o WhatsApp:</b>\n\n"
        f"<code>{escaped_wa}</code>"
    )

    return caption
