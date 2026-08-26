import httpx

from src.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        resp.raise_for_status()
