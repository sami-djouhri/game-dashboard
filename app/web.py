"""Jinja2-Setup + Render-Helfer mit gemeinsamem Template-Kontext."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app import db
from app.auth import Principal
from app.config import settings
from app.guides import GUIDES

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE = re.compile(r"`([^`]+)`")


def _md(text: str) -> Markup:
    """Mini-Markdown fuer Guide-Texte: escape-first, dann **fett** und `code`.
    Bewusst kein vollwertiger Markdown-Renderer."""
    s = str(escape(text))
    s = _MD_BOLD.sub(r"<b>\1</b>", s)
    s = _MD_CODE.sub(r"<code>\1</code>", s)
    return Markup(s)


templates.env.filters["md"] = _md


def render(request: Request, name: str, principal: Optional[Principal] = None,
           status_code: int = 200, **ctx) -> HTMLResponse:
    base = {
        "request": request,
        "brand": settings.brand_name,
        "tagline": settings.brand_tagline,
        "dev_credit": settings.developer_credit,
        "dev_name": settings.developer_name,
        "discord_url": settings.community_discord_url,
        "version": settings.service_version,
        "principal": principal,
        "csrf": principal.csrf if principal else "",
        "flash": request.query_params.get("msg"),
        "flash_err": request.query_params.get("err"),
        "pending_count": db.count_pending_applications() if (principal and principal.is_admin) else 0,
        # Fuer den Scene-Store (JS-gebaute Karten klonen die SVG-Szenen per <template>)
        "scene_keys": list(GUIDES.keys()),
    }
    base.update(ctx)
    return templates.TemplateResponse(name, base, status_code=status_code)


def redirect(url: str, msg: str = "", err: str = "") -> RedirectResponse:
    from urllib.parse import urlencode
    q = {k: v for k, v in (("msg", msg), ("err", err)) if v}
    if q:
        url = url + ("&" if "?" in url else "?") + urlencode(q)
    # 303 -> nach POST folgt ein GET (Post/Redirect/Get)
    return RedirectResponse(url, status_code=303)
