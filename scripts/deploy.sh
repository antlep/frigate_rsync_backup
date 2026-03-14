#!/usr/bin/env bash
# =============================================================================
# deploy.sh  –  Déploie la branche reborn sur le LXC
#
# Usage:
#   ./scripts/deploy.sh                     # déploie depuis le répertoire courant
#   ./scripts/deploy.sh --branch reborn     # force une branche
#   ./scripts/deploy.sh --dry-run           # simulate sans rien toucher
#
# Pré-requis sur le LXC :
#   - docker + docker compose
#   - git remote configuré
#   - config/rclone.conf et config/config.yaml présents (non versionnés)
# =============================================================================
set -euo pipefail

# --------------------------------------------------------------------------- #
# Config – adapte ces variables à ton LXC                                     #
# --------------------------------------------------------------------------- #

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${BRANCH:-reborn}"
NEW_SERVICE="frigate-gdrive-sync"
NEW_COMPOSE="$REPO_DIR/docker-compose.yml"

# Ancien système (stop avant de démarrer le nouveau)
# Adapte cette section à ta setup actuelle :
#   - Si c'est un service systemd :  OLD_STOP_CMD="systemctl stop watchdog-frigate"
#   - Si c'est un script lancé via screen/tmux : OLD_STOP_CMD="pkill -f watchdog_frigate.sh"
#   - Si c'est un docker compose existant :      OLD_STOP_CMD="docker compose -f /chemin/ancien/docker-compose.yml down"
OLD_STOP_CMD="${OLD_STOP_CMD:-systemctl stop watchdog-frigate 2>/dev/null || true}"
OLD_START_CMD="${OLD_START_CMD:-systemctl start watchdog-frigate 2>/dev/null || true}"

DRY_RUN=false

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()     { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy]${NC} $*"; }
error()   { echo -e "${RED}[deploy]${NC} $*" >&2; }
run()     { if $DRY_RUN; then echo "  [DRY] $*"; else eval "$*"; fi; }

require() {
  for cmd in "$@"; do
    command -v "$cmd" &>/dev/null || { error "Commande manquante : $cmd"; exit 1; }
  done
}

# --------------------------------------------------------------------------- #
# Parsing arguments                                                            #
# --------------------------------------------------------------------------- #

while [[ $# -gt 0 ]]; do
  case $1 in
    --branch)  BRANCH="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    *)         error "Argument inconnu : $1"; exit 1 ;;
  esac
done

$DRY_RUN && warn "Mode DRY-RUN – aucune modification ne sera appliquée"

# --------------------------------------------------------------------------- #
# Pré-checks                                                                   #
# --------------------------------------------------------------------------- #

log "Vérification des pré-requis…"
require docker git

[[ -f "$REPO_DIR/config/rclone.conf" ]]   || { error "config/rclone.conf manquant !"; exit 1; }
[[ -f "$REPO_DIR/config/config.yaml" ]]   || { error "config/config.yaml manquant !"; exit 1; }
[[ -f "$NEW_COMPOSE" ]]                   || { error "docker-compose.yml introuvable"; exit 1; }

# --------------------------------------------------------------------------- #
# Sauvegarde de l'état pour rollback                                          #
# --------------------------------------------------------------------------- #

ROLLBACK_FILE="$REPO_DIR/.deploy_rollback"
CURRENT_COMMIT=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
echo "$CURRENT_COMMIT" > "$ROLLBACK_FILE"
log "Commit de rollback enregistré : $CURRENT_COMMIT"

# --------------------------------------------------------------------------- #
# Rollback automatique (appelé sur erreur)                                    #
# --------------------------------------------------------------------------- #

_rollback() {
  error "Échec détecté – rollback en cours…"
  # Arrêter le nouveau container s'il tourne
  docker compose -f "$NEW_COMPOSE" down 2>/dev/null || true
  # Relancer l'ancien système
  warn "Relance de l'ancien système : $OLD_START_CMD"
  eval "$OLD_START_CMD" || true
  error "Rollback terminé. Vérifier les logs avec : docker compose -f $NEW_COMPOSE logs"
  exit 1
}
trap _rollback ERR

# --------------------------------------------------------------------------- #
# 1. Git pull                                                                  #
# --------------------------------------------------------------------------- #

log "Git : fetch + checkout branche '$BRANCH'…"
run "git -C '$REPO_DIR' fetch origin"
run "git -C '$REPO_DIR' checkout '$BRANCH'"
run "git -C '$REPO_DIR' pull origin '$BRANCH'"

NEW_COMMIT=$(git -C "$REPO_DIR" rev-parse HEAD)
log "HEAD → $NEW_COMMIT"

# --------------------------------------------------------------------------- #
# 2. Build image                                                               #
# --------------------------------------------------------------------------- #

log "Build de l'image Docker…"
run "docker compose -f '$NEW_COMPOSE' build --no-cache"

# --------------------------------------------------------------------------- #
# 3. Stop ancien système                                                       #
# --------------------------------------------------------------------------- #

log "Arrêt de l'ancien système : $OLD_STOP_CMD"
run "$OLD_STOP_CMD"
sleep 2

# --------------------------------------------------------------------------- #
# 4. Démarrage du nouveau                                                      #
# --------------------------------------------------------------------------- #

log "Démarrage du nouveau container…"
run "docker compose -f '$NEW_COMPOSE' up -d"

# --------------------------------------------------------------------------- #
# 5. Healthcheck (attend max 60s)                                              #
# --------------------------------------------------------------------------- #

if ! $DRY_RUN; then
  log "Attente du healthcheck (/health)…"
  HEALTH_PORT=$(grep -E '^\s*- "[0-9]+:8080"' "$NEW_COMPOSE" | grep -oE '[0-9]+:' | head -1 | tr -d ':')
  HEALTH_PORT="${HEALTH_PORT:-8080}"

  for i in $(seq 1 12); do
    sleep 5
    STATUS=$(curl -sf "http://localhost:${HEALTH_PORT}/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "down")
    log "Health ($i/12) : $STATUS"
    if [[ "$STATUS" == "ok" ]]; then
      break
    fi
    if [[ $i -eq 12 ]]; then
      error "Container non healthy après 60s"
      exit 1
    fi
  done
fi

# --------------------------------------------------------------------------- #
# Succès                                                                       #
# --------------------------------------------------------------------------- #

trap - ERR  # désactiver le trap rollback
log "✓ Déploiement réussi ! (commit $NEW_COMMIT)"
log "  Logs : docker compose -f $NEW_COMPOSE logs -f"
log "  Rollback manuel : ./scripts/rollback.sh"
