# 🤖 Bot de Ofertas (Mercado Livre & Shopee) com Links de Afiliado

Este robô monitora continuamente as principais ofertas e promoções com alto desconto no **Mercado Livre** e na **Shopee**, formata automaticamente as mensagens de alta conversão para o **WhatsApp** com seu **link de associado/afiliado** e envia tudo com a **foto do produto** diretamente no seu Telegram.

---

## ⚡ Principais Funcionalidades

1. **Monitoramento Duplo em Tempo Real**:
   - **Mercado Livre**: Varredura em categorias de alta conversão (*Tecnologia, Eletrodomésticos, Casa, Ferramentas, Beleza e Mais Vendidos*).
   - **Shopee**: Conexão direta com as Ofertas Relâmpago (Flash Sale) da Shopee.
2. **Mensagem Pronta para WhatsApp (1 Toque para Copiar)**:
   - O Telegram envia a foto e a mensagem formatada para WhatsApp dentro de um bloco de código `<code>`.
   - **No Telegram (celular ou PC):** Basta dar **1 toque** no bloco de texto para copiar a mensagem inteira e colar direto nos seus grupos ou status do WhatsApp!
3. **Inclusão Automática do seu Link de Afiliado**:
   - **Mercado Livre**: Anexa seus parâmetros/tags de afiliado (`matt_tool`, etc.) ou redirecionador.
   - **Shopee**: Anexa suas tags de sub-id/rastreamento ou gera links encurtados via API Oficial de Afiliados Shopee.
4. **Sem Spam / Banco de Dados Anti-Repetição**:
   - Banco de dados SQLite (`deals.db`) integrado que lembra as ofertas já enviadas e não repete o mesmo produto.
5. **Comandos Interativos no Telegram**:
   - `/start` - Mostra boas-vindas e revela seu **Chat ID**.
   - `/ofertas` - Força uma busca imediata das melhores promoções do momento.
   - `/status` - Mostra quantas ofertas foram enviadas hoje e o status do robô.
   - `/ajuda` - Guia rápido de utilização.

---

## 🚀 Como Configurar Passo a Passo

### 1. Criar o Bot no Telegram (Leva 2 minutos)
1. No seu Telegram, busque por **[@BotFather](https://t.me/BotFather)**.
2. Envie o comando `/newbot`.
3. Escolha um nome para o seu robô (ex: `Meu Bot de Ofertas`).
4. Escolha um nome de usuário terminado em `bot` (ex: `minhas_ofertas_promos_bot`).
5. O BotFather vai te enviar um **Token HTTP API** (ex: `7123456789:AAFxAbc...`). Guarde esse token!

### 2. Configurar o arquivo `.env`
Abra o arquivo `.env` que está na pasta do projeto e preencha:

```env
# Cole aqui o token que o BotFather te enviou:
TELEGRAM_BOT_TOKEN=7123456789:AAFxAbc...

# Seu Chat ID (se não souber, deixe em branco inicialmente)
TELEGRAM_CHAT_ID=

# Desconto mínimo desejado (% OFF)
MIN_DISCOUNT_PERCENT=15

# Intervalo entre verificações automáticas (minutos)
CHECK_INTERVAL_MINUTES=30

# AFILIADO MERCADO LIVRE (insira sua tag ou parâmetros)
ML_AFFILIATE_TAG=matt_tool=SEU_ID_AQUI

# AFILIADO SHOPEE (insira sua tag)
SHOPEE_AFFILIATE_TAG=sub_id=whatsapp_promo
```

> 💡 **Como descobrir seu Chat ID facilmente:**
> 1. Inicie o bot com o `TELEGRAM_BOT_TOKEN` preenchido.
> 2. Abra a conversa com o seu bot no Telegram e envie `/start`.
> 3. O bot responderá informando o seu **Chat ID** na hora!
> 4. Basta copiar esse número, colar no `TELEGRAM_CHAT_ID=` do seu `.env` e reiniciar o bot.

---

## 💻 Como Executar

### Opção 1: Teste Rápido (Sem precisar de Telegram)
Para testar a raspagem de ofertas e ver uma prévia da mensagem pronta:
```bash
py bot.py --test
```
*(Ou dê dois cliques no arquivo `testar.bat`)*

### Opção 2: Iniciar o Bot Oficial
Para rodar o bot com envio contínuo para o seu Telegram:
```bash
py bot.py
```
*(Ou dê dois cliques no arquivo `iniciar_bot.bat`)*

### Opção 3: Forçar um Envio Único Imediato
Para executar apenas uma varredura agora e enviar ao Telegram sem manter o robô rodando:
```bash
py bot.py --scan
```

---

## 📱 Exemplo da Mensagem Gerada para WhatsApp

```text
🔥 *SUPER OFERTA NO MERCADO LIVRE!* 🔥

📦 *Fone De Ouvido Soundcore by Anker P20i Bluetooth 5.3*

❌ De: ~R$ 299,00~
✅ Por apenas: *R$ 138,00*
💥 Desconto de: *54% OFF*

🛒 *Acesse e garanta a sua no link:*
👉 https://produto.mercadolivre.com.br/MLB-24028629...?matt_tool=12345678

⚠️ _Preço e estoque sujeitos a alteração a qualquer momento!_
```

---

## 📂 Estrutura dos Arquivos

- `bot.py` - Ponto de entrada, agendador em segundo plano e atendimento de comandos no Telegram.
- `scraper_ml.py` - Coletor de promoções do Mercado Livre com contorno de TLS CloudFront.
- `scraper_shopee.py` - Coletor de Ofertas Relâmpago da Shopee via API.
- `affiliate.py` - Gerador e formatador de links de associado (ML & Shopee).
- `formatter.py` - Formatador de mensagens com emojis, preços riscados e bloco copiável.
- `telegram_client.py` - Comunicação direta com a API do Telegram (fotos, legendas e comandos).
- `database.py` - Banco SQLite (`deals.db`) para controle de histórico e desduplicação.
- `config.py` - Leitor das configurações e variáveis de ambiente.
