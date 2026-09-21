#!/bin/bash
# ansehen.sh: macht Bilder der Seite, wie ein Besucher sie sieht.
#
#   bash scripts/ansehen.sh          Landing + Mitglieder-Ansicht, Desktop + Handy
#   bash scripts/ansehen.sh --behalten   Wegwerf-Instanz danach weiterlaufen lassen
#
# ★ WARUM ES DIESES SKRIPT GIBT (2026-08-27):
# Die Kacheln entstehen erst im Browser aus /api/status. Wer nur den Quelltext liest,
# sieht ein leeres Gitter und haelt die Seite fuer in Ordnung: Stauchungen, fehlende
# Umlaute, unlesbare Zustaende und Knoepfe, die sich ueberlagern, zeigen sich
# ausschliesslich im gerenderten Bild.
#
# ★ ES WIRD NICHT DIE LIVE-SEITE FOTOGRAFIERT, sondern eine Wegwerf-Instanz aus
# demselben Quelltext, mit erfundenen Daten. Zwei Gruende:
#   1. Die Live-Datenbank haelt echte Konten. Ein Prueflauf darf dort nichts anlegen.
#   2. Live sieht man nur den Zustand, der GERADE gilt. Der Prueflauf zeigt alle
#      Kachel-Zustaende nebeneinander: laufend, schlafend, startend, stumm, zu wenig
#      Speicher, Mehr-Welten. Genau die Faelle, die man sonst nie zu Gesicht bekommt.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/.ansehen"
PORT=8199
NAME=gd-ansehen
PASS='pruefstand-nur-lokal-9471'
BEHALTEN=""
for a in "$@"; do [ "$a" = "--behalten" ] && BEHALTEN="ja"; done

aufraeumen() { [ -n "$BEHALTEN" ] || docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap aufraeumen EXIT

mkdir -p "$OUT"
rm -f "$OUT"/*.png "$OUT"/*.html 2>/dev/null || true

echo "== 1. Wegwerf-Instanz bauen =="
docker build -q -t homelab/game-dashboard:ansehen "$HERE" >/dev/null

echo "== 2. starten (eigene, leere Datenbank, kein Volume, kein Netz) =="
docker rm -f "$NAME" >/dev/null 2>&1 || true
# --network none geht nicht: wir sprechen ihn ueber den veroeffentlichten Port an.
# Kein Volume -> die SQLite lebt und stirbt mit dem Container.
# Mod-Listen: dieselbe Datei, aus der auch der Browser-Stub gespeist wird. Live
# fuellt sie mods-sammeln.py auf dem Wirt; hier liegt ein Schnappschuss davon,
# damit die serverseitig gerenderten Seiten (Guides, Landing) im Bild dasselbe
# zeigen wie die Kacheln.
mkdir -p "$OUT/mods"
cp "$HERE/scripts/pruefdaten-mods.json" "$OUT/mods/mods.json"
# ★ Welten-Downloads: live legt welten-schnappschuss.timer sie je SPIEL ab, und bei
# Spielen mit mehreren Welten je WELT in einem Unterordner (terraria/greenleaf.tar.gz).
# Genau dieser Fall war nie im Bild, weil der Pruefstand keine Welten hatte und die
# Seite deshalb immer „Noch keine Sicherungen da" zeigte. Nachgebaut mit derselben
# Struktur, damit die Gruppierung geprueft wird und nicht nur der Leerzustand.
rm -rf "$OUT/welten"; mkdir -p "$OUT/welten/terraria" "$OUT/welten/zomboid"
head -c 900000 /dev/urandom > "$OUT/welten/valheim.tar.gz"
head -c 2400000 /dev/urandom > "$OUT/welten/terraria/greenleaf.tar.gz"
head -c 1800000 /dev/urandom > "$OUT/welten/terraria/solo.tar.gz"
head -c 1500000 /dev/urandom > "$OUT/welten/zomboid/greenleaf.tar.gz"
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8000" \
  -v "$OUT/mods:/pruefmods:ro" -e MODS_FILE=/pruefmods/mods.json \
  -v "$OUT/welten:/pruefwelten:ro" -e WORLDS_DIR=/pruefwelten \
  -e SERVICE_NAME=game-dashboard -e ENV=dev -e LOG_LEVEL=WARNING \
  -e BRAND_NAME=Greenleaf -e COOKIE_SECURE=false \
  -e OWNER_USER=pruefstand -e OWNER_PASSWORD="$PASS" \
  -e GAME_BRIDGE_TOKEN=egal -e GAME_BRIDGE_URL=http://127.0.0.1:1 \
  homelab/game-dashboard:ansehen >/dev/null
for i in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "  Instanz kam nicht hoch"; docker logs "$NAME" | tail -20; exit 1; }
  sleep 1
done
echo "  bereit auf :$PORT"

echo "== 3. Seiten holen (als Owner angemeldet) =="
JAR="$OUT/cookies.txt"; rm -f "$JAR"
curl -fsS -c "$JAR" -o /dev/null "http://127.0.0.1:$PORT/login"
curl -fsS -b "$JAR" -c "$JAR" -o /dev/null -X POST \
  -d "username=pruefstand&password=$PASS" "http://127.0.0.1:$PORT/login"
# ★ Erfundene Eintraege, damit die Admin-Tabellen ZEILEN haben. Eine leere Tabelle zeigt
# nur ihre Leermeldung, und genau die Zellen, in denen bis 2026-08-27 ein einzelnes Komma
# stand (fehlender Kontakt, nie angemeldet, unbegrenzt gueltig), bekommt man sonst nie
# zu sehen. Der zweite Eintrag ist absichtlich MINIMAL ausgefuellt: er erzeugt die
# leeren Zellen.
curl -fsS -o /dev/null -X POST "http://127.0.0.1:$PORT/apply" \
  --data-urlencode "name=Testbewerber" --data-urlencode "contact=test#1234" \
  --data-urlencode "games=Valheim, Terraria" \
  --data-urlencode "message=Hallo, ich wuerde gern mitspielen."
curl -fsS -o /dev/null -X POST "http://127.0.0.1:$PORT/apply" \
  --data-urlencode "name=NurName"        # ohne Kontakt/Spiele/Nachricht -> leere Zellen
CSRF=$(grep -oP 'name="csrf" content="\K[^"]+' "$OUT/roh-login.html" 2>/dev/null || true)
[ -n "$CSRF" ] || CSRF=$(curl -fsS -b "$JAR" "http://127.0.0.1:$PORT/app" \
  | grep -oP 'name="csrf" content="\K[^"]+' | head -1)
curl -fsS -o /dev/null -b "$JAR" -X POST "http://127.0.0.1:$PORT/admin/invites" \
  -d "csrf=$CSRF&role=member&max_uses=1&expires_days=14&note=fuer Max"
curl -fsS -o /dev/null -b "$JAR" -X POST "http://127.0.0.1:$PORT/admin/invites" \
  -d "csrf=$CSRF&role=member&max_uses=5&expires_days=0"   # unbegrenzt + ohne Notiz

curl -fsS -b "$JAR" -o "$OUT/roh-app.html"   "http://127.0.0.1:$PORT/app"
curl -fsS          -o "$OUT/roh-landing.html" "http://127.0.0.1:$PORT/"
curl -fsS -b "$JAR" -o "$OUT/roh-admin.html" "http://127.0.0.1:$PORT/admin" || true
# Der Verlauf ist die einzige Seite mit einer Filterzeile, und Formularfelder sind
# das, was auf einem Handy als erstes aus dem Raster faellt. Mit Zeitraum "alle",
# damit die Tabellen im Bild auch gefuellt sind.
# ★ Spielzeiten erfinden, sonst zeigt der Verlauf drei leere Tabellen -- und genau
# die Zeilen mit Zahlen sind die, deren Umbruch kippen kann. Bewusst mit Bandbreite:
# ein Lauf mit vielen Spielern, einer der nie betreten wurde (die Spalte "ungenutzt"
# soll im Bild belegt sein) und einer, der gerade laeuft.
docker exec "$NAME" python -c "
import sys; sys.path.insert(0,'/app')
from app import db
db.init_db()
for wer, spiel in [('pruefstand','zomboid'),('pruefstand','terraria'),('max','zomboid'),('max','factorio')]:
    db.log_event(wer, 'game.start', spiel + ' -> started')
db.log_event('pruefstand','game.stop','zomboid -> stopped')
a = db.open_play_session('zomboid','greenleaf','pruefstand'); db.update_play_session(a, 6, 640.0); db.close_play_session(a)
b = db.open_play_session('terraria','greenleaf','max');       db.update_play_session(b, 0, 0.0);   db.close_play_session(b)
db.open_play_session('factorio','greenleaf-se','max')
" >/dev/null 2>&1 || true

curl -fsS -b "$JAR" -o "$OUT/roh-verlauf.html" "http://127.0.0.1:$PORT/admin/verlauf?zeitraum=alle" || true
# Die Rechtstexte gehoeren mit ins Bild: sie werden nie beilaeufig gelesen und altern
# deshalb unbemerkt. Genau dort stand am 2026-08-27 noch „laeuft auf eigener Hardware
# (Homelab)" -- fuenf Tage nach dem Umzug auf einen gemieteten Server.
curl -fsS -o "$OUT/roh-datenschutz.html" "http://127.0.0.1:$PORT/datenschutz"
# Als Mitglied geholt: nur dann stehen die Server-Adressen samt Kopier-Knopf da.
# Ohne Anmeldung zeigt dieselbe Seite den Schloss-Hinweis, und geprueft werden soll
# die Fassung, die jemand vor sich hat, der gerade beitreten will.
curl -fsS -b "$JAR" -o "$OUT/roh-guides.html" "http://127.0.0.1:$PORT/guides"
# Die Anmeldung ist die erste Seite, die ein neues Mitglied bedient, und die
# einzige, auf der es nur ein Formular gibt: faellt dort etwas aus dem Raster,
# faellt es sofort auf. Anonym geholt, so wie sie jeder zu sehen bekommt.
curl -fsS -o "$OUT/roh-login.html" "http://127.0.0.1:$PORT/login"
# ★ ALLES aus static, nicht eine Liste von Dateinamen. Die Aufzaehlung hier hat genau
# einmal funktioniert und danach still gefehlt: als am 2026-09-06 `adminlage.js`
# dazukam, lud die Admin-Seite im Prueflauf ihr Skript nicht mehr, und die Lagezeile
# zeigte drei Striche. Das sah aus wie ein Fehler im neuen Skript und war einer in
# dieser Zeile. Eine Eigenschaft („alle Dateien im Ordner") veraltet nicht, eine
# Liste schon.
cp "$HERE"/app/static/*.css "$HERE"/app/static/*.js "$OUT/"

echo "== 4. offline-tauglich machen + Antworten stellen =="
python3 "$HERE/scripts/ansehen_aufbereiten.py" "$OUT"

echo "== 5. Bilder =="
# ★ Das Image hat ENTRYPOINT ["tini","--"] und KEIN CMD, der Browser muss als erstes
# Argument selbst genannt werden. Ohne ihn scheitert tini mit "exec --no-sandbox failed",
# was wie ein falsches Flag aussieht und keins ist.
schuss() {  # datei breite hoehe name
  docker run --rm -v "$OUT:/work" -u "$(id -u):$(id -g)" -e HOME=/tmp \
    zenika/alpine-chrome:with-puppeteer chromium-browser \
    --no-sandbox --headless --disable-gpu --disable-dev-shm-usage \
    --user-data-dir=/tmp/chrome --hide-scrollbars --virtual-time-budget=4000 \
    --window-size="$2,$3" --screenshot="/work/$4.png" "file:///work/$1" >/dev/null 2>&1 || true
  [ -s "$OUT/$4.png" ] && echo "  $4.png  (${2}x${3})" || echo "  !! $4.png nicht entstanden"
}
schuss app.html     1440 1500 app-desktop
schuss app.html      390 1800 app-handy
schuss landing.html 1440 1500 landing-desktop
schuss landing.html  390 1800 landing-handy
schuss login.html   1000  900 login
schuss guides.html  1440 1700 guides-desktop
schuss guides.html   390 1900 guides-handy
schuss datenschutz.html 1000 1750 datenschutz
schuss admin.html   1440 2100 admin-desktop
schuss admin.html    390 2000 admin-handy
schuss verlauf.html 1440 2000 verlauf-desktop
schuss verlauf.html  390 2200 verlauf-handy

echo "== 6. Aufgeklappte Panels =="
# Anleitung, Welten und Sicherungen entstehen erst durch einen Klick; ein
# Screenshot der Seite zeigt sie nie.
cp "$HERE/scripts/ansehen_panels.js" "$OUT/panels.js"
docker run --rm -v "$OUT:/work" -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e NODE_PATH=/usr/src/app/node_modules \
  --entrypoint node zenika/alpine-chrome:with-puppeteer /work/panels.js || PANELS="BEFUND"

echo "== 7. Ueberlauf + Kontrast messen =="
# Der Screenshot zeigt eine Kante, aber nicht, ob dahinter noch etwas steht. Eine Leiste
# mit verstecktem Scrollbalken sieht abgeschnitten genauso aus wie zu Ende: genau dieser
# Unterschied war der Befund vom 2026-08-27 (Account/Abmelden lagen draussen).
cp "$HERE/scripts/ansehen_messen.js" "$OUT/messen.js"
docker run --rm -v "$OUT:/work" -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e NODE_PATH=/usr/src/app/node_modules \
  --entrypoint node zenika/alpine-chrome:with-puppeteer /work/messen.js \
  && MESSUNG="sauber" || MESSUNG="BEFUNDE (siehe oben)"

echo
echo "== fertig: $OUT  ·  Messung: $MESSUNG =="
[ -n "$BEHALTEN" ] && echo "   Instanz laeuft weiter: http://127.0.0.1:$PORT (pruefstand / $PASS)"
exit 0
