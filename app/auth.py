"""Session-basierte Auth mit Rollen (owner/admin/member) + verified-Flag.

Ersetzt die fruehere Authelia-forward-auth: die Seite ist oeffentlich mit
eigenem Login (Bewerbung/Einladung). Sessions liegen serverseitig in SQLite,
das Cookie traegt nur einen opaken Token. CSRF ueber ein Per-Session-Token.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from app import db
from app.config import settings
from app.logging_config import get_logger
from app.security import constant_eq

log = get_logger(__name__)

ADMIN_ROLES = ("owner", "admin")


@dataclass
class Principal:
    id: int
    username: str
    display_name: str
    role: str
    verified: bool
    csrf: str = ""

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    @property
    def may_start(self) -> bool:
        # Jedes eingeloggte, aktive Mitglied darf Games wecken.
        return True

    @property
    def may_manage(self) -> bool:
        return self.role in ADMIN_ROLES

    @property
    def can_download(self) -> bool:
        # Welten-Downloads nur fuer admin-verifizierte Mitglieder (oder Admins).
        return self.verified or self.is_admin


def client_ip(request: Request) -> str:
    """Echte Client-IP: X-Forwarded-For NUR vertrauen, wenn der TCP-Peer ein
    bekannter Reverse-Proxy ist (sonst faelschbar)."""
    peer = request.client.host if request.client else ""
    if peer and _peer_trusted(peer):
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
    return peer


def _peer_trusted(peer: str) -> bool:
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    for entry in settings.trusted_proxies:
        try:
            if "/" in entry:
                if ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _principal_from_request(request: Request) -> Optional[Principal]:
    token = request.cookies.get(settings.session_cookie)
    sess = db.get_session(token) if token else None
    if not sess:
        return None
    user = db.get_user(sess["user_id"])
    if not user or user["disabled"]:
        return None
    return Principal(
        id=user["id"],
        username=user["username"],
        display_name=user["display_name"] or user["username"],
        role=user["role"],
        verified=bool(user["verified"]),
        csrf=sess["csrf"],
    )


async def optional_user(request: Request) -> Optional[Principal]:
    """Fuer Seiten/Endpunkte, die mit ODER ohne Login funktionieren."""
    return _principal_from_request(request)


async def current_user(request: Request) -> Principal:
    """Muss eingeloggt sein, sonst 401 (API) bzw. Redirect (Seiten selbst)."""
    p = _principal_from_request(request)
    if p is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    return p


async def require_admin(principal: Principal = Depends(current_user)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Admins")
    return principal


async def require_owner(principal: Principal = Depends(current_user)) -> Principal:
    if not principal.is_owner:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für den Owner")
    return principal


async def require_verified(principal: Principal = Depends(current_user)) -> Principal:
    if not principal.can_download:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Downloads nur für verifizierte Mitglieder")
    return principal


def check_csrf(request: Request, principal: Principal, token: Optional[str]) -> None:
    """CSRF-Schutz. PRIMAER: das Per-Session-Token (Formularfeld/Header) muss zum
    Session-Token passen — das ist zusammen mit SameSite=Lax der eigentliche Schutz.

    Der Origin-Abgleich ist nur best-effort (Defense-in-Depth) und wird bewusst
    NICHT hart erzwungen: hinter cloudflared/dev-portal weicht der Host vom oeffentlichen
    Hostnamen ab (z. B. games.saganta.de -> games.home.arpa, oder ein
    trycloudflare-Tunnel) — ein harter Vergleich wuerde legitime POSTs 403en.
    Ein Mismatch wird daher nur protokolliert."""
    if not principal or not principal.csrf or not constant_eq(principal.csrf, token or ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF-Token ungültig")
    from urllib.parse import urlparse
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        o_host = (urlparse(origin).hostname or "").lower()
        allowed = set()
        for h in (request.headers.get("host", ""),
                  request.headers.get("x-forwarded-host", ""),
                  urlparse(settings.public_base_url).hostname or ""):
            if h:
                allowed.add(h.split(":")[0].lower())
        if o_host and allowed and o_host not in allowed:
            log.warning("csrf.origin_mismatch", origin=o_host, allowed=",".join(sorted(allowed)))


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(settings.session_cookie, path="/")
