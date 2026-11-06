#!/bin/bash
# welten-schnappschuss.sh -- naechtliche Welt-Sicherung auf dem Spiele-VPS.
#
# Drei Schritte, die frueher auf zwei Hosts verteilt waren:
#   1. Der Arbiter tart je Spiel die Welt nach /var/backups/game-saves/ (feste Ziele,
#      mit Welt-Pruefung und Schrumpf-Schutz -- ein kaputter Stand verdraengt keinen guten).
#   2. Diese Tars gehen in den Ordner, aus dem die Clan-Seite die Welten-Downloads
#      ausliefert -- und zwar BEREINIGT, siehe unten.
#   3. Ein Pruefblick in die ausgelieferten Archive: bleibt dort ein Zugangsdatum uebrig?
# manual/ und die Toepfe bleiben aussen vor: das sind Sicherungen, keine Downloads.
#
# Warum ueberhaupt Tars, wo restic doch /home sichert: restic ist die Katastrophen-Kopie der
# LEBENDEN Welt -- roh und ungeprueft. Diese Archive sind zweierlei: das, was ein Mitglied von
# der Clan-Seite herunterladen kann, UND der einzige gepruefte Stand (Welt-Validierung +
# Schrumpf-Schutz: ein kaputtes Archiv verdraengt kein gutes).
#
# Korrektur 2026-08-27: hier stand, die Archive laegen "NICHT im restic-Pfadsatz". Das war
# falsch. Die QUELLE /var/backups/game-saves liegt tatsaechlich ausserhalb -- das ZIEL
# /opt/game-dashboard/worlds aber nicht, denn restic sichert /opt komplett. Die Archive gehen
# also sehr wohl off-site (gemessen ~350 MB, rund 167 MiB Zuwachs je Lauf).
# Das ist gewollt und wird bewusst bezahlt: der geprueft-konsistente Stand ist im Ernstfall
# mehr wert als die rohe Kopie. Aus demselben Grund laeuft dieser Schnappschuss seit dem
# 27.08. um 04:15 statt 05:20 -- vor restic (04:45) statt danach, sonst ginge immer nur der
# Stand vom Vortag off-site.
#
# Umbau 2026-10-17: Schritt 2 war ein nacktes rsync, das die Sicherung 1:1 zum Download
# machte. Gemessen standen damit in SIEBEN der neun ausgelieferten Archive Zugangsdaten im
# Klartext -- das gemeinsame Beitritts-Passwort aller Spiele und die RCON-/Admin-Passwoerter
# von Zomboid, Avorion und DayZ -- und ladbar waren sie fuer jedes freigeschaltete Mitglied
# (game-dashboard: require_verified, nicht require_admin). Sichern und Ausliefern sind
# seither zwei Dinge: 'arbiter.py --ausliefern' packt die Archive um, leert die in der
# Registry benannten Werte (save.geheim) und liest das Ergebnis zur Gegenprobe noch einmal
# ganz durch. Was es nicht sauber hinbekommt, wird NICHT ausgeliefert.
# ⚠️ Deshalb hier kein rsync mehr. Wer es zurueckbaut, baut das Leck zurueck.
set -euo pipefail
ARB=/opt/game-arbiter/arbiter.py
ZIEL=/opt/game-dashboard/worlds
LOG=$ZIEL/.sync.log
TEXTFILE=/var/lib/prometheus/node-exporter
PROM_SICHERUNG=$TEXTFILE/spiele-sicherung.prom
PROM_AUSLIEFERN=$TEXTFILE/spiele-ausliefern.prom

mkdir -p "$ZIEL"

python3 "$ARB" --live --snapshot-all || echo "$(date -Is) snapshot-all meldete Fehler -- Ausliefern laeuft trotzdem"

# rc>0 heisst: mindestens eine Welt wurde zurueckgehalten. Kein Abbruch -- die uebrigen
# sind davon unberuehrt, und die Meldezeile unten nennt die Zahl.
python3 "$ARB" --live --ausliefern || true

n=$(find "$ZIEL" -name "*.tar.gz" | wc -l)

# "ok: N Archive" allein war eine Zahl ohne Aussage: sie zaehlt DATEIEN und nicht ihr
# ALTER. Am 2026-10-17 lehnte der Schrumpf-Schutz den Minecraft-Stand ab (legitim, es war
# tags zuvor eine Welt geloescht worden), die alte Datei blieb liegen, die Zahl blieb bei 9
# -- und dieser Lauf meldete Erfolg. Die Fehlerzeile stand allein im Journal, das hier
# fluechtig ist. Der Zustand war dauerhaft: der Schutz vergleicht gegen das
# liegengebliebene Archiv und greift jede Nacht erneut.
# Die Zahlen kommen aus denselben Dateien, die der Arbiter gerade geschrieben hat
# (_sicherung_metrik_schreiben, _auslieferung_metrik_schreiben), damit Meldung und Metrik
# nicht auseinanderlaufen koennen.
abgelehnt=$(awk '/^spiele_sicherung_abgelehnt_gesamt /{print $2}' "$PROM_SICHERUNG" 2>/dev/null || true)
nicht_geliefert=$(awk '/^spiele_auslieferung_fehler_gesamt /{print $2}' "$PROM_AUSLIEFERN" 2>/dev/null || true)

# Fehlt eine der Metriken, wird NICHT "ok" gemeldet: eine nicht angekommene Messung ist
# kein Beleg fuer einen guten Zustand.
if [ -z "$abgelehnt" ] || [ -z "$nicht_geliefert" ]; then
  echo "$(date -Is) welten-schnappschuss UNKLAR: $n Archive, aber eine Metrik fehlt (Sicherung='${abgelehnt:-fehlt}', Auslieferung='${nicht_geliefert:-fehlt}')" | tee -a "$LOG"
elif [ "$abgelehnt" = "0" ] && [ "$nicht_geliefert" = "0" ]; then
  echo "$(date -Is) welten-schnappschuss ok: $n Archive, alle Staende uebernommen und bereinigt ausgeliefert" | tee -a "$LOG"
else
  echo "$(date -Is) welten-schnappschuss ACHTUNG: $n Archive, $abgelehnt Stand/Staende NICHT uebernommen (alter bleibt liegen und veraltet), $nicht_geliefert nicht ausgeliefert (Archiv zurueckgehalten) -- journalctl -u welten-schnappschuss" | tee -a "$LOG"
fi

# Schritt 3: die Gegenrichtung zum Scrubber. Er sucht nach WERTEN, die er selbst entfernt
# hat; diese Pruefung sucht nach SCHLUESSELNAMEN und findet damit das Zugangsdatum, das
# keine Regel kennt -- eine neue Datei aus einem Spiel-Update, ein ausgefuelltes
# DiscordToken, die Konfiguration eines Mods. rc 1 ist ein Fund, kein Laufzeitfehler.
python3 "$ARB" --pruefen-auslieferung >/dev/null || \
  echo "$(date -Is) welten-schnappschuss ACHTUNG: in einem ausgelieferten Archiv steht noch ein Zugangsdatum -- 'python3 $ARB --pruefen-auslieferung' nennt Datei und Zeile" | tee -a "$LOG"
