import os
from fastapi import FastAPI, Request
import uvicorn
import qrcode
import io
import ccxt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters, ApplicationHandlerStop
from telegram.ext import MessageHandler, filters
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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

import json

BAL_FILE = "balances.json"

def load_balances():
    if os.path.exists(BAL_FILE):
        with open(BAL_FILE, "r") as f:
            return json.load(f)
    return {}

def save_balances(data):
    with open(BAL_FILE, "w") as f:
        json.dump(data, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # ✅ GIỮ NGUYÊN CÂU CHÀO
    await update.message.reply_text("Elias Ainsworth đã có mặt")

    # ===== CHECK GHI CÓ =====
    last_balances = load_balances()
    balance = exchange.fetch_balance({"type": "funding"})
    total = balance["total"]

    messages = []

    for coin, amount in total.items():
        if amount is None:
            continue

        old = last_balances.get(coin, amount)

        if amount > old:
            diff = amount - old
            messages.append(
                f"🔔 GHI CÓ \n+{diff:.6f} {coin}"
            )

        last_balances[coin] = amount

    save_balances(last_balances)

    if messages:
        await context.bot.send_message(
            chat_id=chat_id,
            text="\n\n".join(messages)
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📭 Báo cáo chưa có khoản ghi có mới"
        )

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

async def spot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balances = exchange.fetch_balance()

        msg = "💰 Spot Balance\n"
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

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Dùng: /deposit <coin> <chain>\n"
            "VD: /deposit USDT TRC20"
        )
        return

    coin = context.args[0].upper()
    chain_input = context.args[1].upper()

    try:
        currencies = exchange.fetch_currencies()

        if coin not in currencies:
            await update.message.reply_text(f"❌ Coin {coin} không tồn tại")
            return

        networks = currencies[coin].get("networks")
        if not networks:
            await update.message.reply_text(f"❌ {coin} không hỗ trợ nạp onchain")
            return

        # tìm chain phù hợp (fuzzy match)
        network_key = None
        for k in networks.keys():
            if chain_input in k.upper():
                network_key = k
                break

        if not network_key:
            chains = ", ".join(networks.keys())
            await update.message.reply_text(
                f"❌ Chain {chain_input} không hỗ trợ cho {coin}\n"
                f"Chain hợp lệ:\n{chains}"
            )
            return

        addr = exchange.fetch_deposit_address(
            coin,
            params={"network": network_key}
        )

        address = addr["address"]
        tag = addr.get("tag")

        # ===== TẠO QR =====
        qr_data = address
        if tag:
            qr_data += f"?memo={tag}"

        qr = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)

        caption = (
            f"📥 NẠP {coin} ({network_key})\n\n"
            f"📍 Address:\n`{address}`\n"
        )

        if tag:
            caption += f"🏷 Memo/Tag:\n`{tag}`\n"

        caption += f"\n⚠️ CHỈ gửi {coin} qua {network_key}"

        await update.message.reply_photo(
            photo=buf,
            caption=caption,
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 4:
        await update.message.reply_text(
            "Dùng:\n/transfer <coin> <amount> <from> <to>\n"
            "VD: /transfer USDT 100 trading funding"
        )
        return

    coin = context.args[0].upper()
    amount = str(context.args[1])  # OKX yêu cầu STRING
    from_acc = context.args[2].lower()
    to_acc = context.args[3].lower()

    acc_map = {
        "trading": "18",  # spot
        "funding": "6"
    }

    if from_acc not in acc_map or to_acc not in acc_map:
        await update.message.reply_text("❌ from/to chỉ dùng: trading | funding")
        return

    try:
        res = exchange.private_post_asset_transfer({
            "ccy": coin,
            "amt": amount,
            "from": acc_map[from_acc],
            "to": acc_map[to_acc],
            "type": "0"  # nội bộ OKX
        })

        await update.message.reply_text(
            f"✅ TRANSFER OKX THÀNH CÔNG\n"
            f"{amount} {coin}\n"
            f"{from_acc.upper()} → {to_acc.upper()}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi transfer: {e}")
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = exchange.fetch_balance({
            "type": "spot"   # 👈 CHỈ SPOT (TRADING)
        })

        msg = "📊 SỐ DƯ VÍ Giao dịch\n\n"
        has_balance = False

        for coin, total in balance["total"].items():
            if total and total > 0:
                free = balance["free"].get(coin, 0)
                used = balance["used"].get(coin, 0)
                msg += (
                    f"• {coin}\n"
                    f"  ├ Total: {total}\n"
                    f"  ├ Free : {free}\n"
                    f"  └ Used : {used}\n\n"
                )
                has_balance = True

        if not has_balance:
            msg += "(Ví spot trống)"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi lấy số dư spot:\n{e}")

tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("price", price))
tg_app.add_handler(CommandHandler("buy", buy))
tg_app.add_handler(CommandHandler("sell", sell))
tg_app.add_handler(CommandHandler("balance", balance))
tg_app.add_handler(CommandHandler("funding", funding))
tg_app.add_handler(CommandHandler("wallet", wallet))
tg_app.add_handler(CommandHandler("deposit", deposit))
tg_app.add_handler(CommandHandler("transfer", transfer))
tg_app.add_handler(CommandHandler("spot", spot))

# ===== FASTAPI WEBHOOK =====

fastapi_app = FastAPI()

@fastapi_app.on_event("startup")
async def startup():
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    print("✅ Webhook set & bot ready")

@fastapi_app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return {"ok": True}
    
if __name__ == "__main__":
    uvicorn.run(
        fastapi_app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
