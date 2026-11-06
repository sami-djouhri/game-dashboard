"""JSON-API: Live-Status (oeffentlich reduziert + Member-Vollbild) und
Steuer-Aktionen (Start = Member, Stop/Restart/Force/Welt-Wechsel = Admin)."""
from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pathlib import Path

from app import bridge, db, games, vault
from app.auth import (Principal, check_csrf, current_user, optional_user,
                      require_admin, require_owner, require_verified)
from app.config import settings
from app.logging_config import get_logger
from app.security import rate

router = APIRouter(prefix="/api")
log = get_logger(__name__)

_WORLD_RE = re.compile(r"^[a-z0-9-]{3,24}$")

# Laenge des Aktivitaets-Streifens auf der Kachel. Vierzehn Balken passen auf
# einem 320-px-Schirm nebeneinander, ohne dass einer unter 3 px breit wird, und
# zwei Wochen decken den Rhythmus einer Runde ab, die sich am Wochenende trifft.
AKTIVITAET_TAGE = 14

# Zeilen im Verlauf-Panel einer Kachel. Genug fuer die letzten Sitzungen samt
# ihrer Vorgeschichte, wenig genug, dass die aufgeklappte Karte nicht zur Seite
# wird. Wer weiter zurueck will, hat den Admin-Verlauf mit Filtern.
VERLAUF_ZEILEN = 25


async def _raw_status() -> dict:
    return await bridge.get_status()


@router.get("/public/status")
async def public_status():
    """Oeffentlich, reduziert: nur was laeuft + Spielerzahlen (kein Interna)."""
    arbiter_ok = True
    try:
        raw = await _raw_status()
    except httpx.HTTPError:
        # Kein Grund, die Seite zu leeren: die Dauerlaeufer probt das Dashboard selbst.
        raw, arbiter_ok = {}, False
    summary = games.public_summary(
        games.build_view(raw, await bridge.get_always_on(), arbiter_ok))
    summary["ok"] = True
    summary["arbiter_ok"] = arbiter_ok
    return summary


@router.get("/me")
async def me(principal: Principal = Depends(current_user)):
    return {
        "username": principal.username,
        "display_name": principal.display_name,
        "role": principal.role,
        "is_admin": principal.is_admin,
        "is_owner": principal.is_owner,
        "verified": principal.verified,
        "may_start": principal.may_start,
        "can_download": principal.can_download,
    }


@router.get("/status")
async def status(principal: Principal = Depends(current_user)):
    arbiter_ok = True
    try:
        raw = await _raw_status()
    except httpx.HTTPError as exc:
        log.warning("status.bridge_unreachable", error=str(exc))
        raw, arbiter_ok = {}, False
    view = games.build_view(raw, await bridge.get_always_on(), arbiter_ok)
    _aktivitaet_anhaengen(view)
    view["ok"] = True
    view["arbiter_ok"] = arbiter_ok
    view["is_admin"] = principal.is_admin
    view["is_owner"] = principal.is_owner
    view["may_start"] = principal.may_start
    return view


def _aktivitaet_anhaengen(view: dict) -> None:
    """Den 14-Tage-Streifen an jede Kachel haengen.

    Hier und nicht in `games.build_view()`: das baut die Kacheln allein aus dem
    Arbiter-Status und kennt die Datenbank nicht. Diese Trennung ist der Grund,
    warum `build_view` in den Tests ohne SQLite laeuft.

    Bewusst NUR in `/api/status`, nie in `/api/public/status`. Wer wann
    gespielt hat, ist auf Tagesaufloesung ein Anwesenheitsprotokoll einer Runde
    von acht Leuten; die oeffentliche Seite bekommt deshalb weiterhin nur das
    grob gestaffelte „zuletzt gespielt" aus `letzte_aktivitaet()`, das kein
    Spiel und keine Uhrzeit nennt. Dieselbe Abwaegung wie dort.
    """
    try:
        aktiv = db.aktivitaet_je_spiel(AKTIVITAET_TAGE)
    except Exception as exc:
        # Ein Streifen ist Beiwerk. Faellt er aus, bleibt die Kachel bedienbar;
        # eine Steuerseite darf an einer Statistikabfrage nicht scheitern.
        log.warning("status.aktivitaet_fehlt", error=str(exc))
        return
    # Jede Kachel bekommt das Feld, auch die ohne jede Aktivitaet. Nur die
    # Kacheln zu versorgen, fuer die Zeilen vorliegen, haette den Streifen
    # ausgerechnet dort weggelassen, wo er die Frage beantwortet: bei einem
    # Server, auf dem lange niemand war. Der Leerzustand ist eine Aussage
    # („in zwei Wochen niemand"), keine fehlende Angabe.
    for kachel in view.get("games", []):
        # Je Kachel ein eigenes Leer-Objekt: ein geteiltes waere eine stille
        # Falle, sobald jemand spaeter eine Kachel nachbearbeitet.
        kachel["aktivitaet"] = aktiv.get(
            kachel.get("key"), {"tage": [0.0] * AKTIVITAET_TAGE, "zuletzt_s": None})


@router.get("/games/{game}/verlauf")
async def game_verlauf(game: str, principal: Principal = Depends(current_user)):
    """Was mit diesem Server passiert ist, juengstes zuerst.

    Mitglieder-Recht, nicht Admin: die Frage „wer hat geweckt und wurde daraus
    eine Runde" stellt sich jedem, der ueberlegt, ob er dazukommt. Was ein
    Mitglied hier ueber Personen sieht, steht ohnehin schon im Feed auf
    derselben Seite.

    ⚠️ `_validate_game` wird hier bewusst NICHT aufgerufen. Es fragt die Bridge,
    und der Verlauf soll gerade dann lesbar sein, wenn die nicht antwortet: ein
    Server, der nicht erreichbar ist, ist der haeufigste Anlass nachzusehen,
    was zuletzt mit ihm war. Die Kennung ist nur eine Datenbankabfrage weit und
    kann nichts anrichten; ein unbekanntes Spiel liefert eine leere Liste.
    """
    zeilen = db.events_fuer_spiel(game, limit=VERLAUF_ZEILEN)
    return {"game": game, "eintraege": [
        {"ts": z["ts"], "actor": z["actor"], "action": z["action"], "detail": z["detail"]}
        for z in zeilen]}


async def _validate_game(game: str) -> dict:
    try:
        raw = await _raw_status()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Server-Steuerung antwortet nicht")
    if game not in games.known_games(raw):
        raise HTTPException(status_code=404, detail=f"Unbekanntes Game: {game}")
    return raw


def _validate_world(raw: dict, game: str, world: str) -> None:
    """world gegen die Arbiter-Registry pruefen (Anti-Injection + klare Fehler)."""
    if not _WORLD_RE.match(world):
        raise HTTPException(status_code=400, detail="Ungültige Welt-ID (a-z, 0-9, -, 3–24 Zeichen)")
    winfo = ((raw.get("games") or {}).get("worlds") or {}).get(game)
    if not winfo:
        raise HTTPException(status_code=400, detail=f"{game} hat keine Multi-Welten")
    if world not in (winfo.get("list") or []):
        raise HTTPException(status_code=404, detail=f"Unbekannte Welt: {world}")


def _csrf(request: Request, principal: Principal) -> None:
    check_csrf(request, principal, request.headers.get("x-csrf-token"))


@router.post("/games/{game}/start")
async def start_game(game: str, request: Request, world: str | None = None,
                     principal: Principal = Depends(current_user)):
    _csrf(request, principal)
    raw = await _validate_game(game)
    if world:
        _validate_world(raw, game, world)
    outcome, msg = await bridge.post_action("start", game, world=world)
    db.log_event(principal.username, "game.start", f"{game}{f' welt={world}' if world else ''} -> {outcome}", game=game)
    # Kein can_force mehr: eine Absage ist endgueltig, auch fuer Admins. Frueher bekam
    # ein Admin hier einen Erzwingen-Knopf angeboten, der eine laufende Partie beendet
    # haette: genau das soll es nicht mehr geben (Ansage 2026-08-23).
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/switch")
async def switch_world(game: str, request: Request, world: str,
                       principal: Principal = Depends(require_admin)):
    """Admin: laufende Welt wechseln (graceful stop mit Save, dann Start der neuen Welt)."""
    _csrf(request, principal)
    raw = await _validate_game(game)
    _validate_world(raw, game, world)
    outcome, msg = await bridge.post_action("restart", game, world=world)
    db.log_event(principal.username, "game.switch", f"{game} welt={world} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/worlds")
async def create_world(game: str, request: Request,
                       principal: Principal = Depends(require_admin)):
    """Admin: neue Welt anlegen (Registry; Dateien entstehen beim ersten Start).
    Durchgesetzt wird im Arbiter: eine neue Welt je Spiel und Tag fuer alle Admins
    zusammen, hoechstens 6 je Spiel, Ersteller steht an der Welt. Der Owner ist vom
    Tageslimit ausgenommen. Das Rate-Limit hier ist nur die zweite Schranke."""
    _csrf(request, principal)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON-Body erwartet")
    wid = str(body.get("id") or "").strip().lower()
    label = str(body.get("label") or "").strip()[:40]
    if not _WORLD_RE.match(wid):
        raise HTTPException(status_code=400, detail="Ungültige Welt-ID (a-z, 0-9, -, 3–24 Zeichen)")
    raw = await _validate_game(game)
    if not ((raw.get("games") or {}).get("worlds") or {}).get(game):
        raise HTTPException(status_code=400, detail=f"{game} hat keine Multi-Welten")
    if not principal.is_owner and not rate.allow(f"worldcreate:{principal.id}", 1, 86400):
        raise HTTPException(status_code=429, detail="Welt-Limit erreicht (1 neue Welt pro Tag)")
    outcome, msg = await bridge.create_world(game, wid, label, wer=principal.username,
                                             owner=principal.is_owner)
    db.log_event(principal.username, "world.create", f"{game}/{wid} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/stop")
async def stop_game(game: str, request: Request,
                    principal: Principal = Depends(require_admin)):
    _csrf(request, principal)
    await _validate_game(game)
    outcome, msg = await bridge.post_action("stop", game)
    db.log_event(principal.username, "game.stop", f"{game} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/restart")
async def restart_game(game: str, request: Request,
                       principal: Principal = Depends(require_admin)):
    _csrf(request, principal)
    await _validate_game(game)
    outcome, msg = await bridge.post_action("restart", game)
    db.log_event(principal.username, "game.restart", f"{game} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/reserve")
async def reserve_game(game: str, request: Request,
                       principal: Principal = Depends(require_admin)):
    """Admin: Server reservieren, kein Auto-Off, keine Verdraengung.

    Das ist der Ersatz fuer den frueheren Erzwingen-Knopf, aber mit umgekehrter
    Richtung: statt anderen den Platz wegzunehmen, sichert man sich den eigenen.
    """
    _csrf(request, principal)
    await _validate_game(game)
    outcome, msg = await bridge.set_reservierung(game, True)
    db.log_event(principal.username, "game.reserve", f"{game} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/release")
async def release_game(game: str, request: Request,
                       principal: Principal = Depends(require_admin)):
    """Admin: Reservierung aufheben, der Server geht wieder von selbst aus."""
    _csrf(request, principal)
    await _validate_game(game)
    outcome, msg = await bridge.set_reservierung(game, False)
    db.log_event(principal.username, "game.release", f"{game} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


# ── Welten-Download (nur admin-verifizierte Mitglieder) ───────────────
@router.get("/worlds/{key}/download")
async def download_world(key: str, world: str | None = None,
                         principal: Principal = Depends(require_verified)):
    """world=<id> lädt bei Multi-World-Games das Tar der jeweiligen Welt
    (<key>/<world>.tar.gz), ohne world das Single-World-Tar (<key>.tar.gz)."""
    path = vault.world_path(key, world)
    if not path:
        raise HTTPException(status_code=404, detail="Kein Snapshot vorhanden")
    db.log_event(principal.username, "world.download",
                 f"{key}{f'/{world}' if world else ''}", game=key)
    fname = f"greenleaf-{key}{f'-{world}' if world else ''}.tar.gz"
    return FileResponse(path, media_type="application/gzip", filename=fname)


# ── Admin: Snapshots erstellen/listen/zurueckspielen/loeschen ─────────
_SNAP_FILE_RE = re.compile(r"^[a-z0-9][A-Za-z0-9._/-]{0,120}\.tar\.gz$")


def _snap_file_from(body: dict) -> str:
    fn = str(body.get("file") or "").strip()
    if ".." in fn or not _SNAP_FILE_RE.match(fn):
        raise HTTPException(status_code=400, detail="Ungültige Snapshot-Datei")
    return fn


@router.get("/games/{game}/snapshots")
async def game_snapshots(game: str, principal: Principal = Depends(require_admin)):
    await _validate_game(game)
    try:
        return await bridge.list_snapshots(game)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Server-Steuerung antwortet nicht")


@router.post("/games/{game}/snapshot")
async def snapshot_game(game: str, request: Request, world: str | None = None,
                        principal: Principal = Depends(require_admin)):
    _csrf(request, principal)
    raw = await _validate_game(game)
    if world:
        _validate_world(raw, game, world)
    outcome, msg = await bridge.snapshot_now(game, world, wer=principal.username,
                                             owner=principal.is_owner)
    db.log_event(principal.username, "snapshot.create", f"{game}{f' welt={world}' if world else ''} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/restore")
async def restore_game(game: str, request: Request,
                       principal: Principal = Depends(require_admin)):
    """Restore, auch bei laufendem Server: der Arbiter kündigt im Spiel 60 s und 10 s
    vorher an, speichert, stoppt, spielt ein und startet mit der vorher laufenden Welt neu.
    Vorher legt er selbst eine Sicherung im Topf vor-einspielen/ an. Der doppelte Confirm
    passiert clientseitig, hier zählt das Audit-Log."""
    _csrf(request, principal)
    await _validate_game(game)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON-Body erwartet")
    fn = _snap_file_from(body)
    outcome, msg = await bridge.restore_snapshot(game, fn, wer=principal.username)
    db.log_event(principal.username, "snapshot.restore", f"{game} {fn} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.get("/games/{game}/snapshots/download")
async def download_snapshot(game: str, file: str, principal: Principal = Depends(require_admin)):
    """Admin: jeden Stand aus jedem Topf herunterladen (Vorgabe 2026-10-04).
    Geliefert wird nur, was der Arbiter fuer dieses Spiel selbst auflistet; die Datei
    liegt read-only unter settings.saves_dir, ein Pfad aus der Anfrage wird nie direkt
    geoeffnet."""
    await _validate_game(game)
    fn = _snap_file_from({"file": file})
    try:
        liste = await bridge.list_snapshots(game)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Server-Steuerung antwortet nicht")
    if fn not in {s.get("file") for s in (liste.get("snapshots") or [])}:
        raise HTTPException(status_code=404, detail="Unbekannte Sicherung")
    root = Path(settings.saves_dir).resolve()
    pfad = (root / fn).resolve()
    if root not in pfad.parents or not pfad.is_file():
        raise HTTPException(status_code=404, detail="Sicherung nicht lesbar")
    db.log_event(principal.username, "snapshot.download", f"{game} {fn}", game=game)
    name = "greenleaf-" + fn.replace("/", "-")
    return FileResponse(str(pfad), media_type="application/gzip", filename=name)


@router.post("/games/{game}/snapshots/delete")
async def delete_game_snapshot(game: str, request: Request,
                               principal: Principal = Depends(require_owner)):
    """Nur der Owner: Admins duerfen Sicherungen anlegen und einspielen, aber keine
    zerstoeren. Die Bridge nimmt den Weg ohnehin nur mit dem Owner-Token an."""
    _csrf(request, principal)
    await _validate_game(game)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON-Body erwartet")
    fn = _snap_file_from(body)
    outcome, msg = await bridge.delete_snapshot(game, fn, wer=principal.username)
    db.log_event(principal.username, "snapshot.delete", f"{game} {fn} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}


@router.post("/games/{game}/worlds/delete")
async def delete_game_world(game: str, request: Request,
                            principal: Principal = Depends(require_owner)):
    """Nur der Owner: Welt löschen. Der Arbiter schützt aktive/letzte Welt und legt
    vorher einen Abschiedsstand unter geloescht/ an, 30 Tage per Restore zurückholbar."""
    _csrf(request, principal)
    raw = await _validate_game(game)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON-Body erwartet")
    wid = str(body.get("id") or "").strip().lower()
    _validate_world(raw, game, wid)
    outcome, msg = await bridge.delete_world(game, wid, wer=principal.username)
    db.log_event(principal.username, "world.delete", f"{game}/{wid} -> {outcome}", game=game)
    return {"outcome": outcome, "message": msg}
