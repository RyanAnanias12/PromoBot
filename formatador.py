# monta as mensagens de texto para Telegram e TikTok
# separei aqui pra facilitar customizar o layout sem mexer no bot

import random

TITULOS = [
    "🔥 OFERTA IMPERDÍVEL 🔥",
    "🚨 PROMOÇÃO INSANA 🚨",
    "💥 SUPER DESCONTO 💥",
    "⚡ ACHADINHO DO DIA ⚡",
    "🤑 PREÇO MUITO BAIXO 🤑",
    "🚀 PROMOÇÃO RELÂMPAGO 🚀",
]

CHAMADAS = [
    "⚡ Aproveite antes que acabe!",
    "🔥 Corre porque pode acabar!",
    "💸 Excelente oportunidade!",
    "🛒 Ótimo preço pra levar!",
    "🤑 Chance perfeita pra economizar!",
]

CTA = [
    "👉 Comprar agora:",
    "🛒 Garanta o seu:",
    "⚡ Aproveitar promoção:",
    "🔥 Conferir desconto:",
]


def telegram(oferta: dict) -> str:
    """Formata mensagem para o canal Telegram."""
    nome      = oferta.get("titulo", "Oferta Mercado Livre")
    preco_de  = oferta.get("preco_de", "")
    preco_por = oferta.get("preco_por", "")
    cupom     = oferta.get("cupom", "")
    descricao = oferta.get("descricao", "")
    url       = oferta.get("url", "")

    linhas = [random.choice(TITULOS), "", "🛒 " + nome.strip(), ""]

    if descricao:
        linhas += [descricao.strip(), ""]

    if preco_de and preco_por:
        linhas += [
            "❌ DE R$ " + preco_de,
            "✅ POR R$ " + preco_por,
        ]
    elif preco_por:
        linhas.append("💰 R$ " + preco_por)
    elif preco_de:
        linhas.append("💰 R$ " + preco_de)

    if cupom:
        linhas += ["", "🎟️ CUPOM: " + cupom.upper()]

    linhas += [
        "",
        random.choice(CHAMADAS),
        "",
        random.choice(CTA),
        url,
        "",
        "📦 Mercado Livre",
    ]
    return "\n".join(linhas)


def tiktok(oferta: dict) -> str:
    """Gera legenda pronta pra copiar e usar no TikTok."""
    nome      = oferta.get("titulo", "")
    preco_de  = oferta.get("preco_de", "")
    preco_por = oferta.get("preco_por", "")
    cupom     = oferta.get("cupom", "")

    linhas = [
        "🔥 " + nome[:80] if nome else "🔥 Oferta imperdível no ML!",
        "",
    ]

    if preco_de and preco_por:
        linhas += [f"De R$ {preco_de} por R$ {preco_por} 😱"]
    elif preco_por:
        linhas += [f"Por apenas R$ {preco_por} 🤑"]

    if cupom:
        linhas += [f"Cupom: {cupom.upper()}"]

    linhas += [
        "",
        "🔗 Link na bio!",
        "",
        "#mercadolivre #oferta #promocao #achados #economizar #compras",
    ]
    return "\n".join(linhas)
