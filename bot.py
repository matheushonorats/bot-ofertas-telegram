import sys
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
    save_deal, get_stats, cleanup_old_deals, get_setting, set_setting,
    get_active_posted_deals, mark_deal_inactive
)
from scraper_ml import fetch_mercadolivre_deals
from scraper_shopee import fetch_shopee_deals
from telegram_client import TelegramClient
from formatter import format_whatsapp_message
from web_server import start_health_server

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

def build_panel_data():
    """Builds text and inline keyboard for the interactive settings panel."""
    comments_active = get_setting("comments_enabled", "true") == "true"
    interval = get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES))
    min_disc = get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT))
    start_hour = int(get_setting("start_hour", "8"))
    end_hour = int(get_setting("end_hour", "22"))
    active_days = get_setting("active_days", "todos")
    repeat_days = get_setting("repeat_days", "2")

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

    text = (
        "⚙️ <b>Painel de Opções do Bot de Ofertas</b>\n\n"
        "<i>Toque nos botões abaixo para personalizar o comportamento do bot:</i>\n\n"
        f"💬 <b>Frases nos Produtos:</b> <code>{status_str}</code>\n"
        f"⏰ <b>Horário de Funcionamento:</b> <code>{hours_str}</code>\n"
        f"📅 <b>Dias de Envio:</b> <code>{days_str}</code>\n"
        f"🔄 <b>Repetir Produtos:</b> <code>{repeat_str}</code>\n"
        f"⏱️ <b>Intervalo Automático:</b> <code>A cada {interval} min</code>\n"
        f"🏷️ <b>Desconto Mínimo:</b> <code>{min_disc}% OFF</code>\n"
        f"🛍️ <b>Plataforma:</b> <code>Shopee (Afiliada Bianca)</code>\n"
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

def run_deal_scanner(telegram: TelegramClient, chat_id: str = None, max_deals: int = None) -> int:
    """Scans for new deals and dispatches them to Telegram."""
    target_chat = chat_id or Config.TELEGRAM_CHAT_ID
    if not target_chat:
        print("[Alerta] TELEGRAM_CHAT_ID não configurado no .env")
        return 0

    max_limit = max_deals or Config.MAX_DEALS_PER_RUN
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔎 Iniciando varredura de ofertas...")

    deals = []
    try:
        deals.extend(fetch_shopee_deals(limit=50))
    except Exception as e:
        print(f"[Erro] Falha ao coletar Shopee: {e}")

    # Só busca no Mercado Livre se houver ML_AFFILIATE_TAG configurada
    if Config.ML_AFFILIATE_TAG:
        try:
            deals.extend(fetch_mercadolivre_deals(limit_per_category=3))
        except Exception as e:
            print(f"[Erro] Falha ao coletar Mercado Livre: {e}")

    # Sort deals by discount percentage (highest first)
    deals.sort(key=lambda x: x.get("discount_percent", 0), reverse=True)

    sent_count = 0
    for deal in deals:
        if sent_count >= max_limit:
            break

        print(f"  📤 Enviando [{deal['platform']}]: {deal['title'][:40]}... ({deal['discount_percent']}% OFF)")
        msg_id = telegram.send_deal(target_chat, deal)
        if msg_id:
            save_deal(deal, message_id=msg_id)
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
                        run_deal_scanner(telegram, chat_id=chat_id, max_deals=3)

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
                    telegram.send_message(chat_id, "🔎 Buscando as melhores ofertas relâmpago na Shopee agora, aguarde um instante...")
                    sent = run_deal_scanner(telegram, chat_id=chat_id, max_deals=3)
                    if sent == 0:
                        telegram.send_message(chat_id, "ℹ️ Nenhuma nova oferta com super desconto encontrada no momento. Buscarei novamente em breve!")

                elif text.startswith("/status"):
                    stats = get_stats()
                    interval = get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES))
                    min_disc = get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT))
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

                    status_msg = (
                        f"📊 <b>Painel do Bot de Ofertas</b>\n\n"
                        f"🔥 <b>Ofertas enviadas hoje:</b> {stats['today']}\n"
                        f"📦 <b>Total histórico de ofertas:</b> {stats['total']}\n"
                        f"⏰ <b>Horário ativo:</b> {h_str}\n"
                        f"📅 <b>Dias ativos:</b> {d_str}\n"
                        f"🔄 <b>Repetir produtos:</b> {r_str}\n"
                        f"⏱️ <b>Verificação automática:</b> A cada {interval} minutos\n"
                        f"🏷️ <b>Desconto mínimo:</b> {min_disc}% OFF\n"
                        f"💬 <b>Frases nos produtos:</b> {c_status}\n"
                        f"🗑️ <b>Auto-remover expirados:</b> Ativado na Shopee\n"
                        f"🛍️ <b>Plataforma ativa:</b> Shopee Oficial (Afiliada Bianca)"
                    )
                    telegram.send_message(chat_id, status_msg)

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
                        "⚙️ Digite <b>/painel</b> para abrir as configurações e ligar/desligar funções."
                    )
                    telegram.send_message(chat_id, help_msg)

        except Exception as e:
            print(f"[Erro no Polling] {e}")
            time.sleep(5)

        time.sleep(1)

def scheduled_worker(telegram: TelegramClient):
    """Background worker that periodically runs deal scans and cleans expired deals."""
    while True:
        try:
            # TRAVA ABSOLUTA: Só roda após a Bianca clicar no botão de ativação!
            if get_setting("bot_activated", "false") != "true":
                time.sleep(15)
                continue

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
