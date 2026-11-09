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
from database import save_deal, get_stats, cleanup_old_deals
from scraper_ml import fetch_mercadolivre_deals
from scraper_shopee import fetch_shopee_deals
from telegram_client import TelegramClient
from formatter import format_whatsapp_message
from web_server import start_health_server

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

    # Fetch from platforms
    deals = []
    try:
        deals.extend(fetch_shopee_deals(limit=15))
    except Exception as e:
        print(f"[Erro] Falha ao coletar Shopee: {e}")

    # Só busca no Mercado Livre se o usuário tiver configurado a tag de afiliado do ML
    if Config.ML_AFFILIATE_TAG:
        try:
            deals.extend(fetch_mercadolivre_deals(limit_per_category=3))
        except Exception as e:
            print(f"[Erro] Falha ao coletar Mercado Livre: {e}")
    else:
        print("[Info] Mercado Livre desativado (aguardando configuracao de ML_AFFILIATE_TAG)")

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
    """Listens for user commands via Telegram long-polling."""
    offset = None
    print("[Telegram] Escutando comandos do Telegram...")

    while True:
        try:
            updates = telegram.get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
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
                        f"🤖 Eu sou o seu <b>Bot de Ofertas & Afiliados</b>.\n\n"
                        f"📌 <b>Seu Chat ID é:</b> <code>{chat_id}</code>\n"
                        f"<i>(Copie este número e coloque na variável TELEGRAM_CHAT_ID no seu arquivo .env se ainda não configurou)</i>\n\n"
                        f"⚙️ <b>Comandos disponíveis:</b>\n"
                        f"• /ofertas - Buscar as melhores promoções agora\n"
                        f"• /status - Ver estatísticas do robô\n"
                        f"• /ajuda - Informações e ajuda"
                    )
                    telegram.send_message(chat_id, welcome)

                elif text.startswith("/ofertas"):
                    telegram.send_message(chat_id, "🔎 Buscando as melhores ofertas no Mercado Livre e Shopee agora, aguarde...")
                    sent = run_deal_scanner(telegram, chat_id=chat_id, max_deals=3)
                    if sent == 0:
                        telegram.send_message(chat_id, "ℹ️ Nenhuma nova oferta com os filtros atuais no momento. Verificarei novamente em breve!")

                elif text.startswith("/status"):
                    stats = get_stats()
                    status_msg = (
                        f"📊 <b>Status do Bot de Ofertas</b>\n\n"
                        f"🔥 <b>Ofertas enviadas hoje:</b> {stats['today']}\n"
                        f"📦 <b>Total histórico:</b> {stats['total']}\n"
                        f"⏱️ <b>Intervalo automático:</b> Cada {Config.CHECK_INTERVAL_MINUTES} minutos\n"
                        f"🏷️ <b>Desconto mínimo:</b> {Config.MIN_DISCOUNT_PERCENT}%\n"
                        f"🛒 <b>Plataformas ativas:</b> Mercado Livre, Shopee"
                    )
                    telegram.send_message(chat_id, status_msg)

                elif text.startswith("/ajuda"):
                    help_msg = (
                        "ℹ️ <b>Como funciona:</b>\n\n"
                        "1. Eu monitoro as páginas de ofertas do <b>Mercado Livre</b> e <b>Shopee</b>.\n"
                        "2. Quando encontro um super desconto, gero a mensagem completa com seu <b>link de associado</b> e <b>foto</b>.\n"
                        "3. A mensagem vem dentro de um bloco copiável: basta dar <b>1 toque</b> no Telegram e colar no seu WhatsApp!\n\n"
                        "Use /ofertas para forçar uma busca imediata."
                    )
                    telegram.send_message(chat_id, help_msg)

        except Exception as e:
            print(f"[Erro no Polling] {e}")
            time.sleep(5)

        time.sleep(1)

def scheduled_worker(telegram: TelegramClient):
    """Background worker that periodically runs deal scans."""
    interval_seconds = Config.CHECK_INTERVAL_MINUTES * 60
    while True:
        try:
            cleanup_old_deals(days=7)
            run_deal_scanner(telegram)
        except Exception as e:
            print(f"[Erro no Agendador] {e}")
        time.sleep(interval_seconds)

def main():
    parser = argparse.ArgumentParser(description="Bot de Ofertas Mercado Livre & Shopee para Telegram / WhatsApp")
    parser.add_argument("--test", action="store_true", help="Executa um teste sem enviar ao Telegram")
    parser.add_argument("--scan", action="store_true", help="Executa uma varredura imediata e envia ao Telegram")
    args = parser.parse_args()

    if args.test:
        run_dry_run_test()
        return

    # Check Telegram Token
    if not Config.TELEGRAM_BOT_TOKEN:
        print("\n❌ ERRO: 'TELEGRAM_BOT_TOKEN' não foi configurado!")
        print("💡 Crie o arquivo .env a partir de .env.example e configure seu token do @BotFather.")
        print("💡 Para testar a raspagem e formatação agora mesmo sem Telegram, execute:")
        print("   py bot.py --test\n")
        sys.exit(1)

    telegram = TelegramClient()
    bot_info = telegram.get_me()
    if not bot_info:
        print("❌ Falha ao conectar na API do Telegram. Verifique seu TELEGRAM_BOT_TOKEN.")
        sys.exit(1)

    print(f"🤖 Bot conectado com sucesso como @{bot_info.get('username')}")

    # Start healthcheck web server for Render / cloud deployments
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
