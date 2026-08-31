"""SQLite-Persistenz fuer game-dashboard: Nutzer, Sessions, Einladungen,
Bewerbungen, Audit-Events.

Eine gemeinsame Verbindung (WAL, check_same_thread=False) mit Schreib-Lock ,
fuer eine Clan-Seite mit sehr wenig Last voellig ausreichend und robust.
Alle Zeiten als ISO-UTC-Strings.

★ In den Spalten `sessions.ip` und `applications.ip` steht KEINE Adresse, sondern
die Kennung aus `security.ip_kennung` (Owner-Entscheid 2026-08-26). Die Spalten
heissen aus Ruecksicht auf bestehende Daten weiter `ip`; wer hier schreibt, gibt
die Kennung weiter, nie `client_ip()`. Dasselbe gilt fuer das `detail`-Feld der
login-Ereignisse, das im Admin-Verlauf sichtbar ist.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Optional

from app.config import settings

_conn: Optional[sqlite3.Connection] = None
_wlock = Lock()

ROLES = ("owner", "admin", "member")
ADMIN_ROLES = ("owner", "admin")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def now_iso() -> str:
    return iso(now_utc())


def _connect() -> sqlite3.Connection:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'member',
    verified      INTEGER NOT NULL DEFAULT 0,
    disabled      INTEGER NOT NULL DEFAULT 0,
    invited_by    INTEGER,
    created_at    TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    csrf        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    ip          TEXT,
    user_agent  TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    role        TEXT NOT NULL DEFAULT 'member',
    verified    INTEGER NOT NULL DEFAULT 0,
    note        TEXT NOT NULL DEFAULT '',
    created_by  INTEGER,
    created_at  TEXT NOT NULL,
    expires_at  TEXT,
    max_uses    INTEGER NOT NULL DEFAULT 1,
    uses        INTEGER NOT NULL DEFAULT 0,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    contact      TEXT NOT NULL DEFAULT '',
    games        TEXT NOT NULL DEFAULT '',
    message      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    ip           TEXT,
    created_at   TEXT NOT NULL,
    reviewed_by  INTEGER,
    reviewed_at  TEXT,
    invite_code  TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL DEFAULT '',
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS play_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    game           TEXT NOT NULL,
    world          TEXT NOT NULL DEFAULT '',
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    peak_players   INTEGER NOT NULL DEFAULT 0,
    player_minutes REAL NOT NULL DEFAULT 0
);

-- Wen die Gaming-Automatik in Ruhe laesst. Ohne diese Liste legt sie bei jedem
-- Durchgang erneut ein Konto an, dessen DM nicht zustellbar ist, nimmt es wieder
-- zurueck und meldet das - alle paar Minuten aufs Neue.
CREATE TABLE IF NOT EXISTS gaming_ausnahmen (
    discord_id  TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    grund       TEXT NOT NULL DEFAULT '',
    seit        TEXT NOT NULL
);

-- Kleine Merkzettel des Betriebs (aktuell: wann die Gaming-Automatik zuletzt
-- gelaufen ist). Ohne so einen Vermerk ist "keine Meldung" nicht von "laeuft
-- nicht" zu unterscheiden - die Stille sieht in beiden Faellen gleich aus.
CREATE TABLE IF NOT EXISTS stand (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT NOT NULL DEFAULT '',
    ts         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_apps_status   ON applications(status);
CREATE INDEX IF NOT EXISTS idx_play_game     ON play_sessions(game, started_at);
"""


# Nachtraegliche Spalten. SQLite kann kein "ADD COLUMN IF NOT EXISTS", deshalb
# gegen PRAGMA table_info pruefen - der Aufruf ist idempotent und laeuft bei
# jedem Start mit, ohne die bestehenden Daten anzufassen.
_NACHRUESTUNG = {
    "users": {
        # Verknuepfung zum Discord-Konto: nur damit ist die Automatik idempotent
        # ("hat diese Person schon ein Konto?") und die DM zustellbar.
        "discord_id":   "TEXT",
        "discord_name": "TEXT NOT NULL DEFAULT ''",
        # 1 = von der Gaming-Rollen-Automatik angelegt. NUR solche Konten fasst
        # sie spaeter wieder an; von Hand angelegte bleiben unberuehrt.
        "auto_gaming":  "INTEGER NOT NULL DEFAULT 0",
        # Die DM mit den Zugangsdaten, damit der Bot sie nach dem Passwort-
        # wechsel wieder loeschen kann.
        "dm_kanal":     "TEXT NOT NULL DEFAULT ''",
        "dm_nachricht": "TEXT NOT NULL DEFAULT ''",
        # 1 = Passwort wurde gewechselt, die DM darf weg (der Bot holt sich das
        # beim naechsten Abgleich ab).
        "dm_loeschen":  "INTEGER NOT NULL DEFAULT 0",
    },
}


def _nachruesten() -> None:
    for tabelle, spalten in _NACHRUESTUNG.items():
        da = {r["name"] for r in conn().execute(f"PRAGMA table_info({tabelle})")}
        for name, typ in spalten.items():
            if name not in da:
                conn().execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")
    conn().execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_discord"
                   " ON users(discord_id) WHERE discord_id IS NOT NULL")
    conn().commit()


def init_db() -> None:
    with _wlock:
        conn().executescript(_SCHEMA)
        conn().commit()
        _nachruesten()


def _exec(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _wlock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur


def _query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn().execute(sql, params).fetchall()


def _one(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    return conn().execute(sql, params).fetchone()


# ── Users ─────────────────────────────────────────────────────────────
def count_users() -> int:
    return _one("SELECT COUNT(*) c FROM users")["c"]


def count_admins() -> int:
    return _one("SELECT COUNT(*) c FROM users WHERE role IN ('owner','admin') AND disabled=0")["c"]


def get_user(uid: int) -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM users WHERE id=?", (uid,))


def get_user_by_name(username: str) -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,))


def create_user(username: str, display_name: str, password_hash: str,
                role: str = "member", verified: bool = False,
                invited_by: Optional[int] = None,
                discord_id: Optional[str] = None, discord_name: str = "",
                auto_gaming: bool = False) -> int:
    cur = _exec(
        "INSERT INTO users(username,display_name,password_hash,role,verified,invited_by,"
        "created_at,discord_id,discord_name,auto_gaming)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        (username, display_name or username, password_hash, role,
         1 if verified else 0, invited_by, now_iso(),
         discord_id or None, discord_name or "", 1 if auto_gaming else 0),
    )
    return cur.lastrowid


# ── Discord-Verknuepfung / Gaming-Rollen-Automatik ────────────────────
def get_user_by_discord(discord_id: str) -> Optional[sqlite3.Row]:
    if not discord_id:
        return None
    return _one("SELECT * FROM users WHERE discord_id=?", (str(discord_id),))


def set_discord(uid: int, discord_id: str, discord_name: str = "") -> None:
    _exec("UPDATE users SET discord_id=?, discord_name=? WHERE id=?",
          (str(discord_id), discord_name or "", uid))


def list_auto_gaming() -> list[sqlite3.Row]:
    """Nur die von der Automatik angelegten Konten - von Hand angelegte
    (Owner, Admins) darf sie nie anfassen."""
    return _query("SELECT * FROM users WHERE auto_gaming=1")


def set_dm_vermerk(uid: int, kanal: str, nachricht: str) -> None:
    """Merkt sich die DM mit den Zugangsdaten, damit sie spaeter weg kann."""
    _exec("UPDATE users SET dm_kanal=?, dm_nachricht=?, dm_loeschen=0 WHERE id=?",
          (kanal or "", nachricht or "", uid))


def markiere_dm_loeschen(uid: int) -> None:
    """Nach dem Passwortwechsel: die DM mit dem alten Passwort darf verschwinden."""
    _exec("UPDATE users SET dm_loeschen=1 WHERE id=? AND dm_nachricht != ''", (uid,))


def offene_dm_loeschungen() -> list[sqlite3.Row]:
    return _query("SELECT id, username, discord_id, dm_kanal, dm_nachricht FROM users"
                  " WHERE dm_loeschen=1 AND dm_nachricht != ''")


def setze_stand(schluessel: str, wert: str) -> None:
    _exec("INSERT OR REPLACE INTO stand(schluessel,wert,ts) VALUES(?,?,?)",
          (schluessel, wert, now_iso()))


def hole_stand(schluessel: str) -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM stand WHERE schluessel=?", (schluessel,))


def ausnahme_setzen(discord_id: str, name: str, grund: str) -> None:
    _exec("INSERT OR REPLACE INTO gaming_ausnahmen(discord_id,name,grund,seit)"
          " VALUES(?,?,?,?)", (str(discord_id), name or "", grund or "", now_iso()))


def ist_ausnahme(discord_id: str) -> bool:
    return _one("SELECT 1 x FROM gaming_ausnahmen WHERE discord_id=?",
                (str(discord_id),)) is not None


def ausnahmen() -> list[sqlite3.Row]:
    return _query("SELECT * FROM gaming_ausnahmen ORDER BY seit DESC")


def ausnahme_loeschen(discord_id: str) -> None:
    _exec("DELETE FROM gaming_ausnahmen WHERE discord_id=?", (str(discord_id),))


def dm_vermerk_entfernen(uid: int) -> None:
    _exec("UPDATE users SET dm_kanal='', dm_nachricht='', dm_loeschen=0 WHERE id=?", (uid,))


def set_password(uid: int, password_hash: str) -> None:
    _exec("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))


def set_role(uid: int, role: str) -> None:
    _exec("UPDATE users SET role=? WHERE id=?", (role, uid))


def set_verified(uid: int, verified: bool) -> None:
    _exec("UPDATE users SET verified=? WHERE id=?", (1 if verified else 0, uid))


def set_disabled(uid: int, disabled: bool) -> None:
    _exec("UPDATE users SET disabled=? WHERE id=?", (1 if disabled else 0, uid))


def touch_login(uid: int) -> None:
    _exec("UPDATE users SET last_login_at=? WHERE id=?", (now_iso(), uid))


def list_users() -> list[sqlite3.Row]:
    return _query("SELECT * FROM users ORDER BY "
                  "CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, username COLLATE NOCASE")


def delete_user(uid: int) -> None:
    _exec("DELETE FROM users WHERE id=?", (uid,))


# ── Sessions ──────────────────────────────────────────────────────────
def create_session(user_id: int, herkunft: str = "", user_agent: str = "") -> tuple[str, str]:
    """`herkunft` ist die Kennung aus security.ip_kennung, NIE eine Adresse."""
    from app.security import new_token
    token = new_token(32)
    csrf = new_token(24)
    exp = iso(now_utc() + timedelta(days=settings.session_ttl_days))
    _exec("INSERT INTO sessions(token,user_id,csrf,created_at,expires_at,ip,user_agent)"
          " VALUES(?,?,?,?,?,?,?)",
          (token, user_id, csrf, now_iso(), exp, herkunft, (user_agent or "")[:300]))
    return token, csrf


def get_session(token: str) -> Optional[sqlite3.Row]:
    if not token:
        return None
    row = _one("SELECT * FROM sessions WHERE token=?", (token,))
    if not row:
        return None
    try:
        if datetime.fromisoformat(row["expires_at"]) < now_utc():
            delete_session(token)
            return None
    except ValueError:
        return None
    return row


def delete_session(token: str) -> None:
    _exec("DELETE FROM sessions WHERE token=?", (token,))


def delete_user_sessions(user_id: int) -> None:
    _exec("DELETE FROM sessions WHERE user_id=?", (user_id,))


def purge_expired_sessions() -> None:
    _exec("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))


# ── Invites ───────────────────────────────────────────────────────────
def create_invite(code: str, role: str, verified: bool, note: str,
                  created_by: Optional[int], expires_at: Optional[str],
                  max_uses: int) -> int:
    cur = _exec(
        "INSERT INTO invites(code,role,verified,note,created_by,created_at,expires_at,max_uses)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (code, role, 1 if verified else 0, note or "", created_by, now_iso(),
         expires_at, max(1, int(max_uses))),
    )
    return cur.lastrowid


def get_invite_by_code(code: str) -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM invites WHERE code=?", (code,))


def invite_usable(inv: sqlite3.Row) -> tuple[bool, str]:
    if inv is None:
        return False, "Einladung nicht gefunden."
    if inv["revoked"]:
        return False, "Diese Einladung wurde zurückgezogen."
    if inv["uses"] >= inv["max_uses"]:
        return False, "Diese Einladung ist bereits aufgebraucht."
    if inv["expires_at"]:
        try:
            if datetime.fromisoformat(inv["expires_at"]) < now_utc():
                return False, "Diese Einladung ist abgelaufen."
        except ValueError:
            pass
    return True, ""


def increment_invite_use(invite_id: int) -> None:
    _exec("UPDATE invites SET uses=uses+1 WHERE id=?", (invite_id,))


def revoke_invite(invite_id: int) -> None:
    _exec("UPDATE invites SET revoked=1 WHERE id=?", (invite_id,))


def list_invites() -> list[sqlite3.Row]:
    return _query("SELECT * FROM invites ORDER BY created_at DESC")


# ── Applications ──────────────────────────────────────────────────────
def create_application(name: str, contact: str, games: str, message: str,
                       herkunft: str = "") -> int:
    """`herkunft` ist die Kennung aus security.ip_kennung, NIE eine Adresse."""
    cur = _exec(
        "INSERT INTO applications(name,contact,games,message,ip,created_at)"
        " VALUES(?,?,?,?,?,?)",
        (name[:80], contact[:120], games[:200], message[:2000], herkunft, now_iso()),
    )
    return cur.lastrowid


def list_applications(status: Optional[str] = None) -> list[sqlite3.Row]:
    if status:
        return _query("SELECT * FROM applications WHERE status=? ORDER BY created_at DESC", (status,))
    return _query("SELECT * FROM applications ORDER BY "
                  "CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC")


def get_application(app_id: int) -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM applications WHERE id=?", (app_id,))


def count_pending_applications() -> int:
    return _one("SELECT COUNT(*) c FROM applications WHERE status='pending'")["c"]


def update_application(app_id: int, status: str, reviewed_by: Optional[int],
                       invite_code: Optional[str] = None) -> None:
    _exec("UPDATE applications SET status=?, reviewed_by=?, reviewed_at=?, invite_code=? WHERE id=?",
          (status, reviewed_by, now_iso(), invite_code, app_id))


def purge_reviewed_applications(days: int) -> int:
    """DSGVO: angenommene/abgelehnte Bewerbungen nach Ablauf loeschen.
    Offene (pending) bleiben, bis ein Admin entscheidet."""
    cutoff = iso(now_utc() - timedelta(days=days))
    cur = _exec("DELETE FROM applications WHERE status != 'pending'"
                " AND reviewed_at IS NOT NULL AND reviewed_at < ?", (cutoff,))
    return cur.rowcount


# ── Play-Sessions (eigener Status-Sampler: Feed + Playtime) ──────────
def open_play_session(game: str, world: str) -> int:
    cur = _exec("INSERT INTO play_sessions(game,world,started_at) VALUES(?,?,?)",
                (game, world or "", now_iso()))
    return cur.lastrowid


def get_open_play_session() -> Optional[sqlite3.Row]:
    return _one("SELECT * FROM play_sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")


def update_play_session(sid: int, peak: int, add_minutes: float) -> None:
    _exec("UPDATE play_sessions SET peak_players=MAX(peak_players,?),"
          " player_minutes=player_minutes+? WHERE id=?", (peak, add_minutes, sid))


def close_play_session(sid: int) -> None:
    _exec("UPDATE play_sessions SET ended_at=? WHERE id=?", (now_iso(), sid))


def close_stale_play_sessions() -> None:
    """Beim App-Start uebriggebliebene offene Sessions schliessen (Neustart/Absturz)."""
    _exec("UPDATE play_sessions SET ended_at=started_at WHERE ended_at IS NULL")


def recent_play_sessions(limit: int = 12) -> list[sqlite3.Row]:
    return _query("SELECT * FROM play_sessions ORDER BY started_at DESC LIMIT ?", (limit,))


def playtime_totals(days: Optional[int] = None) -> list[sqlite3.Row]:
    """Spielzeit je Game: Sessions-Anzahl + Stunden (Session-Dauer, nicht
    Spieler-Minuten) + Spitzen-Spielerzahl. days=None -> gesamt."""
    where, params = "", ()
    if days:
        where = "WHERE started_at >= ?"
        params = (iso(now_utc() - timedelta(days=days)),)
    return _query(
        "SELECT game, COUNT(*) sessions, MAX(peak_players) peak,"
        " SUM((julianday(COALESCE(ended_at, started_at)) - julianday(started_at)) * 24) hours"
        f" FROM play_sessions {where} GROUP BY game ORDER BY hours DESC", params)


# ── Events (Audit) ────────────────────────────────────────────────────
def log_event(actor: str, action: str, detail: str = "") -> None:
    try:
        _exec("INSERT INTO events(ts,actor,action,detail) VALUES(?,?,?,?)",
              (now_iso(), actor[:60], action[:60], detail[:400]))
    except Exception:
        pass


def recent_events(limit: int = 50) -> list[sqlite3.Row]:
    return _query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))


def anonymize_events(username: str) -> None:
    """DSGVO-Selbstloeschung: Audit-Zeilen behalten, Personenbezug entfernen."""
    _exec("UPDATE events SET actor='(gelöscht)' WHERE actor=? COLLATE NOCASE", (username,))
