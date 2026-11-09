import random
import re

COMMENT_CATEGORIES = [
    (
        "pet",
        ["tapete higiênico", "tapete higienico", "ração", "racao", "coleira", "gato", "cachorro", "pet", "brinquedo pet", "cama pet", "arranhador", "petisco"],
        [
            "Seu bichinho merece esse mimo e o seu bolso agradece o desconto! 🐾",
            "Aquele carinho em forma de presente pro verdadeiro dono da casa! 🐶🐱",
            "Mimo especial pro seu melhor amigo de quatro patas pagando pouco! 🦴",
            "Quem ama seu pet não resiste a um achadinho desse! 🐾✨"
        ]
    ),
    (
        "audio",
        ["fone", "bluetooth", "headphone", "headset", "caixa de som", "som", "tws", "earphone", "soundbar", "alto-falante"],
        [
            "Pra você curtir sua playlist favorita ou fingir que não tá ouvindo ninguém! 🎧",
            "Música no talo e zero fios pra atrapalhar o seu dia! 🎵",
            "Aquele som de cinema direto no seu ouvido por preço de banana! 🎶",
            "Perfeito pra treinar, trabalhar ou maratonar vídeos em paz! 🔊"
        ]
    ),
    (
        "cozinha",
        ["air fryer", "panela", "fritadeira", "liquidificador", "cafeteira", "batedeira", "fogão", "cooktop", "micro-ondas", "processador", "grill", "sanduicheira", "arroz", "chaleira"],
        [
            "A desculpa que faltava pra virar masterchef sem passar sufoco na pia! 🧑‍🍳",
            "Comida rápida, gostosa e sem fazer aquela bagunça na cozinha! 🍟",
            "Quem cozinha sabe: ter uma dessas em casa é um caminho sem volta! ☕",
            "Pra agilizar seu almoço e você ter mais tempo livre no sofá! 🍲"
        ]
    ),
    (
        "beleza",
        ["creme", "shampoo", "cachos", "skincare", "sérum", "serum", "hidratante", "progressiva", "maquiagem", "cabelo", "protetor", "clareador", "batom", "rímel", "perfume", "delineador", "esmalte", "cauterização"],
        [
            "Dia de spa em casa e autoestima lá no teto sem esvaziar o bolso! ✨",
            "Aquele glow que você merece pagando uma pechincha! 💅",
            "Seu momento de autocuidado garantido com precinho de atacado! 💆‍♀️",
            "Pra ficar linda(o) e cheirosa(o) sem deixar o salário na farmácia! 🌸"
        ]
    ),
    (
        "ferramentas",
        ["solda", "inversora", "furadeira", "parafusadeira", "trena", "alicate", "chave", "ferramenta", "disco", "martelete", "lixadeira", "esmerilhadeira"],
        [
            "Pra você resolver tudo em casa e ainda se gabar que economizou no conserto! 🛠️",
            "Brinquedo de gente grande pra deixar qualquer oficina no capricho! ⚡",
            "Equipamento bruto pra quem não gosta de passar perrengue no trampo! 🔩",
            "A ferramenta que faltava pra você virar o faz-tudo da família! 🧰"
        ]
    ),
    (
        "tech",
        ["smartwatch", "relógio", "relogio", "carregador", "cabo", "suporte", "tablet", "teclado", "mouse", "power bank", "indução", "magnético"],
        [
            "Aquele upgrade esperto no seu dia a dia pra você nunca mais ficar na mão! 📱",
            "Tecnologia de ponta por um precinho que cabe até no troco do pão! ⌚",
            "Pra quem não vive sem bateria e ama uma novidade tecnológica! 🔋",
            "Praticidade pura pro seu dia render muito mais! 💻"
        ]
    ),
    (
        "esportes",
        ["patinete", "bicicleta", "scooter", "elétrico", "eletrico", "academia", "elástico", "corda", "garrafa", "whey", "creatina", "halter", "luva"],
        [
            "Chega de trânsito ou preguiça, agora o foco tá garantido! 🛴",
            "Aquele empurrãozinho que faltava pra você sair do sedentarismo com estilo! 🏃‍♂️",
            "Economia de combustível e diversão pura pro seu dia a dia! 🚴",
            "Pra dar aquele gás na saúde pagando preço de liquidação! 💪"
        ]
    ),
    (
        "moda",
        ["tênis", "tenis", "chinelo", "sandália", "sandalia", "camisa", "camiseta", "calça", "calca", "vestido", "bolsa", "mochila", "bermuda", "cueca", "meia"],
        [
            "Look novo garantido sem ter que esperar o décimo terceiro cair! 👟",
            "Conforto e estilo pro dia a dia pagando preço de feirinha! 👗",
            "Pra renovar o guarda-roupa com aquela sensação gostosa de pagar pouco! 🛍️",
            "Estilo puro pra você desfilar por aí no precinho da economia! 🕶️"
        ]
    ),
    (
        "casa",
        ["luminária", "luminaria", "led", "cortina", "tapete", "almofada", "natal", "árvore", "arvore", "enfeite", "lâmpada", "lampada", "travesseiro", "lençol", "colcha", "ventilador", "organizador"],
        [
            "Aquele toque de aconchego que vai deixar sua casa com cara de Pinterest! 🏡",
            "Pra renovar o ambiente sem precisar de reforma nem gastar rios de dinheiro! 🛋️",
            "Deixe seu cantinho muito mais bonito e estiloso com esse achadinho! ✨",
            "A casa fica linda e o bolso nem sente a diferença! 🌿"
        ]
    )
]

GENERIC_COMMENTS = [
    "Aquele achado de ouro que a gente só vê uma vez e não pode deixar passar! 💸",
    "Preço tão baixo que quase parece brincadeira de mau gosto! 👀",
    "Se você estava esperando um sinal pra comprar, considere que o sinal é esse! 🚨",
    "Quem viu, viu... quem piscou, perdeu a promoção! 🏃💨",
    "Aquele clássico: bom, bonito e pagando muito menos do que vale! 💥",
    "Aquele empurrãozinho de leve pro seu carrinho de compras agradecer! 🛒✨"
]

def get_relaxed_comment(title: str, category: str = "") -> str:
    """Generates a relaxed, contextually relevant 1-sentence comment based on product name."""
    clean_text = f"{title} {category}".lower()

    for cat_name, keywords, comments in COMMENT_CATEGORIES:
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", clean_text) or kw in clean_text:
                return random.choice(comments)

    return random.choice(GENERIC_COMMENTS)
