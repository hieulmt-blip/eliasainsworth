import os
from dotenv import load_dotenv
import ccxt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import httpx
if os.path.exists(".env"):
    load_dotenv(dotenv_path=".env", override=True)

exchange = ccxt.okx({
    "apiKey": os.getenv("OKX_API_KEY"),
    "secret": os.getenv("OKX_API_SECRET"),
    "password": os.getenv("OKX_PASSPHRASE"),
    "enableRateLimit": True,
    "options": {
        "defaultType": "spot"  
    }
})
BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Elias Ainsworth đã có mặt")
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Dùng: /price BTC/USDT hoặc /price BTC")
        return

    pair = context.args[0].upper()

    if "/" not in pair:
        pair = f"{pair}/USDT"

    try:
        ticker = exchange.fetch_ticker(pair)
        await update.message.reply_text(
            f"📈 {pair}\nGiá: {ticker['last']}"
        )
    except Exception as e:
        await update.message.reply_text(f"Lỗi: {e}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balances = exchange.fetch_balance()

        msg = "💰 TRADING BALANCE\n"
        for coin, amount in balances["total"].items():
            if amount and amount > 0:
                msg += f"{coin}: {amount}\n"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi balance: {e}")
        
async def funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balances = exchange.fetch_balance({"type": "funding"})

        msg = "💰 FUNDING BALANCE\n"
        for coin, amount in balances["total"].items():
            if amount and amount > 0:
                msg += f"{coin}: {amount}\n"

        await update.message.reply_text(msg or "Funding balance = 0")

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi funding: {e}")
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "📦 YOUR WALLET\n"

    for t in ["spot", "funding"]:
        balances = exchange.fetch_balance({"type": t})
        msg += f"\n[{t.upper()}]\n"
        for coin, amount in balances["total"].items():
            if amount and amount > 0:
                msg += f"{coin}: {amount}\n"

    await update.message.reply_text(msg)
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Dùng: /buy BTC 10")
        return

    symbol = context.args[0].upper()
    usdt = float(context.args[1])
    pair = f"{symbol}/USDT"

    try:
        price = exchange.fetch_ticker(pair)["last"]
        amount = usdt / price

        order = exchange.create_market_buy_order(pair, amount)

        await update.message.reply_text(
            f"✅ BUY MARKET\n"
            f"Cặp: {pair}\n"
            f"Số tiền: {usdt} USDT\n"
            f"Số lượng: {amount:.6f}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi buy: {e}")
async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Dùng: /sell BTC 0.001")
        return

    symbol = context.args[0].upper()
    amount = float(context.args[1])
    pair = f"{symbol}/USDT"

    try:
        order = exchange.create_market_sell_order(pair, amount)

        await update.message.reply_text(
            f"✅ SELL MARKET\n"
            f"Cặp: {pair}\n"
            f"Số lượng: {amount}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi sell: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("funding", funding))
    app.add_handler(CommandHandler("wallet", wallet))
    
    print("Bot running...")
    app.run_polling()
if __name__ == "__main__":
    main()
