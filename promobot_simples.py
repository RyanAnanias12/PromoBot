# Meu bot de promoções do Mercado Livre para o Telegram
# Criei isso pra automatizar o canal e não precisar ficar postando na mão
# Basta mandar o link do produto + cupom e ele posta tudo formatado no canal
#
# Como usar:
#   1. Copia o .env.example pra .env e preenche com seus dados
#   2. pip install -r requirements.txt
#   3. python promobot_simples.py
#   4. Manda pro bot: https://meli.la/xxx | CUPOM | preco_final

import re
import logging
import asyncio
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# carrego as variáveis do arquivo .env
# assim não preciso deixar token exposto no código
load_dotenv()

TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ML_AFILIADO_ID      = os.getenv("ML_AFILIADO_ID", "ryanananias")

# log pra eu acompanhar o que tá acontecendo no terminal
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# headers de browser pra não ser bloqueado pelo ML
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


# ── resolve URL curta tipo meli.la e pega a URL real ───────────────────────────
def resolver_url(url):
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except Exception:
        # se falhar, devolve a URL original mesmo
        return url


# ── pega o código MLB do produto dentro da URL ──────────────────────────────────
def extrair_mlb(url):
    match = re.search(r"MLB-?(\d+)", url, re.IGNORECASE)
    return "MLB" + match.group(1) if match else None


# ── busca os dados do produto no ML (nome, preço, foto) ────────────────────────
def buscar_produto(url):
    # primeiro resolvo a URL curta pra pegar a URL real
    url_real = resolver_url(url)
    mlb_id   = extrair_mlb(url_real)

    # tentativa 1: API oficial do ML, mais rápida e confiável
    if mlb_id:
        try:
            r = requests.get(
                "https://api.mercadolibre.com/items/" + mlb_id,
                timeout=10,
            )
            if r.status_code == 200:
                data  = r.json()
                preco = data.get("price", 0)

                # pega a foto em boa resolução
                thumb = ""
                pics  = data.get("pictures", [])
                if pics:
                    thumb = pics[0].get("url", "").replace("http://", "https://")
                    thumb = re.sub(r"-[A-Z]\.jpg", "-O.jpg", thumb)

                # monto o link já com meu ID de afiliado pra rastrear as comissões
                link_aff = (
                    "https://www.mercadolivre.com.br/p/" + mlb_id
                    + "?" + urlencode({"afid": ML_AFILIADO_ID})
                )

                return {
                    "titulo": data.get("title", ""),
                    "preco":  preco,
                    "imagem": thumb,
                    "url":    link_aff,
                    "mlb":    mlb_id,
                    "ok":     True,
                }
        except Exception as e:
            log.warning("API ML falhou, vou tentar scraping: %s", e)

    # tentativa 2: scraping direto da página do produto
    # uso quando a API não funciona ou o token não está configurado
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # acesso a home primeiro pra pegar os cookies, evita bloqueio
        session.get("https://www.mercadolivre.com.br", timeout=8)

        r = session.get(url_real, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            # título do produto
            title_el = (
                soup.select_one("h1.ui-pdp-title") or
                soup.select_one("h1.poly-product-title__title") or
                soup.select_one("h1")
            )

            # preço atual
            price_el = (
                soup.select_one(".ui-pdp-price__second-line .andes-money-amount__fraction") or
                soup.select_one(".poly-price__current .andes-money-amount__fraction") or
                soup.select_one(".andes-money-amount__fraction")
            )

            # foto principal
            img_el = (
                soup.select_one(".ui-pdp-gallery__figure img") or
                soup.select_one(".poly-card__portada img") or
                soup.select_one("figure img")
            )

            titulo    = title_el.text.strip() if title_el else ""
            preco_str = price_el.text.strip().replace(".", "").replace(",", ".") if price_el else "0"
            preco     = float(re.sub(r"[^\d.]", "", preco_str)) if preco_str else 0

            thumb = ""
            if img_el:
                thumb = img_el.get("data-zoom") or img_el.get("data-src") or img_el.get("src") or ""
                thumb = thumb.replace("http://", "https://")

            if mlb_id:
                link_aff = (
                    "https://www.mercadolivre.com.br/p/" + mlb_id
                    + "?" + urlencode({"afid": ML_AFILIADO_ID})
                )
            else:
                link_aff = url_real + ("&" if "?" in url_real else "?") + urlencode({"afid": ML_AFILIADO_ID})

            if titulo:
                return {
                    "titulo": titulo,
                    "preco":  preco,
                    "imagem": thumb,
                    "url":    link_aff,
                    "mlb":    mlb_id or "",
                    "ok":     True,
                }
    except Exception as e:
        log.warning("Scraping também falhou: %s", e)

    # se tudo falhou, devolvo vazio pra pedir preenchimento manual
    return {
        "titulo": "",
        "preco":  0,
        "imagem": "",
        "url":    url_real,
        "mlb":    mlb_id or "",
        "ok":     False,
    }


# ── monta o texto da mensagem que vai pro canal ─────────────────────────────────
def formatar(produto, preco_orig, preco_com_cupom, cupom, url):
    linhas = [
        "🔥 OFERTA IMPERDÍVEL 🔥",
        "",
        "🛒 " + produto,
        "",
    ]

    # mostra de/por se tiver os dois preços, ou só o preço se não tiver cupom
    if preco_orig and preco_com_cupom:
        linhas += [
            "❌ DE R$ " + preco_orig,
            "✅ Por R$ " + preco_com_cupom,
        ]
    elif preco_orig:
        linhas.append("💰 Por R$ " + preco_orig)

    # cupom só aparece se eu informar
    if cupom:
        linhas += ["", "🎟️ Cupom: " + cupom]

    linhas += [
        "",
        "⚡ Aproveite antes que acabe!",
        "",
        "👉 Comprar agora:",
        url,
        "",
        "📦 No Mercado Livre!!!",
    ]
    return "\n".join(linhas)


# ── envia a mensagem pro canal com ou sem foto ──────────────────────────────────
async def enviar_canal(bot, texto, imagem=""):
    try:
        if imagem:
            # se tiver imagem, manda como foto com o texto na legenda
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=imagem,
                caption=texto,
            )
        else:
            # sem foto, manda só o texto
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=texto,
            )
    except Exception as e:
        log.error("Erro ao enviar pro canal: %s", e)


# ── responde o /start com as instruções de uso ──────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *PromoBot ativo!*\n\n"
        "Me manda o link do produto e eu busco o nome e a foto automaticamente.\n\n"
        "*Só o link:*\n"
        "`https://meli.la/xxx`\n\n"
        "*Link + cupom:*\n"
        "`https://meli.la/xxx | CUPOM`\n\n"
        "*Link + cupom + preço final:*\n"
        "`https://meli.la/xxx | CUPOM | 94,90`\n\n"
        "É só isso! 🚀",
        parse_mode="Markdown"
    )


# ── recebe qualquer mensagem de texto e decide o que fazer ──────────────────────
async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto  = update.message.text.strip()
    partes = [p.strip() for p in texto.split("|")]

    url             = partes[0] if len(partes) >= 1 else ""
    cupom           = partes[1] if len(partes) >= 2 else ""
    preco_com_cupom = partes[2] if len(partes) >= 3 else ""

    # ── modo manual: PRODUTO | PRECO_DE/PRECO_POR | CUPOM | LINK ───────────────
    # aceito esse formato também pra quem já estava usando antes
    if len(partes) == 4 and not url.startswith("http"):
        produto_nome = partes[0]
        valor        = partes[1]
        cupom_manual = partes[2]
        link_manual  = partes[3]

        if "/" in valor:
            ps              = valor.split("/")
            preco_orig      = ps[0].strip()
            preco_com_cupom = ps[1].strip()
        else:
            preco_orig      = valor
            preco_com_cupom = ""

        legenda = formatar(produto_nome, preco_orig, preco_com_cupom, cupom_manual, link_manual)
        await update.message.reply_text("✅ Postado no canal!")
        await enviar_canal(context.bot, legenda)
        return

    # ── modo automático: manda o link e eu busco tudo ───────────────────────────
    if not url.startswith("http"):
        await update.message.reply_text(
            "❌ Manda o link do produto!\n\n"
            "Exemplo:\n`https://meli.la/2sfbxZ2 | MODAMELI | 94,90`",
            parse_mode="Markdown"
        )
        return

    # aviso enquanto busca pra não parecer que travou
    msg = await update.message.reply_text("🔍 Buscando dados do produto...")

    produto = buscar_produto(url)

    # se não conseguiu buscar, pede pra preencher na mão
    if not produto["ok"] or not produto["titulo"]:
        await msg.edit_text(
            "⚠️ Não consegui buscar os dados automaticamente.\n\n"
            "Tenta no formato manual:\n"
            "`NOME DO PRODUTO | PREÇO_DE/PREÇO_POR | CUPOM | LINK`",
            parse_mode="Markdown"
        )
        return

    titulo = produto["titulo"]
    imagem = produto["imagem"]

    # formata o preço original em real brasileiro
    preco_orig = ""
    if produto["preco"]:
        preco_orig = (
            "{:,.2f}".format(produto["preco"])
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

    legenda = formatar(titulo, preco_orig, preco_com_cupom, cupom, produto["url"])

    # confirmação pra mim no privado
    await msg.edit_text(
        "✅ *Postado no canal!*\n\n"
        "📦 " + titulo[:60] + ("..." if len(titulo) > 60 else "") + "\n"
        + ("💰 R$ " + preco_orig + (" → R$ " + preco_com_cupom if preco_com_cupom else "") + "\n")
        + ("🎟️ " + cupom if cupom else ""),
        parse_mode="Markdown"
    )

    await enviar_canal(context.bot, legenda, imagem)


# ── inicializa e deixa o bot rodando ───────────────────────────────────────────
def main():
    # checo se o token foi configurado no .env
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN não encontrado! Cria o arquivo .env com suas credenciais.")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # registro os comandos e mensagens que o bot responde
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber))

    log.info("🤖 PromoBot rodando! Manda um link pro bot no Telegram.")
    app.run_polling()


if __name__ == "__main__":
    main()