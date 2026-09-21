"""game-dashboard, „Greenleaf" Clan-Seite vor der wake-bridge.

Laeuft auf dem Spiele-VPS, auf demselben Wirt wie die Spielserver und ihr
Arbiter, das Gegenstueck zum dev-portal im Heimnetz, nur fuer die Spiele.
Bis 2026-08-22 stand es auf host und sprach ueber das LAN nach Node .18;
diese Instanz ist stillgelegt (Compose-Profil), der Baum dort bleibt die
kanonische Quelle.

Oeffentliche Landing (Marketing + Live-Puls + Bewerben), eigenes Login mit
Rollen (owner/admin/member) + verified-Flag, Einladungs-/Bewerbungs-Flow,
Live-Steuerung der on-demand Game-Server und Welten-Downloads fuer verifizierte
Mitglieder. Der Bridge-Bearer-Token bleibt serverseitig.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import secrets

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import settings
from app.logging_config import configure_logging, get_logger
from app.routers import admin, api, gaming, pages
from app.security import hash_password

configure_logging(settings.log_level)
log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    docs_url=None, redoc_url=None, openapi_url=None,  # oeffentlich -> keine API-Docs
)


def _bootstrap_owner() -> None:
    """Auf leerer DB genau einen Owner anlegen. Passwort aus .env (owner_password)
    oder, falls leer, zufaellig erzeugt und einmalig in eine 0600-Datei geschrieben."""
    if db.count_users() > 0:
        return
    username = (settings.owner_user or "admin").strip()
    password = settings.owner_password
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True
    db.create_user(username, username, hash_password(password), role="owner", verified=True)
    db.log_event("system", "owner.bootstrap", username)
    if generated:
        cred = Path(settings.data_dir) / "OWNER_CREDENTIALS.txt"
        try:
            cred.write_text(f"username: {username}\npassword: {password}\n")
            cred.chmod(0o600)
        except OSError:
            pass
        log.warning("owner.bootstrap.generated",
                    user=username, hint=f"Passwort in {cred}, bitte einloggen & aendern")
    else:
        log.info("owner.bootstrap.from_env", user=username)


async def _session_reaper() -> None:
    """Abgelaufene Sessions auch im Dauerbetrieb aufraeumen (nicht nur beim Start)."""
    while True:
        await asyncio.sleep(6 * 3600)
        try:
            db.purge_expired_sessions()
        except Exception as exc:
            log.warning("session.reaper_error", error=str(exc))


async def _application_retention() -> None:
    """DSGVO: entschiedene Bewerbungen nach application_retention_days loeschen
    (taeglich; offene bleiben bis zur Admin-Entscheidung)."""
    while True:
        try:
            n = db.purge_reviewed_applications(settings.application_retention_days)
            if n:
                db.log_event("system", "applications.purged",
                             f"{n} entschiedene nach {settings.application_retention_days} Tagen")
            # Das Audit-Log hatte bis 2026-09-12 gar keine Aufbewahrungsregel und
            # waechst sonst unbegrenzt. Die eigene Loeschzeile wird dabei geschrieben,
            # BEVOR sie selbst altern kann -- sie ist der Beleg, dass die Regel laeuft.
            m = db.events_aufraeumen(settings.event_retention_days)
            if m:
                db.log_event("system", "events.purged",
                             f"{m} Audit-Zeilen aelter als {settings.event_retention_days} Tage")
        except Exception as exc:
            log.warning("retention.error", error=str(exc))
        await asyncio.sleep(24 * 3600)


async def _activity_sampler() -> None:
    """Sampelt den Arbiter-Status (guenstig, TTL-Cache) und fuehrt daraus
    play_sessions: 'Zuletzt gespielt'-Feed + Playtime-Statistik. Session =
    zusammenhaengender Lauf eines Spiels (Welt-genau).

    ★ Fuehrt je laufendem Spiel eine eigene Sitzung. Bis 2026-09-12 stand hier
    `view["active_game"]` -- ein Einzahlfeld, das `next(...)` ueber die Kacheln
    bildet und damit immer nur das ERSTE laufende Spiel nennt. Der Arbiter laesst
    aber seit dem 2026-08-22 mehrere nebeneinander laufen. Die Folge war keine
    Fehlermeldung, sondern eine stille Verfaelschung: von zwei parallelen Servern
    zaehlte nur einer, und wenn dieser ausging, sprang die Sitzung auf den anderen,
    der dadurch aussah, als beginne er gerade erst. `active_game` bleibt fuer die
    Landing-Anzeige, wo genau ein Aufhaenger gewollt ist."""
    from app import bridge, games
    interval = max(15, settings.activity_sample_s)
    while True:
        try:
            view = games.build_view(await bridge.get_status(), await bridge.get_always_on())
            laufend = {t["key"]: t for t in view.get("games", [])
                       if t.get("state") == "active" and not t.get("always_on")}
            offen = db.offene_play_sessions()
            # Beendet oder Welt gewechselt -> Sitzung schliessen.
            for key, sess in offen.items():
                tile = laufend.get(key)
                if tile is None or (tile.get("world") or "") != (sess["world"] or ""):
                    db.close_play_session(sess["id"])
                    offen = db.offene_play_sessions()
            for key, tile in laufend.items():
                sess = offen.get(key)
                if sess is None:
                    db.open_play_session(key, tile.get("world") or "", db.letzter_starter(key))
                    offen = db.offene_play_sessions()
                    sess = offen.get(key)
                players = tile.get("players")
                if sess and isinstance(players, int) and players >= 0:
                    db.update_play_session(sess["id"], players, players * interval / 60.0)
        except Exception:
            pass   # Bridge weg o.ae. -> naechster Versuch; kein Log-Spam pro Minute
        await asyncio.sleep(interval)


@app.on_event("startup")
async def _startup() -> None:
    db.init_db()
    db.purge_expired_sessions()
    db.close_stale_play_sessions()
    _bootstrap_owner()
    # Referenzen an app.state, damit die Tasks nicht vom GC eingesammelt werden.
    app.state.session_reaper = asyncio.create_task(_session_reaper())
    app.state.retention = asyncio.create_task(_application_retention())
    app.state.activity = asyncio.create_task(_activity_sampler())
    log.info("startup", brand=settings.brand_name, version=settings.service_version,
             downloads=settings.downloads_enabled)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.service_version,
        "time": datetime.now(timezone.utc).isoformat(),
    }


app.include_router(pages.router)
app.include_router(api.router)
app.include_router(admin.router)
app.include_router(gaming.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
