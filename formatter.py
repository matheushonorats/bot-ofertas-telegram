import html
from comment_generator import get_relaxed_comment
from database import get_setting

def format_whatsapp_message(deal: dict) -> str:
    """
    Formats an ultra-engaging message ready to be copied and pasted directly into WhatsApp.
    Uses WhatsApp formatting (*bold*, ~strikethrough~, _italic_) and includes a relaxed,
    contextual 1-sentence comment about the product if enabled.
    """
    platform = deal.get("platform", "Promoção")
    title = deal.get("title", "")
    category = deal.get("category", "")
    curr_price = deal.get("current_price_str", "0,00")
    orig_price = deal.get("original_price_str", "")
    discount = deal.get("discount_percent", 0)
    link = deal.get("link", "")

    # Relaxed comment tailored to product (respects user panel toggle)
    comments_active = get_setting("comments_enabled", "true") == "true"
    comment = get_relaxed_comment(title, category) if comments_active else ""

    header = f"🔥 *SUPER OFERTA NA {platform.upper()}!* 🔥" if platform.lower() == "shopee" else f"🔥 *SUPER OFERTA NO {platform.upper()}!* 🔥"

    lines = [
        header,
        "",
        f"📦 *{title}*"
    ]

    if comment:
        lines.append(f"💬 _{comment}_")

    lines.append("")

    if orig_price and orig_price != curr_price:
        lines.append(f"❌ De: ~R$ {orig_price}~")

    lines.append(f"✅ Por apenas: *R$ {curr_price}*")

    if discount > 0:
        lines.append(f"💥 Desconto de: *{discount}% OFF*")

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
    Puts the WhatsApp text inside a <code> block so that tapping it in Telegram
    copies the text to clipboard instantly.
    """
    platform = deal.get("platform", "Oferta")
    discount = deal.get("discount_percent", 0)
    disc_text = f" ({discount}% OFF)" if discount else ""

    escaped_wa = html.escape(whatsapp_text)

    caption = (
        f"🎯 <b>Nova Oferta Detectada: {platform}{disc_text}</b>\n\n"
        f"📋 <b>Toque no bloco abaixo para copiar a mensagem do WhatsApp:</b>\n\n"
        f"<code>{escaped_wa}</code>"
    )

    return caption
