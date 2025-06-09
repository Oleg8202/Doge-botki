import os
os.system("pip uninstall -y binance && pip install python-binance")
import time
import math
from binance.client import Client
from binance.enums import *
import pandas as pd
import talib
from flask import Flask
from threading import Thread

# 🔐 API ключи
api_key = "pzmx5Wi90g3dIeb23Z2xrUusw0XPoE0QGfTZGnYnelLSRaBOgL4fDAdzuIbEz7io"
api_secret = "vTyFj3kAc686NEXjcBbG21lKNLO1elbHfadB2CZbfv6XvsEYEkKWwa5s2cVWdvRT"

client = Client(api_key, api_secret)

symbol = "DOGEUSDT"
rsi_period = 14
rsi_oversold = 30
rsi_takeprofit = 70  # RSI выше — продаём
trade_amount = 8  # $8

def get_symbol_info():
    info = client.get_symbol_info(symbol)
    lot_size = None
    min_qty = None
    price_filter = None
    for f in info['filters']:
        if f['filterType'] == 'LOT_SIZE':
            min_qty = float(f['minQty'])
            lot_size = float(f['stepSize'])
        if f['filterType'] == 'PRICE_FILTER':
            price_filter = f
    return min_qty, lot_size, price_filter

min_qty, step_size, price_filter = get_symbol_info()
price_precision = int(round(-math.log10(float(price_filter['tickSize']))))

def round_down_qty(qty, step):
    return float(math.floor(qty / step) * step)

def round_down_price(price, precision):
    return float(f"{price:.{precision}f}")

def get_klines():
    klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_1MINUTE, limit=100)
    closes = [float(k[4]) for k in klines]
    return closes

def get_rsi():
    closes = get_klines()
    rsi = talib.RSI(pd.Series(closes), timeperiod=rsi_period)
    return rsi.iloc[-1]

def get_price():
    return float(client.get_symbol_ticker(symbol=symbol)['price'])

def get_free_balance(asset='USDT'):
    balance = client.get_asset_balance(asset)
    return float(balance['free']) if balance else 0

def get_free_doge():
    balance = client.get_asset_balance(asset='DOGE')
    return float(balance['free']) if balance else 0

def cancel_all_orders():
    orders = client.get_open_orders(symbol=symbol)
    for order in orders:
        try:
            client.cancel_order(symbol=symbol, orderId=order['orderId'])
            print(f"❌ Отменён ордер ID {order['orderId']}")
        except Exception as e:
            print("⚠️ Ошибка отмены ордера:", e)

def place_trade():
    price = get_price()
    usdt = get_free_balance()
    print(f"💰 Баланс USDT: {usdt}")

    amount = trade_amount / price
    qty = round_down_qty(amount, step_size)
    if qty < min_qty:
        print(f"❌ Количество {qty} меньше минимального {min_qty}")
        return

    if usdt < trade_amount:
        print("❌ Недостаточно USDT")
        return

    try:
        # Покупка
        buy_order = client.order_market_buy(symbol=symbol, quantity=qty)
        print(f"✅ Куплено {qty} DOGE по рынку")

        buy_price = price

        qty_for_orders = qty * 0.99
        qty_for_orders = round_down_qty(qty_for_orders, step_size)
        if qty_for_orders < min_qty:
            print("❌ Мало DOGE для TP/SL")
            return

        qty_tp = round_down_qty(qty_for_orders / 2, step_size)
        qty_sl = qty_for_orders - qty_tp

        if qty_tp < min_qty or qty_sl < min_qty:
            print("❌ Недостаточно DOGE для TP или SL")
            return

        tp_price = round_down_price(buy_price * 1.05, price_precision)
        sl_price = round_down_price(buy_price * 0.985, price_precision)

        print(f"🎯 TP: {tp_price}, SL: {sl_price}")

        client.order_limit_sell(
            symbol=symbol,
            quantity=str(qty_tp),
            price=str(tp_price),
            timeInForce=TIME_IN_FORCE_GTC
        )

        client.create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_STOP_LOSS_LIMIT,
            quantity=str(qty_sl),
            price=str(sl_price),
            stopPrice=str(sl_price),
            timeInForce=TIME_IN_FORCE_GTC
        )

        print(f"📌 Установлены ордера: TP {qty_tp}, SL {qty_sl}")

    except Exception as e:
        print("⚠️ Ошибка при размещении:", e)

def check_open_orders():
    orders = client.get_open_orders(symbol=symbol)
    return len(orders) > 0

def sell_all_doge():
    cancel_all_orders()
    doge_balance = get_free_doge()
    if doge_balance >= min_qty:
        qty = round_down_qty(doge_balance, step_size)
        try:
            client.order_market_sell(symbol=symbol, quantity=qty)
            print(f"🚀 Продано {qty} DOGE по рынку (RSI > 70)")
        except Exception as e:
            print("⚠️ Ошибка при продаже DOGE:", e)
    else:
        print("❌ Недостаточно DOGE для продажи при RSI > 70")

# 🔁 Главный цикл
def run_bot():
    while True:
        try:
            rsi = get_rsi()
            print(f"📊 Индекс относительной силы: {rsi:.2f}")

            if rsi > rsi_takeprofit:
                print("📈 RSI выше 70 — продаём всё и отменяем ордера")
                sell_all_doge()
            else:
                if not check_open_orders():
                    if rsi < rsi_oversold:
                        place_trade()
                    else:
                        print("⏳ Ждём сигнала RSI...")
                else:
                    print("🔒 Ордера уже есть, ждём...")

        except Exception as e:
            print("⚠️ Ошибка в цикле:", e)

        time.sleep(60)

# 🚀 Flask-сервер для UptimeRobot, чтобы бот не спал
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ DOGE Бот работает!"

def run_server():
    app.run(host='0.0.0.0', port=8080)

# 🧵 Запускаем бота и сервер в отдельных потоках
Thread(target=run_bot).start()
Thread(target=run_server).start()
