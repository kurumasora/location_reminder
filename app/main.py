from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import logger
from app.db import _init_db, _load_states
from app import locations
from app.routers import owntracks, join, telegram_webhook, misc


@asynccontextmanager
async def lifespan(_: FastAPI):
    _init_db()
    locations.user_state.update(_load_states())
    logger.info("Loaded user_state from DB: %s", list(locations.user_state.keys()))
    yield


app = FastAPI(title="Location Notifier", lifespan=lifespan)

app.include_router(owntracks.router)
app.include_router(join.router)
app.include_router(telegram_webhook.router)
app.include_router(misc.router)
