"""Push-Benachrichtigung bei neuer Bewerbung → Discord-Webhook (Herb-#admin).

Fire-and-forget: Der Bewerbungs-Request wartet nie auf Discord; Fehler werden
nur geloggt. Ohne konfigurierte Webhook-URL ist das Modul ein No-op.
"""
from __future__ import annotations

import asyncio

import httpx

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)


async def _post_webhook(payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(settings.admin_webhook_url, json=payload)
            if resp.status_code >= 400:
                log.warning("notify.webhook_status", status=resp.status_code)
    except httpx.HTTPError as exc:
        log.warning("notify.webhook_error", error=str(exc))


def application_received(name: str, games: str, message: str) -> None:
    """Neue Bewerbung → Embed in den #admin-Kanal (alle Admins sehen sie dort,
    Handy-Push kommt über Discord selbst)."""
    if not settings.admin_webhook_url:
        return
    fields = []
    if games.strip():
        fields.append({"name": "Spiele", "value": games.strip()[:200], "inline": True})
    if message.strip():
        fields.append({"name": "Nachricht", "value": message.strip()[:500], "inline": False})
    payload = {
        "embeds": [{
            "title": "Neue Bewerbung: " + name[:80],
            "description": f"Im Admin-Bereich entscheiden: {settings.public_base_url}/admin",
            "color": 0x64D178,
            "fields": fields,
        }],
        "allowed_mentions": {"parse": []},
    }
    # Kontaktdaten bewusst NICHT in den Webhook (Discord = Drittanbieter);
    # sie stehen im Admin-Panel.
    asyncio.create_task(_post_webhook(payload))
