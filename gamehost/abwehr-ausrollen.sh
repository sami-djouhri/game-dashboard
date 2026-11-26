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

echo "== 3. Ausnahme fuer angemeldete SSH-Sitzungen (alle Jails) =="
# Erst das Skript einspielen und auf dem Wirt selbst pruefen: die Adresse, von der
# diese Sitzung kommt, muss ausgenommen sein, eine Dokumentationsadresse nicht.
# Erst danach zeigt fail2ban darauf; scheitert etwas, bleibt die Datei weg.
ssh "$H" "install -m 755 -o root -g root /dev/stdin /usr/local/sbin/f2b-ssh-sitzung" < "$HERE/fail2ban/f2b-ssh-sitzung.py"
ICH="$(ssh "$H" 'echo "${SSH_CLIENT%% *}"')"
if ssh "$H" "/usr/local/sbin/f2b-ssh-sitzung '$ICH' && ! /usr/local/sbin/f2b-ssh-sitzung 192.0.2.1"; then
  echo "  Skript ok: eigene Adresse ausgenommen, 192.0.2.1 nicht"
  ssh "$H" "cat > /etc/fail2ban/jail.d/05-ssh-sitzung.local" < "$HERE/fail2ban/jail.d/05-ssh-sitzung.local"
  if ssh "$H" "fail2ban-client -t >/dev/null 2>&1"; then
    ssh "$H" 'fail2ban-client reload >/dev/null && sleep 2 && for j in caddy-proben recidive sshd; do printf "  %-13s %s\n" "$j" "$(fail2ban-client get "$j" ignorecommand)"; done'
  else
    ssh "$H" "rm -f /etc/fail2ban/jail.d/05-ssh-sitzung.local"
    echo "  FEHLER: fail2ban-Pruefung gescheitert, Ausnahme wieder entfernt" >&2; exit 1
  fi
else
  echo "  FEHLER: Skript entscheidet falsch, fail2ban bleibt unveraendert" >&2; exit 1
fi

echo "== 4. Gegenprobe =="
ssh "$H" 'for p in / /.env /packs/schach.zip; do printf "  %-20s %s\n" "$p" "$(curl -s -o /dev/null -w "%{http_code}" --resolve games.saganta.de:443:127.0.0.1 https://games.saganta.de$p)"; done'
echo "  erwartet: / 200, /.env 404, /packs/schach.zip 200"
