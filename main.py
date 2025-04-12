from asyncio import sleep
import psycopg2
from tradingview_ta import TA_Handler, Interval
import datetime
import time
import asyncio
from telegram import Bot
import os

# Telegram Bot Credentials
bot_token = os.getenv('BOT_TOKEN')  # Replace with your Telegram bot token
CHAT_ID = os.getenv('CHAT_ID')  # Replace with your Telegram chat ID
bot = Bot(token=bot_token)


# PostgreSQL connection
DB_URL = "postgresql://postgres:OZDFcNUBiBkzQXPKAMpaNUCHvkEsXeGE@postgres.railway.internal:5432/railway"  # Replace with your Railway PostgreSQL URL
conn = psycopg2.connect(DB_URL)
cursor = conn.cursor()

# Define symbols
symbols = ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD", "DOGEUSD", "DOTUSD", "ADAUSD"]
exchange = "COINBASE"
directions = ['high', 'low']


# Create a table if it doesn’t exist
def create_ohlc_table(symbol, direction):
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {symbol}_w_{direction} (
            id SERIAL PRIMARY KEY,
            symbol TEXT,
            {direction} FLOAT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def store_daily_data(symbol, direction):
    ta = TA_Handler(
        symbol=symbol,
        exchange=exchange,
        screener="crypto",
        interval=Interval.INTERVAL_1_WEEK,
    )
    analysis = ta.get_analysis()
    level = analysis.indicators.get(f"{direction}", None)
    print(f"{symbol} - {direction}: {level}")

    # Insert into PostgreSQL
    cursor.execute(f"INSERT INTO {symbol}_w_{direction} (symbol, {direction}) VALUES (%s, %s)",
                   (symbol, level))

    conn.commit()

    time.sleep(2)  # Prevent rate-limiting


def filter_highs(symbol):
    # Read data
    cursor.execute(f"SELECT * FROM {symbol}_w_high")
    rows = cursor.fetchall()
    # Keep the significant highs
    for row in rows[0:-1]:
        print(f"symbol: {symbol}, row: {row}, price: {row[2]}, last price: {rows[-1][2]}")
        if row[2] <= rows[-1][2]:
            row_id = row[0]
            cursor.execute(f"DELETE FROM {symbol}_w_high WHERE id = %s", (row_id,))
            conn.commit()
            print(f"Deleted row with ID {row_id}!")


def filter_lows(symbol):
    # Read data
    cursor.execute(f"SELECT * FROM {symbol}_w_low")
    rows = cursor.fetchall()
    # Keep the significant levels
    for row in rows[0:-1]:
        if row[2] >= rows[-1][2]:
            row_id = row[0]
            cursor.execute(f"DELETE FROM {symbol}_w_low WHERE id = %s", (row_id,))
            conn.commit()
            print(f"Deleted row with ID {row_id}!")


async def send_telegram_message(message):
    """Sends an async Telegram message."""
    await bot.send_message(chat_id=CHAT_ID, text=message)


async def compare_highs(symbol, high, close):
    cursor.execute(f"SELECT * FROM {symbol}_w_high")
    rows = cursor.fetchall()
    tasks = []

    for row in rows:
        print(row[2])
        if high > row[2] > close:
            print(f'{symbol} faked out the weekly high')
            message = f'{symbol} just faked out a weekly high'
            tasks.append(send_telegram_message(message))  # Collect tasks

    await asyncio.gather(*tasks)  # Run all tasks concurrently


async def compare_lows(symbol, low, close):
    cursor.execute(f"SELECT * FROM {symbol}_w_low")
    rows = cursor.fetchall()
    tasks = []

    for row in rows:
        print(row[2])
        if low < row[2] < close:
            print(f'{symbol} faked out the weekly low')
            message = f'{symbol} just faked out a weekly low'
            tasks.append(send_telegram_message(message))  # Collect tasks

    await asyncio.gather(*tasks)  # Run all tasks concurrently


def h_ohlc(symbol):
    ta = TA_Handler(
        symbol=symbol,
        exchange=exchange,
        screener="crypto",
        interval=Interval.INTERVAL_4_HOURS,
    )
    analysis = ta.get_analysis()
    high = analysis.indicators.get("high", None)
    low = analysis.indicators.get("low", None)
    close = analysis.indicators.get("close", None)
    time.sleep(3)
    return high, low, close


async def main():
    if time.localtime()[3] == 23 and datetime.datetime.today().weekday() == 6:
        for symbol in symbols:
            for direction in directions:
                create_ohlc_table(symbol, direction)
                store_daily_data(symbol, direction)
            filter_highs(symbol)
            filter_lows(symbol)

    tasks = []  # Collect async tasks
    for symbol in symbols:
        high, low, close = h_ohlc(symbol)
        print(symbol, high, low, close)
        tasks.append(compare_highs(symbol, high, close))
        tasks.append(compare_lows(symbol, low, close))

    await asyncio.gather(*tasks)  # Run all Telegram messages concurrently

asyncio.run(main())  # Call the main function properly

# Close connection
cursor.close()
conn.close()

