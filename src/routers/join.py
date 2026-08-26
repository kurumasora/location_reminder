import json
from pathlib import Path
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

from src.config import BASE_URL, PLACES
from src.qr import make_qr_base64

router = APIRouter()

JOIN_TEMPLATE = Template((Path(__file__).parent.parent / "templates" / "join.html").read_text(encoding="utf-8"))


@router.get("/join", response_class=HTMLResponse)
async def join_page():
    join_url = f"{BASE_URL}/join"
    qr_b64 = make_qr_base64(join_url)
    html = JOIN_TEMPLATE.substitute(qr_b64=qr_b64, join_url=join_url)
    return HTMLResponse(content=html)


@router.get("/config")
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
