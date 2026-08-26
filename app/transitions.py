import asyncio
from datetime import datetime

from fastapi.responses import JSONResponse

from app.config import DEBOUNCE_SECONDS, logger
from app.telegram import send_telegram

# (username, desc) -> 確定済みの方向 ("enter"/"leave")。未確定時は "leave"(圏外) 扱い
confirmed_direction: dict[tuple[str, str], str] = {}

# (username, desc) -> 保留中(未確定)のデバウンスタスク
pending_transitions: dict[tuple[str, str], asyncio.Task] = {}


async def confirm_transition(username: str, desc: str, direction: str, key: tuple[str, str], event_time: datetime):
    """DEBOUNCE_SECONDS 待ち、その間に取り消されなければ確定して通知する"""
    task = asyncio.current_task()
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return

    time_str = event_time.strftime("%H:%M")
    if direction == "enter":
        msg = f"📍 {username} が「{desc}」に到着しました ({time_str})"
    elif direction == "leave":
        msg = f"🚶 {username} が「{desc}」を出発しました ({time_str})"
    else:
        logger.info("Ignoring unknown transition direction: %s (%s)", direction, key)
        if task is not None and pending_transitions.get(key) is task:
            pending_transitions.pop(key, None)
        return

    try:
        logger.info(msg)
        await send_telegram(msg)
    except Exception:
        logger.exception("Failed to send transition notification: %s", key)
        return
    finally:
        if task is not None and pending_transitions.get(key) is task:
            pending_transitions.pop(key, None)

    confirmed_direction[key] = direction


def handle_transition(data: dict) -> JSONResponse:
    topic = data.get("topic", "")
    parts = topic.split("/")
    username = parts[1] if len(parts) >= 2 else data.get("tid", "unknown")
    event = data.get("event")
    desc = data.get("desc", "不明な場所")

    key = (username, desc)
    current = confirmed_direction.get(key, "leave")
    pending = pending_transitions.get(key)

    if event == current:
        # 確定済みの状態に戻った＝チャタリングだったので保留中の通知を取り消す
        if pending is not None:
            pending.cancel()
            pending_transitions.pop(key, None)
            logger.info("Debounce cancelled (reverted): %s", key)
    elif pending is None:
        # 新しい状態変化 → デバウンス開始（DEBOUNCE_SECONDS後に確定通知）
        pending_transitions[key] = asyncio.create_task(
            confirm_transition(username, desc, event, key, datetime.now())
        )
        logger.info("Debounce started: %s -> %s", key, event)
    # pending が既にある（同方向で確定待ち中）場合は何もせずタイマー継続

    return JSONResponse(content=[])
