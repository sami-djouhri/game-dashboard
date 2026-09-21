"""Welten-Snapshot-Downloads (Game-Vault).

Quelle: die taeglichen Snapshots unter `/var/backups/game-saves/` auf dem
Spiele-VPS, die `welten-schnappschuss.timer` (05:23) dort nach settings.worlds_dir
spiegelt — also derselbe Wirt, kein Netzweg. Die App liest NUR lokal und serviert
read-only, kein SSH-Key/Fetch im Container.

Layout seit dem Per-Welt-Umbau:
  <game>.tar.gz            Single-World-Games (dayz/valheim/factorio/avorion/minecraft)
  <game>/<welt>.tar.gz     Multi-World-Games (terraria/zomboid), ein Tar je Welt
Manuelle Admin-Snapshots (manual/) werden bewusst NICHT gespiegelt — die laufen
live ueber die wake-bridge im Admin-Bereich.

Zugriff ist im Router auf admin-verifizierte Mitglieder beschraenkt.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.guides import GUIDES

_WORLD_FILE_RE = re.compile(r"^[a-z0-9-]{1,32}\.tar\.gz$")


def _worlds_root() -> Path:
    return Path(settings.worlds_dir)


def _human(size: int) -> str:
    v = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} GB"


def _entry(key: str, f: Path, world: str) -> dict | None:
    try:
        st = f.stat()
    except OSError:
        return None
    return {
        "world": world,
        "filename": f.name,
        "size_bytes": st.st_size,
        "size": _human(st.st_size),
        "updated": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="minutes"),
    }


def list_world_groups() -> list[dict]:
    """Snapshots gruppiert Spiel -> Welten, nur kuratierte Game-Keys aus GUIDES.
    Manuelle Backups (z.B. `zomboid-vor-mods-*.tar.gz`) bleiben unsichtbar."""
    from app.games import FALLBACK_COLOR, GAME_META   # kein Zyklus: games importiert nichts
    root = _worlds_root()
    if not root.is_dir():
        return []
    out = []
    for key, g in GUIDES.items():
        worlds: list[dict] = []
        gdir = root / key
        if gdir.is_dir():
            for f in sorted(gdir.glob("*.tar.gz")):
                if _WORLD_FILE_RE.match(f.name):
                    e = _entry(key, f, f.name[:-7])
                    if e:
                        e["per_world"] = True
                        worlds.append(e)
        else:
            e = _entry(key, root / f"{key}.tar.gz", g.get("world", ""))
            if e:
                e["per_world"] = False
                worlds.append(e)
        if worlds:
            out.append({
                "key": key,
                "label": g["label"],
                "color": (GAME_META.get(key) or {}).get("color", FALLBACK_COLOR),
                "worlds": worlds,
            })
    return out


def world_path(key: str, world: str | None = None) -> Path | None:
    """Validierter Pfad zum Snapshot. Allowlist: bekannte Game-Keys; world nur
    als geprüfter Dateiname im Game-Unterverzeichnis (Multi-World-Layout)."""
    if key not in GUIDES:
        return None
    root = _worlds_root().resolve()
    if world:
        if not _WORLD_FILE_RE.match(f"{world}.tar.gz"):
            return None
        candidate = (root / key / f"{world}.tar.gz").resolve()
    else:
        candidate = (root / f"{key}.tar.gz").resolve()
    # Muss innerhalb des worlds_dir liegen UND existieren.
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate
