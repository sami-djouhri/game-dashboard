"""game-dashboard — Web-UI vor der wake-bridge (Node .18).

Freunde (Gruppe `user`) sehen den Live-Status und starten Games; der Owner
(Gruppe `admin`) darf zusaetzlich stoppen/neustarten/erzwingen. Auth kommt per
Authelia-forward-auth vom dev-portal (Remote-Groups). Der Bridge-Bearer-Token
bleibt serverseitig.
"""
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import bridge, games
from app.auth import Principal, current_user, require_admin, require_start
from app.config import settings
from app.logging_config import configure_logging, get_logger

configure_logging(settings.log_level)
log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url=None,
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/me")
async def me(principal: Principal = Depends(current_user)) -> dict:
    return {
        "username": principal.username,
        "groups": principal.groups,
        "is_admin": principal.is_admin,
        "may_start": principal.may_start,
    }


@app.get("/api/status")
async def api_status(principal: Principal = Depends(current_user)) -> dict:
    try:
        raw = await bridge.get_status()
    except httpx.HTTPError as exc:
        log.warning("status.bridge_unreachable", error=str(exc))
        return {"ok": False, "error": "Arbiter (.18) nicht erreichbar", "games": []}
    view = games.build_view(raw)
    view["ok"] = True
    view["is_admin"] = principal.is_admin
    view["may_start"] = principal.may_start
    return view


async def _validate_game(game: str) -> None:
    """Game-Key gegen die Live-Registry pruefen (Anti-Injection)."""
    try:
        raw = await bridge.get_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Arbiter (.18) nicht erreichbar")
    if game not in games.known_games(raw):
        raise HTTPException(status_code=404, detail=f"Unbekanntes Game: {game}")


@app.post("/api/games/{game}/start")
async def start_game(game: str, principal: Principal = Depends(require_start)) -> dict:
    await _validate_game(game)
    outcome, msg = await bridge.post_action("start", game, force=False)
    log.info("action.start", game=game, user=principal.username, outcome=outcome)
    return {"outcome": outcome, "message": msg, "can_force": principal.is_admin and outcome == "conflict"}


@app.post("/api/games/{game}/stop")
async def stop_game(game: str, principal: Principal = Depends(require_admin)) -> dict:
    await _validate_game(game)
    outcome, msg = await bridge.post_action("stop", game)
    log.info("action.stop", game=game, user=principal.username, outcome=outcome)
    return {"outcome": outcome, "message": msg}


@app.post("/api/games/{game}/restart")
async def restart_game(game: str, principal: Principal = Depends(require_admin)) -> dict:
    await _validate_game(game)
    outcome, msg = await bridge.post_action("restart", game)
    log.info("action.restart", game=game, user=principal.username, outcome=outcome)
    return {"outcome": outcome, "message": msg}


@app.post("/api/games/{game}/force")
async def force_game(game: str, principal: Principal = Depends(require_admin)) -> dict:
    """Start erzwingen — verdraengt die aktuell belegte Rolle (nur Admin)."""
    await _validate_game(game)
    outcome, msg = await bridge.post_action("start", game, force=True)
    log.info("action.force", game=game, user=principal.username, outcome=outcome)
    return {"outcome": outcome, "message": msg}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
