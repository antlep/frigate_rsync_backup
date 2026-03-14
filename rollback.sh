#!/usr/bin/env bash
# =============================================================================
# rollback.sh  –  Revient à l'état avant le dernier déploiement
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NEW_COMPOSE="$REPO_DIR/docker-compose.yml"
ROLLBACK_FILE="$REPO_DIR/.deploy_rollback"

OLD_START_CMD="${OLD_START_CMD:-systemctl start watchdog-frigate 2>/dev/null || true}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[rollback]${NC} $*"; }
warn() { echo -e "${YELLOW}[rollback]${NC} $*"; }
error(){ echo -e "${RED}[rollback]${NC} $*" >&2; }

# --------------------------------------------------------------------------- #

log "Arrêt du nouveau container…"
docker compose -f "$NEW_COMPOSE" down 2>/dev/null || true

if [[ -f "$ROLLBACK_FILE" ]]; then
  PREV_COMMIT=$(cat "$ROLLBACK_FILE")
  log "Retour au commit : $PREV_COMMIT"
  git -C "$REPO_DIR" checkout "$PREV_COMMIT" -- . 2>/dev/null || warn "Impossible de checkout $PREV_COMMIT"
else
  warn "Pas de fichier de rollback trouvé (.deploy_rollback)"
fi

log "Relance de l'ancien système : $OLD_START_CMD"
eval "$OLD_START_CMD"

log "✓ Rollback terminé"
