"""Passwort-Hashing (argon2id), Token-Erzeugung und ein schlanker In-Memory-
Rate-Limiter. Bewusst abhaengigkeitsarm, nur argon2-cffi + stdlib.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings
from app.logging_config import get_logger

log = get_logger(__name__)

# argon2id mit moderaten Kosten, fuer eine Clan-Seite reichlich, ohne den
# kleinen Pi/Container-Host zu ueberlasten.
_ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _ph.verify(stored_hash, password)
    except VerifyMismatchError:
        return False
    except InvalidHashError:
        # Defekter Hash in der DB -> sichtbar machen statt still schlucken.
        log.warning("password.invalid_hash")
        return False
    except Exception as exc:
        log.warning("password.verify_error", error=str(exc))
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _ph.check_needs_rehash(stored_hash)
    except Exception:
        return False


def new_token(nbytes: int = 32) -> str:
    """URL-sicherer Zufallstoken (Session-Cookie, Einladungs-Code, CSRF)."""
    return secrets.token_urlsafe(nbytes)


def invite_code() -> str:
    """Kurzer, gut teilbarer Einladungs-Code (kein 0/O/1/l-Wirrwarr)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


def constant_eq(a: str, b: str) -> bool:
    return secrets.compare_digest(a or "", b or "")


# ── Herkunft ohne Adresse ─────────────────────────────────────────────
# Gespeichert wird nie die IP, sondern eine kurze Kennung daraus. Fuer den
# einzigen Zweck, den der Verlauf hat ("kamen die 20 Fehlversuche von einer
# Quelle oder von zwanzig?"), reicht Wiedererkennbarkeit - die Adresse selbst
# braucht dafuer niemand. Der Schluessel liegt im Datenverzeichnis und wird
# einmalig erzeugt; ohne ihn ist aus der Kennung nichts zurueckzurechnen.
_ip_key: bytes | None = None
_ip_key_lock = Lock()


def _ip_schluessel() -> bytes:
    global _ip_key
    with _ip_key_lock:
        if _ip_key is None:
            pfad = Path(settings.data_dir) / "ip-kennung.secret"
            try:
                if pfad.exists():
                    _ip_key = pfad.read_bytes().strip()
                else:
                    _ip_key = secrets.token_bytes(32)
                    pfad.parent.mkdir(parents=True, exist_ok=True)
                    pfad.write_bytes(_ip_key)
                    pfad.chmod(0o600)
            except OSError as exc:
                # Lieber eine Laufzeit-Kennung als eine gespeicherte Adresse:
                # nach einem Neustart passen alte und neue nicht mehr zusammen,
                # aber es landet nie eine IP in der Datenbank.
                log.warning("ip_kennung.kein_schluessel", error=str(exc))
                _ip_key = secrets.token_bytes(32)
        return _ip_key


def ip_kennung(ip: str) -> str:
    """Kurze, wiedererkennbare Kennung einer Herkunft - keine Adresse."""
    if not ip:
        return ""
    mac = hmac.new(_ip_schluessel(), ip.encode("utf-8"), hashlib.sha256)
    return "quelle-" + mac.hexdigest()[:8]


class RateLimiter:
    """Gleitendes Fenster pro Schluessel (IP, IP+User …). Prozess-lokal."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_s: int) -> bool:
        now = time.time()
        with self._lock:
            q = self._hits[key]
            cutoff = now - window_s
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


rate = RateLimiter()
