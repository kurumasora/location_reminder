import os

from fastapi.responses import JSONResponse

from app.config import PLACES, logger
from app.geo import haversine
from app.db import _save_state
from app.telegram import send_telegram

# ユーザーごとの前回状態（起動時にDBからロード）
user_state: dict[str, dict] = {}

# 全員集合通知済みフラグ（全員insideになったら1回だけ通知）
all_inside_notified = False


async def handle_location(data: dict) -> JSONResponse:
    lat = data.get("lat")
    lon = data.get("lon")
    topic = data.get("topic", "")

    if lat is None or lon is None:
        return JSONResponse(content=[])

    parts = topic.split("/")
    user = data.get("tid", "unknown")
    username = parts[1] if len(parts) >= 2 else user

    # haversine でサーバー側から inside/outside を判定
    now_in = [p["name"] for p in PLACES if haversine(lat, lon, p["lat"], p["lon"]) <= p["radius_m"]]

    new_state = {"inside": now_in, "lat": lat, "lon": lon}
    user_state[username] = new_state
    _save_state(username, new_state)

    # 全員 inside になったら1回だけ通知
    global all_inside_notified
    if user_state and all(state["inside"] for state in user_state.values()):
        if not all_inside_notified:
            all_inside_notified = True
            await send_telegram("おめでとうございます！全員集まりました！🎉")
            await send_telegram(
                "記念にmanso君から皆さんにプレゼントです！\n"
                + os.environ["PRESENT_URL"]
            )
    else:
        all_inside_notified = False

    return JSONResponse(content=[])
