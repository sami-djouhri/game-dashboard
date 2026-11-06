"""HTML-Seiten: Landing, Login, Bewerbung, Einladungs-Einloesung, Member-Dashboard,
Guides, Account. Post/Redirect/Get mit einfachem Flash ueber Query-Parameter.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app import db, guides, karte, mods, notify, vault
from app.auth import (Principal, check_csrf, clear_session_cookie, client_ip,
                      current_user, optional_user, set_session_cookie)
from app.config import settings
from app.games import FALLBACK_COLOR, GAME_META
from app.security import (hash_password, ip_kennung, needs_rehash, rate,
                          verify_password)
from app.web import redirect, render

router = APIRouter()

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-]{3,24}$")


# ── Landing (oeffentlich) ─────────────────────────────────────────────
def _zuletzt_gespielt() -> str:
    """„vor 20 min" / „gestern" / „vor 3 Tagen" -- grob und ohne Namen.

    Bewusst UNGENAU, und zwar nach oben hin zunehmend. Die Frage, die diese Zeile
    auf einer oeffentlichen Seite beantwortet, ist „lebt hier jemand", nicht „wer war
    wann da". Eine Angabe auf die Minute genau waere auf einer Runde von acht Leuten
    ein Anwesenheitsprotokoll, auf die Woche gerundet ist sie eine Auskunft ueber den
    Clan. Deshalb steht hier auch kein Spiel dabei: welche Welt zuletzt lief, sagt
    zusammen mit der Uhrzeit mehr ueber einzelne Personen, als die Zeile braucht.

    Leere Rueckgabe heisst „nichts anzuzeigen", nicht „noch nie gespielt". Das
    Template laesst die Zeile dann ganz weg, statt eine Null zu behaupten: die
    Tabelle beginnt am Tag ihrer Einfuehrung, nicht am Tag des ersten Spiels.
    """
    roh = db.letzte_aktivitaet()
    if not roh:
        return ""
    try:
        stand = datetime.fromisoformat(roh)
    except ValueError:
        return ""
    minuten = int((db.now_utc() - stand).total_seconds() // 60)
    if minuten < 0:            # Uhr des Wirts zurueckgestellt: lieber nichts sagen
        return ""
    if minuten < 90:
        return "gerade eben" if minuten < 20 else f"vor {minuten} min"
    stunden = minuten // 60
    if stunden < 20:
        # Einzahl ist hier kein Feinschliff: 90 bis 119 Minuten ergeben genau eine
        # Stunde, und „vor 1 Stunden" stand damit regelmaessig auf der Startseite.
        return "vor 1 Stunde" if stunden == 1 else f"vor {stunden} Stunden"
    tage = minuten // 1440
    if tage <= 1:
        return "gestern"
    if tage < 14:
        return f"vor {tage} Tagen"
    if tage < 60:
        return f"vor {tage // 7} Wochen"
    return f"vor {tage // 30} Monaten"


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, principal: Principal = Depends(optional_user)):
    return render(request, "landing.html", principal, guides=guides.all_guides(),
                  zuletzt_gespielt=_zuletzt_gespielt())


# ── Login ─────────────────────────────────────────────────────────────
@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, principal: Principal = Depends(optional_user)):
    if principal:
        return redirect("/app")
    return render(request, "login.html", principal)


@router.post("/login")
async def login_submit(request: Request,
                       username: str = Form(...), password: str = Form(...)):
    ip = client_ip(request)
    # Die Adresse bleibt im Arbeitsspeicher (Rate-Limiter); gespeichert wird nur
    # die Kennung daraus - siehe security.ip_kennung.
    herkunft = ip_kennung(ip)
    uname = username.strip().lower()[:40]
    # Zweistufig: pro IP+User (wie in config.py dokumentiert) plus eine breitere
    # IP-Gesamtschranke als Enumerations-Bremse.
    if (not rate.allow(f"login:{ip}", settings.login_max_attempts * 3, settings.login_window_s)
            or not rate.allow(f"login:{ip}:{uname}", settings.login_max_attempts, settings.login_window_s)):
        return redirect("/login", err="Zu viele Versuche. Bitte später erneut.")
    user = db.get_user_by_name(username.strip())
    if not user or user["disabled"] or not verify_password(user["password_hash"], password):
        db.log_event(username[:40], "login.fail", herkunft)
        return redirect("/login", err="Benutzername oder Passwort falsch.")
    rate.reset(f"login:{ip}:{uname}")
    if needs_rehash(user["password_hash"]):
        db.set_password(user["id"], hash_password(password))
    token, _ = db.create_session(user["id"], herkunft, request.headers.get("user-agent", ""))
    db.touch_login(user["id"])
    db.log_event(user["username"], "login.ok", herkunft)
    resp = redirect("/app")
    set_session_cookie(resp, token)
    return resp


@router.post("/logout")
async def logout(request: Request, principal: Principal = Depends(current_user),
                 csrf: str = Form("")):
    check_csrf(request, principal, csrf)
    token = request.cookies.get(settings.session_cookie)
    if token:
        db.delete_session(token)
    resp = redirect("/")
    clear_session_cookie(resp)
    return resp


# ── Bewerbung (oeffentlich) ───────────────────────────────────────────
@router.get("/apply", response_class=HTMLResponse)
async def apply_form(request: Request, principal: Principal = Depends(optional_user)):
    if principal:
        return redirect("/app")
    return render(request, "apply.html", principal, game_list=guides.all_guides())


@router.post("/apply")
async def apply_submit(request: Request,
                       name: str = Form(...), contact: str = Form(""),
                       games: str = Form(""), message: str = Form("")):
    ip = client_ip(request)
    if not rate.allow(f"apply:{ip}", settings.apply_max_per_hour, 3600):
        return redirect("/apply", err="Zu viele Bewerbungen. Bitte später erneut.")
    name = name.strip()
    if len(name) < 2:
        return redirect("/apply", err="Bitte einen Namen / Discord angeben.")
    herkunft = ip_kennung(ip)
    db.create_application(name, contact.strip(), games.strip(), message.strip(), herkunft)
    db.log_event(name[:40], "application.new", herkunft)
    notify.application_received(name, games, message)   # fire-and-forget → Discord #admin
    return render(request, "apply_done.html", None)


# ── Einladung einloesen ───────────────────────────────────────────────
@router.get("/join/{code}", response_class=HTMLResponse)
async def redeem_form(request: Request, code: str,
                      principal: Principal = Depends(optional_user)):
    if principal:
        return redirect("/app")
    inv = db.get_invite_by_code(code.strip())
    ok, reason = db.invite_usable(inv)
    if not ok:
        return render(request, "redeem.html", None, invalid=reason, code=code)
    return render(request, "redeem.html", None, code=code, invite=inv)


@router.post("/join/{code}")
async def redeem_submit(request: Request, code: str,
                        username: str = Form(...), display_name: str = Form(""),
                        password: str = Form(...), password2: str = Form(...)):
    inv = db.get_invite_by_code(code.strip())
    ok, reason = db.invite_usable(inv)
    if not ok:
        return render(request, "redeem.html", None, invalid=reason, code=code)

    username = username.strip()
    if not _USERNAME_RE.match(username):
        return render(request, "redeem.html", None, code=code, invite=inv,
                      err="Benutzername: 3–24 Zeichen, nur Buchstaben/Ziffern/_-.")
    if db.get_user_by_name(username):
        return render(request, "redeem.html", None, code=code, invite=inv,
                      err="Benutzername ist bereits vergeben.")
    if len(password) < 8:
        return render(request, "redeem.html", None, code=code, invite=inv,
                      err="Passwort mindestens 8 Zeichen.")
    if password != password2:
        return render(request, "redeem.html", None, code=code, invite=inv,
                      err="Passwörter stimmen nicht überein.")

    uid = db.create_user(username, display_name.strip(), hash_password(password),
                         role=inv["role"], verified=bool(inv["verified"]),
                         invited_by=inv["created_by"])
    db.increment_invite_use(inv["id"])
    db.log_event(username, "user.joined", f"invite#{inv['id']} role={inv['role']}")
    token, _ = db.create_session(uid, ip_kennung(client_ip(request)),
                                 request.headers.get("user-agent", ""))
    resp = redirect("/app", msg="Willkommen bei " + settings.brand_name + "!")
    set_session_cookie(resp, token)
    return resp


# ── Member-Dashboard ──────────────────────────────────────────────────
def fmt_minutes(mins: int) -> str:
    if mins < 60:
        return f"{mins} min"
    return f"{mins // 60} h {mins % 60:02d} min"


def _activity_feed(limit: int = 8) -> list[dict]:
    out = []
    for r in db.recent_play_sessions(limit):
        try:
            start = datetime.fromisoformat(r["started_at"])
            end = datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None
        except ValueError:
            continue
        dur = int((((end or db.now_utc()) - start).total_seconds()) // 60)
        meta = GAME_META.get(r["game"]) or {}
        out.append({
            "game": r["game"],
            "label": meta.get("label", r["game"].capitalize()),
            "color": meta.get("color", FALLBACK_COLOR),
            "world": r["world"],
            "day": start.strftime("%d.%m."),
            "start": start.strftime("%H:%M"),
            "running": end is None,
            "duration": fmt_minutes(max(1, dur)),
            "peak": r["peak_players"],
        })
    return out


def _playtime_rows(days=None) -> list[dict]:
    rows = []
    for r in db.playtime_totals(days):
        meta = GAME_META.get(r["game"]) or {}
        hours = float(r["hours"] or 0)
        rows.append({
            "game": r["game"],
            "label": meta.get("label", r["game"].capitalize()),
            "color": meta.get("color", FALLBACK_COLOR),
            "hours": hours,
            "hours_h": fmt_minutes(int(hours * 60)),
            "sessions": r["sessions"],
            "peak": r["peak"],
        })
    return rows


@router.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request, principal: Principal = Depends(optional_user)):
    if not principal:
        return redirect("/login")
    world_groups = (vault.list_world_groups()
                    if (settings.downloads_enabled and principal.can_download) else [])
    playtime = _playtime_rows(30)
    max_hours = max((p["hours"] for p in playtime), default=0.0)
    return render(request, "dashboard.html", principal,
                  guides=guides.all_guides(), world_groups=world_groups,
                  downloads_enabled=settings.downloads_enabled,
                  feed=_activity_feed(), playtime=playtime, max_hours=max_hours)


@router.get("/guides", response_class=HTMLResponse)
async def guides_page(request: Request, principal: Principal = Depends(optional_user)):
    # Anonym: Server-Adressen maskiert, Adressen gibt es erst nach dem Login.
    # Mods sind kein Geheimnis und bleiben auch anonym sichtbar: wer sich bewirbt,
    # will genau wissen, was hier gespielt wird.
    return render(request, "guides.html", principal,
                  guides=guides.all_guides(public=principal is None),
                  mods_stand=mods.stand())


# ── Account (Passwort aendern) ────────────────────────────────────────
@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, principal: Principal = Depends(optional_user)):
    if not principal:
        return redirect("/login")
    return render(request, "account.html", principal)


@router.post("/account/password")
async def change_password(request: Request, principal: Principal = Depends(current_user),
                          csrf: str = Form(""), current: str = Form(...),
                          new: str = Form(...), new2: str = Form(...)):
    check_csrf(request, principal, csrf)
    user = db.get_user(principal.id)
    if not user or not verify_password(user["password_hash"], current):
        return redirect("/account", err="Aktuelles Passwort falsch.")
    if len(new) < 8:
        return redirect("/account", err="Neues Passwort mindestens 8 Zeichen.")
    if new != new2:
        return redirect("/account", err="Passwörter stimmen nicht überein.")
    db.set_password(principal.id, hash_password(new))
    # Das zugeschickte Passwort ist ab jetzt wertlos - die DM damit darf weg.
    # Loeschen kann sie nur der Bot (ihm gehoert die Nachricht); er holt sich
    # den Auftrag beim naechsten Abgleich ab.
    db.markiere_dm_loeschen(principal.id)
    db.log_event(principal.username, "user.password_changed", "")
    return redirect("/account", msg="Passwort geändert.")


@router.post("/account/delete")
async def delete_own_account(request: Request, principal: Principal = Depends(current_user),
                             csrf: str = Form(""), password: str = Form(...)):
    """DSGVO-Selbstloeschung: Passwort-bestaetigt. Loescht den Account samt
    Sessions (FK-Cascade) und anonymisiert die Audit-Zeilen."""
    check_csrf(request, principal, csrf)
    if principal.is_owner:
        return redirect("/account", err="Der Owner-Account kann sich nicht selbst löschen. "
                                        "Erst die Owner-Rolle übertragen.")
    user = db.get_user(principal.id)
    if not user or not verify_password(user["password_hash"], password):
        return redirect("/account", err="Passwort falsch, Account nicht gelöscht.")
    db.anonymize_events(principal.username)
    db.delete_user(principal.id)          # sessions via ON DELETE CASCADE
    db.log_event("(gelöscht)", "user.self_delete", "DSGVO-Selbstlöschung")
    resp = redirect("/", msg="Dein Account und deine Daten wurden gelöscht.")
    clear_session_cookie(resp)
    return resp


# ── Impressum / Datenschutz (oeffentlich) ─────────────────────────────
@router.get("/impressum", response_class=HTMLResponse)
async def impressum(request: Request, principal: Principal = Depends(optional_user)):
    return render(request, "impressum.html", principal,
                  imprint_name=settings.imprint_name,
                  imprint_address=settings.imprint_address,
                  imprint_location=settings.imprint_location,
                  imprint_email=settings.imprint_email)


@router.get("/datenschutz", response_class=HTMLResponse)
async def datenschutz(request: Request, principal: Principal = Depends(optional_user)):
    return render(request, "datenschutz.html", principal,
                  imprint_name=settings.imprint_name,
                  imprint_location=settings.imprint_location,
                  imprint_email=settings.imprint_email,
                  retention_days=settings.application_retention_days,
                  session_ttl_days=settings.session_ttl_days)


# ── Minecraft-Karte (BlueMap, nur Mitglieder) ─────────────────────────
# Entscheid 2026-10-17: „nur fuer Mitglieder". Deshalb `current_user` und
# nicht `optional_user` -- die Karte zeigt jedes Bauwerk samt Koordinaten.
#
# Warum ueberhaupt hier und nicht ueber BlueMaps eigenen Webserver: Minecraft
# laeuft on-demand, und mit dem Server verschwaende auch dessen Webserver. Eine
# Karte, die nur sichtbar ist, waehrend jemand spielt, beantwortet die Frage nie,
# fuer die man sie aufruft. Die gerenderten Kacheln sind statische Dateien und
# ueberleben den Schlaf. Begruendung vollstaendig in `app/karte.py`.
@router.get("/karte", response_class=HTMLResponse)
async def karte_start(request: Request, principal: Principal = Depends(current_user)):
    """Einstieg. Ohne gerenderte Karte eine Auskunft statt einer leeren Seite."""
    if not karte.vorhanden():
        return render(request, "karte_leer.html", principal, status_code=200)
    return redirect("/karte/index.html")


@router.get("/karte/{pfad:path}")
async def karte_datei(pfad: str, principal: Principal = Depends(current_user)):
    """Eine Datei der gerenderten Karte.

    ⚠️ `{pfad:path}` nimmt Schraegstriche mit, der Pfad kommt also roh aus der
    Anfrage. Die Pruefung liegt in `karte.datei()` (resolve + Containment +
    Endungs-Allowlist), nicht hier: so gibt es genau EINE Stelle, an der ueber
    Pfade entschieden wird, und `tests/test_karte_pfade.py` prueft sie.
    """
    treffer = karte.datei(pfad)
    if not treffer:
        raise HTTPException(status_code=404, detail="Nicht gefunden")
    ziel, typ = treffer
    kopf = {
        # Kacheln aendern sich nur beim Rendern; der Browser soll nicht bei jedem
        # Schwenk alles neu holen. Kurz genug, dass eine frische Renderung binnen
        # Minuten ankommt.
        "Cache-Control": "private, max-age=300",
    }
    if karte.ist_gzip(ziel):
        kopf["Content-Encoding"] = "gzip"
    return FileResponse(ziel, media_type=typ, headers=kopf)
