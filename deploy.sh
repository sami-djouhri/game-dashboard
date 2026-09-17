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
#   mods/         fuellt mods-sammeln.timer dort. ★ Ohne diese Zeile loescht --delete
#                 das Verzeichnis bei JEDEM Ausrollen und legt es leer wieder an.
#                 Der laufende Container haelt seinen Bind-Mount dann auf die
#                 geloeschte Inode: im Container blieb /app/data/mods leer, die Seite
#                 zeigte gar keine Mods, und auf dem Wirt lag die Datei sichtbar da.
#   data/         SQLite (Konten, Rollen, Bewerbungen), liegt ohnehin im Volume
#   .env          Secrets
#   compose       das Laufzeit-Rezept kommt aus gamehost/, nicht aus der Projektwurzel
AUS=(
  --exclude='worlds/'  --exclude='mods/'  --exclude='data/'  --exclude='.env'
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

echo "== 3. Mod-Sammler + Timer =="
# Die Mod-Listen stehen in den Arbeitsverzeichnissen der Spiele, jede in einem
# anderen Format. Der Sammler laeuft deshalb auf dem WIRT und legt eine fertige
# JSON ab, die der Container read-only einhaengt; das Dashboard muss die
# Verzeichnisstruktur des Wirts nicht kennen.
# ★ Auch hier gilt: was nur von Hand auf dem Wirt existiert, existiert beim
# naechsten Neuaufbau nicht mehr. Deshalb kommen Skript UND Units aus dem Repo.
ssh "$ZIEL_HOST" "install -d -m 755 $ZIEL/mods"
ssh "$ZIEL_HOST" "cat > $ZIEL/mods-sammeln.py && chmod 755 $ZIEL/mods-sammeln.py" \
  < "$HERE/gamehost/mods-sammeln.py"
ssh "$ZIEL_HOST" "cat > /etc/systemd/system/mods-sammeln.service" < "$HERE/gamehost/mods-sammeln.service"
ssh "$ZIEL_HOST" "cat > /etc/systemd/system/mods-sammeln.timer"   < "$HERE/gamehost/mods-sammeln.timer"
ssh "$ZIEL_HOST" "systemctl daemon-reload && systemctl enable --now mods-sammeln.timer >/dev/null 2>&1; \
  systemctl start mods-sammeln.service && systemctl is-active --quiet mods-sammeln.timer \
  && echo '  Timer aktiv, Sammellauf gemacht'"
# Gegenprobe am Ergebnis, nicht am Rueckgabewert des Starts: ein oneshot meldet
# auch dann Erfolg, wenn er nichts gefunden hat.
ssh "$ZIEL_HOST" "python3 -c \"
import json,sys
d=json.load(open('$ZIEL/mods/mods.json'))
sp=d['spiele']
ohne=[k for k,v in sp.items() if not v.get('gelesen')]
print('  %d Spiele gelesen, Stand %s' % (len(sp)-len(ohne), d['stand'][:16]))
if ohne: print('  !! ohne Messung: %s' % ', '.join(ohne))
\""

echo "== 4. Bauen + starten =="
ssh "$ZIEL_HOST" "cd $ZIEL && docker compose up -d --build" 2>&1 | tail -5

echo "== 5. Health =="
for i in $(seq 1 20); do
  if ssh "$ZIEL_HOST" "curl -fsS http://127.0.0.1:8144/health" 2>/dev/null; then echo; break; fi
  [ "$i" = 20 ] && { echo "  KEIN Health nach 20 Versuchen"; exit 1; }
  sleep 2
done

echo "== 6. Sichtprobe (anonym) =="
# Der Test misst, was ein Besucher OHNE Login zu sehen bekommt. Die Guides duerfen keine
# Server-Adresse zeigen. Die Maskierung war schon einmal still wirkungslos, weil sie auf
# eine IP zeigte, die es nicht mehr gab.
#
# Zwei Proben, weil eine allein einen blinden Fleck hat:
#   a) das generische IP-Muster (faengt auch Adressen, die in keiner Liste stehen)
#   b) die Bausteine aus `app.games.adress_bausteine()`, aus dem LAUFENDEN Container
#      geholt. Seit Minecraft seine Adresse hat, ist eine davon ein Hostname, und (a)
#      allein haette sie durchgelassen: dieselbe Luecke, nur mit anderer Schreibweise.
ssh "$ZIEL_HOST" 'seite=$(curl -fsS http://127.0.0.1:8144/guides);
  n=$(printf "%s" "$seite" | grep -coE "\b[0-9]{1,3}(\.[0-9]{1,3}){3}\b" || true);
  if [ "${n:-0}" -ne 0 ]; then echo "  !! /guides anonym: $n IP-Fundstellen, Maskierung prueft nicht mehr"; exit 1; fi
  muster=$(docker exec game-dashboard python -c "from app.games import adress_bausteine; print(\"|\".join(adress_bausteine()))" 2>/dev/null);
  if [ -z "$muster" ]; then echo "  !! Adress-Bausteine nicht abfragbar, Probe b waere still gruen"; exit 1; fi
  m=$(printf "%s" "$seite" | grep -coE "$muster" || true);
  if [ "${m:-0}" -ne 0 ]; then echo "  !! /guides anonym: $m Fundstellen bekannter Adressen (auch Hostnamen)"; exit 1; fi
  echo "  /guides anonym: keine Adresse sichtbar, IP und Hostname geprueft"'
echo "== fertig. Oeffentlich: https://games.saganta.de =="
