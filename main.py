import os
import io
import json
import math
import base64
import sqlite3
import httpx
import qrcode
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "state.db")


def _db():
    return sqlite3.connect(DB_PATH)


def _init_db():
    with _db() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS user_state "
            "(username TEXT PRIMARY KEY, inside TEXT, lat REAL, lon REAL)"
        )


def _load_states() -> dict[str, dict]:
    with _db() as con:
        rows = con.execute("SELECT username, inside, lat, lon FROM user_state").fetchall()
    return {
        row[0]: {"inside": json.loads(row[1]), "lat": row[2], "lon": row[3]}
        for row in rows
    }


def _save_state(username: str, state: dict):
    with _db() as con:
        con.execute(
            "INSERT INTO user_state (username, inside, lat, lon) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(username) DO UPDATE SET inside=excluded.inside, lat=excluded.lat, lon=excluded.lon",
            (username, json.dumps(state["inside"]), state.get("lat"), state.get("lon")),
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_db()
    user_state.update(_load_states())
    logger.info("Loaded user_state from DB: %s", list(user_state.keys()))
    yield


app = FastAPI(title="Location Notifier", lifespan=lifespan)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BASE_URL = os.getenv("BASE_URL", "https://manso.ahirukuma.cc")

PLACES = [
    {
        "name": os.getenv("PLACE_1_NAME", "会社"),
        "lat": float(os.getenv("PLACE_1_LAT", "35.6895")),
        "lon": float(os.getenv("PLACE_1_LON", "139.6917")),
        "radius_m": float(os.getenv("PLACE_1_RADIUS", "200")),
    },
]

# ユーザーごとの前回状態（起動時にDBからロード）
user_state: dict[str, dict] = {}

# transition イベントの重複通知防止（username -> {key, time}）
last_transition: dict[str, dict] = {}

# 全員集合通知済みフラグ（全員insideになったら1回だけ通知）
all_inside_notified = False


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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

    # transition イベントは Telegram 通知のみ（状態管理は location イベントに一本化）
    if data.get("_type") == "transition":
        topic = data.get("topic", "")
        parts = topic.split("/")
        username = parts[1] if len(parts) >= 2 else data.get("tid", "unknown")
        event = data.get("event")
        desc = data.get("desc", "不明な場所")
        time_str = datetime.now().strftime("%H:%M")

        # 60秒以内に同じ通知を送っていればスキップ
        dedup_key = (username, event, desc)
        last = last_transition.get(username)
        now_ts = datetime.now().timestamp()
        if last and last["key"] == dedup_key and now_ts - last["time"] < 60:
            logger.info("Skipping duplicate transition: %s", dedup_key)
            return JSONResponse(content=[])
        last_transition[username] = {"key": dedup_key, "time": now_ts}

        if event == "enter":
            msg = f"📍 {username} が「{desc}」に到着しました ({time_str})"
            logger.info(msg)
            await send_telegram(msg)
        elif event == "leave":
            msg = f"🚶 {username} が「{desc}」を出発しました ({time_str})"
            logger.info(msg)
            await send_telegram(msg)
        return JSONResponse(content=[])

    if data.get("_type") != "location":
        return JSONResponse(content=[])

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
    waypoints = [
        {
            "_type": "waypoint",
            "desc": p["name"],
            "lat": p["lat"],
            "lon": p["lon"],
            "rad": int(p["radius_m"]),
            "tst": 0,
        }
        for p in PLACES
    ]
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
        "waypoints": waypoints,
    }
    content = json.dumps(config, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{name}.otrc"'},
    )


WELCOME_MESSAGE = """👋 ようこそ！位置情報通知グループへ！

このグループでは、メンバーが特定の場所に到着・出発したときに自動で通知が届きます。

━━━━━━━━━━━━━━━━
📱 導入手順（3ステップ）
━━━━━━━━━━━━━━━━

① OwnTracks アプリをインストール
　• iPhone: App Store で「OwnTracks」を検索
　• Android: Google Play で「OwnTracks」を検索

② 設定ファイルをダウンロード
　以下のリンクを開いて名前を入力するだけで自動設定されます👇
　{join_url}

③ 位置情報の許可を「常に」に設定
　設定アプリ → OwnTracks → 位置情報 → 常に許可

以上で完了です！何かわからないことがあれば気軽に聞いてください 😊"""


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    logger.info("Telegram update: %s", data)

    message = data.get("message", {})

    new_members = message.get("new_chat_members", [])
    for member in new_members:
        if member.get("is_bot"):
            continue
        first_name = member.get("first_name", "")
        text = f"@{member.get('username', first_name)} さん、\n\n" + WELCOME_MESSAGE.format(join_url=f"{BASE_URL}/join")
        await send_telegram(text)

    return JSONResponse(content={"ok": True})


@app.get("/health")
async def health():
    return {"status": "ok"}


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
