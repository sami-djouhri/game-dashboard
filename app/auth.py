"""Forward-auth (Authelia via dev-portal nginx) mit Anti-Spoofing-Proxy-Check.

Uebernommen aus service-template/app/auth.py — bewaehrt, prueft den TCP-Peer
gegen auth_trusted_proxies, bevor Remote-User/-Groups-Header vertraut wird.
"""
import ipaddress

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)


class Principal(BaseModel):
    username: str
    groups: list[str] = []
    source: str = "forward-auth"

    @property
    def is_admin(self) -> bool:
        return settings.admin_group in self.groups

    @property
    def may_start(self) -> bool:
        # Starten (wake) darf, wer user ODER admin ist.
        return settings.user_group in self.groups or settings.admin_group in self.groups


def _peer_trusted(request: Request) -> bool:
    """Nur der authentifizierende Reverse-Proxy darf die forward-auth-Header setzen.

    Sonst koennte jeder Client, der den Dienst direkt erreicht, Remote-User/-Groups
    faelschen und die Auth umgehen.
    """
    client = request.client
    if client is None:
        return False
    try:
        peer = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    for entry in settings.auth_trusted_proxies:
        try:
            if "/" in entry:
                if peer in ipaddress.ip_network(entry, strict=False):
                    return True
            elif peer == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


async def current_user(request: Request) -> Principal:
    if not settings.auth_required:
        return Principal(username="anonymous", groups=[settings.admin_group], source="disabled")

    if not _peer_trusted(request):
        log.warning(
            "auth.untrusted_peer",
            path=str(request.url.path),
            peer=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Direkter Zugriff nicht erlaubt — Anfragen muessen ueber den Reverse-Proxy laufen",
        )

    remote_user = request.headers.get(settings.auth_header_user)
    if not remote_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    raw_groups = request.headers.get(settings.auth_header_groups, "")
    groups = [g.strip() for g in raw_groups.split(",") if g.strip()]
    return Principal(username=remote_user, groups=groups)


async def require_start(principal: Principal = Depends(current_user)) -> Principal:
    """Darf Games starten (user oder admin)."""
    if not principal.may_start:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Keine Start-Berechtigung")
    return principal


async def require_admin(principal: Principal = Depends(current_user)) -> Principal:
    """Darf stoppen/neustarten/erzwingen/reservieren (nur admin)."""
    if not principal.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur fuer Admins")
    return principal
