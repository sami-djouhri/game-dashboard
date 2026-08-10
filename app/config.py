from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "game-dashboard"
    service_version: str = "0.1.0"
    env: str = "prod"
    log_level: str = "INFO"

    # ── wake-bridge (Node .18, LAN-only) ──────────────────────────────
    # GET /status ist token-frei; POST /wake|/sleep|/restart braucht Bearer.
    # Der Token bleibt serverseitig — er wird NIE an den Browser gegeben.
    game_bridge_url: str = "http://192.0.2.10:8129"
    game_bridge_token: str = ""
    # Der Arbiter laeuft hinter der Bridge mit subprocess-Timeout ~180s -> der
    # HTTP-Client muss laenger warten, sonst bricht er einen laufenden Vorgang ab.
    bridge_action_timeout_s: float = 200.0
    bridge_status_timeout_s: float = 10.0

    # ── Auth (Authelia forward-auth via dev-portal nginx) ─────────────
    auth_required: bool = True
    auth_header_user: str = "Remote-User"
    auth_header_groups: str = "Remote-Groups"
    # Nur von diesen Peer-IPs werden die Remote-User/-Groups-Header akzeptiert
    # (der authentifizierende dev-portal-Reverse-Proxy auf der homelab-Bridge).
    auth_trusted_proxies: list[str] = ["127.0.0.1", "172.16.0.0/12", "10.210.0.0/16"]
    # Rollen: wer in admin_group ist, darf alles (stop/restart/force/reserve);
    # wer in user_group ODER admin_group ist, darf Games starten (wake).
    admin_group: str = "admin"
    user_group: str = "user"


settings = Settings()
