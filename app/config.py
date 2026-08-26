import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "state.db")

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

# 状態変化が何秒継続したら確定通知するか（チャタリング防止のデバウンス）
DEBOUNCE_SECONDS = int(os.getenv("DEBOUNCE_SECONDS", "180"))
