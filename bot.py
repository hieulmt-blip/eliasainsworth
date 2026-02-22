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
from decimal import Decimal
from decimal import Decimal, getcontext
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import asyncio
import requests
import re
from datetime import datetime
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler, CallbackQueryHandler

def parse_money(value) -> float:
    """
    Parse mọi kiểu tiền từ Google Sheet:
    $ 1.885.719.621.143,16
    1,885,719,621,143.16
    1885719621143.16
    """
    if value is None:
        raise ValueError("Giá trị tiền rỗng")

    s = str(value).strip()

    # bỏ ký tự tiền tệ và khoảng trắng
    s = re.sub(r"[^\d,.\-]", "", s)

    # Nếu có cả . và , → xác định decimal là ký tự xuất hiện cuối
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # format VN: 1.234.567,89
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # format US: 1,234,567.89
            s = s.replace(",", "")
    else:
        # chỉ có 1 loại dấu
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    return float(s)
getcontext().prec = 50  # tăng precision lớn

ADD_COIN = 1
REMOVE_COIN = 2
def fmt(x):
    d = Decimal(str(x))
    return format(d.normalize(), 'f').rstrip('0').rstrip('.')

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

tg_app = ApplicationBuilder().token(BOT_TOKEN).build()
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

exchange = ccxt.okx({
    "apiKey": os.getenv("OKX_API_KEY"),
    "secret": os.getenv("OKX_SECRET"),
    "password": os.getenv("OKX_PASSWORD"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

# 🚨 BẮT BUỘC – chặn load markets
exchange.load_markets = lambda *args, **kwargs: {}
exchange_trade = ccxt.okx({
    "apiKey": os.getenv("OKX_API_KEY"),
    "secret": os.getenv("OKX_SECRET"),
    "password": os.getenv("OKX_PASSWORD"),
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
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
    await update.message.reply_text("Elias Ainsworth đã có mặt 🫡")

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
                f"🤑 GHI CÓ \n+{diff:.6f} {coin}"
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
            text="🫡 Báo cáo chưa có khoản ghi có mới"
        )

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Dùng: /price BTC/USDT hoặc /price BTC")
        return

    pair = context.args[0].upper()
    if "/" not in pair:
        pair = f"{pair}/USDT"

    try:
        inst_id = pair.replace("/", "-")

        ticker = exchange.public_get_market_ticker({
            "instId": inst_id
        })

        last = float(ticker["data"][0]["last"])

        await update.message.reply_text(
            f"📈 {pair}\nGiá: {last}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi price: {e}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balances = exchange.fetch_balance({"type": "spot"})

        msg = "💰 TRADING BALANCE\n"
        for coin, amount in balances["total"].items():
            if amount and amount > 0:
               msg += f"{coin}: {fmt(amount)}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi balance: {e}")
        
async def funding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balances = exchange.fetch_balance({"type": "funding"})

        msg = "💰 FUNDING BALANCE\n"
        for coin, amount in balances["total"].items():
            if amount and amount > 0:
               msg += f"{coin}: {fmt(amount)}\n"
        await update.message.reply_text(msg or "Funding balance = 0")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi funding: {e}")
        
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        msg = "💳 YOUR WALLET\n"

        # ===== SPOT & FUNDING =====
        for t in ["trading", "funding"]:
            balances = exchange.fetch_balance({"type": t})
            msg += f"\n[{t.upper()}]\n"

            has_coin = False
            for coin, amount in balances["total"].items():
                if amount and amount > 0:
                    msg += f"{coin}: {fmt(amount)}\n"
                    has_coin = True
            if not has_coin:
                msg += "0\n"

        # ===== EARN (FLEXIBLE SAVINGS) =====
        try:
            earn = exchange.private_get_finance_savings_balance()
            data = earn.get("data", [])

            msg += "\n[EARN]\n"

            has_earn = False
            for item in data:
                ccy = item.get("ccy")
                amt = float(item.get("amt", 0))
                earnings = float(item.get("earnings", 0))

                if amt > 0:
                    msg += f"{ccy}: {amt} \n"
                    has_earn = True

            if not has_earn:
                msg += "0\n"

        except Exception:
            msg += "\n[EARN]\nKhông đọc được\n"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi wallet: {e}")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "Dùng:\n/deposit <coin> <network>\nVD:\n/deposit BTC BTC"
        )
        return

    coin = context.args[0].upper()
    network = context.args[1].upper()

    try:
        # 🔥 Gọi trực tiếp OKX v5
        res = exchange.private_get_asset_deposit_address({
            "ccy": coin
        })

        data = res.get("data", [])

        if not data:
            await update.message.reply_text("❌ Không có địa chỉ nạp")
            return

        # Lọc đúng network
        address = None
        tag = ""

        for item in data:
            if item.get("chain", "").upper().startswith(network):
                address = item.get("addr")
                tag = item.get("tag") or ""
                break

        if not address:
            await update.message.reply_text(
                f"❌ Không tìm thấy network {network}"
            )
            return

        # ===== QR =====
        qr_content = address
        if tag:
            qr_content = f"{address}?memo={tag}"

        qr = qrcode.make(qr_content)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)

        caption = (
            f"📥 NẠP {coin} ({network})\n\n"
            f"📍 Address:\n`{address}`\n"
        )

        if tag:
            caption += f"\n🏷 Memo/Tag:\n`{tag}`\n"

        caption += f"\n⚠️ Chỉ gửi {coin} qua mạng {network}"

        await update.message.reply_photo(
            photo=buf,
            caption=caption,
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi deposit:\n{e}")


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
            f"♻️ TRANSFER OKX THÀNH CÔNG\n"
            f"{amount} {coin}\n"
            f"{from_acc.upper()} → {to_acc.upper()}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi transfer: {e}")
        
def get_fixed_margin(exchange):
    positions = exchange.fetch_positions()
    total_margin = 0.0

    for p in positions:
        contracts = p.get("contracts", 0)
        if contracts and float(contracts) > 0:
            total_margin += float(p.get("initialMargin", 0) or 0)

    return total_margin
       
async def future(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # 1️⃣ Equity & free từ account
        bal = exchange.fetch_balance({"type": "swap"})
        usdt = bal["USDT"]

        free = usdt.get("free", 0) or 0
        equity = usdt.get("total", 0) or 0

        # 2️⃣ Margin cố định (initial margin)
        margin = get_fixed_margin(exchange)

        # 3️⃣ PNL thật
        pnl = equity - (free + margin)

        msg = (
            "📊 FUTURE ACCOUNT (USDT)\n\n"
            f"💵 Khả dụng : {free:.4f} USDT\n"
            f"🔒 Margin   : {margin:.4f} USDT\n"
            f"📈 PNL      : {pnl:+.4f} USDT\n"
            "──────────────\n"
            f"💰 Equity   : {equity:.4f} USDT"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ {e} = 0")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        positions = exchange.fetch_positions()

        open_positions = [
            p for p in positions
            if p.get("contracts") and float(p["contracts"]) > 0
        ]

        if not open_positions:
            await update.message.reply_text("📊 Không có vị thế future đang mở")
            return

        msg = "📊 VỊ THẾ FUTURE ĐANG MỞ\n\n"

        for p in open_positions:
            symbol = p.get("symbol")
            side = p.get("side", "").upper()
            contracts = p.get("contracts")
            entry = p.get("entryPrice")
            mark = p.get("markPrice")

            pnl = p.get("unrealizedPnl", 0) or 0
            roe = p.get("percentage", 0) or 0
            leverage = p.get("leverage")
            margin = p.get("initialMargin", 0) or 0   # 👈 CÁI M CẦN

            msg += (
                f"🪙 {symbol}\n"
                f"• Side: {side}\n"
                f"• Size: {contracts}\n"
                f"• Entry: {entry}\n"
                f"• Mark: {mark}\n"
                f"• Margin: {margin:.4f} USDT\n"
                f"• PNL: {pnl:+.4f} USDT\n"
                f"• ROE: {roe:.2f}%\n"
                f"• Leverage: {leverage}x\n"
                f"----------------------\n"
            )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi positions:\n{e}")
async def staking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = exchange.private_get_finance_savings_balance()
        data = res.get("data", [])

        if not data:
            await update.message.reply_text("📦 Không có tài sản Earn.")
            return

        msg = "🏦 EARN BALANCE\n\n"

        for item in data:
            ccy = item.get("ccy")
            amt = Decimal(item.get("amt", "0"))
            earnings = Decimal(item.get("earnings", "0"))

            if amt <= 0:
                continue

            principal = amt - earnings

            msg += (
                f"{ccy}\n"
                f"• 💰 Gốc: {fmt(principal)}\n"
                f"• 💹 Lãi: {fmt(earnings)}\n"
                f"• 📦 Tổng: {fmt(amt)}\n\n"
            )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi staking: {e}")
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2:
            await update.message.reply_text("Ví dụ: /buy btc 10")
            return

        coin = context.args[0].upper()
        usdt_amount = str(context.args[1])

        inst_id = f"{coin}-USDT"

        order = exchange_trade.private_post_trade_order({
            "instId": inst_id,
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": usdt_amount
        })

        await update.message.reply_text(
            f"✅ BUY {inst_id}\n"
            f"💸 {usdt_amount} USDT"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ BUY lỗi: {e}")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(context.args) < 2:
            await update.message.reply_text("Ví dụ: /sell btc 10")
            return

        coin = context.args[0].upper()
        usdt_amount = float(context.args[1])
        inst_id = f"{coin}-USDT"

        ticker = exchange.public_get_market_ticker({
            "instId": inst_id
        })

        price = float(ticker["data"][0]["last"])

        base_amount = usdt_amount / price

        # 👇 CẮT 8 DECIMAL CHO BTC
        base_amount = format(base_amount, ".8f")

        order = exchange_trade.private_post_trade_order({
            "instId": inst_id,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "market",
            "sz": base_amount
        })

        await update.message.reply_text(
            f"✅ SELL {inst_id}\n≈ {usdt_amount} USDT 🤑"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ SELL lỗi: {e}")
def get_sheet():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS chưa cấu hình")

    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        raise Exception("SHEET_ID chưa cấu hình")

    creds_dict = json.loads(creds_json)

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict, scope
    )

    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id).sheet1
    
def calculate_c20():
    sheet = get_sheet()

    # ===== LẤY COIN Ở ROW 6 =====
    header = sheet.get("A6:T6")[0]

    coins = []
    for c in header:
        if not c:
            continue
        c = c.strip().upper()
        if not c.isalnum():
            continue
        if len(c) > 10:
            continue
        coins.append(c)

    if not coins:
        raise Exception("Danh sách coin rỗng")

    # ===== CALL CMC =====
    api_key = os.getenv("CMC_API_KEY")
    if not api_key:
        raise Exception("CMC_API_KEY chưa cấu hình")

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": api_key}
    params = {"symbol": ",".join(coins), "convert": "USD"}

    r = requests.get(url, headers=headers, params=params, timeout=20)

    if r.status_code != 200:
        raise Exception(f"CMC error {r.status_code}")

    data = r.json()

    total_marketcap = 0
    valid = 0

    for coin in coins:
        try:
            mc = float(data["data"][coin]["quote"]["USD"]["market_cap"])
            total_marketcap += mc
            valid += 1
        except:
            continue

    if valid == 0:
        raise Exception("CMC không trả dữ liệu hợp lệ")

    # ===== BASE VALUE =====
    base_raw = sheet.acell("A17").value
    if not base_raw:
        raise Exception("A17 trống")

    base_value = parse_money(base_raw)

    index_value = round((total_marketcap / base_value) * 1000, 4)

    # ===== TIMEZONE VN =====
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    # ===== ĐỌC MỐC NGÀY =====
    stored_date = sheet.acell("B23").value
    midnight_raw = sheet.acell("A23").value

    # Nếu sang ngày mới hoặc chưa có mốc
    if stored_date != today_str or not midnight_raw:
        sheet.update("A23", [[index_value]])
        sheet.update("B23", [[today_str]])
        midnight_value = index_value
    else:
        midnight_value = parse_money(midnight_raw)

    # ===== TÍNH ĐIỂM =====
    point_change = round(index_value - midnight_value, 4)

    # ===== TÍNH % =====
    if midnight_value == 0:
        percent_change = 0
    else:
        percent_change = round((point_change / midnight_value) * 100, 2)

    # ===== UPDATE SHEET =====
    sheet.update("A21", [[index_value]])
    sheet.update("A1", [[f"Last update: {now.strftime('%Y-%m-%d %H:%M:%S')}"]])

    return index_value, point_change, percent_change, valid
    
async def c20inx(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("⏳ Đang tính C20INDEX...")

        index, point, percent, count = await asyncio.to_thread(calculate_c20)

        emoji = "🟢" if point >= 0 else "🔴"
        arrow = "▲" if point >= 0 else "▼"

        await update.message.reply_text(
            f"📊 C20INDEX\n\n"
            f"Value: {index}\n"
            f"{emoji} {arrow} {point:+.4f} pts ({percent:+.2f}%)\n"
            f"Coins used: {count}"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi C20INDEX:\n{e}")
# ================== C20 LIST LOGIC ==================

def get_c20_list():
    sheet = get_sheet()
    values = sheet.get("D17:D100")
    return [row[0].strip().upper() for row in values if row and row[0]]
    
def update_and_get_capital_ratios():
    sheet = get_sheet()

    header = sheet.get("A6:T6")[0]
    base_row = sheet.get("A8:T8")[0]

    base_dict = {}

    for i, coin in enumerate(header):
        if coin and base_row[i]:
            try:
                val = str(base_row[i]).replace(",", ".")
                base_dict[coin.strip().upper()] = float(val)
            except:
                continue

    values = sheet.get("D17:D100")
    coins = [row[0].strip().upper() for row in values if row and row[0]]

    if not coins:
        return {}

    total_base = sum(base_dict.get(c, 0) for c in coins)

    if total_base == 0:
        return {}

    ratios = {}
    ratio_rows = []

    for coin in coins:
        base_val = base_dict.get(coin, 0)
        ratio = round((base_val / total_base) * 100, 4)
        ratios[coin] = ratio
        ratio_rows.append([ratio])

    sheet.update("E17:E100", [[""]] * 84)
    sheet.update(f"E17:E{16+len(ratio_rows)}", ratio_rows)

    return ratios
def write_full_list(coins):
    sheet = get_sheet()

    # Clear vùng
    sheet.update("D17:D100", [[""]] * 84)

    # Ghi lại từ đầu
    for i, coin in enumerate(coins):
        sheet.update(f"D{17+i}", [[coin]])


async def c20(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coins = await asyncio.to_thread(get_c20_list)

        if not coins:
            await update.message.reply_text("📊 C20 trống")
            return

        api_key = os.getenv("CMC_API_KEY")
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": api_key}
        params = {"symbol": ",".join(coins), "convert": "USD"}

        r = requests.get(url, headers=headers, params=params, timeout=20)
        data = r.json()

        market_caps = {}
        total = 0

        for coin in coins:
            try:
                mc = float(data["data"][coin]["quote"]["USD"]["market_cap"])
                market_caps[coin] = mc
                total += mc
            except:
                pass

        if total == 0:
            await update.message.reply_text("Không đọc được market cap.")
            return

        text = "📊 C20 LIST\n\n"

        for coin in coins:
            mc = market_caps.get(coin, 0)
            percent = (mc / total) * 100 if total else 0
            text += f"{coin} — {percent:.2f}%\n"

        text += f"\n💰 Total Market Cap:\n{total:,.0f} USD"

        keyboard = [
            [InlineKeyboardButton("➕ Thêm coin", callback_data="add_coin")],
            [InlineKeyboardButton("➖ Xoá coin", callback_data="remove_coin")]
        ]

        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi C20:\n{e}")
    
async def add_coin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Nhập ticker coin muốn thêm (VD: SOL)")
    return ADD_COIN


async def receive_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = update.message.text.strip().upper()
        coins = await asyncio.to_thread(get_c20_list)

        if coin in coins:
            await update.message.reply_text("⚠️ Coin đã tồn tại.")
            return ConversationHandler.END

        # ===== LẤY MARKET CAP =====
        api_key = os.getenv("CMC_API_KEY")
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": api_key}

        # Lấy cap danh sách cũ
        old_total = 0
        if coins:
            params_old = {"symbol": ",".join(coins), "convert": "USD"}
            r_old = requests.get(url, headers=headers, params=params_old, timeout=20)
            data_old = r_old.json()

            for c in coins:
                try:
                    old_total += float(data_old["data"][c]["quote"]["USD"]["market_cap"])
                except:
                    pass

        # Lấy cap coin mới
        params_new = {"symbol": coin, "convert": "USD"}
        r_new = requests.get(url, headers=headers, params=params_new, timeout=20)
        data_new = r_new.json()

        new_cap = float(data_new["data"][coin]["quote"]["USD"]["market_cap"])

        # ===== TÍNH % TĂNG =====
        percent_increase = 0
        if old_total > 0:
            percent_increase = (new_cap / old_total) * 100

        # ===== GHI COIN =====
        coins.append(coin)
        await asyncio.to_thread(write_full_list, coins)

        # ===== UPDATE RATIO NHƯ CŨ =====
        await asyncio.to_thread(update_and_get_capital_ratios)

        await update.message.reply_text(
            f"✅ Đã thêm {coin}\n"
            f"📈 Vốn danh sách tăng +{percent_increase:.2f}%"
        )

        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi thêm coin:\n{e}")
        return ConversationHandler.END

async def remove_coin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coins = await asyncio.to_thread(get_c20_list)

    if not coins:
        await query.message.reply_text("Không có coin để xoá.")
        return ConversationHandler.END

    text = "Nhập ticker coin muốn xoá:\n"
    for c in coins:
        text += f"• {c}\n"

    await query.message.reply_text(text)

    return REMOVE_COIN


async def receive_remove_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        coin = update.message.text.strip().upper()
        coins = await asyncio.to_thread(get_c20_list)

        if coin not in coins:
            await update.message.reply_text("⚠️ Coin không tồn tại.")
            return ConversationHandler.END

        api_key = os.getenv("CMC_API_KEY")
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        headers = {"X-CMC_PRO_API_KEY": api_key}

        # ===== LẤY MARKET CAP TOÀN BỘ LIST =====
        params = {"symbol": ",".join(coins), "convert": "USD"}
        r = requests.get(url, headers=headers, params=params, timeout=20)
        data = r.json()

        total_cap = 0
        remove_cap = 0

        for c in coins:
            try:
                mc = float(data["data"][c]["quote"]["USD"]["market_cap"])
                total_cap += mc
                if c == coin:
                    remove_cap = mc
            except:
                pass

        percent_decrease = 0
        if total_cap > 0:
            percent_decrease = (remove_cap / total_cap) * 100

        # ===== XOÁ COIN =====
        coins.remove(coin)
        await asyncio.to_thread(write_full_list, coins)

        # ===== UPDATE RATIO NHƯ CŨ =====
        await asyncio.to_thread(update_and_get_capital_ratios)

        await update.message.reply_text(
            f"🗑 Đã xoá {coin}\n"
            f"📉 Vốn danh sách giảm -{percent_decrease:.2f}%"
        )

        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi xoá coin:\n{e}")
        return ConversationHandler.END


conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(add_coin_button, pattern="add_coin"),
        CallbackQueryHandler(remove_coin_button, pattern="remove_coin"),
    ],
    states={
        ADD_COIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coin)
        ],
        REMOVE_COIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_coin)
        ],
    },
    fallbacks=[],
)
async def scale(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        combined = {}

        # =========================
        # 1️⃣ ACCOUNT (SPOT + FUTURES + UNIFIED)
        # =========================
        account_balance = exchange.private_get_account_balance()

        for acc in account_balance.get("data", []):
            for detail in acc.get("details", []):
                coin = detail.get("ccy")
                amount = float(detail.get("eq", 0))
                if amount > 0:
                    combined[coin] = combined.get(coin, 0) + amount

        # =========================
        # 2️⃣ FUNDING WALLET
        # =========================
        funding_balance = exchange.private_get_asset_balances()

        for item in funding_balance.get("data", []):
            coin = item.get("ccy")
            amount = float(item.get("bal", 0))
            if amount > 0:
                combined[coin] = combined.get(coin, 0) + amount

        # =========================
        # 3️⃣ EARN (Flexible + Staking)
        # =========================
        try:
            earn = exchange.private_get_finance_savings_balance()
            for item in earn.get("data", []):
                coin = item.get("ccy")
                amount = float(item.get("amt", 0))
                if amount > 0:
                    combined[coin] = combined.get(coin, 0) + amount
        except:
            pass

        # =========================
        # 4️⃣ TÍNH USDT VALUE
        # =========================
        coin_data = []
        total_value = 0

        for coin, amount in combined.items():
            try:
                if coin == "USDT":
                    price = 1
                else:
                    ticker = exchange.public_get_market_ticker({
                        "instId": f"{coin}-USDT"
                    })
                    price = float(ticker["data"][0]["last"])

                value = amount * price

                if value < 0.5:
                    continue

                total_value += value

                coin_data.append({
                    "coin": coin,
                    "amount": amount,
                    "value": value
                })

            except:
                continue

        # =========================
        # 5️⃣ TÍNH %
        # =========================
        for item in coin_data:
            item["percent"] = (item["value"] / total_value) * 100 if total_value else 0

        coin_data.sort(key=lambda x: x["percent"], reverse=True)

        # =========================
        # 6️⃣ OUTPUT
        # =========================
        msg = "📊 *TOTAL PORTFOLIO *\n\n"

        for item in coin_data:
            msg += (
                f"*{item['coin']}*\n"
                f"Amount: `{fmt(item['amount'])}`\n"
                f"Value: `{item['value']:.2f} USDT`\n"
                f"Allocation: `{item['percent']:.2f}%`\n\n"
            )

        msg += f"💰 *TOTAL:* `{total_value:.2f} USDT`"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ SCALE lỗi:\n{e}")
# ================= DAILY MARKET CAP RECORD =================

# ================= DAILY MARKET CAP RECORD =================

# ================= DAILY MARKET CAP RECORD =================

async def record_daily_market_cap():
    try:
        sheet = get_sheet()
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        now = datetime.now(tz)

        current_time = now.time()
        today_str = now.strftime("%Y-%m-%d")

        raw = sheet.acell("U13").value
        if not raw:
            return

        current_cap = parse_money(raw)

        # ===============================
        # 🔹 1️⃣ GHI MARKET CAP DAY (G + H)
        # 00:00:01 → 18:00:00
        # LẦN ĐẦU TIÊN TRONG NGÀY
        # ===============================
        if (
            current_time.hour < 18 and
            (current_time.hour > 0 or current_time.minute > 0)
        ):
            existing_dates = sheet.get("H17:H500")

            already_recorded = False
            for row in existing_dates:
                if row and today_str in row[0]:
                    already_recorded = True
                    break

            if not already_recorded:
                col_data = sheet.get("G17:G500")
                last_row = 16

                for i, row in enumerate(col_data):
                    if row and row[0]:
                        last_row = 17 + i

                next_row = last_row + 1

                sheet.update(f"G{next_row}", [[current_cap]])
                sheet.update(f"H{next_row}", [[today_str]])

                print(f"✅ DAY recorded at G{next_row}")

        # ===============================
        # 🔹 2️⃣ GHI MARKET CAP CLOSE (I)
        # 23:00:00 → 23:59:59
        # GHI 1 LẦN DUY NHẤT
        # ===============================
        if current_time.hour == 23:

            col_data = sheet.get("H17:H500")
            target_row = None

            for i, row in enumerate(col_data):
                if row and today_str in row[0]:
                    target_row = 17 + i
                    break

            if target_row:
                close_cell = sheet.acell(f"I{target_row}").value

                if not close_cell:
                    sheet.update(f"I{target_row}", [[current_cap]])
                    print(f"🌙 CLOSE recorded at I{target_row}")

    except Exception as e:
        print("❌ record error:", e)

async def scheduler_loop():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    print("🚀 Scheduler started")

    while True:
        await record_daily_market_cap()
        await asyncio.sleep(60)

async def capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        sheet = get_sheet()
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
        now = datetime.now(tz)

        # ===== C = Current (U13)
        current_raw = sheet.acell("U13").value
        C = parse_money(current_raw)

        # ===== Tìm ngày 20 gần nhất
        history = sheet.get("G17:H500")

        X = None
        anchor_date = None

        for row in history:
            if len(row) < 2:
                continue
            try:
                cap = parse_money(row[0])
                d = datetime.strptime(row[1], "%Y-%m-%d %H:%M")
            except:
                continue

            if d.day == 20 and d < now:
                if anchor_date is None or d > anchor_date:
                    anchor_date = d
                    X = cap

        # ===== Nếu không có ngày 20 => lấy base A17
        if X is None:
            base_raw = sheet.acell("A17").value
            X = parse_money(base_raw)
            anchor_label = "BASE (A17)"
        else:
            anchor_label = anchor_date.strftime("%d/%m/%Y")

        # ===== % = (C - X) / X
        percent = (C - X) / X * 100

        msg = (
            f"📊 CAPITAL ALLOCATION \n\n"
            f"C (Current): {C:,.0f}\n"
            f"X (Anchor): {X:,.0f}\n"
            f"Anchor used: {anchor_label}\n\n"
            f"% = (C - X) / X\n"
            f"= {percent:+.2f}%"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi capital:\n{e}")
def write_market_cap_if_needed(sheet, total_marketcap):
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    now = datetime.now(tz)

    # chỉ ghi nếu 12h
    if not (now.hour == 12 and now.minute <= 1):
        return

    today_str = now.strftime("%Y-%m-%d")

    history = sheet.get("H17:H500")
    for row in history:
        if row and today_str in row[0]:
            return  # đã ghi rồi

    # tìm dòng cuối có dữ liệu
    col_data = sheet.get("G17:G500")
    last_filled = 16

    for i, row in enumerate(col_data):
        if row and row[0]:
            last_filled = 17 + i

    next_row = last_filled + 1

    sheet.update(f"G{next_row}", [[total_marketcap]])
    sheet.update(f"H{next_row}", [[now.strftime("%Y-%m-%d 12:00")]])
    
tg_app.add_handler(CommandHandler("C20", c20))
tg_app.add_handler(CommandHandler("start", start))
tg_app.add_handler(CommandHandler("price", price))
tg_app.add_handler(CommandHandler("balance", balance))
tg_app.add_handler(CommandHandler("funding", funding))
tg_app.add_handler(CommandHandler("wallet", wallet))
tg_app.add_handler(CommandHandler("deposit", deposit))
tg_app.add_handler(CommandHandler("transfer", transfer))
tg_app.add_handler(CommandHandler("future", future))
tg_app.add_handler(CommandHandler("positions", positions))
tg_app.add_handler(CommandHandler("staking", staking))
tg_app.add_handler(CommandHandler("buy", buy))
tg_app.add_handler(CommandHandler("sell", sell))
tg_app.add_handler(CommandHandler("c20inx", c20inx))
tg_app.add_handler(CommandHandler("scale", scale))
conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(add_coin_button, pattern="add_coin"),
        CallbackQueryHandler(remove_coin_button, pattern="remove_coin"),
    ],
    states={
        ADD_COIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_coin)
        ],
        REMOVE_COIN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_coin)
        ],
    },
    fallbacks=[],
)
tg_app.add_handler(conv_handler)
tg_app.add_handler(CommandHandler("capital", capital))
# ===== FASTAPI WEBHOOK =====

fastapi_app = FastAPI()

@fastapi_app.on_event("startup")
async def startup():
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    asyncio.create_task(scheduler_loop())
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
