"""Client fuer die wake-bridge des Wirts, der die Spiele haelt (seit 2026-08-22 gamehost).

GET /status  -> token-frei, Live-Snapshot des Arbiters
POST /wake|/sleep|/restart/<game> -> Bearer, steuert eine Game-Rolle
POST /reservieren|/freigeben/<game> -> Bearer, Schutz vor Auto-Off und Verdraengung

Der Bearer-Token bleibt hier serverseitig und wird nie an den Browser gereicht.
"""
import asyncio
import socket
import time

import httpx

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

_KIND_PATH = {"start": "wake", "stop": "sleep", "restart": "restart"}

# Kurzer TTL-Cache fuer /status: mehrere offene Tabs + Steuer-Aktionen sehen
# denselben Snapshot statt leicht unterschiedlicher, und der Doppel-Fetch pro
# Aktion (Validierung + folgendes refresh()) entfaellt.
_STATUS_TTL_S = 2.5
_status_cache: dict = {"ts": 0.0, "data": None}
_status_lock = asyncio.Lock()


def _invalidate_status() -> None:
    _status_cache["ts"] = 0.0


# Dauerlaeufer (DayZ auf netcup) stehen NICHT in der Arbiter-Registry — ihre Spielerzahl
# kommt per Steam-Query direkt vom Server. Eigener, laengerer Cache: die Abfrage ist ein
# UDP-Roundtrip uebers Internet, den nicht jeder Seitenaufruf neu bezahlen soll.
_ALWAYS_ON_TTL_S = 20.0
_always_on_cache: dict = {"ts": 0.0, "data": {}}
_always_on_lock = asyncio.Lock()


def _tcp_offen(host: str, port: int, timeout: float = 2.5) -> bool:
    """Nimmt der Port Verbindungen an? Fuer Spiele ohne Steam-Abfrage die einzige Auskunft."""
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def _dauerlaeufer_info(cfg: dict) -> dict | None:
    """Zustand eines Dauerlaeufers je nach hinterlegter Probe-Art.

    Bei `tcp` bleibt `players` bewusst None — "laeuft" und "niemand ist drauf" sind
    zweierlei. Bei `keine` ist der Zustand von aussen gar nicht feststellbar; das wird
    als solches gemeldet und nicht als Ausfall.
    """
    art = cfg.get("probe", "a2s")
    if art == "keine":
        return {"karte": "", "players": None, "slots": None, "unbekannt": True}
    if art == "tcp":
        if _tcp_offen(cfg["host"], cfg["query_port"]):
            return {"karte": "", "players": None, "slots": None}
        return None
    return _a2s_info(cfg["host"], cfg["query_port"])


def _a2s_info(host: str, port: int, timeout: float = 2.5) -> dict | None:
    """Steam-Query (A2S_INFO). None, wenn der Server nicht antwortet.

    Der Challenge-Token muss an die KOMPLETTE Anfrage inklusive Nullbyte angehaengt
    werden — ohne das Nullbyte bleibt die zweite Anfrage unbeantwortet.
    """
    req = b"\xff\xff\xff\xffTSource Engine Query\x00"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(req, (host, port))
        data, _ = sock.recvfrom(4096)
        if len(data) >= 9 and data[4] == 0x41:          # 'A' = Challenge
            sock.sendto(req + data[5:9], (host, port))
            data, _ = sock.recvfrom(4096)
        if not (len(data) >= 6 and data[4] == 0x49):    # 'I' = INFO
            return None
        felder = data[6:].split(b"\x00", 4)            # name/map/folder/game/rest
        if len(felder) < 5 or len(felder[4]) < 4:
            return None
        return {"karte": felder[1].decode("utf-8", "replace"),
                "players": felder[4][2], "slots": felder[4][3]}
    except OSError:
        return None
    finally:
        sock.close()


async def get_always_on() -> dict:
    """{key: {players, slots, karte} | None} fuer alle Dauerlaeufer, mit TTL-Cache."""
    from app.games import ALWAYS_ON

    now = time.monotonic()
    if now - _always_on_cache["ts"] < _ALWAYS_ON_TTL_S:
        return _always_on_cache["data"]
    async with _always_on_lock:
        now = time.monotonic()
        if now - _always_on_cache["ts"] < _ALWAYS_ON_TTL_S:
            return _always_on_cache["data"]
        ergebnis = {}
        for key, cfg in ALWAYS_ON.items():
            ergebnis[key] = await asyncio.to_thread(_dauerlaeufer_info, cfg)
        _always_on_cache["data"] = ergebnis
        _always_on_cache["ts"] = time.monotonic()
        return ergebnis


async def get_status() -> dict:
    """Arbiter-Status mit kurzem TTL-Cache. Wirft httpx-Fehler bei Unerreichbarkeit."""
    now = time.monotonic()
    if _status_cache["data"] is not None and now - _status_cache["ts"] < _STATUS_TTL_S:
        return _status_cache["data"]
    async with _status_lock:
        now = time.monotonic()
        if _status_cache["data"] is not None and now - _status_cache["ts"] < _STATUS_TTL_S:
            return _status_cache["data"]
        url = f"{settings.game_bridge_url}/status"
        async with httpx.AsyncClient(timeout=settings.bridge_status_timeout_s) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        _status_cache["data"] = data
        _status_cache["ts"] = time.monotonic()
        return data


async def post_action(action: str, game: str,
                      world: str | None = None) -> tuple[str, str]:
    """Steuer-Aktion an die Bridge. action in {start,stop,restart}.

    world: gewuenschte Welt (nur multi_world-Games; wake/restart). Der Arbiter
    validiert gegen seine Registry und lehnt einen Welt-Wechsel bei laufendem
    Server ab (rc==3) — Wechsel = erst stoppen, dann mit neuer Welt starten.

    Rueckgabe (outcome, menschliche Meldung), outcome in {ok, conflict, error}.
    'conflict' = Arbiter lehnt ab (rc==3), weil eine belegte oder reservierte
    Rolle Vorrang hat. Das ist endgueltig: seit dem 2026-08-23 gibt es kein
    Erzwingen mehr, auch nicht fuer Admins (wer spielt, wird nicht gekickt).
    Der Anfragende versucht es spaeter erneut.
    """
    if not settings.game_bridge_token:
        return "error", "Kein GAME_BRIDGE_TOKEN gesetzt, Steuerung deaktiviert."
    verb = _KIND_PATH[action]
    params = []
    if world:
        params.append(f"world={world}")
    url = f"{settings.game_bridge_url}/{verb}/{game}" + (("?" + "&".join(params)) if params else "")
    headers = {"Authorization": f"Bearer {settings.game_bridge_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.bridge_action_timeout_s) as client:
            resp = await client.post(url, headers=headers)
    except httpx.TimeoutException:
        _invalidate_status()
        return "error", "Zeitüberschreitung, der Vorgang läuft evtl. im Hintergrund weiter. Status in ~1 min prüfen."
    except httpx.HTTPError as exc:
        log.warning("bridge.unreachable", url=url, error=str(exc))
        return "error", f"wake-bridge nicht erreichbar: {exc}"

    # Nach jeder Aktion den Status-Cache verwerfen, damit das naechste
    # refresh() den neuen Zustand zeigt (sonst wirkt die UI bis TTL "haengend").
    _invalidate_status()
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
        return "error", "Arbiter-Timeout, Status in ~1 min prüfen."
    return "error", f"Unerwartete Antwort ({resp.status_code})."


async def set_reservierung(game: str, an: bool) -> tuple[str, str]:
    """Reservierung setzen/aufheben: der Server bleibt stehen, bis sie faellt.

    Gedacht fuer den Fall, dass jemand gleich spielen will oder an einer Welt
    arbeitet — ohne den Schalter koennte ein leerer Server jederzeit dem
    Startwunsch eines anderen weichen oder ins Auto-Off laufen.
    Rueckgabe (outcome, Meldung), outcome in {ok, error}.
    """
    if not settings.game_bridge_token:
        return "error", "Kein GAME_BRIDGE_TOKEN gesetzt, Steuerung deaktiviert."
    verb = "reservieren" if an else "freigeben"
    url = f"{settings.game_bridge_url}/{verb}/{game}"
    headers = {"Authorization": f"Bearer {settings.game_bridge_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.bridge_action_timeout_s) as client:
            resp = await client.post(url, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("bridge.unreachable", url=url, error=str(exc))
        return "error", f"wake-bridge nicht erreichbar: {exc}"
    _invalidate_status()
    if resp.status_code != 200:
        return "error", f"Unerwartete Antwort ({resp.status_code})."
    data = resp.json()
    rc = data.get("rc")
    if rc == 0:
        return "ok", ("Reserviert: der Server bleibt an, bis die Reservierung "
                      "aufgehoben wird." if an else
                      "Reservierung aufgehoben, der Server geht wieder von selbst "
                      "aus, wenn ihn niemand nutzt.")
    if rc == 3:
        # Ein Schutz fuer etwas, das gar nicht laeuft, waere eine stille Karteileiche:
        # der Arbiter fuehrt nur, was er verwaltet.
        return "error", "Der Server läuft gerade nicht. Erst starten, dann reservieren."
    return "error", _tail_log(data)


async def create_world(game: str, world_id: str, label: str = "") -> tuple[str, str]:
    """Neue Welt in der Arbiter-Registry anlegen (Dateien entstehen beim ersten Start).

    Rueckgabe (outcome, Meldung), outcome in {ok, error}."""
    if not settings.game_bridge_token:
        return "error", "Kein GAME_BRIDGE_TOKEN gesetzt, Steuerung deaktiviert."
    url = f"{settings.game_bridge_url}/worlds/{game}/create"
    headers = {"Authorization": f"Bearer {settings.game_bridge_token}"}
    try:
        async with httpx.AsyncClient(timeout=settings.bridge_action_timeout_s) as client:
            resp = await client.post(url, headers=headers,
                                     json={"id": world_id, "label": label})
    except httpx.HTTPError as exc:
        log.warning("bridge.unreachable", url=url, error=str(exc))
        return "error", f"wake-bridge nicht erreichbar: {exc}"
    _invalidate_status()
    if resp.status_code == 200:
        data = resp.json()
        if data.get("rc") == 0:
            return "ok", f"Welt „{world_id}“ angelegt, sie wird beim ersten Start erzeugt."
        return "error", _tail_log(data)
    if resp.status_code == 400:
        return "error", "Ungültige Welt-ID oder unbekanntes Game (400)."
    if resp.status_code == 401:
        return "error", "Token abgelehnt (401)."
    return "error", f"Unerwartete Antwort ({resp.status_code})."


async def list_snapshots(game: str) -> dict:
    """Snapshot-Liste eines Games (nightly + manuell). Wirft httpx-Fehler."""
    url = f"{settings.game_bridge_url}/snapshots/{game}"
    async with httpx.AsyncClient(timeout=settings.bridge_status_timeout_s * 2) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# Arbiter-Exit-Codes der Snapshot-Kommandos -> menschliche Meldung.
_SNAP_RC = {
    0: "ok",
    1: "Fehlgeschlagen, Details im Arbiter-Log.",
    4: "Abgelehnt: Spiel läuft oder die Welt ist geschützt (aktiv/letzte).",
    5: "Unbekanntes Ziel (Datei/Welt nicht gefunden).",
}


async def _post_snapshot_api(path: str, json_body: dict | None = None,
                             timeout: float | None = None) -> tuple[str, str]:
    """POST an die Snapshot-/Welt-Endpunkte der Bridge; mappt Arbiter-rc.
    Rueckgabe (outcome, Meldung), outcome in {ok, blocked, error}."""
    if not settings.game_bridge_token:
        return "error", "Kein GAME_BRIDGE_TOKEN gesetzt, Steuerung deaktiviert."
    url = f"{settings.game_bridge_url}{path}"
    headers = {"Authorization": f"Bearer {settings.game_bridge_token}"}
    try:
        async with httpx.AsyncClient(timeout=timeout or settings.bridge_action_timeout_s) as client:
            resp = await client.post(url, headers=headers, json=json_body)
    except httpx.TimeoutException:
        return "error", "Zeitüberschreitung. Der Vorgang läuft evtl. im Hintergrund weiter."
    except httpx.HTTPError as exc:
        log.warning("bridge.unreachable", url=url, error=str(exc))
        return "error", f"wake-bridge nicht erreichbar: {exc}"
    _invalidate_status()
    if resp.status_code == 200:
        data = resp.json()
        rc = data.get("rc")
        if rc == 0:
            return "ok", _tail_log(data)
        outcome = "blocked" if rc == 4 else "error"
        return outcome, _SNAP_RC.get(rc, f"Arbiter-Fehler (rc={rc}).") + "\n" + _tail_log(data)
    if resp.status_code == 401:
        return "error", "Token abgelehnt (401)."
    if resp.status_code == 400:
        return "error", "Ungültige Anfrage (400)."
    if resp.status_code == 504:
        return "error", "Arbiter-Timeout, Status in ~1 min prüfen."
    return "error", f"Unerwartete Antwort ({resp.status_code})."


async def snapshot_now(game: str, world: str | None = None) -> tuple[str, str]:
    q = f"?world={world}" if world else ""
    return await _post_snapshot_api(f"/snapshot/{game}{q}", timeout=600.0)


async def restore_snapshot(game: str, file: str) -> tuple[str, str]:
    return await _post_snapshot_api(f"/restore/{game}", {"file": file}, timeout=600.0)


async def delete_snapshot(game: str, file: str) -> tuple[str, str]:
    return await _post_snapshot_api(f"/snapshots/{game}/delete", {"file": file})


async def delete_world(game: str, world_id: str) -> tuple[str, str]:
    return await _post_snapshot_api(f"/worlds/{game}/delete", {"id": world_id}, timeout=600.0)


def _tail_log(data: dict) -> str:
    log_lines = data.get("log") or []
    lines = [str(x) for x in log_lines[-4:] if str(x).strip()]
    return "\n".join(lines) if lines else "fertig"


def _conflict_msg(data: dict) -> str:
    """Der Arbiter schreibt seine Absage im Klartext ins Log — die wird 1:1 gezeigt.

    Der Rahmensatz nennt nur noch das Ergebnis. Frueher stand hier '.18 hat nur einen
    RAM-Slot': das galt, als nur ein Spiel gleichzeitig laufen konnte, und stimmt seit
    dem Umzug auf den Spiele-VPS doppelt nicht mehr — dort laufen mehrere nebeneinander,
    und die Grenze ist der Speicher, nicht ein Slot.
    """
    reason = ""
    for line in reversed([str(x) for x in (data.get("log") or [])]):
        if "ABGELEHNT" in line:
            reason = line.split("ABGELEHNT:", 1)[-1].strip()
            break
    base = "Gerade nicht möglich."
    return f"{base} {reason}" if reason else (
        base + " Es wird gerade gespielt oder der Speicher reicht nicht, "
        "bitte später erneut versuchen."
    )
