#!/bin/bash
# welten-schnappschuss.sh -- naechtliche Welt-Sicherung auf dem Spiele-VPS.
#
# Zwei Schritte, die frueher auf zwei Hosts verteilt waren:
#   1. Der Arbiter tart je Spiel die Welt nach /var/backups/game-saves/ (feste Ziele,
#      mit Welt-Pruefung und Schrumpf-Schutz -- ein kaputter Stand verdraengt keinen guten).
#   2. Diese Tars werden in den Ordner gespiegelt, aus dem die Clan-Seite die
#      Welten-Downloads ausliefert. Auf .18 machte das ein rsync von host aus; hier
#      liegen Quelle und Ziel auf demselben Wirt.
# manual/ bleibt aussen vor: das sind Admin-Schnappschuesse, keine Nightlies.
#
# Warum ueberhaupt Tars, wo restic doch /home sichert: restic ist die Katastrophen-Kopie der
# LEBENDEN Welt -- roh und ungeprueft. Diese Archive sind zweierlei: das, was ein Mitglied von
# der Clan-Seite herunterladen kann, UND der einzige gepruefte Stand (Welt-Validierung +
# Schrumpf-Schutz: ein kaputtes Archiv verdraengt kein gutes).
#
# ★ Korrektur 2026-08-27: hier stand, die Archive laegen "NICHT im restic-Pfadsatz". Das war
# falsch. Die QUELLE /var/backups/game-saves liegt tatsaechlich ausserhalb -- das ZIEL
# /opt/game-dashboard/worlds aber nicht, denn restic sichert /opt komplett. Die Archive gehen
# also sehr wohl off-site (gemessen ~350 MB, rund 167 MiB Zuwachs je Lauf).
# Das ist gewollt und wird bewusst bezahlt: der geprueft-konsistente Stand ist im Ernstfall
# mehr wert als die rohe Kopie. Aus demselben Grund laeuft dieser Schnappschuss seit dem
# 27.08. um 04:15 statt 05:20 -- vor restic (04:45) statt danach, sonst ginge immer nur der
# Stand vom Vortag off-site.
set -euo pipefail
ARB=/opt/game-arbiter/arbiter.py
QUELLE=/var/backups/game-saves
ZIEL=/opt/game-dashboard/worlds
LOG=$ZIEL/.sync.log

python3 "$ARB" --live --snapshot-all || echo "$(date -Is) snapshot-all meldete Fehler -- Spiegeln laeuft trotzdem"

mkdir -p "$ZIEL"
# --filter="P .env" ist hier Pflicht und nicht Zierde: --exclude schuetzt bei --delete NICHT.
rsync -a --prune-empty-dirs \
  --filter="P .env" \
  --exclude="manual/" \
  --include="*/" --include="*.tar.gz" --exclude="*" \
  --delete \
  "$QUELLE/" "$ZIEL/"

chown -R valheim:valheim "$ZIEL" 2>/dev/null || true
chmod -R a+rX "$ZIEL" 2>/dev/null || true
n=$(find "$ZIEL" -name "*.tar.gz" | wc -l)
echo "$(date -Is) welten-schnappschuss ok: $n Archive" | tee -a "$LOG"
