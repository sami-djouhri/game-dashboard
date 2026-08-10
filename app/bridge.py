"""Client fuer die wake-bridge (Node .18, LAN-only).

GET /status  -> token-frei, Live-Snapshot des Arbiters
POST /wake|/sleep|/restart/<game>[?force=1] -> Bearer, steuert eine Game-Rolle

Der Bearer-Token bleibt hier serverseitig und wird nie an den Browser gereicht.
"""
import httpx

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

_KIND_PATH = {"start": "wake", "stop": "sleep", "restart": "restart"}


async def get_status() -> dict:
    """Roher Arbiter-Status. Wirft httpx-Fehler bei Unerreichbarkeit."""
    url = f"{settings.game_bridge_url}/status"
    async with httpx.AsyncClient(timeout=settings.bridge_status_timeout_s) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


async def post_action(action: str, game: str, force: bool = False) -> tuple[str, str]:
    """Steuer-Aktion an die Bridge. action in {start,stop,restart}.

    Rueckgabe (outcome, menschliche Meldung), outcome in {ok, conflict, error}.
    'conflict' = Arbiter lehnt ab (rc==3), weil eine belegte Rolle Vorrang hat
    -> nur ein Admin kann mit force=True verdraengen.
    """
    if not settings.game_bridge_token:
        return "error", "Kein GAME_BRIDGE_TOKEN gesetzt — Steuerung deaktiviert."
    verb = _KIND_PATH[action]
    url = f"{settings.game_bridge_url}/{verb}/{game}" + ("?force=1" if force else "")
    headers = {"Authorization": f"Bearer {settings.game_bridge_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.bridge_action_timeout_s) as client:
            resp = await client.post(url, headers=headers)
    except httpx.TimeoutException:
        return "error", "Zeitüberschreitung — der Vorgang läuft evtl. im Hintergrund weiter. Status in ~1 min prüfen."
    except httpx.HTTPError as exc:
        log.warning("bridge.unreachable", url=url, error=str(exc))
        return "error", f"wake-bridge nicht erreichbar: {exc}"

    if resp.status_code == 200:
        data = resp.json()
        rc = data.get("rc")
        if rc == 0:
            return "ok", _tail_log(data)
        if rc == 3:
            return "conflict", _conflict_msg(data)
        return "error", f"Arbiter-Fehler (rc={rc}).\n{_tail_log(data)}"
    if resp.status_code == 401:
        return "error", "Token abgelehnt (401)."
    if resp.status_code == 400:
        return "error", "Unbekanntes Game (400)."
    if resp.status_code == 504:
        return "error", "Arbiter-Timeout — Status in ~1 min prüfen."
    return "error", f"Unerwartete Antwort ({resp.status_code})."


def _tail_log(data: dict) -> str:
    log_lines = data.get("log") or []
    lines = [str(x) for x in log_lines[-4:] if str(x).strip()]
    return "\n".join(lines) if lines else "fertig"


def _conflict_msg(data: dict) -> str:
    reason = ""
    for line in reversed([str(x) for x in (data.get("log") or [])]):
        if "ABGELEHNT" in line:
            reason = line.split("ABGELEHNT:", 1)[-1].strip()
            break
    base = "Abgelehnt — eine andere Rolle hat gerade Vorrang (.18 hat nur einen RAM-Slot)."
    return f"{base}\n{reason}" if reason else base
