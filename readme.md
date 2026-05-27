# 🤖 PromoBot — Achados do Telegram

Bot para postar promoções do Mercado Livre automaticamente no canal do Telegram.  
Mando o link + preço + cupom, ele busca o nome e a foto e posta formatado.

---

## 📦 O que tem nesse projeto

```
promobot/
├── promobot_simples.py   # bot principal — roda e responde no Telegram
├── .env.example          # modelo de configuração
├── requirements.txt      # dependências
└── README.md             # esse arquivo
```

---

## ⚙️ Configuração

### 1. Clone o repositório

```bash
git clone https://github.com/RyanAnanias12/PromoBot.git
cd PromoBot
```

### 2. Crie o ambiente virtual e instale as dependências

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure o .env

```bash
cp .env.example .env
```

Abra o `.env` e preencha:

```env
TELEGRAM_TOKEN=seu_token_aqui
TELEGRAM_CHANNEL_ID=-100seu_channel_id
ML_AFILIADO_ID=ryanananias
```

**Como pegar cada valor:**

| Variável | Como obter |
|---|---|
| `TELEGRAM_TOKEN` | Fala com [@BotFather](https://t.me/BotFather) → `/newbot` → copia o token |
| `TELEGRAM_CHANNEL_ID` | Encaminha uma mensagem do canal pro [@userinfobot](https://t.me/userinfobot) → copia o ID (começa com `-100`) |
| `ML_AFILIADO_ID` | Seu ID de afiliado do ML — encontra em mercadolivre.com.br/afiliados |

### 4. Adicione o bot como admin do canal

No Telegram: canal → Administradores → Adicionar administrador → busca o username do seu bot.

### 5. Rode

```bash
python promobot_simples.py
```

---

## 📱 Como usar

Manda mensagem pro bot no privado com o link do produto.

### Formatos aceitos

| Formato | Exemplo |
|---|---|
| Só o link | `https://meli.la/xxx` |
| Link + preço | `https://meli.la/xxx \| 49,90` |
| Link + de/por | `https://meli.la/xxx \| 70/49` |
| Link + cupom | `https://meli.la/xxx \| CUPOMXYZ` |
| Link + cupom + preço | `https://meli.la/xxx \| CUPOMXYZ \| 49,90` |
| Link + de/por + cupom | `https://meli.la/xxx \| CUPOMXYZ \| 70/49` |
| Com descrição | `https://meli.la/xxx \| 70/49 \| descrição do produto` |
| Com foto | Manda a foto com a legenda no formato acima |

> Cupom e preço são sempre **opcionais**. Se não informar o preço e o bot não conseguir buscar automaticamente, ele vai pedir pra você digitar antes de postar.

### Exemplos reais

```
https://meli.la/2T5ZArf | | 70 / 49 | Garrafa Térmica 1000ml Inox
```

```
https://meli.la/2sfbxZ2 | MODAMELI | 299,99/110,41
```

```
https://meli.la/29Yu2e5 | MLPRACASA | 429,90/284
```

### Mensagem gerada no canal

```
🔥 OFERTA IMPERDÍVEL 🔥

🛒 Kit 6 Cuecas Boxer Lupo Poliamida

Sem costura, kit com 6 peças coloridas

❌ DE R$ 299,99
✅ POR R$ 110,41

🎟️ CUPOM: MODAMELI

⚡ Aproveite antes que acabe!

👉 Comprar agora:
https://meli.la/xxx

📦 Mercado Livre
```

---

## 🚀 Rodar 24/7 de graça

### Opção 1 — Oracle Cloud Free Tier (recomendado)

1. Cria conta em [oracle.com/cloud/free](https://oracle.com/cloud/free)
2. Cria uma VM Ubuntu (Always Free — 1 OCPU, 6GB RAM)
3. Instala o Docker:
```bash
curl -fsSL https://get.docker.com | sh
```
4. Sobe com PM2:
```bash
npm install -g pm2
pm2 start promobot_simples.py --interpreter python3 --name promobot
pm2 save && pm2 startup
```

### Opção 2 — Replit (mais fácil)

1. Acessa [replit.com](https://replit.com) e cria conta
2. New Repl → Python → cola o código
3. Adiciona as variáveis de ambiente nas Secrets do Replit
4. Clica Run — fica online mesmo com PC desligado

---

## 🔧 Requisitos

- Python 3.11+
- pip

### Dependências

```
python-telegram-bot==22.7
python-dotenv==1.0.1
requests==2.32.3
beautifulsoup4==4.12.3
```

---

## 📊 Próximas features (Fase 1)

- [ ] Painel web para cadastrar e agendar posts
- [ ] Agendador automático — posta nos horários de pico (12h, 18h, 21h)
- [ ] Rastreamento de cliques por post
- [ ] Estatísticas: top posts, cliques totais, média por post

---

## 🤝 Afiliado

Os links gerados já incluem o ID de afiliado configurado no `.env`.  
Cadastre-se em [mercadolivre.com.br/afiliados](https://www.mercadolivre.com.br/afiliados) pra monetizar os cliques.

---

## ⚠️ Aviso

Nunca suba o arquivo `.env` pro GitHub — ele contém seus tokens.  
O `.gitignore` já está configurado pra bloquear isso.