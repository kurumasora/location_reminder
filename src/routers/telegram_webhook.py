from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.config import BASE_URL, logger
from src.telegram import send_telegram

router = APIRouter()

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


@router.post("/telegram-webhook")
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
