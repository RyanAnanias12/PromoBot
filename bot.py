# bot principal — junta todos os módulos
# funcionalidades:
#   - recebe link via Telegram e busca produto automaticamente
#   - mostra preview antes de postar (confirmar / editar / cancelar)
#   - posta no canal com foto
#   - gera legenda TikTok automaticamente
#   - agendador roda em background e posta nos horários do agenda.txt
#   - histórico de posts com /historico
#
# Instalar: pip install python-telegram-bot python-dotenv requests beautifulsoup4 apscheduler
# Rodar: python bot.py

import re
import os
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from ml_auth import buscar_produto_api, get_token
from formatador import telegram as fmt_telegram, tiktok as fmt_tiktok
from historico import registrar, ja_postou, listar
from agenda import ofertas_do_momento, criar_agenda_exemplo

load_dotenv()

TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ML_AFILIADO_ID      = os.getenv("ML_AFILIADO_ID", "ryanananias")
ADMIN_IDS           = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# guarda os previews pendentes por chat_id enquanto espera confirmação
_pendentes: dict = {}
# guarda contexto de quem está esperando digitar o preço
_aguardando_preco: dict = {}


# ── detectores de tipo de campo ────────────────────────────────────────────────
def eh_preco(s: str) -> bool:
    s = s.replace("R$", "").replace("r$", "").replace("Por", "").strip()
    return bool(re.match(r'^[\d.,/\s]+$', s))

def eh_cupom(s: str) -> bool:
    s = s.strip()
    return bool(s) and not eh_preco(s) and "http" not in s and len(s) <= 20 and " " not in s

def limpar_preco(s: str) -> str:
    return s.replace("R$", "").replace("r$", "").replace("Por", "").strip()


# ── interpreta o texto que eu mandei ──────────────────────────────────────────
def interpretar(texto: str) -> dict | None:
    partes = [p.strip() for p in texto.split("|")]

    url = next((p.strip() for p in partes if "http" in p), "")
    if not url:
        return None

    outras    = [p for p in partes if "http" not in p and p.strip()]
    cupom     = ""
    preco_de  = ""
    preco_por = ""
    descricao = ""

    for parte in outras:
        if not parte:
            continue
        if "/" in parte and eh_preco(parte):
            ps        = parte.split("/")
            preco_de  = limpar_preco(ps[0])
            preco_por = limpar_preco(ps[1])
        elif eh_preco(parte):
            preco_por = limpar_preco(parte)
        elif eh_cupom(parte):
            cupom = parte
        else:
            descricao = parte

    return {
        "url":      url,
        "cupom":    cupom,
        "preco_de": preco_de,
        "preco_por": preco_por,
        "descricao": descricao,
    }


# ── resolve URL curta e extrai MLB ID ─────────────────────────────────────────
def resolver_url(url: str) -> str:
    try:
        r = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url
    except Exception:
        return url

def extrair_mlb(url: str) -> str | None:
    match = re.search(r"MLB-?(\d+)", url, re.IGNORECASE)
    return "MLB" + match.group(1) if match else None


# ── busca produto no ML (API primeiro, scraping como fallback) ─────────────────
def buscar_produto(url: str) -> dict:
    url_real = resolver_url(url)
    mlb_id   = extrair_mlb(url_real)

    # API oficial
    if mlb_id:
        resultado = buscar_produto_api(mlb_id)
        if resultado.get("ok") and resultado.get("titulo"):
            link_aff = (
                f"https://www.mercadolivre.com.br/p/{mlb_id}?"
                + urlencode({"afid": ML_AFILIADO_ID})
            )
            resultado["url"] = link_aff
            return resultado

    # scraping como fallback
    try:
        s = requests.Session()
        s.headers.update(HEADERS)
        s.get("https://www.mercadolivre.com.br", timeout=8)
        r = s.get(url_real, timeout=15)
        if r.status_code == 200:
            soup     = BeautifulSoup(r.text, "html.parser")
            title_el = soup.select_one("h1.ui-pdp-title") or soup.select_one("h1")
            img_el   = soup.select_one(".ui-pdp-gallery__figure img") or soup.select_one("img")
            titulo   = title_el.text.strip() if title_el else ""
            thumb    = ""
            if img_el:
                thumb = img_el.get("data-zoom") or img_el.get("data-src") or img_el.get("src") or ""
                thumb = thumb.replace("http://", "https://")
            if titulo:
                link_aff = url_real + ("&" if "?" in url_real else "?") + urlencode({"afid": ML_AFILIADO_ID})
                return {"titulo": titulo, "preco": 0, "imagem": thumb, "url": link_aff, "ok": True}
    except Exception as e:
        log.warning("Scraping falhou: %s", e)

    return {"titulo": "", "preco": 0, "imagem": "", "url": url_real, "ok": False}


# ── envia pro canal ────────────────────────────────────────────────────────────
async def enviar_canal(bot, oferta: dict):
    texto  = fmt_telegram(oferta)
    imagem = oferta.get("imagem", "")

    try:
        if imagem:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=imagem,
                caption=texto,
            )
        else:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=texto)
        registrar(oferta)
        log.info("Postado: %s", oferta.get("titulo","")[:50])
    except Exception as e:
        log.error("Erro ao postar: %s", e)
        try:
            await bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=texto)
            registrar(oferta)
        except Exception as e2:
            log.error("Fallback falhou: %s", e2)


# ── monta teclado de confirmação ───────────────────────────────────────────────
def teclado_confirmacao(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Postar",    callback_data=f"postar:{chat_id}"),
            InlineKeyboardButton("✏️ Editar preço", callback_data=f"editar:{chat_id}"),
            InlineKeyboardButton("❌ Cancelar",  callback_data=f"cancelar:{chat_id}"),
        ]
    ])


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *PromoBot v3 Online!*\n\n"
        "Manda o link do produto e eu busco tudo:\n\n"
        "`https://meli.la/xxx`\n"
        "`https://meli.la/xxx | CUPOM`\n"
        "`https://meli.la/xxx | 70/49`\n"
        "`https://meli.la/xxx | CUPOM | 70/49`\n"
        "`https://meli.la/xxx | CUPOM | 70/49 | descrição`\n\n"
        "Antes de postar vou mostrar um *preview* pra você confirmar.\n\n"
        "Comandos:\n"
        "/historico — ver últimos posts\n"
        "/tiktok — legenda do último post pra TikTok\n"
        "/agenda — ver agenda do dia",
        parse_mode="Markdown"
    )


# ── /historico ─────────────────────────────────────────────────────────────────
async def cmd_historico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    posts = listar(10)
    if not posts:
        await update.message.reply_text("Nenhum post ainda.")
        return

    linhas = ["📋 *Últimos 10 posts:*\n"]
    for i, p in enumerate(posts, 1):
        preco = f"R$ {p['preco_por']}" if p.get("preco_por") else ""
        linhas.append(f"{i}. {p['titulo'][:45]} {preco} — {p['postado_em']}")

    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


# ── /tiktok ────────────────────────────────────────────────────────────────────
async def cmd_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    posts = listar(1)
    if not posts:
        await update.message.reply_text("Nenhum post ainda.")
        return

    legenda = fmt_tiktok(posts[0])
    await update.message.reply_text(
        "📱 *Legenda pra copiar no TikTok:*\n\n" + legenda,
        parse_mode="Markdown"
    )


# ── /agenda ────────────────────────────────────────────────────────────────────
async def cmd_agenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from agenda import ler_agenda
    ofertas = ler_agenda()
    if not ofertas:
        await update.message.reply_text(
            "Agenda vazia. Edite o arquivo `agenda.txt` na pasta do bot.",
            parse_mode="Markdown"
        )
        return

    linhas = ["📅 *Agenda de hoje:*\n"]
    for o in ofertas:
        preco = f"{o['preco_de']}/{o['preco_por']}" if o["preco_de"] else o["preco_por"]
        linhas.append(f"⏰ {o['horario']} — {o.get('descricao') or o['url'][:40]} {preco}")

    await update.message.reply_text("\n".join(linhas), parse_mode="Markdown")


# ── recebe mensagem ────────────────────────────────────────────────────────────
async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id   = update.message.chat_id
    texto_raw = (update.message.caption or update.message.text or "").strip()
    texto     = texto_raw.replace("\n", " ").strip()

    foto_file_id = None
    if update.message.photo:
        foto_file_id = update.message.photo[-1].file_id

    # ── resposta de preço pendente ──────────────────────────────────────────────
    if chat_id in _aguardando_preco and not texto.startswith("http") and "|" not in texto:
        pendente  = _aguardando_preco.pop(chat_id)
        preco_raw = texto.replace("R$","").replace("r$","").strip()

        if "/" in preco_raw:
            ps = preco_raw.split("/")
            pendente["preco_de"]  = ps[0].strip()
            pendente["preco_por"] = ps[1].strip()
        else:
            pendente["preco_por"] = preco_raw

        _pendentes[chat_id] = pendente
        preview = fmt_telegram(pendente)
        await update.message.reply_text(
            f"*Preview:*\n\n{preview}",
            parse_mode="Markdown",
            reply_markup=teclado_confirmacao(chat_id),
        )
        return

    # ── fluxo normal ────────────────────────────────────────────────────────────
    dados = interpretar(texto)
    if not dados:
        await update.message.reply_text(
            "❌ Manda o link do produto!\n`https://meli.la/xxx | CUPOM | 70/49`",
            parse_mode="Markdown"
        )
        return

    if ja_postou(dados["url"]):
        await update.message.reply_text(
            "⚠️ Esse produto já foi postado nas últimas 24h!\nUse /historico pra ver."
        )
        return

    msg = await update.message.reply_text("🔍 Buscando produto no ML...")

    produto  = buscar_produto(dados["url"])
    preco_de = dados["preco_de"]
    preco_por = dados["preco_por"]

    if not preco_de and not preco_por and produto.get("preco"):
        preco_por = (
            "{:,.2f}".format(produto["preco"])
            .replace(",","X").replace(".",",").replace("X",".")
        )

    oferta = {
        "id":        extrair_mlb(resolver_url(dados["url"])) or dados["url"][:20],
        "titulo":    produto.get("titulo") or "Oferta Mercado Livre",
        "preco_de":  preco_de,
        "preco_por": preco_por,
        "cupom":     dados["cupom"],
        "descricao": dados["descricao"],
        "url":       produto.get("url") or dados["url"],
        "imagem":    foto_file_id or produto.get("imagem") or "",
    }

    # pede o preço se não tiver nenhum
    if not preco_de and not preco_por:
        _aguardando_preco[chat_id] = oferta
        await msg.edit_text(
            f"📦 *{oferta['titulo'][:60]}*\n\n"
            "⚠️ Não encontrei o preço. Digita agora:\n\n"
            "`94,90` — preço único\n"
            "`129/94,90` — de/por",
            parse_mode="Markdown"
        )
        return

    # mostra preview com botões
    _pendentes[chat_id] = oferta
    preview = fmt_telegram(oferta)
    await msg.edit_text(
        f"*Preview:*\n\n{preview}",
        parse_mode="Markdown",
        reply_markup=teclado_confirmacao(chat_id),
    )


# ── callback dos botões ────────────────────────────────────────────────────────
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()

    acao, chat_id_str = query.data.split(":")
    chat_id = int(chat_id_str)

    if acao == "postar":
        oferta = _pendentes.pop(chat_id, None)
        if not oferta:
            await query.edit_message_text("⚠️ Post expirado. Manda o link de novo.")
            return
        await enviar_canal(context.bot, oferta)
        legenda_tt = fmt_tiktok(oferta)
        await query.edit_message_text(
            "✅ *Postado no canal!*\n\n"
            "📱 *Legenda pra copiar no TikTok:*\n\n" + legenda_tt,
            parse_mode="Markdown"
        )

    elif acao == "editar":
        oferta = _pendentes.get(chat_id)
        if not oferta:
            await query.edit_message_text("⚠️ Post expirado.")
            return
        _aguardando_preco[chat_id] = oferta
        _pendentes.pop(chat_id, None)
        await query.edit_message_text(
            "✏️ Digita o novo preço:\n\n"
            "`94,90` — preço único\n"
            "`129/94,90` — de/por",
            parse_mode="Markdown"
        )

    elif acao == "cancelar":
        _pendentes.pop(chat_id, None)
        await query.edit_message_text("❌ Post cancelado.")


# ── loop do agendador ──────────────────────────────────────────────────────────
async def verificar_agenda(bot):
    ofertas = ofertas_do_momento()
    for o in ofertas:
        if ja_postou(o["url"]):
            log.info("Agenda: já postado — %s", o["url"])
            continue
        produto = buscar_produto(o["url"])
        oferta  = {
            "id":        extrair_mlb(resolver_url(o["url"])) or o["url"][:20],
            "titulo":    produto.get("titulo") or "Oferta Mercado Livre",
            "preco_de":  o["preco_de"],
            "preco_por": o["preco_por"],
            "cupom":     o["cupom"],
            "descricao": o["descricao"],
            "url":       produto.get("url") or o["url"],
            "imagem":    produto.get("imagem") or "",
        }
        await enviar_canal(bot, oferta)
        log.info("Agenda: postado às %s — %s", o["horario"], oferta["titulo"][:50])
        await asyncio.sleep(5)


# ── main ───────────────────────────────────────────────────────────────────────
async def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN não encontrado no .env")
        return

    criar_agenda_exemplo()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("historico", cmd_historico))
    app.add_handler(CommandHandler("tiktok",    cmd_tiktok))
    app.add_handler(CommandHandler("agenda",    cmd_agenda))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receber))

    # agendador roda a cada minuto
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(
        verificar_agenda,
        "interval",
        minutes=1,
        args=[app.bot],
    )
    scheduler.start()

    log.info("🤖 PromoBot v3 iniciado!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
