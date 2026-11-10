import random
import re
import requests
from collections import deque
from config import Config

# Remembers recently used comments so the same comment is not reused (buffer of 60)
_recent_comments = deque(maxlen=60)

def generate_gemini_comment(title: str, category: str = "", platform: str = "") -> str:
    """
    Calls Google Gemini AI API to generate a bespoke, ultra-coherent 1-sentence comment
    tailored specifically to the exact product title.
    Requires GEMINI_API_KEY in environment.
    """
    api_key = getattr(Config, "GEMINI_API_KEY", "")
    if not api_key:
        return ""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    prompt = (
        "Você é uma curadora de achadinhos carismática em um grupo VIP de promoções no WhatsApp no Brasil.\n"
        "Crie APENAS UMA frase curta (máximo 14 palavras), descontraída, inteligente e que faça sentido REAL com o produto abaixo:\n\n"
        f"Produto: {title}\n"
        f"Categoria: {category}\n"
        f"Loja: {platform}\n\n"
        "Regras obrigatórias:\n"
        "1. Retorne APENAS a frase direta (sem aspas, sem introduções e sem balãozinho de fala 💬).\n"
        "2. Termine com 1 emoji condizente com o produto.\n"
        "3. Destaque um benefício prático, conforto, economia real ou situação do cotidiano."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 60
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                # Clean quotes, symbols and newlines
                text = text.replace('"', '').replace("'", '').replace("💬", "").replace("\n", " ").strip()
                if 5 < len(text) < 160:
                    return text
    except Exception as e:
        print(f"[IA Gemini] Fallback para gerador dinâmico: {e}")

    return ""

# Rich contextual category phrases for offline fallback
COMMENT_CATEGORIES = [
    (
        "calcados_tenis",
        ["tênis", "tenis", "sneaker", "ultimashow", "running", "corrida", "caminhada", "olympikus", "mizuno", "adidas", "nike", "asics", "puma"],
        [
            "Pisando nas nuvens e com o bolso intacto, conforto absurdo pro dia a dia! 👟",
            "Aquele tênis coringa pra bater no treino ou passear no fim de semana! 🏃‍♀️",
            "Amortecimento de primeira pagando preço de calçado de feira! 👟✨",
            "Visual esportivo impecável sem ter que deixar o salário na loja do shopping! 🏃‍♂️",
            "Conforto garantido pros seus pés aguentarem a correria da semana! 👟💨",
            "Tênis de marca famosa com quase metade do preço é achado dos raros! 🔥👟",
            "Pra quem não abre mão de estilo no rolê e conforto na caminhada! 🚶‍♂️👟"
        ]
    ),
    (
        "sandalias_chinelos",
        ["chinelo", "sandália", "sandalia", "havaianas", "slide", "crocs", "rasteirinha", "tamanco", "papete"],
        [
            "Descanso merecido pros pés com muito estilo e precinho amigo! 👡",
            "Aquele chinelo que não sai mais do seu pé nos dias de calor! ☀️🩴",
            "Praticidade e leveza pra relaxar em casa ou curtir um passeio tranquilo! 🏖️",
            "Básico, resistente e perfeito pro dia a dia pagando quase nada! 🩴✨"
        ]
    ),
    (
        "audio",
        ["fone", "bluetooth", "headphone", "headset", "caixa de som", "som", "tws", "earphone", "soundbar", "alto-falante", "jbl"],
        [
            "Pra você curtir sua playlist favorita ou fingir que não tá ouvindo ninguém! 🎧",
            "Música no talo e zero fios pra atrapalhar o seu treino ou faxina! 🎵",
            "Aquele som de cinema direto no seu ouvido por preço de banana! 🎶",
            "Perfeito pra treinar, trabalhar ou maratonar vídeos em paz! 🔊",
            "Isolamento acústico de qualidade pra focar no que realmente importa! 🎼",
            "Bateria de longa duração e graves que fazem a diferença! 🎧⚡",
            "Conexão rápida no celular e som limpinho sem chiado! 🎶✨"
        ]
    ),
    (
        "cozinha_eletro",
        ["air fryer", "panela", "fritadeira", "liquidificador", "cafeteira", "batedeira", "fogão", "cooktop", "micro-ondas", "processador", "grill", "sanduicheira", "chaleira"],
        [
            "A desculpa que faltava pra virar masterchef sem passar sufoco na pia! 🧑‍🍳",
            "Comida rápida, gostosa e sem fazer aquela bagunça na cozinha! 🍟",
            "Quem cozinha sabe: ter uma dessas em casa é um caminho sem volta! ☕",
            "Pra agilizar seu almoço e você ter mais tempo livre no sofá! 🍲",
            "Praticidade pura pra quem não tem tempo a perder na cozinha! 🍳",
            "Café quentinho ou almoço pronto em minutos sem complicação! ☕✨",
            "Cozinha equipada com eletro moderno pagando precinho de liquidação! 🏠🍳"
        ]
    ),
    (
        "cozinha_utensilios",
        ["pote", "frigideira", "faca", "tábua", "escorredor", "refratário", "copo", "garrafa", "térmico", "stanley", "prato", "talher"],
        [
            "Aquele kit que deixa qualquer armário organizado e com cara de novo! 🍽️",
            "Praticidade pura pra preparar e guardar suas refeições do dia! 🥗",
            "Bebida gelada o dia inteiro pra você enfrentar o calor com estilo! 🧊🥤",
            "Utensílio resistente pra facilitar sua vida na hora de servir! 🍴"
        ]
    ),
    (
        "beleza_cabelos",
        ["creme", "shampoo", "condicionador", "cachos", "skincare", "sérum", "serum", "hidratante", "progressiva", "cabelo", "máscara", "mascara", "óleo", "oleo", "cauterização"],
        [
            "Dia de spa em casa e autoestima lá no teto sem esvaziar o bolso! ✨",
            "Aquele glow que você merece pagando uma pechincha! 💅",
            "Seu momento de autocuidado garantido com precinho de atacado! 💆‍♀️",
            "Cabelo brilhoso e sedoso sem ter que pagar fortuna no salão! 🌸",
            "Tratamento profissional no conforto do seu banho! 🧴✨",
            "Cronograma capilar em dia pagando muito menos do que na farmácia! 🧖‍♀️"
        ]
    ),
    (
        "beleza_make_perfume",
        ["maquiagem", "batom", "rímel", "rimel", "perfume", "delineador", "esmalte", "base", "corretivo", "paleta", "blush", "gloss"],
        [
            "Pra ficar maravilhosa(o) e cheirosa(o) o dia inteiro gastando pouco! 💄",
            "Fragrância marcante que arranca elogios por onde passa! 🌸✨",
            "Make duradoura pra realçar sua beleza sem pesar no orçamento! 💋",
            "Aquele produtinho milagroso que não pode faltar na sua bolsa! 👛✨"
        ]
    ),
    (
        "ferramentas",
        ["solda", "inversora", "furadeira", "parafusadeira", "trena", "alicate", "chave", "ferramenta", "disco", "martelete", "lixadeira", "esmerilhadeira", "jogo de ferramentas"],
        [
            "Pra você resolver tudo em casa e ainda se gabar que economizou no conserto! 🛠️",
            "Brinquedo de gente grande pra deixar qualquer oficina no capricho! ⚡",
            "Equipamento bruto pra quem não gosta de passar perrengue no trampo! 🔩",
            "A ferramenta que faltava pra você virar o faz-tudo oficial da família! 🧰",
            "Dureza mesmo é ver esse desconto e deixar passar! 🔧💥",
            "Agilidade total nos reparos com ferramenta potente e resistente! ⚡🔨"
        ]
    ),
    (
        "tech_celular_smartwatch",
        ["smartwatch", "relógio", "relogio", "carregador", "cabo", "suporte", "tablet", "power bank", "indução", "magnético", "capa", "película", "xiaomi", "apple", "samsung"],
        [
            "Aquele upgrade esperto no seu dia a dia pra você nunca mais ficar na mão! 📱",
            "Tecnologia de ponta por um precinho que cabe até no troco do pão! ⌚",
            "Pra quem não vive sem bateria e ama uma novidade tecnológica! 🔋",
            "Monitore seus passos, mensagens e saúde no pulso com muito estilo! ⌚✨",
            "Acessório indispensável pra quem vive conectado e não para um minuto! 🔌⚡"
        ]
    ),
    (
        "informatica",
        ["teclado", "mouse", "monitor", "notebook", "gabinete", "ssd", "memória", "headset gamer", "cadeira gamer", "mousepad"],
        [
            "Mais produtividade pro trabalho e muito mais FPS pros seus jogos! 💻🎮",
            "Setup renovado e estiloso sem comprometer o orçamento do mês! 🖥️✨",
            "Velocidade pura pro seu computador voar e nunca mais travar! ⚡💾",
            "Ergonomia e conforto pra passar horas no computador sem dor nas costas! 💺🖱️"
        ]
    ),
    (
        "pet",
        ["tapete higiênico", "tapete higienico", "ração", "racao", "coleira", "gato", "cachorro", "pet", "brinquedo pet", "cama pet", "arranhador", "petisco", "sachê"],
        [
            "Seu bichinho merece esse mimo e o seu bolso agradece o desconto! 🐾",
            "Aquele carinho em forma de presente pro verdadeiro dono da casa! 🐶🐱",
            "Mimo especial pro seu melhor amigo de quatro patas pagando pouco! 🦴",
            "Quem ama seu pet não resiste a um achadinho desse! 🐾✨",
            "Aquele agrado que deixa qualquer rabo abanando de felicidade! 🐕❤️"
        ]
    ),
    (
        "casa_limpeza",
        ["aspirador", "robô", "robo", "mop", "vassoura", "balde", "organizador", "varal", "passadeira", "ferro de passar"],
        [
            "Faxina rápida e casa brilhando sem você quebrar a coluna! 🧹✨",
            "Praticidade que devolve suas horas de descanso no fim de semana! 🏠🛋️",
            "Tecnologia limpando o chão enquanto você assiste sua série em paz! 🤖✨",
            "Tudo no seu devido lugar com organização impecável e sem esforço! 📦🧼"
        ]
    ),
    (
        "casa_decoracao",
        ["luminária", "luminaria", "led", "cortina", "tapete", "almofada", "natal", "árvore", "arvore", "enfeite", "lâmpada", "lampada", "travesseiro", "lençol", "colcha", "ventilador"],
        [
            "Aquele toque de aconchego que vai deixar sua casa com cara de Pinterest! 🏡",
            "Pra renovar o ambiente sem precisar de reforma nem gastar rios de dinheiro! 🛋️",
            "Deixe seu cantinho muito mais bonito e estiloso com esse achadinho! ✨",
            "A casa fica linda, moderna e o bolso nem sente a diferença! 🌿",
            "Conforto puro pra você dormir igual a um bebê todas as noites! 🛌💤"
        ]
    ),
    (
        "moda_vestuario",
        ["camisa", "camiseta", "calça", "calca", "vestido", "bolsa", "mochila", "bermuda", "cueca", "meia", "jaqueta", "casaco", "pijama"],
        [
            "Look novo garantido sem ter que esperar o décimo terceiro cair! 👗✨",
            "Conforto e elegância pro dia a dia pagando preço de feirinha! 👕",
            "Pra renovar o guarda-roupa com aquela sensação gostosa de pagar pouco! 🛍️",
            "Peça coringa pra você andar sempre no estilo gastando quase nada! 👖🕶️",
            "Tecido leve, corte moderno e caimento perfeito pro rolê! ✨👚"
        ]
    )
]

GENERIC_COMMENTS = [
    "Aquele achado de ouro que a gente só vê uma vez e não pode deixar passar! 💸",
    "Preço tão baixo que quase parece brincadeira de mau gosto! 👀🔥",
    "Se você estava esperando um sinal pra comprar, considere que o sinal é esse! 🚨",
    "Quem viu, viu... quem piscou, perdeu a promoção relâmpago! 🏃💨",
    "Aquele clássico: bom, bonito e pagando muito menos do que vale! 💥",
    "Aquele empurrãozinho de leve pro seu carrinho de compras agradecer! 🛒✨",
    "Economia pura num item super útil pro seu dia a dia render mais! 🎯",
    "Promoção relâmpago que faz os olhos brilharem e o bolso sorrir! ⭐💰",
    "Desconto pesado no que realmente vale a pena ter em casa! 🛍️🔥",
    "Pechincha daquelas que esgota rapidinho no estoque! ⏳⚡"
]

def get_relaxed_comment(title: str, category: str = "", platform: str = "") -> str:
    """
    Generates an engaging, contextual 1-sentence comment based on product name.
    1. Tries Google Gemini AI first (if GEMINI_API_KEY is configured).
    2. Falls back to the rich dynamic category engine with 60-item anti-repetition memory.
    """
    # 1. Try Gemini AI if available
    ai_comment = generate_gemini_comment(title, category, platform)
    if ai_comment:
        return ai_comment

    # 2. Dynamic matching fallback
    clean_text = f"{title} {category}".lower()
    pool = None

    for cat_name, keywords, comments in COMMENT_CATEGORIES:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", clean_text) or kw in clean_text:
                pool = comments
                break
        if pool:
            break

    if not pool:
        pool = GENERIC_COMMENTS

    # Filter out recently used comments to avoid repetition
    available = [c for c in pool if c not in _recent_comments]
    if not available:
        available = pool  # fallback if all were used recently

    chosen = random.choice(available)
    _recent_comments.append(chosen)
    return chosen
