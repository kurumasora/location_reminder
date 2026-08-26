import json
import sqlite3

from src.config import DB_PATH


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
