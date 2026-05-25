from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# CONFIGURAÇÕES
TELEGRAM_TOKEN = "8866992639:AAHpNpSKUlfHvEFKCc56t8U3-wl2eRhF1UU"
TELEGRAM_CHANNEL_ID = "-1003771513512"


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envie assim:\n\nPRODUTO | PREÇO | CUPOM | LINK"
    )


# GERAR COPY PROFISSIONAL
def gerar_legenda(produto, valor, cupom, link):

    # tratamento de preço com desconto
    if "/" in valor:
        partes = valor.split("/")
        preco_original = partes[0].strip()
        preco_promocional = partes[1].strip()
        preco_texto = f"💰 DE R$ {preco_original} por R$ {preco_promocional}"
    else:
        preco_texto = f"💰 Preço: R$ {valor}"

    # cupom opcional
    cupom_texto = f"🎟️ Cupom: {cupom}" if cupom else ""

    return f"""
🔥 OFERTA IMPERDÍVEL 🔥

🛒 Produto: {produto}
{preco_texto}
{cupom_texto}

⚡ Aproveite antes que acabe!

👉 Comprar agora:
{link}
"""


# RECEBER MENSAGEM
async def receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    partes = texto.split("|")

    if len(partes) != 4:
        await update.message.reply_text(
            "❌ Formato inválido!\n\nUse:\nPRODUTO | PREÇO | CUPOM | LINK"
        )
        return

    produto = partes[0].strip()
    valor = partes[1].strip()
    cupom = partes[2].strip()
    link = partes[3].strip()

    legenda = gerar_legenda(produto, valor, cupom, link)

    # resposta no privado
    await update.message.reply_text(legenda)

    # envio no canal
    await context.bot.send_message(
        chat_id=TELEGRAM_CHANNEL_ID,
        text=legenda
    )


# INICIAR BOT
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receber))

    print("🤖 Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()