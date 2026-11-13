import sys
import html
import time
import threading
import argparse
import requests
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 output in Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import Config
from database import (
    save_deal, delete_deal, get_stats, cleanup_old_deals, get_setting, set_setting,
    get_active_posted_deals, mark_deal_inactive, is_deal_seen,
    get_dagd_deals, delete_dagd_deals
)
from scraper_ml import fetch_mercadolivre_deals
from scraper_shopee import fetch_shopee_deals
from affiliate import shorten_url
from telegram_client import TelegramClient
from formatter import (
    format_whatsapp_message, HEADER_STYLES,
    DEFAULT_CTA_TEXT, DEFAULT_FOOTER_TEXT
)
from web_server import start_health_server

# Prevents concurrent scans (e.g. timer + /ofertas button) from overlapping
_scanner_lock = threading.Lock()
_start_with_ml = True

def is_within_schedule() -> tuple:
    """
    Checks if current time in Brazil (Brasilia UTC-3) matches the configured schedule.
    Returns (is_allowed: bool, reason: str).
    """
    br_tz = timezone(timedelta(hours=-3))
    now_br = datetime.now(br_tz)

    active_days = get_setting("active_days", "todos")
    weekday = now_br.weekday()  # 0=Monday, ..., 5=Saturday, 6=Sunday

    if active_days == "seg-sex" and weekday >= 5:
        return False, "Bot configurado para funcionar apenas de Segunda a Sexta."
    if active_days == "seg-sab" and weekday == 6:
        return False, "Bot configurado para funcionar de Segunda a Sábado (domingo pausado)."

    start_hour = int(get_setting("start_hour", "8"))
    end_hour = int(get_setting("end_hour", "22"))

    if start_hour == 0 and end_hour == 24:
        return True, "24 horas ativo"

    current_hour = now_br.hour
    if not (start_hour <= current_hour < end_hour):
        return False, f"Fora do horário ({start_hour:02d}h às {end_hour:02d}h - Horário atual em Brasília: {current_hour:02d}h{now_br.minute:02d})"

    return True, "Dentro do horário"

SAMPLE_PREVIEW_DEAL = {
    "platform": "Shopee",
    "title": "Fone Bluetooth Sem Fio TWS Pro",
    "category": "Eletrônicos",
    "original_price_str": "149,90",
    "current_price_str": "69,90",
    "discount_percent": 53,
    "coupon": "15% OFF com Cupom",
    "link": "https://s.shopee.com.br/exemplo",
}

_MSG_FIELD_PROMPTS = {
    "topo": (
        "✏️ <b>Para personalizar o Topo da mensagem</b>, responda ESTA mensagem com o novo texto.\n\n"
        "📌 <b>Variáveis disponíveis:</b>\n"
        "• <code>{desconto}</code> — percentual (ex: 53)\n"
        "• <code>{produto}</code> — nome do produto\n"
        "• <code>{preco}</code> — preço atual (ex: 69,90)\n"
        "• <code>{preco_de}</code> — preço antigo\n"
        "• <code>{loja}</code> — Shopee ou Mercado Livre\n\n"
        "💡 Exemplo: <code>💥 {desconto}% OFF: {produto} por R$ {preco}</code>\n"
        "↩️ Envie <code>padrao</code> para voltar ao padrão ou <code>cancelar</code> para cancelar."
    ),
    "cta": (
        "📣 <b>Para personalizar a Chamada do link (CTA)</b>, responda ESTA mensagem com o novo texto.\n\n"
        "💡 Exemplo: <code>👇 Aproveite antes que acabe:</code>\n"
        "↩️ Envie <code>padrao</code> para restaurar o padrão ou <code>cancelar</code> para cancelar."
    ),
    "footer": (
        "📝 <b>Para personalizar o Rodapé</b>, responda ESTA mensagem com o novo texto.\n\n"
        "💡 Exemplo: <code>⚡ Estoque limitado! Corre garantir!</code>\n"
        "↩️ Envie <code>padrao</code> para restaurar o padrão ou <code>cancelar</code> para cancelar."
    ),
    "cupom_shopee": (
        "🎟️ <b>Para definir um Cupom fixo da Shopee</b> (opcional), responda ESTA mensagem com o código/descrição.\n\n"
        "💡 Exemplo: <code>SHOPEE10 (10% OFF acima de R$ 50)</code>\n"
        "⚠️ <i>Use apenas cupons oficiais da Shopee ou seu cupom próprio da Central de Afiliados — cupons exclusivos de terceiros podem tirar sua comissão!</i>\n"
        "↩️ Envie <code>limpar</code> para remover ou <code>cancelar</code> para cancelar."
    ),
    "cupom_ml": (
        "🎟️ <b>Para definir um Cupom fixo do Mercado Livre</b> (opcional), responda ESTA mensagem com o código/descrição.\n\n"
        "💡 Exemplo: <code>MELI10 (10% OFF na loja)</code>\n"
        "⚠️ <i>Use apenas cupons oficiais do Mercado Livre ou seu cupom próprio da Central de Afiliados — cupons exclusivos de outro divulgador podem tirar sua comissão!</i>\n"
        "↩️ Envie <code>limpar</code> para remover ou <code>cancelar</code> para cancelar."
    ),
}


def _apply_msg_field_update(field: str, raw_value: str) -> str:
    """Applies a message template field update and returns confirmation HTML."""
    val = raw_value.strip()
    is_reset = val.lower() in ("padrao", "padrão", "default", "reset", "limpar", "nenhum", "remover", "off", "-")

    if field == "topo":
        if is_reset or not val:
            set_setting("msg_custom_header", "")
            set_setting("msg_header_style", "direct")
            return "✅ Topo restaurado para o padrão (🔥 Desconto + Produto)."
        set_setting("msg_custom_header", val)
        set_setting("msg_header_style", "custom")
        return f"✅ Topo personalizado salvo:\n<code>{html.escape(val)}</code>"

    if field == "cta":
        new_cta = DEFAULT_CTA_TEXT if (is_reset or not val) else val
        set_setting("msg_cta_text", new_cta)
        return f"✅ Chamada do link atualizada:\n<code>{html.escape(new_cta)}</code>"

    if field == "footer":
        new_footer = DEFAULT_FOOTER_TEXT if (is_reset or not val) else val
        set_setting("msg_footer_text", new_footer)
        set_setting("msg_show_footer", "true")
        return f"✅ Rodapé atualizado:\n<code>{html.escape(new_footer)}</code>"

    if field in ("cupom_shopee", "cupom_ml"):
        key = "coupon_shopee" if field == "cupom_shopee" else "coupon_ml"
        store = "Shopee" if field == "cupom_shopee" else "Mercado Livre"
        if is_reset or not val:
            set_setting(key, "")
            return f"✅ Cupom fixo da {store} removido (cupons automáticos por produto continuam ativos se ligados)."
        set_setting(key, val)
        set_setting("msg_show_coupon", "true")
        return f"✅ Cupom fixo da {store} ativado:\n<code>{html.escape(val)}</code>"

    return "⚠️ Campo de mensagem desconhecido."


def build_msg_panel_data():
    """Builds text and inline keyboard for WhatsApp message customization."""
    header_style = get_setting("msg_header_style", "direct")
    style_label = HEADER_STYLES.get(header_style, HEADER_STYLES["direct"])
    show_platform = get_setting("msg_show_platform", "true") == "true"
    show_footer = get_setting("msg_show_footer", "true") == "true"
    show_coupon = get_setting("msg_show_coupon", "true") == "true"
    custom_header = get_setting("msg_custom_header", "").strip()
    cta_text = get_setting("msg_cta_text", DEFAULT_CTA_TEXT).strip() or DEFAULT_CTA_TEXT
    cupom_shopee = get_setting("coupon_shopee", "").strip()
    cupom_ml = get_setting("coupon_ml", "").strip()

    preview = format_whatsapp_message(SAMPLE_PREVIEW_DEAL)
    plat_icon = "✅" if show_platform else "❌"
    foot_icon = "✅" if show_footer else "❌"
    coupon_icon = "✅" if show_coupon else "❌"
    topo_info = custom_header if (header_style == "custom" and custom_header) else style_label

    coupon_parts = []
    if cupom_shopee:
        coupon_parts.append(f"Shopee={cupom_shopee}")
    if cupom_ml:
        coupon_parts.append(f"ML={cupom_ml}")
    coupon_summary = ("Auto + " + ", ".join(coupon_parts)) if coupon_parts else ("Automático (se houver)" if show_coupon else "Oculto")

    text = (
        "✏️ <b>Personalizar Mensagens do WhatsApp</b>\n\n"
        "<i>A 1ª linha prioriza o produto para cada notificação no celular ficar única:</i>\n\n"
        f"🎨 <b>Topo:</b> <code>{html.escape(topo_info)}</code>\n"
        f"📣 <b>Chamada (CTA):</b> <code>{html.escape(cta_text)}</code>\n"
        f"🏪 <b>Mostrar Loja:</b> <code>{'Sim' if show_platform else 'Não'}</code>  |  "
        f"📝 <b>Rodapé:</b> <code>{'Ativado' if show_footer else 'Desativado'}</code>\n"
        f"🎟️ <b>Cupons:</b> <code>{html.escape(coupon_summary)}</code>\n\n"
        "👀 <b>Pré-via de como vai chegar:</b>\n"
        f"<pre>{html.escape(preview)}</pre>\n"
        "💡 <i>Atalhos:</i> <code>/topo</code>, <code>/cta</code>, <code>/rodape</code>, <code>/cupomshopee</code>, <code>/cupomml</code>."
    )

    keyboard = {
        "inline_keyboard": [
            [{"text": f"🎨 Estilo do Topo: {style_label}", "callback_data": "cycle_msg_header"}],
            [
                {"text": f"🏪 Loja: {plat_icon}", "callback_data": "toggle_msg_platform"},
                {"text": f"📝 Rodapé: {foot_icon}", "callback_data": "toggle_msg_footer"},
                {"text": f"🎟️ Cupons: {coupon_icon}", "callback_data": "toggle_msg_coupon"},
            ],
            [{"text": "✍️ Escrever Topo Personalizado", "callback_data": "prompt_msg_topo"}],
            [
                {"text": "📣 Editar Chamada", "callback_data": "prompt_msg_cta"},
                {"text": "📝 Editar Rodapé", "callback_data": "prompt_msg_footer"},
            ],
            [
                {"text": "🎟️ Cupom Shopee", "callback_data": "prompt_msg_cupom_shopee"},
                {"text": "🎟️ Cupom ML", "callback_data": "prompt_msg_cupom_ml"},
            ],
            [{"text": "🔄 Restaurar Padrão", "callback_data": "reset_msg_template"}],
            [{"text": "⬅️ Voltar ao Painel", "callback_data": "back_to_main_panel"}],
        ]
    }
    return text, keyboard


def build_panel_data():
    """Builds text and inline keyboard for the interactive settings panel."""
    comments_active = get_setting("comments_enabled", "true") == "true"
    interval = get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES))
    min_disc = get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT))
    max_deals = get_setting("max_deals_per_run", str(Config.MAX_DEALS_PER_RUN))
    start_hour = int(get_setting("start_hour", "8"))
    end_hour = int(get_setting("end_hour", "22"))
    active_days = get_setting("active_days", "todos")
    repeat_days = get_setting("repeat_days", "2")
    header_style = get_setting("msg_header_style", "direct")
    style_label = HEADER_STYLES.get(header_style, HEADER_STYLES["direct"])

    if start_hour == 0 and end_hour == 24:
        hours_str = "24h (Sem pausa)"
    else:
        hours_str = f"{start_hour:02d}h às {end_hour:02d}h"

    days_map = {
        "todos": "Todos os dias",
        "seg-sex": "Segunda a Sexta",
        "seg-sab": "Segunda a Sábado"
    }
    days_str = days_map.get(active_days, "Todos os dias")

    repeat_map = {
        "2": "Após 2 dias",
        "3": "Após 3 dias",
        "7": "Após 7 dias",
        "30": "Nunca (30d)"
    }
    repeat_str = repeat_map.get(repeat_days, "Após 2 dias")

    status_str = "✅ ATIVADAS" if comments_active else "❌ DESATIVADAS"
    toggle_label = "💬 Frases: DESATIVAR" if comments_active else "💬 Frases: ATIVAR"
    deals_label = "1 oferta" if max_deals == "1" else f"{max_deals} ofertas"

    text = (
        "⚙️ <b>Painel de Opções do Bot de Ofertas</b>\n\n"
        "<i>Toque nos botões abaixo para personalizar o comportamento do bot:</i>\n\n"
        f"💬 <b>Frases nos Produtos:</b> <code>{status_str}</code>\n"
        f"✏️ <b>Estilo da Mensagem:</b> <code>{html.escape(style_label)}</code>\n"
        f"⏰ <b>Horário de Funcionamento:</b> <code>{hours_str}</code>\n"
        f"📅 <b>Dias de Envio:</b> <code>{days_str}</code>\n"
        f"🔄 <b>Repetir Produtos:</b> <code>{repeat_str}</code>\n"
        f"⏱️ <b>Intervalo Automático:</b> <code>A cada {interval} min</code>\n"
        f"🏷️ <b>Desconto Mínimo:</b> <code>{min_disc}% OFF</code>\n"
        f"📨 <b>Ofertas por Vez:</b> <code>{deals_label}</code>\n"
        f"🛍️ <b>Plataformas:</b> <code>Shopee & Mercado Livre (Afiliada Bianca)</code>\n"
    )

    keyboard = {
        "inline_keyboard": [
            [{"text": toggle_label, "callback_data": "toggle_comments"}],
            [
                {"text": f"⏰ Horário: {hours_str}", "callback_data": "cycle_hours"},
                {"text": f"📅 Dias: {days_str}", "callback_data": "cycle_days"}
            ],
            [{"text": f"🔄 Repetir: {repeat_str}", "callback_data": "cycle_repeat"}],
            [
                {"text": f"⏱️ A cada: {interval}m", "callback_data": "cycle_interval"},
                {"text": f"🏷️ Mínimo: {min_disc}%", "callback_data": "cycle_discount"}
            ],
            [{"text": f"📨 Por vez: {deals_label}", "callback_data": "cycle_max_deals"}],
            [{"text": "✏️ Personalizar Mensagens", "callback_data": "open_msg_panel"}],
            [{"text": "🔎 Buscar Novas Ofertas Agora", "callback_data": "trigger_deals"}]
        ]
    }
    return text, keyboard

def get_bianca_presentation() -> tuple:
    """Returns the personalized presentation message and activation button for Bianca."""
    text = (
        "👋 <b>Oi Bianca! Prazer em te conhecer!</b>\n\n"
        "Eu sou o seu <b>Assistente de Ofertas da Shopee</b>, criado exclusivamente para facilitar a sua vida "
        "e abastecer o seu grupo de WhatsApp com as melhores promoções todos os dias! 🛍️✨\n\n"
        "Aqui está um resumo bem simples de como eu vou te ajudar a lucrar:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>1. Como eu trabalho por você</b>\n"
        "• Eu fico vigiando a Shopee o dia todo buscando apenas <b>super descontos reais</b> e fotos bonitas.\n"
        "• <b>Seu link já embutido:</b> Todas as ofertas já saem com o seu código de afiliada (<code>an_18345610975</code>). Você ganha comissão em cada venda!\n"
        "• <b>Auto-limpeza inteligente:</b> Se a promoção acabar ou o produto esgotar na Shopee, eu apago a mensagem aqui do Telegram sozinho para você nunca mandar link vencido no WhatsApp!\n"
        "• <b>Respeito ao seu sono:</b> Trabalho apenas das <b>08h às 22h</b> para não te incomodar de madrugada.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 <b>2. Como enviar no WhatsApp (2 formas bem fáceis):</b>\n\n"
        "👉 <b>Opção A (Mais rápida - 1 Toque):</b>\n"
        "Abaixo de cada oferta, toque no botão azul <b>[ 📲 Compartilhar no WhatsApp ]</b>. "
        "O WhatsApp abre direto com a mensagem, preços e o seu link prontinhos. Ao enviar, o WhatsApp carrega a foto de capa na prévia do link automaticamente!\n\n"
        "👉 <b>Opção B (Para enviar com a foto grande):</b>\n"
        "Se quiser que a foto vá bem grandona:\n"
        "1. Toque na <b>foto do produto</b> aqui no Telegram.\n"
        "2. Toque no ícone de <b>Compartilhar</b> (a setinha) e escolha o WhatsApp.\n"
        "3. A foto vai em alta resolução e o texto vai junto na legenda!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ <b>3. Seu Painel de Opções (/painel)</b>\n"
        "Você tem controle total! A qualquer momento digite <b>/painel</b> para ligar/desligar frases, "
        "alterar horários ou dias de envio.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Estou pronto! Para dar a largada oficial e receber as primeiras ofertas, toque no botão abaixo:</b>"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Iniciar Trabalhos Oficialmente", "callback_data": "start_bot_official"}]
        ]
    }
    return text, keyboard

def setup_commands(telegram: TelegramClient):
    """Registers official command buttons in Telegram menu."""
    commands = [
        {"command": "ofertas", "description": "🔎 Buscar ofertas relâmpago na Shopee agora"},
        {"command": "refazer", "description": "🧹 Apagar ofertas antigas e enviar novas com link oficial"},
        {"command": "painel", "description": "⚙️ Painel de opções (ativar/desativar frases e filtros)"},
        {"command": "status", "description": "📊 Ver quantas ofertas foram enviadas hoje"},
        {"command": "ajuda", "description": "❓ Como compartilhar no WhatsApp"}
    ]
    telegram.set_my_commands(commands)

def run_dry_run_test():
    """Performs a test run without requiring Telegram credentials."""
    print("=" * 60)
    print(" 🚀 INICIANDO TESTE DO BOT DE OFERTAS (DRY RUN)")
    print("=" * 60)

    print("\n🔍 1. Buscando ofertas no Shopee...")
    shopee_deals = fetch_shopee_deals(limit=5)
    print(f"-> Encontradas {len(shopee_deals)} ofertas na Shopee com desconto >= {Config.MIN_DISCOUNT_PERCENT}%")

    print("\n🔍 2. Buscando ofertas no Mercado Livre...")
    if Config.ML_AFFILIATE_TAG:
        ml_deals = fetch_mercadolivre_deals(limit_per_category=2)
        print(f"-> Encontradas {len(ml_deals)} ofertas no Mercado Livre com desconto >= {Config.MIN_DISCOUNT_PERCENT}%")
    else:
        ml_deals = []
        print("-> Mercado Livre desativado (aguardando ML_AFFILIATE_TAG no .env)")

    all_deals = shopee_deals + ml_deals
    if not all_deals:
        print("\n⚠️ Nenhuma oferta encontrada com os filtros atuais.")
        return

    print("\n" + "=" * 60)
    print(" 📱 EXEMPLO DE MENSAGEM PRONTA PARA O WHATSAPP:")
    print("=" * 60)

    sample = all_deals[0]
    sample["link"] = shorten_url(sample.get("link", ""))
    wa_msg = format_whatsapp_message(sample)
    print(wa_msg)

    print("\n" + "=" * 60)
    print(f"🖼️ Foto do produto: {sample.get('image')}")
    print(f"🔗 Link associado: {sample.get('link')}")
    print("=" * 60)
    print("✅ Teste concluído com sucesso!")

def check_and_remove_expired_deals(telegram: TelegramClient):
    """
    Checks active deals posted in the Telegram group.
    If the promotion has expired (time > end_time) or is out of stock,
    automatically deletes the message from Telegram so Bianca only sees valid promotions.
    """
    target_chat = Config.TELEGRAM_CHAT_ID
    if not target_chat:
        return

    active_deals = get_active_posted_deals()
    if not active_deals:
        return

    current_ts = int(time.time())

    # Fetch current flash items to check stock
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://shopee.com.br/flash_sale",
        "Accept": "application/json"
    }
    flash_stocks = {}
    try:
        resp = requests.get("https://shopee.com.br/api/v4/flash_sale/flash_sale_get_items?limit=100&offset=0", headers=headers, timeout=10)
        if resp.status_code == 200:
            for item in resp.json().get("data", {}).get("items", []):
                item_key = f"shopee_{item.get('shopid')}_{item.get('itemid')}"
                flash_stocks[item_key] = {
                    "stock": item.get("stock", 0),
                    "end_time": item.get("end_time", 0)
                }
    except Exception as e:
        print(f"[Auto-Remoção] Aviso ao checar estoque Shopee: {e}")

    for deal in active_deals:
        msg_id = deal.get("telegram_message_id")
        end_time = deal.get("end_time", 0)
        pid = deal.get("product_id")

        if not msg_id:
            continue

        should_delete = False
        reason = ""

        # 1. Checa se o horário da promoção expirou
        if end_time and current_ts >= end_time:
            should_delete = True
            reason = "Promoção expirou"

        # 2. Se o produto estava no Flash Sale e o estoque zerou
        if pid in flash_stocks and flash_stocks[pid]["stock"] <= 0:
            should_delete = True
            reason = "Estoque esgotado"

        if should_delete:
            print(f"[Auto-Remoção] 🗑️ Apagando do Telegram ({reason}): {deal.get('title', '')[:35]}...")
            telegram.delete_message(target_chat, msg_id)
            mark_deal_inactive(pid)

def cleanup_and_repost_dagd_deals(telegram: TelegramClient, chat_id: str = None) -> tuple:
    """
    Deletes any previously posted Telegram messages containing da.gd links,
    removes them from seen_deals, and dispatches fresh replacement deals with official store links.
    Returns (deleted_count, new_sent_count).
    """
    target_chat = chat_id or Config.TELEGRAM_CHAT_ID
    if not target_chat:
        return 0, 0

    dagd_deals = get_dagd_deals()
    deleted_count = 0
    if dagd_deals:
        print(f"[Cleanup] 🧹 Encontradas {len(dagd_deals)} ofertas com link da.gd para remover do Telegram...")
        for deal in dagd_deals:
            msg_id = deal.get("telegram_message_id")
            if msg_id:
                try:
                    telegram.delete_message(target_chat, msg_id)
                    deleted_count += 1
                    time.sleep(0.5)
                except Exception as e:
                    print(f"[Cleanup] Erro ao apagar msg {msg_id}: {e}")

        delete_dagd_deals()
        print(f"[Cleanup] ✅ {deleted_count} mensagens com link da.gd apagadas com sucesso.")

    # Rescan and post fresh deals with official store links
    new_sent = run_deal_scanner(telegram, chat_id=target_chat)
    return deleted_count, new_sent

def run_deal_scanner(telegram: TelegramClient, chat_id: str = None, max_deals: int = None) -> int:
    """Scans for new deals and dispatches them to Telegram."""
    global _start_with_ml
    target_chat = chat_id or Config.TELEGRAM_CHAT_ID
    if not target_chat:
        print("[Alerta] TELEGRAM_CHAT_ID não configurado no .env")
        return 0

    with _scanner_lock:
        max_limit = max_deals if max_deals is not None else int(
            get_setting("max_deals_per_run", str(Config.MAX_DEALS_PER_RUN))
        )
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔎 Iniciando varredura de ofertas (limite: {max_limit})...")

        shopee_deals = []
        ml_deals = []

        try:
            shopee_deals = fetch_shopee_deals(limit=50)
        except Exception as e:
            print(f"[Erro] Falha ao coletar Shopee: {e}")

        # Só busca no Mercado Livre se houver ML_AFFILIATE_TAG configurada
        if Config.ML_AFFILIATE_TAG:
            try:
                ml_deals = fetch_mercadolivre_deals(limit_per_category=3)
            except Exception as e:
                print(f"[Erro] Falha ao coletar Mercado Livre: {e}")

        # Ordena cada plataforma individualmente pelo maior desconto
        shopee_deals.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)
        ml_deals.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)

        # Intercala Mercado Livre e Shopee alternando quem começa a cada rodada
        candidate_deals = []
        idx_s, idx_m = 0, 0
        ml_first = _start_with_ml
        _start_with_ml = not _start_with_ml

        while idx_s < len(shopee_deals) or idx_m < len(ml_deals):
            if ml_first:
                if idx_m < len(ml_deals):
                    candidate_deals.append(ml_deals[idx_m])
                    idx_m += 1
                if idx_s < len(shopee_deals):
                    candidate_deals.append(shopee_deals[idx_s])
                    idx_s += 1
            else:
                if idx_s < len(shopee_deals):
                    candidate_deals.append(shopee_deals[idx_s])
                    idx_s += 1
                if idx_m < len(ml_deals):
                    candidate_deals.append(ml_deals[idx_m])
                    idx_m += 1

        sent_count = 0
        sent_ids = set()
        sent_titles = set()

        for deal in candidate_deals:
            if sent_count >= max_limit:
                break

            pid = deal.get("id", "")
            title = deal.get("title", "").strip()
            norm_title = title.lower()

            if pid in sent_ids or norm_title in sent_titles or is_deal_seen(pid, title=title):
                print(f"  ⏭️ Pulando duplicata: {title[:40]}")
                continue

            deal["link"] = shorten_url(deal.get("link", ""))
            print(f"  📤 Enviando [{deal['platform']}]: {title[:40]}... ({deal['discount_percent']}% OFF)")
            msg_id = telegram.send_deal(target_chat, deal)
            if msg_id:
                save_deal(deal, message_id=msg_id)
                sent_ids.add(pid)
                sent_titles.add(norm_title)
                sent_count += 1
                time.sleep(2)  # brief pause to avoid Telegram rate limits

        print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Varredura finalizada. {sent_count} novas ofertas enviadas.")
        return sent_count

def handle_telegram_updates(telegram: TelegramClient):
    """Listens for user commands and inline button callbacks."""
    offset = None
    print("[Telegram] Escutando comandos do Telegram...")

    while True:
        try:
            updates = telegram.get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1

                # 1. Handle Inline Button Callbacks (from /painel)
                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_id = cb["id"]
                    data = cb.get("data", "")
                    msg = cb.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    msg_id = msg.get("message_id")

                    if data == "toggle_comments":
                        curr = get_setting("comments_enabled", "true") == "true"
                        new_val = "false" if curr else "true"
                        set_setting("comments_enabled", new_val)
                        alert = "❌ Frases descontraídas desativadas!" if new_val == "false" else "✅ Frases descontraídas ativadas!"
                        telegram.answer_callback_query(cb_id, text=alert)
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_interval":
                        intervals = ["10", "20", "30"]
                        curr = get_setting("check_interval", "10")
                        next_idx = (intervals.index(curr) + 1) % len(intervals) if curr in intervals else 0
                        new_val = intervals[next_idx]
                        set_setting("check_interval", new_val)
                        telegram.answer_callback_query(cb_id, text=f"⏱️ Intervalo alterado para {new_val} minutos!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_discount":
                        discounts = ["15", "20", "30"]
                        curr = get_setting("min_discount", "15")
                        next_idx = (discounts.index(curr) + 1) % len(discounts) if curr in discounts else 0
                        new_val = discounts[next_idx]
                        set_setting("min_discount", new_val)
                        telegram.answer_callback_query(cb_id, text=f"🏷️ Desconto mínimo alterado para {new_val}% OFF!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_hours":
                        hour_presets = [
                            (8, 22),
                            (9, 21),
                            (7, 23),
                            (0, 24)
                        ]
                        curr_start = int(get_setting("start_hour", "8"))
                        curr_end = int(get_setting("end_hour", "22"))
                        curr_pair = (curr_start, curr_end)

                        next_idx = (hour_presets.index(curr_pair) + 1) % len(hour_presets) if curr_pair in hour_presets else 0
                        new_start, new_end = hour_presets[next_idx]

                        set_setting("start_hour", str(new_start))
                        set_setting("end_hour", str(new_end))

                        desc = "24h (Sem pausa)" if new_start == 0 and new_end == 24 else f"{new_start:02d}h às {new_end:02d}h"
                        telegram.answer_callback_query(cb_id, text=f"⏰ Horário alterado para {desc}!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_days":
                        day_presets = ["todos", "seg-sex", "seg-sab"]
                        day_names = {
                            "todos": "Todos os dias",
                            "seg-sex": "Segunda a Sexta",
                            "seg-sab": "Segunda a Sábado"
                        }
                        curr = get_setting("active_days", "todos")
                        next_idx = (day_presets.index(curr) + 1) % len(day_presets) if curr in day_presets else 0
                        new_val = day_presets[next_idx]

                        set_setting("active_days", new_val)
                        telegram.answer_callback_query(cb_id, text=f"📅 Dias alterados para {day_names[new_val]}!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_repeat":
                        repeat_presets = ["2", "3", "7", "30"]
                        repeat_labels = {
                            "2": "Após 2 dias",
                            "3": "Após 3 dias",
                            "7": "Após 7 dias",
                            "30": "Nunca (30 dias)"
                        }
                        curr = get_setting("repeat_days", "2")
                        next_idx = (repeat_presets.index(curr) + 1) % len(repeat_presets) if curr in repeat_presets else 0
                        new_val = repeat_presets[next_idx]

                        set_setting("repeat_days", new_val)
                        telegram.answer_callback_query(cb_id, text=f"🔄 Repetição configurada para: {repeat_labels[new_val]}!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_max_deals":
                        deal_presets = ["1", "2", "3", "4", "5"]
                        curr = get_setting("max_deals_per_run", str(Config.MAX_DEALS_PER_RUN))
                        next_idx = (deal_presets.index(curr) + 1) % len(deal_presets) if curr in deal_presets else 0
                        new_val = deal_presets[next_idx]

                        set_setting("max_deals_per_run", new_val)
                        label = "1 oferta" if new_val == "1" else f"{new_val} ofertas"
                        telegram.answer_callback_query(cb_id, text=f"📨 Quantidade por envio alterada para {label}!")
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "open_msg_panel":
                        telegram.answer_callback_query(cb_id)
                        text, kb = build_msg_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "back_to_main_panel":
                        telegram.answer_callback_query(cb_id)
                        text, kb = build_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "cycle_msg_header":
                        custom_hdr = get_setting("msg_custom_header", "").strip()
                        styles = ["direct", "price_first", "alert", "custom"] if custom_hdr else ["direct", "price_first", "alert"]
                        curr = get_setting("msg_header_style", "direct")
                        next_idx = (styles.index(curr) + 1) % len(styles) if curr in styles else 0
                        new_style = styles[next_idx]
                        set_setting("msg_header_style", new_style)
                        telegram.answer_callback_query(cb_id, text=f"🎨 Topo: {HEADER_STYLES[new_style]}")
                        text, kb = build_msg_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data in ("toggle_msg_platform", "toggle_msg_footer", "toggle_msg_coupon"):
                        toggle_cfg = {
                            "toggle_msg_platform": ("msg_show_platform", "Nome da loja"),
                            "toggle_msg_footer": ("msg_show_footer", "Rodapé"),
                            "toggle_msg_coupon": ("msg_show_coupon", "Cupons na mensagem"),
                        }
                        key, label = toggle_cfg[data]
                        curr = get_setting(key, "true") == "true"
                        new_val = "false" if curr else "true"
                        set_setting(key, new_val)
                        state = "ativado" if new_val == "true" else "oculto"
                        telegram.answer_callback_query(cb_id, text=f"{label} {state}!")
                        text, kb = build_msg_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data in ("prompt_msg_topo", "prompt_msg_cta", "prompt_msg_footer", "prompt_msg_cupom_shopee", "prompt_msg_cupom_ml"):
                        field = data.replace("prompt_msg_", "", 1)
                        cb_user_id = str(cb.get("from", {}).get("id", ""))
                        set_setting(f"pending_msg_edit_{chat_id}_{cb_user_id}", f"{field}:{int(time.time())}")
                        telegram.answer_callback_query(cb_id, text="✏️ Responda à mensagem que vou enviar!")
                        telegram.send_message(
                            chat_id,
                            _MSG_FIELD_PROMPTS[field],
                            reply_markup={"force_reply": True}
                        )

                    elif data == "reset_msg_template":
                        set_setting("msg_header_style", "direct")
                        set_setting("msg_custom_header", "")
                        set_setting("msg_cta_text", DEFAULT_CTA_TEXT)
                        set_setting("msg_footer_text", DEFAULT_FOOTER_TEXT)
                        set_setting("msg_show_platform", "true")
                        set_setting("msg_show_footer", "true")
                        set_setting("msg_show_coupon", "true")
                        telegram.answer_callback_query(cb_id, text="🔄 Layout restaurado para o padrão!")
                        text, kb = build_msg_panel_data()
                        telegram.edit_message_text(chat_id, msg_id, text, reply_markup=kb)

                    elif data == "start_bot_official":
                        set_setting("bot_activated", "true")
                        telegram.answer_callback_query(cb_id, text="🚀 Trabalhos iniciados oficialmente com sucesso!", show_alert=True)
                        confirm_msg = (
                            "🎉 <b>Maravilha, Bianca! Robô ativado com sucesso!</b>\n\n"
                            "A partir de agora estou conectado na Shopee e vou entregar as melhores ofertas aqui para você.\n\n"
                            "⚙️ Este é o seu <b>Painel de Opções</b> (você pode acessá-lo sempre digitando /painel):"
                        )
                        telegram.send_message(chat_id, confirm_msg)
                        panel_text, panel_kb = build_panel_data()
                        telegram.send_message(chat_id, panel_text, reply_markup=panel_kb)
                        # Envia imediatamente as primeiras ofertas para dar a largada oficial
                        run_deal_scanner(telegram, chat_id=chat_id, max_deals=2)

                    elif data == "trigger_deals":
                        telegram.answer_callback_query(cb_id, text="🔎 Buscando ofertas relâmpago agora...")
                        run_deal_scanner(telegram, chat_id=chat_id)

                    continue

                # 2. Handle Text Commands
                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat = message.get("chat", {})
                chat_id = str(chat.get("id", ""))
                username = chat.get("first_name", "Usuário")

                if not text or not chat_id:
                    continue

                print(f"[Comando Recebido] {username} ({chat_id}): {text}")

                from_user_id = str(message.get("from", {}).get("id", ""))
                chat_type = chat.get("type", "")
                reply_to = message.get("reply_to_message", {})
                pending_key = f"pending_msg_edit_{chat_id}_{from_user_id}"

                if text.startswith("/"):
                    if get_setting(pending_key, ""):
                        set_setting(pending_key, "")
                else:
                    pending_val = get_setting(pending_key, "")
                    if pending_val:
                        field, _, ts_str = pending_val.partition(":")
                        is_fresh = ts_str.isdigit() and (time.time() - int(ts_str)) <= 600
                        reply_text = reply_to.get("text", "") if isinstance(reply_to, dict) else ""
                        is_prompt_reply = (
                            isinstance(reply_to, dict)
                            and bool(reply_to.get("from", {}).get("is_bot"))
                            and ("responda ESTA mensagem" in reply_text)
                        )
                        if not is_fresh:
                            set_setting(pending_key, "")
                        elif is_prompt_reply or chat_type == "private":
                            set_setting(pending_key, "")
                            if text.lower() == "cancelar":
                                telegram.send_message(chat_id, "❌ Edição cancelada.")
                            else:
                                confirm = _apply_msg_field_update(field, text)
                                telegram.send_message(chat_id, confirm)
                                msg_text, msg_kb = build_msg_panel_data()
                                telegram.send_message(chat_id, msg_text, reply_markup=msg_kb)
                            continue

                if text.startswith("/start"):
                    welcome = (
                        f"👋 <b>Olá, {username}!</b>\n\n"
                        f"🛍️ Este é o seu <b>Bot de Ofertas Shopee</b>.\n\n"
                        f"Ele busca automaticamente as melhores promoções da Shopee com o seu <b>link de afiliada já embutido</b>!\n\n"
                        f"📌 <b>Como usar no dia a dia:</b>\n"
                        f"1. Toque no botão <b>[ 📲 Compartilhar no WhatsApp ]</b> abaixo de qualquer oferta.\n"
                        f"2. Escolha o seu grupo no WhatsApp e clique em <b>Enviar</b>!\n\n"
                        f"⚙️ <b>Comandos:</b>\n"
                        f"• /painel - Painel de opções (ligar/desligar frases e filtros)\n"
                        f"• /ofertas - Buscar ofertas agora mesmo\n"
                        f"• /status - Ver quantas ofertas foram enviadas hoje\n"
                        f"• /bianca - Apresentação do bot para a Bianca"
                    )
                    telegram.send_message(chat_id, welcome)

                elif text.startswith("/painel") or text.startswith("/config"):
                    panel_text, panel_kb = build_panel_data()
                    telegram.send_message(chat_id, panel_text, reply_markup=panel_kb)

                elif text.startswith("/bianca") or text.startswith("/apresentacao"):
                    pres_text, pres_kb = get_bianca_presentation()
                    telegram.send_message(chat_id, pres_text, reply_markup=pres_kb)

                elif text.startswith("/ofertas"):
                    telegram.send_message(chat_id, "🔎 Buscando as melhores ofertas relâmpago na Shopee e no Mercado Livre agora, aguarde um instante...")
                    sent = run_deal_scanner(telegram, chat_id=chat_id)
                    if sent == 0:
                        telegram.send_message(chat_id, "ℹ️ Nenhuma nova oferta com super desconto encontrada no momento. Buscarei novamente em breve!")

                elif text.startswith("/refazer"):
                    telegram.send_message(chat_id, "🧹 Apagando do Telegram as mensagens com link antigo e enviando novas ofertas com os links oficiais das lojas...")
                    deleted, sent = cleanup_and_repost_dagd_deals(telegram, chat_id=chat_id)
                    telegram.send_message(
                        chat_id,
                        f"✅ Concluído! {deleted} mensagens antigas apagadas e {sent} novas ofertas enviadas com os links oficiais da Shopee e do Mercado Livre."
                    )

                elif text.startswith("/status"):
                    stats = get_stats()
                    interval = get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES))
                    min_disc = get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT))
                    max_deals = get_setting("max_deals_per_run", str(Config.MAX_DEALS_PER_RUN))
                    comments_active = get_setting("comments_enabled", "true") == "true"
                    c_status = "Ativadas" if comments_active else "Desativadas"
                    start_h = int(get_setting("start_hour", "8"))
                    end_h = int(get_setting("end_hour", "22"))
                    h_str = "24h (Sem pausa)" if start_h == 0 and end_h == 24 else f"{start_h:02d}h às {end_h:02d}h"
                    days_map = {"todos": "Todos os dias", "seg-sex": "Seg a Sex", "seg-sab": "Seg a Sáb"}
                    d_str = days_map.get(get_setting("active_days", "todos"), "Todos os dias")
                    rep_days = get_setting("repeat_days", "2")
                    rep_map = {"2": "Após 2 dias", "3": "Após 3 dias", "7": "Após 7 dias", "30": "Nunca (30d)"}
                    r_str = rep_map.get(rep_days, "Após 2 dias")
                    deals_label = "1 oferta" if max_deals == "1" else f"{max_deals} ofertas"

                    status_msg = (
                        f"📊 <b>Painel do Bot de Ofertas</b>\n\n"
                        f"🔥 <b>Ofertas enviadas hoje:</b> {stats['today']}\n"
                        f"📦 <b>Total histórico de ofertas:</b> {stats['total']}\n"
                        f"⏰ <b>Horário ativo:</b> {h_str}\n"
                        f"📅 <b>Dias ativos:</b> {d_str}\n"
                        f"🔄 <b>Repetir produtos:</b> {r_str}\n"
                        f"⏱️ <b>Verificação automática:</b> A cada {interval} minutos\n"
                        f"🏷️ <b>Desconto mínimo:</b> {min_disc}% OFF\n"
                        f"📨 <b>Ofertas por vez:</b> {deals_label}\n"
                        f"💬 <b>Frases nos produtos:</b> {c_status}\n"
                        f"🗑️ <b>Auto-remover expirados:</b> Ativado (Shopee & ML)\n"
                        f"🛍️ <b>Plataformas ativas:</b> Shopee & Mercado Livre (Afiliada Bianca)"
                    )
                    telegram.send_message(chat_id, status_msg)

                elif text.startswith("/dbcheck"):
                    from database import USE_POSTGRES, DATABASE_URL
                    db_type = "✅ PostgreSQL (persistente)" if USE_POSTGRES else "⚠️ SQLite (efêmero - repete após redeploy!)"
                    db_url_hint = DATABASE_URL[:30] + "..." if DATABASE_URL else "❌ Não configurado"
                    telegram.send_message(chat_id, (
                        f"🗄️ <b>Status do Banco de Dados</b>\n\n"
                        f"<b>Tipo:</b> {db_type}\n"
                        f"<b>DATABASE_URL:</b> <code>{db_url_hint}</code>"
                    ))

                elif text.startswith("/ajuda"):
                    help_msg = (
                        "❓ <b>Como compartilhar as ofertas no WhatsApp:</b>\n\n"
                        "<b>Opção 1 (A mais rápida - 1 Toque):</b>\n"
                        "Toque no botão azul <b>[ 📲 Compartilhar no WhatsApp ]</b> embaixo da oferta. "
                        "O WhatsApp vai abrir sozinho com a mensagem e o seu link prontos. É só selecionar o seu grupo e enviar!\n\n"
                        "<b>Opção 2 (Com foto no WhatsApp):</b>\n"
                        "Se você quiser mandar com a foto grande no WhatsApp:\n"
                        "1. Toque na foto aqui no Telegram e compartilhe no seu grupo de WhatsApp.\n"
                        "2. Depois toque no texto da oferta (ele copia sozinho) e cole na legenda da foto!\n\n"
                        "⚙️ Digite <b>/painel</b> para abrir as configurações e personalizar mensagens e filtros."
                    )
                    telegram.send_message(chat_id, help_msg)

                elif text.split(None, 1)[0].split("@")[0].lower() in ("/topo", "/cta", "/rodape", "/cupomshopee", "/cupomml"):
                    parts = text.split(None, 1)
                    cmd_name = parts[0].split("@")[0].lower()
                    cmd_arg = parts[1].strip() if len(parts) > 1 else ""
                    field = {
                        "/topo": "topo",
                        "/cta": "cta",
                        "/rodape": "footer",
                        "/cupomshopee": "cupom_shopee",
                        "/cupomml": "cupom_ml",
                    }[cmd_name]
                    if cmd_arg:
                        confirm = _apply_msg_field_update(field, cmd_arg)
                        telegram.send_message(chat_id, confirm)
                        msg_text, msg_kb = build_msg_panel_data()
                        telegram.send_message(chat_id, msg_text, reply_markup=msg_kb)
                    else:
                        set_setting(pending_key, f"{field}:{int(time.time())}")
                        telegram.send_message(
                            chat_id,
                            _MSG_FIELD_PROMPTS[field],
                            reply_markup={"force_reply": True}
                        )

        except Exception as e:
            print(f"[Erro no Polling] {e}")
            time.sleep(5)

        time.sleep(1)

def scheduled_worker(telegram: TelegramClient):
    """Background worker that periodically runs deal scans and cleans expired deals."""
    while True:
        try:
            # Respect dynamic interval from settings
            interval_minutes = int(get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES)))
            interval_seconds = interval_minutes * 60
            cleanup_old_deals()
            check_and_remove_expired_deals(telegram)

            in_schedule, reason = is_within_schedule()
            if in_schedule:
                run_deal_scanner(telegram)
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⏸️ Envio automático pausado: {reason}")
        except Exception as e:
            print(f"[Erro no Agendador] {e}")
            interval_seconds = 600
        time.sleep(interval_seconds)

def main():
    parser = argparse.ArgumentParser(description="Bot de Ofertas Shopee para Telegram / WhatsApp")
    parser.add_argument("--test", action="store_true", help="Executa um teste sem enviar ao Telegram")
    parser.add_argument("--scan", action="store_true", help="Executa uma varredura imediata e envia ao Telegram")
    args = parser.parse_args()

    if args.test:
        run_dry_run_test()
        return

    # Check Telegram Token
    if not Config.TELEGRAM_BOT_TOKEN:
        print("\n❌ ERRO: 'TELEGRAM_BOT_TOKEN' não foi configurado!")
        sys.exit(1)

    telegram = TelegramClient()
    bot_info = telegram.get_me()
    if not bot_info:
        print("❌ Falha ao conectar na API do Telegram. Verifique seu TELEGRAM_BOT_TOKEN.")
        sys.exit(1)

    print(f"🤖 Bot conectado com sucesso como @{bot_info.get('username')}")

    # Registra o menu nativo de comandos no Telegram
    setup_commands(telegram)

    # Inicia o servidor web interno para o Render / cloud
    start_health_server()

    # Limpa automaticamente mensagens antigas com link da.gd e envia novas ofertas com links oficiais
    try:
        cleanup_and_repost_dagd_deals(telegram)
    except Exception as e:
        print(f"[Cleanup Inicial] Erro na limpeza: {e}")

    if args.scan:
        run_deal_scanner(telegram)
        return

    print("⚡ Iniciando agendador em segundo plano...")
    timer_thread = threading.Thread(target=scheduled_worker, args=(telegram,), daemon=True)
    timer_thread.start()

    # Run Telegram command polling in main thread
    handle_telegram_updates(telegram)

if __name__ == "__main__":
    main()
