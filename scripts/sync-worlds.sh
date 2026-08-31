#!/usr/bin/env bash
# sync-worlds.sh — spiegelt die täglichen Welt-Snapshots von Node .18
# (/var/backups/game-saves/) nach ./worlds/. Das ist die Quelle für die
# Welten-Downloads im game-dashboard (nur für verifizierte Mitglieder).
#
# Layout seit dem Per-Welt-Umbau:
#   <game>.tar.gz          Single-World-Games
#   <game>/<welt>.tar.gz   Multi-World-Games (terraria/zomboid), ein Tar je Welt
# manual/ (Admin-Snapshots) wird bewusst NICHT gespiegelt — die laufen live über
# die wake-bridge. --delete räumt gelöschte Welten auch hier ab; manuelle
# Alt-Dateien (zomboid-vor-*.tar.gz) schützt der manual-Exclude nicht, daher
# --delete nur innerhalb der Game-Unterverzeichnisse (filter-Regeln unten).
#
# Läuft als host via id_flux1 (root@.18 ist autorisiert). Der Container liest
# ./worlds read-only. Per Cron/Timer täglich ~06:00 (nach dem .18-Snapshot 05:20).
set -euo pipefail

DEST="/home/user/docker/game-dashboard/worlds"
KEY="/home/user/.ssh/id_flux1"
SRC="root@192.0.2.10:/var/backups/game-saves/"
LOG="/home/user/docker/game-dashboard/worlds/.sync.log"

mkdir -p "$DEST"
rsync -a --timeout=120 --prune-empty-dirs \
  -e "ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10" \
  --exclude='manual/' \
  --include='*/' --include='*.tar.gz' --exclude='*' \
  --delete --filter='P zomboid-vor-*.tar.gz' \
  "$SRC" "$DEST/"

chmod -R a+rX "$DEST" 2>/dev/null || true
n=$(find "$DEST" -name '*.tar.gz' | wc -l)
echo "$(date -Is) sync-worlds ok: $n Snapshots" | tee -a "$LOG"
