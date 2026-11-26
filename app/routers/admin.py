"""Admin-Bereich: Bewerbungen freigeben/ablehnen, Einladungen erstellen/zurückziehen,
Mitglieder verifizieren/rollen/sperren. Owner darf zusaetzlich Admins ernennen & löschen.

Alle Aktionen sind Form-POSTs mit Session-CSRF und enden in Post/Redirect/Get.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse

from app import bridge, db
from app.auth import Principal, check_csrf, current_user, require_admin, require_owner
from app.config import settings
from app.db import iso, now_utc
from app.games import FALLBACK_COLOR, GAME_META
from app.routers.pages import fmt_minutes
from app.security import invite_code
from app.web import redirect, render

router = APIRouter(prefix="/admin")


def _join_base(request: Request) -> str:
    """Basis-URL fuer Einladungslinks aus dem Request ableiten.

    Im LAN-Preview entstehen so funktionierende `http://192.0.2.10:8144/...`-
    Links, nach dem Go-Live hinter tardis/cloudflared automatisch
    `https://games.saganta.de/...`. settings.public_base_url nur als Fallback."""
    host = request.headers.get("host", "").strip()
    if not host:
        return settings.public_base_url.rstrip("/")
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme}://{host}"


def _join_link(request: Request, code: str) -> str:
    return f"{_join_base(request)}/join/{code}"


# ── Panel ─────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def panel(request: Request, principal: Principal = Depends(current_user)):
    if not principal.is_admin:
        return redirect("/app", err="Kein Admin-Zugang.")
    return render(
        request, "admin.html", principal,
        applications=db.list_applications(),
        invites=db.list_invites(),
        users=db.list_users(),
        events=db.recent_events(30),
        join_base=_join_base(request),
    )


# ── Verlauf (Audit) + Auslastung ──────────────────────────────────────
# Bis 2026-09-12 standen auf /admin die letzten 30 Audit-Zeilen ohne Filter. Die
# Frage "wer hat am Dienstag den Server neu gestartet" war damit protokolliert,
# aber nicht beantwortbar: was aelter war als 30 Ereignisse, war praktisch weg.
_ZEITRAEUME = {"7": 7, "30": 30, "90": 90, "alle": None}


@router.get("/verlauf", response_class=HTMLResponse)
async def verlauf(request: Request, principal: Principal = Depends(current_user),
                  actor: str = "", art: str = "", suche: str = "", zeitraum: str = "30"):
    if not principal.is_admin:
        return redirect("/app", err="Kein Admin-Zugang.")
    tage = _ZEITRAEUME.get(zeitraum, 30)
    return render(
        request, "verlauf.html", principal,
        eintraege=db.events_filtern(actor=actor, action=art, suche=suche, tage=tage, limit=300),
        arten=db.event_arten(),
        personen=[u["username"] for u in db.list_users()],
        starter=db.starter_statistik(tage),
        nutzung=_nutzungs_zeilen(tage),
        filter={"actor": actor, "art": art, "suche": suche, "zeitraum": zeitraum},
        zeitraeume=list(_ZEITRAEUME),
        aufbewahrung=settings.event_retention_days,
    )


def _nutzungs_zeilen(tage):
    """Auslastung je Spiel, aufbereitet fuer die Tabelle. 'leerlaeufe' ist die Zahl,
    die den Betrieb interessiert: ein Lauf ohne einen einzigen Spieler ist Speicher,
    den jemand belegt hat, ohne ihn zu benutzen."""
    zeilen = []
    for r in db.spiel_nutzung(tage):
        meta = GAME_META.get(r["game"]) or {}
        stunden = float(r["stunden"] or 0)
        zeilen.append({
            "game": r["game"],
            "label": meta.get("label", r["game"].capitalize()),
            "color": meta.get("color", FALLBACK_COLOR),
            "laeufe": r["laeufe"],
            "stunden": stunden,
            "stunden_h": fmt_minutes(int(stunden * 60)),
            "spielerstunden": round(float(r["spielerminuten"] or 0) / 60.0, 1),
            "spitze": r["spitze"],
            "leerlaeufe": r["leerlaeufe"],
        })
    return zeilen


# ── Server-Updates (2026-11-22) ───────────────────────────────────────
# Bis hierhin kannte nur ntfy den Befund des game-version-watchers, eingespielt wurde
# per ssh. Die Seite zeigt je Spiel, ob der Server zurueckliegt, und dem Owner einen
# Knopf, der dasselbe Werkzeug mit denselben Schutzschritten startet. Eigene Seite statt
# Abschnitt auf /admin: dort stehen die Menschen, die Maschinen stehen auf /app.
_SPIEL_RE = re.compile(r"^[a-z0-9-]{2,30}$")


def _zeit(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(float(ts), db._anzeige_zone()).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError, OSError):
        return ""


def _update_zeilen(daten: dict) -> list[dict]:
    zeilen = []
    for s in daten.get("spiele") or []:
        meta = GAME_META.get(s["name"]) or {}
        lauf = s.get("update") or None
        if lauf:
            lauf = dict(lauf, start_h=_zeit(lauf.get("start")), ende_h=_zeit(lauf.get("ende")))
        zeilen.append(dict(s, label=meta.get("label", s["name"].capitalize()),
                           color=meta.get("color", FALLBACK_COLOR), lauf=lauf))
    # Veraltete zuerst: die Seite wird aufgerufen, um genau diese zu finden.
    zeilen.sort(key=lambda z: (z.get("hinterher") is not True, z["label"]))
    return zeilen


@router.get("/updates", response_class=HTMLResponse)
async def updates(request: Request, principal: Principal = Depends(current_user)):
    if not principal.is_admin:
        return redirect("/app", err="Kein Admin-Zugang.")
    fehler = ""
    try:
        daten = await bridge.get_updates()
    except Exception as exc:  # Bridge weg oder alt: Seite zeigt das, statt zu kippen
        daten, fehler = {}, f"Stand nicht abrufbar ({type(exc).__name__})."
    zeilen = _update_zeilen(daten)
    gemessen = daten.get("gemessen") or ""
    return render(request, "updates.html", principal, zeilen=zeilen, fehler=fehler,
                  gemessen=gemessen[:16].replace("T", " "),
                  laeuft=any(z["lauf"] and z["lauf"].get("laeuft") for z in zeilen))


@router.post("/updates/{game}")
async def update_starten(game: str, request: Request,
                         principal: Principal = Depends(require_owner),
                         csrf: str = Form("")):
    check_csrf(request, principal, csrf)
    if not _SPIEL_RE.match(game):
        return redirect("/admin/updates", err="Unbekanntes Spiel.")
    outcome, meldung = await bridge.start_update(game, wer=principal.username)
    db.log_event(principal.username, "game.update", f"{game}: {outcome}")
    if outcome == "ok":
        return redirect("/admin/updates", msg=meldung)
    return redirect("/admin/updates", err=meldung)


# ── Bewerbungen ───────────────────────────────────────────────────────
@router.post("/applications/{app_id}/approve")
async def approve_application(app_id: int, request: Request,
                              principal: Principal = Depends(require_admin),
                              csrf: str = Form(""), verified: str = Form("")):
    check_csrf(request, principal, csrf)
    app = db.get_application(app_id)
    if not app or app["status"] != "pending":
        return redirect("/admin", err="Bewerbung nicht (mehr) offen.")
    code = invite_code()
    exp = iso(now_utc() + timedelta(days=14))
    db.create_invite(code, "member", bool(verified), f"Bewerbung: {app['name']}",
                     principal.id, exp, 1)
    db.update_application(app_id, "approved", principal.id, code)
    db.log_event(principal.username, "application.approve", f"#{app_id} {app['name']}")
    return redirect("/admin", msg=f"Angenommen. Einladungslink für {app['name']}: {_join_link(request, code)}")


@router.post("/applications/{app_id}/reject")
async def reject_application(app_id: int, request: Request,
                             principal: Principal = Depends(require_admin),
                             csrf: str = Form("")):
    check_csrf(request, principal, csrf)
    app = db.get_application(app_id)
    if not app or app["status"] != "pending":
        return redirect("/admin", err="Bewerbung nicht (mehr) offen.")
    db.update_application(app_id, "rejected", principal.id, None)
    db.log_event(principal.username, "application.reject", f"#{app_id} {app['name']}")
    return redirect("/admin", msg="Bewerbung abgelehnt.")


# ── Einladungen ───────────────────────────────────────────────────────
@router.post("/invites")
async def create_invite_route(request: Request,
                              principal: Principal = Depends(require_admin),
                              csrf: str = Form(""), role: str = Form("member"),
                              verified: str = Form(""), note: str = Form(""),
                              max_uses: int = Form(1), expires_days: int = Form(14)):
    check_csrf(request, principal, csrf)
    if role not in ("member", "admin"):
        role = "member"
    # Admin-Einladungen darf nur der Owner erstellen.
    if role == "admin" and not principal.is_owner:
        return redirect("/admin", err="Nur der Owner kann Admin-Einladungen erstellen.")
    exp = iso(now_utc() + timedelta(days=expires_days)) if expires_days > 0 else None
    code = invite_code()
    db.create_invite(code, role, bool(verified), note.strip(), principal.id, exp,
                     max(1, min(50, max_uses)))
    db.log_event(principal.username, "invite.create", f"{code} role={role}")
    return redirect("/admin", msg=f"Einladung erstellt: {_join_link(request, code)}")


@router.post("/invites/{invite_id}/revoke")
async def revoke_invite_route(invite_id: int, request: Request,
                              principal: Principal = Depends(require_admin),
                              csrf: str = Form("")):
    check_csrf(request, principal, csrf)
    db.revoke_invite(invite_id)
    db.log_event(principal.username, "invite.revoke", f"#{invite_id}")
    return redirect("/admin", msg="Einladung zurückgezogen.")


# ── Mitglieder ────────────────────────────────────────────────────────
@router.post("/users/{uid}/verify")
async def verify_user(uid: int, request: Request,
                      principal: Principal = Depends(require_admin),
                      csrf: str = Form(""), value: str = Form("1")):
    check_csrf(request, principal, csrf)
    target = db.get_user(uid)
    if not target:
        return redirect("/admin", err="Nutzer nicht gefunden.")
    db.set_verified(uid, value == "1")
    db.log_event(principal.username, "user.verify", f"{target['username']}={value}")
    return redirect("/admin", msg=f"{target['username']}: Verifizierung {'gesetzt' if value=='1' else 'entfernt'}.")


@router.post("/users/{uid}/disable")
async def disable_user(uid: int, request: Request,
                       principal: Principal = Depends(require_admin),
                       csrf: str = Form(""), value: str = Form("1")):
    check_csrf(request, principal, csrf)
    target = db.get_user(uid)
    if not target:
        return redirect("/admin", err="Nutzer nicht gefunden.")
    if target["id"] == principal.id:
        return redirect("/admin", err="Sich selbst kann man nicht sperren.")
    if target["role"] in ("owner", "admin") and not principal.is_owner:
        return redirect("/admin", err="Admins/Owner kann nur der Owner sperren.")
    if target["role"] == "owner":
        return redirect("/admin", err="Der Owner kann nicht gesperrt werden.")
    db.set_disabled(uid, value == "1")
    if value == "1":
        db.delete_user_sessions(uid)  # aktive Sessions sofort beenden
    db.log_event(principal.username, "user.disable", f"{target['username']}={value}")
    return redirect("/admin", msg=f"{target['username']}: {'gesperrt' if value=='1' else 'entsperrt'}.")


@router.post("/users/{uid}/role")
async def set_user_role(uid: int, request: Request,
                        principal: Principal = Depends(require_owner),
                        csrf: str = Form(""), role: str = Form("member")):
    check_csrf(request, principal, csrf)
    target = db.get_user(uid)
    if not target:
        return redirect("/admin", err="Nutzer nicht gefunden.")
    if target["role"] == "owner":
        return redirect("/admin", err="Die Owner-Rolle bleibt beim Owner.")
    if role not in ("admin", "member"):
        return redirect("/admin", err="Ungültige Rolle.")
    db.set_role(uid, role)
    db.log_event(principal.username, "user.role", f"{target['username']}->{role}")
    return redirect("/admin", msg=f"{target['username']} ist jetzt {role}.")


@router.post("/users/{uid}/delete")
async def delete_user_route(uid: int, request: Request,
                            principal: Principal = Depends(require_owner),
                            csrf: str = Form("")):
    check_csrf(request, principal, csrf)
    target = db.get_user(uid)
    if not target:
        return redirect("/admin", err="Nutzer nicht gefunden.")
    if target["role"] == "owner":
        return redirect("/admin", err="Den Owner kann man nicht löschen.")
    db.delete_user(uid)
    db.log_event(principal.username, "user.delete", target["username"])
    return redirect("/admin", msg=f"{target['username']} gelöscht.")
