import html
from comment_generator import get_relaxed_comment
from database import get_setting

def format_whatsapp_message(deal: dict) -> str:
    """
    Formats a WhatsApp message leading directly with the discount and product title
    so mobile lock-screen notifications show the actual product instead of generic text.
    """
    platform = deal.get("platform", "Promoção")
    title = deal.get("title", "").strip()
    category = deal.get("category", "")
    curr_price = deal.get("current_price_str", "0,00")
    orig_price = deal.get("original_price_str", "")
    discount = deal.get("discount_percent", 0)
    link = deal.get("link", "")

    comments_active = get_setting("comments_enabled", "true") == "true"
    comment = get_relaxed_comment(title, category, platform=platform) if comments_active else ""

    if discount > 0:
        first_line = f"🔥 *{discount}% OFF* • *{title}*"
    else:
        first_line = f"🔥 *{title}*"

    lines = [first_line]

    if comment:
        lines.append(f"_{comment}_")

    lines.append("")

    if orig_price and orig_price != curr_price:
        lines.append(f"❌ De: ~R$ {orig_price}~")

    lines.append(f"✅ Por apenas: *R$ {curr_price}* _({platform})_")

    lines.extend([
        "",
        "🛒 *Acesse e garanta a sua no link:*",
        f"👉 {link}",
        "",
        "⚠️ _Preço e estoque sujeitos a alteração a qualquer momento!_"
    ])

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
