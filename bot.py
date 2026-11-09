import sys
import time
import threading
import argparse
from datetime import datetime

# Ensure UTF-8 output in Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import Config
from database import save_deal, get_stats, cleanup_old_deals, get_setting, set_setting
from scraper_ml import fetch_mercadolivre_deals
from scraper_shopee import fetch_shopee_deals
from telegram_client import TelegramClient
from formatter import format_whatsapp_message
from web_server import start_health_server

def build_panel_data():
    """Builds text and inline keyboard for the interactive settings panel."""
    comments_active = get_setting("comments_enabled", "true") == "true"
    interval = get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES))
    min_disc = get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT))

    status_str = "✅ ATIVADOS" if comments_active else "❌ DESATIVADOS"
    toggle_label = "💬 Frases: DESATIVAR" if comments_active else "💬 Frases: ATIVAR"

    text = (
        "⚙️ <b>Painel de Opções do Bot de Ofertas</b>\n\n"
        "<i>Toque nos botões abaixo para ligar/desligar funções e personalizar os envios:</i>\n\n"
        f"💬 <b>Frases Descontraídas:</b> <code>{status_str}</code>\n"
        f"⏱️ <b>Intervalo Automático:</b> <code>A cada {interval} min</code>\n"
        f"🏷️ <b>Desconto Mínimo:</b> <code>{min_disc}% OFF</code>\n"
        f"🛍️ <b>Plataforma:</b> <code>Shopee (Afiliada Bianca)</code>\n"
    )

    keyboard = {
        "inline_keyboard": [
            [{"text": toggle_label, "callback_data": "toggle_comments"}],
            [
                {"text": f"⏱️ Intervalo: {interval}m", "callback_data": "cycle_interval"},
                {"text": f"🏷️ Mínimo: {min_disc}%", "callback_data": "cycle_discount"}
            ],
            [{"text": "🔎 Buscar Ofertas Agora", "callback_data": "trigger_deals"}]
        ]
    }
    return text, keyboard

def get_bianca_presentation() -> str:
    """Returns the personalized presentation message for Bianca."""
    return (
        "👋 <b>Olá, Bianca! Prazer em te conhecer!</b>\n\n"
        "Eu sou o seu <b>Assistente Pessoal de Ofertas da Shopee</b>, criado exclusivamente para "
        "encontrar os melhores achados e abastecer o seu grupo de promoções com facilidade! 🛍️✨\n\n"
        "Aqui está como eu funciono e como você pode lucrar comigo todos os dias:\n\n"
        "🔍 <b>1. Varredura 24 Horas nas Nuvens</b>\n"
        "Eu fico ligado 24h por dia buscando as <b>Ofertas Relâmpago da Shopee</b> com super descontos "
        "reais e fotos em alta qualidade.\n\n"
        "💰 <b>2. Seu Link de Afiliada Já Embutido</b>\n"
        "Todas as ofertas que envio aqui já vêm com o seu código de afiliada (<code>an_18345610975</code>) "
        "e a etiqueta do WhatsApp. Cada compra feita pelo seu link gera comissão para você!\n\n"
        "📲 <b>3. Como Mandar no WhatsApp com 1 Toque</b>\n"
        "Abaixo de cada oferta, você verá o botão azul: <b>[ 📲 Compartilhar no WhatsApp ]</b>.\n"
        "Basta <b>dar 1 toque nele no seu celular</b>! O WhatsApp abre sozinho com a mensagem, fotos na prévia, "
        "preços e o seu link prontinhos. Você só seleciona o seu grupo e envia! Zero trabalho de copiar e colar.\n\n"
        "⚙️ <b>4. Seu Painel de Opções (/painel)</b>\n"
        "Você tem controle total! Digite <b>/painel</b> para:\n"
        "• Ativar ou desativar as frases descontraídas.\n"
        "• Mudar o intervalo de envio das ofertas.\n"
        "• Alterar o desconto mínimo desejado.\n\n"
        "💡 <i>Dica: Sempre que quiser novas promoções na mesma hora, basta tocar em <b>/ofertas</b> no menu!</i>\n\n"
        "Estou pronto para fazer o seu grupo bombar! Boas vendas! 🚀💰"
    )

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
        success = telegram.send_deal(target_chat, deal)
        if success:
            save_deal(deal)
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
                    pres = get_bianca_presentation()
                    telegram.send_message(chat_id, pres)

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

                    status_msg = (
                        f"📊 <b>Painel do Bot de Ofertas</b>\n\n"
                        f"🔥 <b>Ofertas enviadas hoje:</b> {stats['today']}\n"
                        f"📦 <b>Total histórico de ofertas:</b> {stats['total']}\n"
                        f"⏱️ <b>Verificação automática:</b> A cada {interval} minutos\n"
                        f"🏷️ <b>Desconto mínimo:</b> {min_disc}% OFF\n"
                        f"💬 <b>Frases descontraídas:</b> {c_status}\n"
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
    """Background worker that periodically runs deal scans."""
    while True:
        try:
            # Respect dynamic interval from settings
            interval_minutes = int(get_setting("check_interval", str(Config.CHECK_INTERVAL_MINUTES)))
            interval_seconds = interval_minutes * 60
            cleanup_old_deals(days=7)
            run_deal_scanner(telegram)
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
