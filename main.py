import os
import io
import math
import json
import base64
import httpx
import qrcode
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Location Notifier")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BASE_URL = os.getenv("BASE_URL", "https://manso.ahirukuma.cc")

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


def make_qr_base64(url: str) -> str:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@app.get("/join", response_class=HTMLResponse)
async def join_page():
    join_url = f"{BASE_URL}/join"
    qr_b64 = make_qr_base64(join_url)
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>位置通知グループに参加</title>
<style>
  body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; background: #0f1117; color: #e2e8f0; margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 24px; box-sizing: border-box; }}
  .card {{ background: #1a1f2e; border: 1px solid #2d3550; border-radius: 16px; padding: 32px 28px; max-width: 400px; width: 100%; }}
  h1 {{ font-size: 22px; font-weight: 800; margin: 0 0 6px; }}
  p {{ color: #8892a4; font-size: 14px; margin: 0 0 24px; line-height: 1.6; }}
  label {{ font-size: 13px; font-weight: 600; color: #8892a4; letter-spacing: .05em; text-transform: uppercase; display: block; margin-bottom: 6px; }}
  input {{ width: 100%; box-sizing: border-box; padding: 12px 14px; background: #0f1117; border: 1px solid #2d3550; border-radius: 8px; color: #e2e8f0; font-size: 15px; font-family: inherit; outline: none; }}
  input:focus {{ border-color: #4d8eff; }}
  button {{ width: 100%; margin-top: 16px; padding: 13px; background: #2563eb; color: #fff; border: none; border-radius: 8px; font-size: 15px; font-weight: 700; font-family: inherit; cursor: pointer; }}
  button:hover {{ background: #1d4ed8; }}
  .divider {{ text-align: center; color: #4a5270; font-size: 13px; margin: 24px 0; }}
  .qr-wrap {{ text-align: center; }}
  .qr-wrap img {{ width: 160px; height: 160px; border-radius: 8px; background: white; padding: 8px; }}
  .qr-label {{ font-size: 12px; color: #8892a4; margin-top: 8px; }}
  .step {{ display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; font-size: 13.5px; color: #8892a4; }}
  .step-num {{ background: #2563eb; color: #fff; border-radius: 50%; width: 22px; height: 22px; font-size: 12px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }}
  .steps {{ margin-bottom: 24px; }}
</style>
</head>
<body>
<div class="card">
  <h1>📍 位置通知グループに参加</h1>
  <p>名前を入力して設定ファイルをダウンロードし、OwnTracks で読み込むと自動設定されます。</p>

  <div class="steps">
    <div class="step"><div class="step-num">1</div><div>OwnTracks アプリをインストール（App Store / Google Play）</div></div>
    <div class="step"><div class="step-num">2</div><div>下のフォームに名前を入力して設定ファイルをダウンロード</div></div>
    <div class="step"><div class="step-num">3</div><div>ダウンロードしたファイルを開くと OwnTracks が自動設定される</div></div>
    <div class="step"><div class="step-num">4</div><div>位置情報の許可を「常に」に設定して完了</div></div>
  </div>

  <form action="/config" method="get">
    <label for="name">あなたの名前（通知に表示されます）</label>
    <input type="text" id="name" name="name" placeholder="例: taro" required pattern="[A-Za-z0-9_\\-]+" title="半角英数字・アンダースコア・ハイフンのみ">
    <button type="submit">設定ファイルをダウンロード</button>
  </form>

  <div class="divider">── または QR コードでこのページを共有 ──</div>
  <div class="qr-wrap">
    <img src="data:image/png;base64,{qr_b64}" alt="QR Code">
    <div class="qr-label">{join_url}</div>
  </div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/config")
async def download_config(name: str):
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        return JSONResponse(status_code=400, content={"error": "名前は半角英数字・ハイフン・アンダースコアのみ使用できます"})
    tid = name[:2].lower()
    config = {
        "_type": "configuration",
        "mode": 3,
        "url": f"{BASE_URL}/owntracks",
        "userid": name,
        "deviceid": "phone",
        "tid": tid,
        "monitoring": 1,
        "ranging": False,
        "positions": 1,
        "autostartOnBoot": True,
    }
    content = json.dumps(config, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}.otrc"'},
    )


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
