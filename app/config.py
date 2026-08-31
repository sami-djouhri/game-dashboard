from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Marke / Auftritt ──────────────────────────────────────────────
    brand_name: str = "Greenleaf"
    brand_tagline: str = "Privater Game-Cluster · Beitritt auf Bewerbung"
    # Subtiler Entwickler-Credit (Footer/About), nicht plakativ auf der Startseite.
    # „im eigenen Homelab" stand hier bis 2026-08-27 — seit dem Umzug am 22.08. laeuft
    # nichts davon mehr zu Hause. Selbst gebaut und selbst betrieben stimmt weiterhin
    # und ist ohnehin die Aussage, um die es geht.
    developer_credit: str = "Selbst gebaut & selbst betrieben."
    developer_name: str = ""  # optional; leer = anonym „der Admin"
    # Absolute Basis-URL fuer Einladungs-/Bewerbungslinks (fuer Mail/Discord kopierbar).
    public_base_url: str = "https://games.saganta.de"
    community_discord_url: str = ""  # optional Discord-Invite auf der Landing

    # ── Impressum / Datenschutz (Angaben wie djouhri.de) ──────────────
    imprint_name: str = "Sami Djouhri"
    imprint_location: str = "Heiligenhaus, NRW"
    imprint_email: str = "sami@djouhri.de"
    # Vollstaendige Postanschrift (Owner-Schritt via Env, nicht committen).
    imprint_address: str = ""

    # ── Bewerbungs-Benachrichtigung (Discord-Webhook, Herb-#admin) ────
    # Owner-Schritt: Webhook im #admin-Kanal anlegen, URL in die .env.
    admin_webhook_url: str = ""

    # ── DSGVO: entschiedene Bewerbungen automatisch loeschen ──────────
    application_retention_days: int = 30

    # ── Aktivitaet (Feed + Playtime aus eigenem Status-Sampler) ───────
    activity_sample_s: int = 60

    service_name: str = "game-dashboard"
    service_version: str = "0.2.0"
    env: str = "prod"
    log_level: str = "INFO"

    # ── Persistenz ────────────────────────────────────────────────────
    data_dir: str = "data"

    @property
    def db_path(self) -> str:
        return str(Path(self.data_dir) / "game-dashboard.sqlite")

    @property
    def secret_file(self) -> str:
        return str(Path(self.data_dir) / "session.secret")

    # ── Sessions / Cookies ────────────────────────────────────────────
    session_cookie: str = "gd_session"
    session_ttl_days: int = 30
    # hinter cloudflared/dev-portal ist der externe Kanal HTTPS -> Secure-Cookie.
    # Fuer LAN-only-Tests (http) via GD_COOKIE_SECURE=false abschaltbar.
    cookie_secure: bool = True
    # optionaler fester Session/CSRF-Secret; sonst wird einer erzeugt+persistiert.
    session_secret: str = ""

    # ── Owner-Bootstrap ───────────────────────────────────────────────
    # Beim ersten Start ohne Owner: aus diesen Env-Werten den Owner anlegen.
    # (Owner-Schritt in .env, analog zum Bridge-Token, nie committen.)
    owner_user: str = ""
    owner_password: str = ""

    # ── Gaming-Rollen-Automatik (Greenleaf-Bot) ───────────────────────
    # Der Bot gleicht ab, wer auf Discord die Gaming-Rolle traegt, und laesst
    # dafuer Konten anlegen bzw. sperren. Der Endpunkt haengt nicht am oeffentlichen
    # Weg, sondern nur am SSH-Tunnel von node1 - der Token ist die zweite Schranke.
    # Leer = Automatik aus (Endpunkt antwortet dann mit 503).
    provision_token: str = ""
    # Sicherheitsdeckel: sperrt der Abgleich mehr Konten als das, bricht er ab und
    # meldet - eine unvollstaendige Mitgliederliste soll niemanden aussperren.
    provision_max_sperren: int = 3

    # ── wake-bridge ───────────────────────────────────────────────────
    # GET /status ist token-frei; POST /wake|/sleep|/restart braucht Bearer.
    # Der Token bleibt serverseitig, er wird NIE an den Browser gegeben.
    # Die Bridge sitzt IMMER auf dem Wirt, der die Spiele haelt — seit 2026-08-22
    # ist das gamehost (host-nativ neben dem Dashboard), nicht mehr Node .18.
    # Deshalb der Wirts-Default statt einer festen LAN-Adresse: .18 hat keine
    # Spielrolle mehr, und seine Bridge ist LAN-only, vom VPS aus unerreichbar.
    game_bridge_url: str = "http://host.docker.internal:8129"
    game_bridge_token: str = ""
    # Der Arbiter laeuft hinter der Bridge mit subprocess-Timeout ~180s -> der
    # HTTP-Client muss laenger warten, sonst bricht er einen laufenden Vorgang ab.
    bridge_action_timeout_s: float = 200.0
    bridge_status_timeout_s: float = 10.0

    # ── Welten-Downloads (Game-Vault) ─────────────────────────────────
    # Nur fuer admin-verifizierte Mitglieder. Ein Host-Timer packt die taeglichen
    # Welt-Snapshots (<wirt>:/var/backups/game-saves/<game>.tar.gz) hierher — auf
    # gamehost ist das welten-schnappschuss.timer (05:23), der die Spielstaende der
    # dort laufenden Server sichert und spiegelt. Die App serviert sie read-only aus
    # diesem Verzeichnis (kein SSH-Key im Container).
    downloads_enabled: bool = True
    worlds_dir: str = "data/worlds"

    # ── Reverse-Proxy / echte Client-IP ───────────────────────────────
    # X-Forwarded-For wird NUR akzeptiert, wenn der TCP-Peer hier drin ist
    # (dev-portal auf der homelab-Bridge). Sonst zaehlt die Peer-IP direkt.
    trusted_proxies: list[str] = ["127.0.0.1", "172.16.0.0/12", "10.210.0.0/16"]

    # ── Rate-Limits (in-memory, pro Prozess) ──────────────────────────
    login_max_attempts: int = 8         # pro IP+User im Fenster
    login_window_s: int = 900           # 15 min
    apply_max_per_hour: int = 5         # Bewerbungen pro IP/Stunde


settings = Settings()
