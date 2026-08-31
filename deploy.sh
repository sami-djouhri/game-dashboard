#!/bin/bash
# deploy.sh — rollt die Clan-Seite auf den Spiele-VPS aus (dort laufen auch die Spiele).
# Kanonisch ist dieses Gitea-Repo auf host; ausgerollt wird von Hand.
#
#   ./deploy.sh            uebertragen + bauen + Health + Sichtprobe
#   ./deploy.sh --dry      nur zeigen, was uebertragen wuerde
#
# ★ WARUM ES DIESES SKRIPT GIBT (2026-08-24):
# Ein von Hand getippter rsync hat in EINEM Lauf zwei Dinge ueberschrieben, die dem Wirt
# gehoeren — die aktuellen Welt-Archive (3 Tage alte host-Kopien darueber, die echte
# Terraria-Welt 122 MB gegen 14 MB) und das Laufzeit-Compose (das host-Rezept mit
# profiles:["rueckfall"], das dort gar nichts startet).
#
# Ursache war beide Male derselbe Irrtum: --filter='P …' schuetzt eine Datei nur vor dem
# LOESCHEN durch --delete. Gegen das UEBERSCHREIBEN hilft ausschliesslich --exclude.
# Die Regel steht hier jetzt einmal richtig, statt bei jedem Ausrollen neu getippt zu werden.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ZIEL_HOST="gamehost"
ZIEL="/opt/game-dashboard"
DRY=""
for a in "$@"; do [ "$a" = "--dry" ] && DRY="--dry-run"; done

# Was dem WIRT gehoert und nie von hier kommen darf. --exclude, nicht --filter='P'.
#   worlds/       fuellt welten-schnappschuss.timer dort taeglich aus /var/backups/game-saves
#   data/         SQLite (Konten, Rollen, Bewerbungen) — liegt ohnehin im Volume
#   .env          Secrets
#   compose       das Laufzeit-Rezept kommt aus gamehost/, nicht aus der Projektwurzel
AUS=(
  --exclude='worlds/'  --exclude='data/'  --exclude='.env'
  --exclude='docker-compose.yml' --exclude='docker-compose.override.yml'
  --exclude='docker-compose.yml.host-original'
  --exclude='docker-compose.override.yml.host-preview-ENTFERNT'
  --exclude='gamehost/' --exclude='.git/' --exclude='.github/'
  --exclude='__pycache__/' --exclude='*.pyc'
  --exclude='.ansehen/'   # Bilder + Wegwerf-HTML des Sicht-Pruefstands, nur lokal
)

echo "== 1. Anwendung uebertragen -> $ZIEL_HOST:$ZIEL =="
# --chmod: rsync -a nimmt sonst die Gruppenrechte von host mit, und der unprivilegierte
# Prozess im Container liest seine eigenen Dateien nicht mehr.
rsync -az --delete ${DRY} "${AUS[@]}" --chmod=F644,D755 "$HERE/" "$ZIEL_HOST:$ZIEL/"

if [ -n "$DRY" ]; then echo "(Trockenlauf — nichts geschrieben)"; exit 0; fi

echo "== 2. Laufzeit-Rezept aus gamehost/ =="
# Bewusst eine eigene Zeile: das Rezept des Wirts liegt im Repo unter gamehost/, damit der
# Live-Stand versioniert ist — es darf aber nie aus der Projektwurzel kommen (host-Variante).
ssh "$ZIEL_HOST" "cat > $ZIEL/docker-compose.yml" < "$HERE/gamehost/docker-compose.yml"
ssh "$ZIEL_HOST" "cd $ZIEL && docker compose config --quiet && echo '  compose gueltig'"

echo "== 3. Bauen + starten =="
ssh "$ZIEL_HOST" "cd $ZIEL && docker compose up -d --build" 2>&1 | tail -5

echo "== 4. Health =="
for i in $(seq 1 20); do
  if ssh "$ZIEL_HOST" "curl -fsS http://127.0.0.1:8144/health" 2>/dev/null; then echo; break; fi
  [ "$i" = 20 ] && { echo "  KEIN Health nach 20 Versuchen"; exit 1; }
  sleep 2
done

echo "== 5. Sichtprobe (anonym) =="
# Der Test misst, was ein Besucher OHNE Login zu sehen bekommt. Die Guides duerfen keine
# Server-Adresse zeigen — die Maskierung war schon einmal still wirkungslos, weil sie auf
# eine IP zeigte, die es nicht mehr gab.
ssh "$ZIEL_HOST" 'n=$(curl -fsS http://127.0.0.1:8144/guides | grep -coE "\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b" || true);
  if [ "${n:-0}" -eq 0 ]; then echo "  /guides anonym: keine IP sichtbar (richtig)";
  else echo "  !! /guides anonym: $n IP-Fundstellen — Maskierung prueft nicht mehr"; exit 1; fi'
echo "== fertig. Oeffentlich: https://games.saganta.de =="
