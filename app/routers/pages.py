"""HTML-Seiten: Landing, Login, Bewerbung, Einladungs-Einloesung, Member-Dashboard,
Guides, Account. Post/Redirect/Get mit einfachem Flash ueber Query-Parameter.
"""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app import db, guides, notify, vault
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
@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, principal: Principal = Depends(optional_user)):
    return render(request, "landing.html", principal, guides=guides.all_guides())


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
def _fmt_minutes(mins: int) -> str:
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
            "duration": _fmt_minutes(max(1, dur)),
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
            "hours_h": _fmt_minutes(int(hours * 60)),
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
    # Anonym: Server-Adressen maskiert — Adressen gibt es erst nach dem Login.
    return render(request, "guides.html", principal,
                  guides=guides.all_guides(public=principal is None))


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
