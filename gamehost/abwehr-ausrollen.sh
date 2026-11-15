#!/bin/bash
# abwehr-ausrollen.sh: Caddyfile und fail2ban-Jail caddy-proben auf gamehost einspielen.
# Kanonisch sind gamehost/caddy/ und gamehost/fail2ban/ in diesem Repo.
#
#   bash gamehost/abwehr-ausrollen.sh
#
# Reihenfolge mit Pruefung vor jedem Scharfschalten: Caddy erst validieren, dann
# reload (kein restart, die TLS-Verbindungen bleiben stehen); fail2ban erst mit
# `-t` pruefen. Scheitert eine Pruefung, kommt die alte Datei zurueck.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
H="gamehost"
STEMPEL="$(date +%Y%m%d-%H%M)"

echo "== 1. Caddyfile =="
ssh "$H" "cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.vor-proben-$STEMPEL"
ssh "$H" "cat > /etc/caddy/Caddyfile.neu" < "$HERE/caddy/Caddyfile"
if ssh "$H" "caddy validate --config /etc/caddy/Caddyfile.neu --adapter caddyfile >/dev/null 2>&1"; then
  ssh "$H" "mv /etc/caddy/Caddyfile.neu /etc/caddy/Caddyfile && systemctl reload caddy && echo '  caddy neu geladen'"
else
  ssh "$H" "rm -f /etc/caddy/Caddyfile.neu"; echo "  FEHLER: Caddyfile ungueltig, nichts geaendert" >&2; exit 1
fi

echo "== 2. fail2ban caddy-proben =="
ssh "$H" "cat > /etc/fail2ban/filter.d/caddy-proben.conf" < "$HERE/fail2ban/filter.d/caddy-proben.conf"
ssh "$H" "cat > /etc/fail2ban/jail.d/caddy-proben.local" < "$HERE/fail2ban/jail.d/caddy-proben.local"
if ssh "$H" "fail2ban-client -t >/dev/null 2>&1"; then
  ssh "$H" "fail2ban-client reload >/dev/null && sleep 2 && fail2ban-client status caddy-proben"
else
  ssh "$H" "rm -f /etc/fail2ban/jail.d/caddy-proben.local /etc/fail2ban/filter.d/caddy-proben.conf"
  echo "  FEHLER: fail2ban-Pruefung gescheitert, Jail wieder entfernt" >&2; exit 1
fi

echo "== 3. Gegenprobe =="
ssh "$H" 'for p in / /.env /packs/schach.zip; do printf "  %-20s %s\n" "$p" "$(curl -s -o /dev/null -w "%{http_code}" --resolve games.saganta.de:443:127.0.0.1 https://games.saganta.de$p)"; done'
echo "  erwartet: / 200, /.env 404, /packs/schach.zip 200"
