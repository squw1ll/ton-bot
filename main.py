import os
import re
import time
import json
import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message




BOT_TOKEN = os.getenv("BOT_TOKEN")

# === НАСТРОЙКИ ===
STARS_50_USD = 0.78          # фиксированная цена 50⭐ в долларах
CACHE_FILE = "ton_usd_cache.json"
CACHE_TTL_SEC = 60           # обновлять курс не чаще раза в минуту

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=the-open-network&vs_currencies=usd"
)

@dataclass
class TonUsdPrice:
    ton_usd: float
    ts: float

def load_cache() -> Optional[TonUsdPrice]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return TonUsdPrice(ton_usd=float(d["ton_usd"]), ts=float(d["ts"]))
    except Exception:
        return None

def save_cache(p: TonUsdPrice) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"ton_usd": p.ton_usd, "ts": p.ts}, f, ensure_ascii=False, indent=2)

async def fetch_ton_usd(session: aiohttp.ClientSession) -> float:
    cached = load_cache()
    now = time.time()

    if cached and (now - cached.ts) < CACHE_TTL_SEC:
        return cached.ton_usd

    async with session.get(COINGECKO_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
        resp.raise_for_status()
        data = await resp.json()

    # ожидаем: {"the-open-network":{"usd":<price>}}
    ton_usd = float(data["the-open-network"]["usd"])
    if ton_usd <= 0:
        raise RuntimeError("Получен некорректный ton_usd")

    save_cache(TonUsdPrice(ton_usd=ton_usd, ts=now))
    return ton_usd

def parse_ton_price(text: str) -> Optional[float]:
    # принимает "12.3" или "12,3"
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*", text or "")
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def calc(price_ton: float, ton_usd: float) -> dict:
    price_minus_5 = price_ton * 0.95

    # 50⭐ в TON = $0.78 / (USD за 1 TON)
    stars50_ton = STARS_50_USD / ton_usd

    # передача = 25⭐ = половина от 50⭐
    transfer25_ton = stars50_ton / 2.0

    result = price_minus_5 - transfer25_ton
    return {
        "price_ton": price_ton,
        "minus5_ton": price_minus_5,
        "ton_usd": ton_usd,
        "stars50_ton": stars50_ton,
        "transfer25_ton": transfer25_ton,
        "result_ton": result,
    }

async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан в .env")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def start(m: Message):
        await m.answer(
            "Отправь просто цену в TON (например: 12.8)\n"
            "Считаю: price*0.95 - ( (0.78$ / курс TON$) / 2 )"
        )

    @dp.message()
    async def on_price(m: Message):
        price_ton = parse_ton_price(m.text)
        if price_ton is None:
            await m.answer("Отправь только число (цена в TON), например: 12.8")
            return

        async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            try:
                ton_usd = await fetch_ton_usd(session)
                d = calc(price_ton, ton_usd)

                await m.answer(
                    f"Цена: {d['price_ton']:.6f} TON\n"
                    f"–5%: {d['minus5_ton']:.6f} TON\n"
                    f"Курс: 1 TON = {d['ton_usd']:.6f} USD\n"
                    f"50⭐ = $0.78 → {d['stars50_ton']:.6f} TON\n"
                    f"25⭐ (передача) → {d['transfer25_ton']:.6f} TON\n"
                    f"Итого: {d['result_ton']:.6f} TON"
                )
            except Exception as e:
                await m.answer(f"Ошибка: {e}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
