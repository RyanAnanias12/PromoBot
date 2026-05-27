# Bot de promoções do Mercado Livre para o Telegram
# Mando link + o que tiver (cupom, preço, foto) — ele detecta automaticamente
#
# Formatos aceitos (qualquer ordem após o link):
#   https://meli.la/xxx
#   https://meli.la/xxx | CUPOMXYZ
#   https://meli.la/xxx | 58,90
#   https://meli.la/xxx | CUPOMXYZ | 58,90
#   https://meli.la/xxx | 129/94,90
#   https://meli.la/xxx | CUPOMXYZ | 129/94,90
#
# Com foto: manda a foto com a legenda no formato acima
#
# Instalar: pip install python-telegram-bot python-dotenv requests beautifulsoup4
# Rodar: python promobot_simples.py

import re
import os
import random
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ML_AFILIADO_ID      = os.getenv("ML_AFILIADO_ID", "ryanananias")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# títulos e chamadas aleatórias pra não ficar repetitivo
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
    "🚨 Tá valendo muito a pena!",
    "🤑 Chance perfeita pra economizar!",
]

CTA = [
    "👉 Comprar agora:",
    "🛒 Garanta o seu:",
    "⚡ Aproveitar promoção:",
    "🔥 Conferir desconto:",
]


# ── detecta se uma string é um cupom ou um preço ───────────────────────────────
def eh_preco(s):
    # preço tem número, vírgula ou ponto, e pode ter barra (de/por)
    s = s.replace("R$", "").replace("r$", "").strip()
    return bool(re.match(r'^[\d.,/\s]+$', s))

def eh_cupom(s):
    # cupom é texto sem número puro — geralmente letras maiúsculas ou mix
    s = s.strip()
    return bool(s) and not eh_preco(s) and "http" not in s and len(s) <= 30

def limpar_preco(s):
    return s.replace("R$", "").replace("r$", "").strip()


# ── interpreta qualquer formato que eu mandar ──────────────────────────────────
def interpretar(texto):
    """
    Recebe o texto e retorna:
    - url: link do produto
    - cupom: cupom se tiver, senão vazio
    - preco_de: preço original se tiver, senão vazio
    - preco_por: preço promocional ou único
    """
    partes = [p.strip() for p in texto.split("|")]

    url      = ""
    cupom    = ""
    preco_de = ""
    preco_por = ""

    # primeiro passo: acho o link
    for p in partes:
        if "http" in p:
            url = p.strip()
            break

    if not url:
        return None

    # segundo passo: processo o restante das partes
    outras = [p for p in partes if "http" not in p and p.strip()]

    descricao = ""

    for parte in outras:
        parte = parte.strip()
        if not parte:
            continue

        # se tiver barra, é de/por
        if "/" in parte and eh_preco(parte):
            ps        = parte.split("/")
            preco_de  = limpar_preco(ps[0])
            preco_por = limpar_preco(ps[1])

        # se for preço sem barra
        elif eh_preco(parte):
            preco_por = limpar_preco(parte)

        # cupom: sem espaço, até 20 chars
        elif eh_cupom(parte) and " " not in parte and len(parte) <= 20:
            cupom = parte

        # texto com espaço = descrição do produto
        else:
            descricao = parte

    return {
        "url":       url,
        "cupom":     cupom,
        "preco_de":  preco_de,
        "preco_por": preco_por,
        "descricao": descricao,
    }


# ── resolve URL curta tipo meli.la ─────────────────────────────────────────────
def resolver_url(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except Exception:
        return url


# ── extrai o código MLB do produto ─────────────────────────────────────────────
def extrair_mlb(url):
    match = re.search(r"MLB-?(\d+)", url, re.IGNORECASE)
    return "MLB" + match.group(1) if match else None


# ── busca nome e foto do produto no ML ─────────────────────────────────────────
def buscar_produto(url):
    url_real = resolver_url(url)
    mlb_id   = extrair_mlb(url_real)

    # tentativa 1: API oficial do ML
    if mlb_id:
        try:
            r = requests.get(
                "https://api.mercadolibre.com/items/" + mlb_id,
                timeout=10
            )
            if r.status_code == 200:
                data  = r.json()
                preco = data.get("price", 0)
                thumb = ""
                pics  = data.get("pictures", [])
                if pics:
                    thumb = pics[0].get("url", "").replace("http://", "https://")
                    thumb = re.sub(r"-[A-Z]\.jpg", "-O.jpg", thumb)
                link_aff = (
                    "https://www.mercadolivre.com.br/p/" + mlb_id
                    + "?" + urlencode({"afid": ML_AFILIADO_ID})
                )
                return {"titulo": data.get("title", ""), "preco": preco, "imagem": thumb, "url": link_aff, "ok": True}
        except Exception as e:
            log.warning("API ML falhou: %s", e)

    # tentativa 2: scraping da página
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        session.get("https://www.mercadolivre.com.br", timeout=8)
        r = session.get(url_real, timeout=15)
        if r.status_code == 200:
            soup     = BeautifulSoup(r.text, "html.parser")
            title_el = soup.select_one("h1.ui-pdp-title") or soup.select_one("h1")
            img_el   = soup.select_one(".ui-pdp-gallery__figure img") or soup.select_one("img")
            titulo   = title_el.text.strip() if title_el else ""
            thumb    = ""
            if img_el:
                thumb = img_el.get("data-zoom") or img_el.get("data-src") or img_el.get("src") or ""
                thumb = thumb.replace("http://", "https://")
            link_aff = url_real + ("&" if "?" in url_real else "?") + urlencode({"afid": ML_AFILIADO_ID})
            if titulo:
                return {"titulo": titulo, "preco": 0, "imagem": thumb, "url": link_aff, "ok": True}
    except Exception as e:
        log.warning("Scraping falhou: %s", e)

    return {"titulo": "", "preco": 0, "imagem": "", "url": url_real, "ok": False}


# ── monta a mensagem final ─────────────────────────────────────────────────────
def formatar(nome, preco_de, preco_por, cupom, url, descricao=""):
    linhas = [random.choice(TITULOS), "", "🛒 " + nome.strip(), ""]

    # descrição opcional embaixo do nome
    if descricao:
        linhas += [descricao.strip(), ""]

    if preco_de and preco_por:
        linhas += ["❌ DE R$ " + preco_de, "✅ POR R$ " + preco_por]
    elif preco_por:
        linhas.append("💰 R$ " + preco_por)
    elif preco_de:
        linhas.append("💰 R$ " + preco_de)

    # cupom só aparece se eu informar — não é obrigatório
    if cupom:
        linhas += ["", "🎟️ CUPOM: " + cupom.upper()]

    linhas += ["", random.choice(CHAMADAS), "", random.choice(CTA), url, "", "📦 Mercado Livre"]
    return "\n".join(linhas)


# ── envia pro canal (com ou sem foto) ─────────────────────────────────────────
async def enviar_canal(bot, texto, imagem=""):
    try:
        if imagem:
            await bot.send_photo(chat_id=TELEGRAM_CHANNEL_ID, photo=imagem, caption=texto)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=texto)
        log.info("Postado no canal.")
    except Exception as e:
        log.error("Erro ao enviar: %s", e)
        # fallback sem foto
        try:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=texto)
        except Exception as e2:
            log.error("Fallback também falhou: %s", e2)


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *PromoBot Online!*\n\n"
        "Manda só o link:\n"
        "`https://meli.la/xxx`\n\n"
        "Link + cupom:\n"
        "`https://meli.la/xxx | CUPOMXYZ`\n\n"
        "Link + preço:\n"
        "`https://meli.la/xxx | 58,90`\n\n"
        "Link + de/por:\n"
        "`https://meli.la/xxx | 129/94,90`\n\n"
        "Tudo junto:\n"
        "`https://meli.la/xxx | CUPOMXYZ | 129/94,90`\n\n"
        "Com descrição:\n"
        "`https://meli.la/xxx | CUPOM | 94,90 | Sem costura, kit com 6 peças`\n\n"
        "Com foto: manda a foto com a legenda acima 📸",
        parse_mode="Markdown"
    )


# ── guarda contexto pendente enquanto espera o preço ───────────────────────────
# chave = chat_id, valor = dict com dados do post aguardando preço
_pendentes = {}


# ── recebe texto ou foto ────────────────────────────────────────────────────────
async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id   = update.message.chat_id
    texto_raw = (update.message.caption or update.message.text or "").strip()
    texto     = texto_raw.replace("\n", " ").strip()

    foto_file_id = None
    if update.message.photo:
        foto_file_id = update.message.photo[-1].file_id

    # ── verifica se é resposta de preço pendente ────────────────────────────────
    if chat_id in _pendentes and not texto.startswith("http") and "|" not in texto:
        pendente = _pendentes.pop(chat_id)

        # aceita o preço que eu digitar agora
        preco_raw = texto.strip().replace("R$","").replace("r$","").strip()

        if "/" in preco_raw:
            ps = preco_raw.split("/")
            pendente["preco_de"]  = ps[0].strip()
            pendente["preco_por"] = ps[1].strip()
        else:
            pendente["preco_por"] = preco_raw

        legenda = formatar(
            pendente["nome"], pendente["preco_de"], pendente["preco_por"],
            pendente["cupom"], pendente["url_final"], pendente.get("descricao","")
        )
        await enviar_canal(context.bot, legenda, pendente.get("imagem_final",""))
        await update.message.reply_text("✅ *Postado no canal!*", parse_mode="Markdown")
        return

    # ── fluxo normal ────────────────────────────────────────────────────────────
    dados = interpretar(texto)

    if not dados:
        await update.message.reply_text(
            "❌ Não encontrei um link válido.\n\n"
            "Manda assim:\n"
            "`https://meli.la/xxx | CUPOM | 94,90`\n\n"
            "Cupom e preço são opcionais!",
            parse_mode="Markdown"
        )
        return

    msg = await update.message.reply_text("🔍 Buscando produto...")

    produto  = buscar_produto(dados["url"])
    preco_de = dados["preco_de"]
    preco_por = dados["preco_por"]

    # usa o preço do ML se conseguiu buscar e eu não informei
    if not preco_de and not preco_por and produto.get("preco"):
        preco_por = (
            "{:,.2f}".format(produto["preco"])
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    nome      = produto["titulo"] if produto.get("titulo") else "Oferta Mercado Livre"
    url_final = produto.get("url") or dados["url"]
    imagem_final = foto_file_id or produto.get("imagem") or ""

    # ── se não tiver preço nenhum, pede antes de postar ────────────────────────
    if not preco_de and not preco_por:
        _pendentes[chat_id] = {
            "nome":        nome,
            "descricao":   dados.get("descricao",""),
            "preco_de":    "",
            "preco_por":   "",
            "cupom":       dados["cupom"],
            "url_final":   url_final,
            "imagem_final": imagem_final,
        }
        await msg.edit_text(
            "⚠️ *Não encontrei o preço automaticamente.*\n\n"
            "Digita o preço agora pra eu postar:\n\n"
            "`94,90` — preço único\n"
            "`129,90/94,90` — de/por",
            parse_mode="Markdown"
        )
        return

    legenda = formatar(nome, preco_de, preco_por, dados["cupom"], url_final, dados.get("descricao",""))
    await enviar_canal(context.bot, legenda, imagem_final)

    status = "✅ *Postado no canal!*"
    if not produto.get("titulo"):
        status += "\n⚠️ _Nome não encontrado automaticamente_"

    await msg.edit_text(status, parse_mode="Markdown")


# ── inicia o bot ───────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN não encontrado! Cria o .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receber))

    log.info("🤖 PromoBot rodando!")
    app.run_polling()


if __name__ == "__main__":
    main()