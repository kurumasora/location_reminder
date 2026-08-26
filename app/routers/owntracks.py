from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import logger
from app.transitions import handle_transition
from app.locations import handle_location

router = APIRouter()


@router.post("/owntracks")
async def owntracks_webhook(request: Request):
    """OwnTracks HTTP modeのwebhook受信エンドポイント"""
    data = await request.json()
    logger.info("Received: %s", data)

    # transition イベントは Telegram 通知のみ（状態管理は location イベントに一本化）
    if data.get("_type") == "transition":
        return handle_transition(data)

    if data.get("_type") != "location":
        return JSONResponse(content=[])

    return await handle_location(data)
