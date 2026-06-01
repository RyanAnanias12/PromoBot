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
from functools import lru_cache
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urlparse
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError

load_dotenv()

TELEGRAM_TOKEN      = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ML_AFILIADO_ID      = os.getenv("ML_AFILIADO_ID", "ryanananias")

# Configuração de logging melhorada
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# Cache para requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Mensagens aleatórias
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

# Pendentes por usuário com timeout
_pendentes = {}


# ── Validação de Preço e Cupom ─────────────────────────────────────────────────
def eh_preco(s):
    """Verifica se a string é um preço (contém números, vírgula, ponto ou barra)."""
    s = s.replace("R$", "").replace("r$", "").strip()
    return bool(re.match(r'^[\d.,/\s]+$', s))


def eh_cupom(s):
    """Verifica se a string é um cupom (texto curto sem links e sem ser preço)."""
    s = s.strip()
    return (
        bool(s)
        and not eh_preco(s)
        and "http" not in s.lower()
        and len(s) <= 30
        and not s.isdigit()
    )


def limpar_preco(s):
    """Remove símbolos de moeda e espaços do preço."""
    return s.replace("R$", "").replace("r$", "").strip()


def formatar_preco(preco_float):
    """Converte float para formato brasileiro (R$ 123,45)."""
    if not preco_float or preco_float <= 0:
        return ""
    return "{:,.2f}".format(preco_float).replace(",", "X").replace(".", ",").replace("X", ".")


# ── Parser de Entrada ──────────────────────────────────────────────────────────
def interpretar(texto):
    """
    Interpreta texto e retorna:
    - url: link do produto
    - cupom: cupom se tiver
    - preco_de: preço original
    - preco_por: preço promocional
    - descricao: descrição opcional
    """
    partes = [p.strip() for p in texto.split("|")]
    
    url = ""
    cupom = ""
    preco_de = ""
    preco_por = ""
    descricao = ""
    
    # Extrai o link
    for p in partes:
        if "http" in p.lower():
            url = p.strip()
            break
    
    if not url:
        return None
    
    # Processa o restante
    outras = [p for p in partes if "http" not in p.lower() and p.strip()]
    
    for parte in outras:
        parte = parte.strip()
        if not parte:
            continue
        
        # De/Por
        if "/" in parte and eh_preco(parte):
            ps = parte.split("/")
            preco_de = limpar_preco(ps[0])
            preco_por = limpar_preco(ps[1])
        # Preço sem barra
        elif eh_preco(parte):
            preco_por = limpar_preco(parte)
        # Cupom: sem espaço, até 20 caracteres
        elif eh_cupom(parte) and " " not in parte and len(parte) <= 20:
            cupom = parte
        # Texto com espaço = descrição
        else:
            descricao = parte
    
    return {
        "url": url,
        "cupom": cupom,
        "preco_de": preco_de,
        "preco_por": preco_por,
        "descricao": descricao,
    }


# ── Resoluções de URL ──────────────────────────────────────────────────────────
def resolver_url(url, timeout=10):
    """Resolve URLs curtas (meli.la)."""
    try:
        r = requests.head(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )
        return r.url
    except requests.Timeout:
        log.warning(f"Timeout ao resolver URL: {url}")
        return url
    except Exception as e:
        log.warning(f"Erro ao resolver URL: {e}")
        return url


def extrair_mlb(url):
    """Extrai o ID MLB (Mercado Livre) da URL."""
    match = re.search(r"MLB-?(\d+)", url, re.IGNORECASE)
    return "MLB" + match.group(1) if match else None


@lru_cache(maxsize=32)
def buscar_via_api(mlb_id):
    """Busca informações do produto via API oficial do ML (com cache)."""
    try:
        r = requests.get(
            f"https://api.mercadolibre.com/items/{mlb_id}",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            preco = data.get("price", 0)
            thumb = ""
            pics = data.get("pictures", [])
            
            if pics:
                thumb = pics[0].get("url", "").replace("http://", "https://")
                # Aumenta a qualidade da imagem
                thumb = re.sub(r"-[A-Z]\.jpg", "-O.jpg", thumb)
            
            return {
                "titulo": data.get("title", ""),
                "preco": preco,
                "imagem": thumb,
            }
    except requests.Timeout:
        log.warning(f"Timeout na API ML para {mlb_id}")
    except Exception as e:
        log.warning(f"Erro na API ML: {e}")
    
    return None


def buscar_via_scraping(url_real):
    """Faz scraping da página do Mercado Livre."""
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # Primeiro acessa o site pra receber cookies
        session.get("https://www.mercadolivre.com.br", timeout=8)
        
        r = session.get(url_real, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Tenta vários seletores para encontrar o título
            title_el = (
                soup.select_one("h1.ui-pdp-title")
                or soup.select_one("h1[class*='title']")
                or soup.select_one("h1")
            )
            
            # Tenta vários seletores para encontrar a imagem
            img_el = (
                soup.select_one(".ui-pdp-gallery__figure img")
                or soup.select_one("img[data-zoom]")
                or soup.select_one("img[class*='gallery']")
            )
            
            titulo = title_el.text.strip() if title_el else ""
            thumb = ""
            
            if img_el:
                thumb = (
                    img_el.get("data-zoom")
                    or img_el.get("data-src")
                    or img_el.get("src")
                    or ""
                )
                thumb = thumb.replace("http://", "https://")
            
            return {
                "titulo": titulo,
                "imagem": thumb,
            }
    except requests.Timeout:
        log.warning(f"Timeout ao fazer scraping: {url_real}")
    except Exception as e:
        log.warning(f"Erro no scraping: {e}")
    
    return None


def buscar_produto(url):
    """Busca nome e foto do produto (API + Scraping)."""
    try:
        url_real = resolver_url(url)
        mlb_id = extrair_mlb(url_real)
        
        resultado = {
            "titulo": "",
            "preco": 0,
            "imagem": "",
            "url": url_real,
            "ok": False
        }
        
        # Tenta API primeiro (mais rápido)
        if mlb_id:
            api_result = buscar_via_api(mlb_id)
            if api_result:
                resultado.update(api_result)
                resultado["ok"] = bool(resultado["titulo"])
        
        # Se API falhou, tenta scraping
        if not resultado["titulo"]:
            scrape_result = buscar_via_scraping(url_real)
            if scrape_result:
                resultado.update(scrape_result)
                resultado["ok"] = bool(resultado["titulo"])
        
        # Adiciona affiliate link
        if "?" in url_real:
            resultado["url"] = url_real + f"&afid={ML_AFILIADO_ID}"
        else:
            resultado["url"] = url_real + f"?afid={ML_AFILIADO_ID}"
        
        return resultado
    
    except Exception as e:
        log.error(f"Erro ao buscar produto: {e}")
        return {"titulo": "", "preco": 0, "imagem": "", "url": url, "ok": False}


# ── Formatação de Mensagem ─────────────────────────────────────────────────────
def formatar(nome, preco_de, preco_por, cupom, url, descricao=""):
    """Formata a mensagem final para o Telegram."""
    linhas = [random.choice(TITULOS), "", "🛒 " + nome.strip(), ""]
    
    # Descrição opcional
    if descricao:
        linhas += [descricao.strip(), ""]
    
    # Preços
    if preco_de and preco_por:
        linhas += [f"❌ DE R$ {preco_de}", f"✅ POR R$ {preco_por}"]
    elif preco_por:
        linhas.append(f"💰 R$ {preco_por}")
    elif preco_de:
        linhas.append(f"💰 R$ {preco_de}")
    
    # Cupom
    if cupom:
        linhas += ["", f"🎟️ CUPOM: {cupom.upper()}"]
    
    # CTA
    linhas += [
        "",
        random.choice(CHAMADAS),
        "",
        random.choice(CTA),
        url,
        "",
        "📦 Mercado Livre"
    ]
    
    return "\n".join(linhas)


# ── Envio para Canal ───────────────────────────────────────────────────────────
async def enviar_canal(bot, texto, imagem=""):
    """Envia mensagem para o canal (com ou sem foto)."""
    try:
        if imagem:
            await bot.send_photo(
                chat_id=TELEGRAM_CHANNEL_ID,
                photo=imagem,
                caption=texto
            )
            log.info("✅ Postado no canal com foto")
        else:
            await bot.send_message(
                chat_id=TELEGRAM_CHANNEL_ID,
                text=texto
            )
            log.info("✅ Postado no canal (texto)")
    
    except TelegramError as e:
        log.error(f"Erro ao enviar para canal: {e}")
        # Fallback: tenta sem foto
        if imagem:
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHANNEL_ID,
                    text=texto
                )
                log.info("⚠️ Fallback: postado sem foto")
            except TelegramError as e2:
                log.error(f"Fallback também falhou: {e2}")


# ── Handlers do Bot ────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start com instruções."""
    await update.message.reply_text(
        "🤖 *PromoBot Online!*\n\n"
        "*Exemplos de uso:*\n\n"
        "📌 *Só o link:*\n"
        "`https://meli.la/xxx`\n\n"
        "📌 *Link + cupom:*\n"
        "`https://meli.la/xxx | CUPOMXYZ`\n\n"
        "📌 *Link + preço:*\n"
        "`https://meli.la/xxx | 58,90`\n\n"
        "📌 *Link + de/por:*\n"
        "`https://meli.la/xxx | 129/94,90`\n\n"
        "📌 *Tudo junto:*\n"
        "`https://meli.la/xxx | CUPOMXYZ | 129/94,90`\n\n"
        "📌 *Com descrição:*\n"
        "`https://meli.la/xxx | CUPOM | 94,90 | Sem costura, kit com 6`\n\n"
        "📸 *Com foto:* manda a foto com a legenda acima",
        parse_mode="Markdown"
    )


async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler principal: recebe mensagens de texto ou foto."""
    chat_id = update.message.chat_id
    texto_raw = (update.message.caption or update.message.text or "").strip()
    texto = texto_raw.replace("\n", " ").strip()
    
    # Foto enviada
    foto_file_id = None
    if update.message.photo:
        foto_file_id = update.message.photo[-1].file_id
    
    # Valida se há texto
    if not texto:
        await update.message.reply_text(
            "❌ Envie um link ou use /start para ver as instruções.",
            parse_mode="Markdown"
        )
        return
    
    # ── Resposta a preço pendente ──────────────────────────────────────────────
    if chat_id in _pendentes and not texto.lower().startswith("http") and "|" not in texto:
        pendente = _pendentes.pop(chat_id)
        
        # Aceita o preço digitado
        preco_raw = texto.strip().replace("R$", "").replace("r$", "").strip()
        
        if not eh_preco(preco_raw):
            await update.message.reply_text(
                "❌ Isso não parece um preço. Tenta novamente:\n\n"
                "`94,90` ou `129/94,90`",
                parse_mode="Markdown"
            )
            return
        
        if "/" in preco_raw:
            ps = preco_raw.split("/")
            pendente["preco_de"] = ps[0].strip()
            pendente["preco_por"] = ps[1].strip()
        else:
            pendente["preco_por"] = preco_raw
        
        legenda = formatar(
            pendente["nome"],
            pendente["preco_de"],
            pendente["preco_por"],
            pendente["cupom"],
            pendente["url_final"],
            pendente.get("descricao", "")
        )
        
        await enviar_canal(context.bot, legenda, pendente.get("imagem_final", ""))
        await update.message.reply_text("✅ *Postado no canal!*", parse_mode="Markdown")
        return
    
    # ── Fluxo normal ───────────────────────────────────────────────────────────
    dados = interpretar(texto)
    
    if not dados:
        await update.message.reply_text(
            "❌ Link não encontrado.\n\n"
            "Manda assim:\n"
            "`https://meli.la/xxx | CUPOM | 94,90`\n\n"
            "Use /start para ver todos os formatos!",
            parse_mode="Markdown"
        )
        return
    
    msg = await update.message.reply_text("🔍 Buscando produto...")
    
    try:
        produto = buscar_produto(dados["url"])
        preco_de = dados["preco_de"]
        preco_por = dados["preco_por"]
        
        # Usa preço do ML se conseguir e não informou
        if not preco_de and not preco_por and produto.get("preco"):
            preco_por = formatar_preco(produto["preco"])
        
        nome = produto["titulo"] or "Oferta Mercado Livre"
        url_final = produto.get("url") or dados["url"]
        imagem_final = foto_file_id or produto.get("imagem") or ""
        
        # ── Pede preço se não tiver ───────────────────────────────────────────
        if not preco_de and not preco_por:
            _pendentes[chat_id] = {
                "nome": nome,
                "descricao": dados.get("descricao", ""),
                "preco_de": "",
                "preco_por": "",
                "cupom": dados["cupom"],
                "url_final": url_final,
                "imagem_final": imagem_final,
            }
            
            await msg.edit_text(
                "⚠️ *Preço não encontrado automaticamente.*\n\n"
                "Digita o preço agora:\n\n"
                "`94,90` — preço único\n"
                "`129/94,90` — de/por",
                parse_mode="Markdown"
            )
            return
        
        # ── Posta no canal ────────────────────────────────────────────────────
        legenda = formatar(
            nome,
            preco_de,
            preco_por,
            dados["cupom"],
            url_final,
            dados.get("descricao", "")
        )
        
        await enviar_canal(context.bot, legenda, imagem_final)
        
        status = "✅ *Postado no canal!*"
        if not produto.get("titulo"):
            status += "\n⚠️ _Nome não encontrado (usar o padrão)_"
        
        await msg.edit_text(status, parse_mode="Markdown")
    
    except Exception as e:
        log.error(f"Erro no processamento: {e}")
        await msg.edit_text(
            "❌ Erro ao processar. Tenta novamente!",
            parse_mode="Markdown"
        )


# ── Inicialização ──────────────────────────────────────────────────────────────
def main():
    """Inicia o bot."""
    if not TELEGRAM_TOKEN:
        log.error("❌ TELEGRAM_TOKEN não encontrado!")
        print("Cria um arquivo .env com TELEGRAM_TOKEN e TELEGRAM_CHANNEL_ID")
        return
    
    if not TELEGRAM_CHANNEL_ID:
        log.error("❌ TELEGRAM_CHANNEL_ID não encontrado!")
        print("Cria um arquivo .env com TELEGRAM_TOKEN e TELEGRAM_CHANNEL_ID")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
            receber
        )
    )
    
    log.info("🤖 PromoBot iniciado e rodando!")
    app.run_polling()


if __name__ == "__main__":
    main()
