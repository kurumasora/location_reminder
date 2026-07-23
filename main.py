import os
import math
import httpx
import logging
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Location Notifier")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# 場所の設定（.envまたは環境変数で上書き可能）
PLACES = [
    {
        "name": os.getenv("PLACE_1_NAME", "会社"),
        "lat": float(os.getenv("PLACE_1_LAT", "35.6895")),
        "lon": float(os.getenv("PLACE_1_LON", "139.6917")),
        "radius_m": float(os.getenv("PLACE_1_RADIUS", "200")),
    },
]

# ユーザーごとの前回状態（メモリ内。再起動でリセット）
user_state: dict[str, dict] = {}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離をメートルで返す"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
        resp.raise_for_status()


@app.post("/owntracks")
async def owntracks_webhook(request: Request):
    """OwnTracks HTTP modeのwebhook受信エンドポイント"""
    data = await request.json()
    logger.info("Received: %s", data)

    # transition イベント（OwnTracks の Region 入退場）を処理
    if data.get("_type") == "transition":
        topic = data.get("topic", "")
        parts = topic.split("/")
        username = parts[1] if len(parts) >= 2 else data.get("tid", "unknown")
        event = data.get("event")  # "enter" or "leave"
        desc = data.get("desc", "不明な場所")
        time_str = datetime.now().strftime("%H:%M")
        if event == "enter":
            msg = f"📍 {username} が「{desc}」に到着しました ({time_str})"
            logger.info(msg)
            await send_telegram(msg)
        elif event == "leave":
            msg = f"🚶 {username} が「{desc}」を出発しました ({time_str})"
            logger.info(msg)
            await send_telegram(msg)
        return JSONResponse(content=[])

    # OwnTracksのlocationイベントのみ処理
    if data.get("_type") != "location":
        return JSONResponse(content=[])

    user = data.get("tid", "unknown")  # Tracker ID (OwnTracksアプリで設定する2文字のID)
    lat = data.get("lat")
    lon = data.get("lon")
    topic = data.get("topic", "")  # 例: owntracks/username/device

    if lat is None or lon is None:
        return JSONResponse(content=[])

    # topic からユーザー名を取得
    parts = topic.split("/")
    username = parts[1] if len(parts) >= 2 else user

    now_in = set()
    for place in PLACES:
        dist = haversine(lat, lon, place["lat"], place["lon"])
        if dist <= place["radius_m"]:
            now_in.add(place["name"])

    prev_state = user_state.get(username, {})
    prev_in = set(prev_state.get("inside", []))

    entered = now_in - prev_in
    left = prev_in - now_in

    time_str = datetime.now().strftime("%H:%M")

    for place in entered:
        msg = f"📍 {username} が「{place}」に到着しました ({time_str})"
        logger.info(msg)
        await send_telegram(msg)

    for place in left:
        msg = f"🚶 {username} が「{place}」を出発しました ({time_str})"
        logger.info(msg)
        await send_telegram(msg)

    user_state[username] = {"inside": list(now_in), "lat": lat, "lon": lon}

    return JSONResponse(content=[])


@app.get("/health")
async def health():
    return {"status": "ok", "places": [p["name"] for p in PLACES]}


@app.get("/status")
async def status():
    return {
        "users": {
            name: {
                "inside": state["inside"],
                "lat": state.get("lat"),
                "lon": state.get("lon"),
            }
            for name, state in user_state.items()
        }
    }
