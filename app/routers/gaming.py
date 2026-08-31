"""Gaming-Rollen-Automatik: Abgleich zwischen Discord-Rolle und Portal-Konto.

Wer auf Discord die Gaming-Rolle traegt, bekommt hier ein Mitglieds-Konto; wer
sie verliert, wird gesperrt (Owner-Entscheid 2026-08-26: sperren, nicht loeschen).
Den Anstoss gibt der Greenleaf-Bot - er kennt Discord, dieses Portal kennt die
Konten. Beide Seiten behalten, was ihnen gehoert: das Passwort entsteht hier und
geht nur als Antwort einmal hinaus, die DM verschickt und loescht der Bot.

Erreichbar ist der Router NICHT ueber den oeffentlichen Weg, sondern ueber den
SSH-Tunnel von node1; der Bearer-Token ist die zweite Schranke.

★ Angefasst werden ausschliesslich Konten mit `auto_gaming=1`. Von Hand angelegte
Konten (Owner, Admins) bleiben unberuehrt - sonst haette der erste Abgleich die
Admins ausgesperrt, die gar keine Gaming-Rolle tragen.
"""
from __future__ import annotations

import json
import re
import secrets

from fastapi import APIRouter, Header, HTTPException, Request, status

from app import db
from app.config import settings
from app.logging_config import get_logger
from app.security import constant_eq, hash_password

router = APIRouter(prefix="/api/gaming")
log = get_logger(__name__)

_ERLAUBT = re.compile(r"[^A-Za-z0-9_\-]")
_PASSWORT_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _pruefe_token(authorization: str | None) -> None:
    if not settings.provision_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Automatik nicht eingerichtet")
    vorgelegt = ""
    if authorization and authorization.lower().startswith("bearer "):
        vorgelegt = authorization[7:].strip()
    if not constant_eq(settings.provision_token, vorgelegt):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ungültig")


def _passwort() -> str:
    """Gut abtippbar, ohne 0/O/1/l-Wirrwarr - es wird per DM verschickt."""
    return "-".join("".join(secrets.choice(_PASSWORT_ALPHABET) for _ in range(4))
                    for _ in range(4))


def _nutzername(vorschlag: str, ersatz: str = "") -> str:
    """Discord-Name -> zulaessiger Benutzername (^[A-Za-z0-9_-]{3,24}$).

    Punkte sind auf Discord ueblich, hier aber nicht erlaubt - sie werden zu '_'.
    Bleibt nichts Brauchbares uebrig (rein grafische Namen), greift ein neutraler
    Ersatz. Kollisionen bekommen eine Ziffer angehaengt.
    """
    for kandidat in (vorschlag, ersatz):
        roh = _ERLAUBT.sub("_", (kandidat or "").strip().replace(".", "_"))
        roh = re.sub(r"_{2,}", "_", roh).strip("_-")[:24]
        if len(roh) >= 3:
            basis = roh
            break
    else:
        basis = "spieler-" + secrets.token_hex(3)

    name = basis
    for n in range(2, 60):
        if not db.get_user_by_name(name):
            return name
        stamm = basis[:22]
        name = f"{stamm}-{n}"
    return "spieler-" + secrets.token_hex(4)


@router.post("/abgleich")
async def abgleich(request: Request, authorization: str | None = Header(default=None)):
    """Nimmt die Liste der Discord-Mitglieder mit Gaming-Rolle entgegen.

    `vollstaendig=false` heisst: der Bot konnte die Mitgliederliste nicht sicher
    vollstaendig erheben - dann wird nur angelegt und entsperrt, nie gesperrt.
    Eine lueckenhafte Liste darf niemanden aussperren.
    """
    _pruefe_token(authorization)
    daten = await request.json()
    mitglieder = daten.get("mitglieder") or []
    vollstaendig = bool(daten.get("vollstaendig"))

    if not isinstance(mitglieder, list):
        raise HTTPException(status_code=400, detail="mitglieder muss eine Liste sein")

    neu, entsperrt, gesperrt, unveraendert = [], [], [], 0
    uebergangen: list[str] = []
    gesehen: set[str] = set()

    for m in mitglieder:
        did = str(m.get("discord_id") or "").strip()
        if not did:
            continue
        gesehen.add(did)
        discord_name = str(m.get("name") or "").strip()[:60]
        anzeige = str(m.get("anzeige") or discord_name).strip()[:60]

        konto = db.get_user_by_discord(did)
        if konto is None and db.ist_ausnahme(did):
            # Bewusst uebergangen (z. B. DM war nicht zustellbar). Ohne diese
            # Bremse legt jeder Durchgang dasselbe Konto neu an und nimmt es
            # wieder zurueck - samt Meldung im Admin-Kanal.
            uebergangen.append(did)
            continue
        if konto is None:
            nutzer = _nutzername(discord_name, anzeige)
            passwort = _passwort()
            uid = db.create_user(nutzer, anzeige or nutzer, hash_password(passwort),
                                 role="member", verified=False,
                                 discord_id=did, discord_name=discord_name,
                                 auto_gaming=True)
            db.log_event("automatik", "user.created", f"{nutzer} (Gaming-Rolle)")
            neu.append({"discord_id": did, "uid": uid, "nutzer": nutzer,
                        "passwort": passwort, "anzeige": anzeige})
        elif konto["disabled"] and konto["auto_gaming"]:
            # Rolle zurueck -> Zugang zurueck, ohne neues Passwort.
            db.set_disabled(konto["id"], False)
            db.log_event("automatik", "user.enable", f"{konto['username']} (Gaming-Rolle zurück)")
            entsperrt.append({"discord_id": did, "nutzer": konto["username"]})
        else:
            unveraendert += 1

    # Wer die Rolle verloren hat: sperren. Nur eigene Konten, nie Owner/Admin.
    if vollstaendig:
        kandidaten = [k for k in db.list_auto_gaming()
                      if k["discord_id"] and str(k["discord_id"]) not in gesehen
                      and not k["disabled"] and k["role"] == "member"]
        if len(kandidaten) > settings.provision_max_sperren:
            log.warning("gaming.abgleich_abgebrochen", zu_sperren=len(kandidaten),
                        deckel=settings.provision_max_sperren)
            db.log_event("automatik", "abgleich.abgebrochen",
                         f"{len(kandidaten)} Sperrungen > Deckel {settings.provision_max_sperren}")
            return {"ok": False, "grund": "zu viele Sperrungen auf einmal",
                    "zu_sperren": len(kandidaten), "deckel": settings.provision_max_sperren,
                    "neu": neu, "entsperrt": entsperrt, "gesperrt": [],
                    "unveraendert": unveraendert, "dm_loeschen": []}
        for k in kandidaten:
            db.set_disabled(k["id"], True)
            db.delete_user_sessions(k["id"])
            db.log_event("automatik", "user.disable", f"{k['username']} (Gaming-Rolle entzogen)")
            gesperrt.append({"discord_id": str(k["discord_id"]), "nutzer": k["username"]})

    # Auftraege fuer den Bot: DMs, deren Passwort inzwischen gewechselt wurde.
    dm_weg = [{"uid": r["id"], "discord_id": r["discord_id"], "nutzer": r["username"],
               "kanal": r["dm_kanal"], "nachricht": r["dm_nachricht"]}
              for r in db.offene_dm_loeschungen()]

    # Merkzettel: ohne ihn ist "keine Meldung" nicht von "laeuft nicht mehr" zu
    # unterscheiden. Der Admin-Bereich zeigt daraus, wann zuletzt abgeglichen wurde.
    db.setze_stand("gaming_abgleich", json.dumps({
        "traeger": len(gesehen), "neu": len(neu), "gesperrt": len(gesperrt),
        "entsperrt": len(entsperrt), "unveraendert": unveraendert,
        "uebergangen": len(uebergangen), "vollstaendig": vollstaendig,
    }))

    return {"ok": True, "neu": neu, "entsperrt": entsperrt, "gesperrt": gesperrt,
            "unveraendert": unveraendert, "uebergangen": len(uebergangen),
            "dm_loeschen": dm_weg}


@router.post("/dm-vermerk")
async def dm_vermerk(request: Request, authorization: str | None = Header(default=None)):
    """Der Bot meldet, welche DM die Zugangsdaten traegt - damit sie nach dem
    Passwortwechsel gezielt geloescht werden kann."""
    _pruefe_token(authorization)
    daten = await request.json()
    n = 0
    for e in daten.get("eintraege") or []:
        konto = db.get_user_by_discord(str(e.get("discord_id") or ""))
        if konto:
            db.set_dm_vermerk(konto["id"], str(e.get("kanal") or ""),
                              str(e.get("nachricht") or ""))
            n += 1
    return {"ok": True, "vermerkt": n}


@router.post("/dm-erledigt")
async def dm_erledigt(request: Request, authorization: str | None = Header(default=None)):
    """Der Bot hat die DM geloescht (oder sie war schon weg) - Vermerk raeumen."""
    _pruefe_token(authorization)
    daten = await request.json()
    n = 0
    for uid in daten.get("uids") or []:
        try:
            db.dm_vermerk_entfernen(int(uid))
            n += 1
        except (TypeError, ValueError):
            continue
    return {"ok": True, "geraeumt": n}


@router.post("/ruecknahme")
async def ruecknahme(request: Request, authorization: str | None = Header(default=None)):
    """DM war nicht zustellbar -> das frische Konto kennt niemand, es kommt weg.

    Nur Konten der Automatik, die sich noch nie angemeldet haben. Sonst wuerde
    ein einzelner Zustellfehler ein benutztes Konto mitreissen.
    """
    _pruefe_token(authorization)
    daten = await request.json()
    grund = str(daten.get("grund") or "DM nicht zustellbar")[:120]
    entfernt = []
    for did in daten.get("discord_ids") or []:
        konto = db.get_user_by_discord(str(did))
        if konto and konto["auto_gaming"] and konto["last_login_at"] is None \
                and konto["role"] == "member":
            name = konto["discord_name"] or konto["username"]
            db.delete_user(konto["id"])
            db.anonymize_events(konto["username"])
            db.log_event("automatik", "user.delete", f"{konto['username']} ({grund})")
            entfernt.append(konto["username"])
        else:
            name = str(did)
        # Merken, damit der naechste Durchgang nicht dasselbe noch einmal tut.
        db.ausnahme_setzen(str(did), name, grund)
    return {"ok": True, "entfernt": entfernt}
