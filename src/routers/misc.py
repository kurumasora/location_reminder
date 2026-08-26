from fastapi import APIRouter

from src.locations import user_state

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/status")
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
