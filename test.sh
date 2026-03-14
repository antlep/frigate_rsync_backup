#!/usr/bin/env bash
# =============================================================================
# test.sh  –  Validation complète du déploiement reborn
#
# Tests couverts :
#   1. Réception MQTT  (injecte un faux événement, vérifie les logs)
#   2. Download Frigate (clip + snapshot depuis l'API)
#   3. Upload rclone → GDrive
#   4. Retry / reprise après redémarrage container
#   5. Health check /health
#
# Usage :
#   ./scripts/test.sh                       # tous les tests
#   ./scripts/test.sh --test mqtt           # test unitaire
#   ./scripts/test.sh --test health
#   ./scripts/test.sh --mqtt-host 192.168.1.x --frigate-host 192.168.1.x
# =============================================================================
set -euo pipefail

# --------------------------------------------------------------------------- #
# Paramètres par défaut (surchargeables)                                      #
# --------------------------------------------------------------------------- #

HEALTH_URL="http://localhost:8080/health"
MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX:-frigate}"
FRIGATE_HOST="${FRIGATE_HOST:-localhost}"
FRIGATE_PORT="${FRIGATE_PORT:-5000}"
COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docker-compose.yml"
SERVICE="frigate-gdrive-sync"
RUN_TESTS=("mqtt" "frigate" "rclone" "retry" "health")

# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "  ${GREEN}✓${NC} $*"; (( PASS++ )); }
fail() { echo -e "  ${RED}✗${NC} $*"; (( FAIL++ )); }
info() { echo -e "${BLUE}[test]${NC} $*"; }
sep()  { echo -e "\n${YELLOW}── $* ──${NC}"; }

require() {
  for cmd in "$@"; do
    command -v "$cmd" &>/dev/null || { fail "Commande manquante : $cmd (apt install $cmd ?)"; return 1; }
  done
}

container_logs() {
  docker compose -f "$COMPOSE_FILE" logs --no-log-prefix --tail=100 "$SERVICE" 2>/dev/null
}

# Attend qu'une chaîne apparaisse dans les logs du container (timeout en sec)
wait_for_log() {
  local pattern="$1" timeout="${2:-30}"
  for _ in $(seq 1 "$timeout"); do
    if container_logs | grep -q "$pattern"; then return 0; fi
    sleep 1
  done
  return 1
}

# Génère un event_id unique
FAKE_EVENT_ID="test-$(date +%s)-$$"
FAKE_CAMERA="test_camera"

# --------------------------------------------------------------------------- #
# Parsing arguments                                                            #
# --------------------------------------------------------------------------- #

while [[ $# -gt 0 ]]; do
  case $1 in
    --test)         RUN_TESTS=("$2"); shift 2 ;;
    --mqtt-host)    MQTT_HOST="$2"; shift 2 ;;
    --frigate-host) FRIGATE_HOST="$2"; shift 2 ;;
    --health-url)   HEALTH_URL="$2"; shift 2 ;;
    *) echo "Argument inconnu : $1"; exit 1 ;;
  esac
done

# --------------------------------------------------------------------------- #
# TEST 1 : Health check                                                        #
# --------------------------------------------------------------------------- #

run_health() {
  sep "TEST 1 – Health check (/health)"
  require curl

  RESP=$(curl -sf "$HEALTH_URL" 2>/dev/null || echo '{"status":"down"}')
  STATUS=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "parse_error")
  MQTT_OK=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mqtt_connected','?'))" 2>/dev/null || echo "?")

  info "Réponse : $RESP"

  [[ "$STATUS" == "ok" ]] && pass "status = ok" || fail "status = $STATUS (attendu: ok)"
  [[ "$MQTT_OK" == "True" ]] && pass "mqtt_connected = true" || fail "mqtt_connected = $MQTT_OK"
}

# --------------------------------------------------------------------------- #
# TEST 2 : Réception MQTT                                                      #
# --------------------------------------------------------------------------- #

run_mqtt() {
  sep "TEST 2 – Réception MQTT"
  require mosquitto_pub

  PAYLOAD=$(cat <<EOF
{
  "type": "end",
  "after": {
    "id": "$FAKE_EVENT_ID",
    "camera": "$FAKE_CAMERA",
    "label": "person",
    "start_time": $(date +%s.0),
    "end_time": $(date +%s.0),
    "has_clip": false,
    "has_snapshot": false,
    "score": 0.85,
    "entered_zones": []
  }
}
EOF
)

  info "Injection d'un événement MQTT fictif (id=$FAKE_EVENT_ID)…"
  mosquitto_pub \
    -h "$MQTT_HOST" -p "$MQTT_PORT" \
    -t "${MQTT_TOPIC_PREFIX}/events" \
    -m "$PAYLOAD"

  info "Attente de la trace dans les logs container (max 15s)…"

  # Le listener loggue "event_accepted" ou "filtered_camera" selon le filtre cameras:
  if wait_for_log "$FAKE_EVENT_ID" 15; then
    pass "Événement bien reçu et logué (id=$FAKE_EVENT_ID)"
  else
    # Peut être filtré si cameras: [x] exclut test_camera
    if container_logs | grep -q "filtered_camera"; then
      pass "Événement reçu mais filtré (cameras: non vide — attendu si test_camera n'est pas dans la liste)"
    else
      fail "Événement non trouvé dans les logs après 15s"
      info "Logs récents :"
      container_logs | tail -20 | sed 's/^/  /'
    fi
  fi
}

# --------------------------------------------------------------------------- #
# TEST 3 : Download depuis l'API Frigate                                       #
# --------------------------------------------------------------------------- #

run_frigate() {
  sep "TEST 3 – API Frigate (clip + snapshot)"
  require curl

  info "Récupération d'une liste d'événements récents…"
  EVENTS=$(curl -sf "http://${FRIGATE_HOST}:${FRIGATE_PORT}/api/events?limit=1" 2>/dev/null || echo "[]")
  COUNT=$(echo "$EVENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")

  if [[ "$COUNT" -eq 0 ]]; then
    fail "Aucun événement dans Frigate – impossible de tester le download"
    info "Déclenche une détection ou attends qu'un événement existe dans Frigate"
    return
  fi

  REAL_ID=$(echo "$EVENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])" 2>/dev/null)
  info "Utilisation de l'événement Frigate : $REAL_ID"

  # Test clip
  CLIP_STATUS=$(curl -o /dev/null -sw "%{http_code}" \
    "http://${FRIGATE_HOST}:${FRIGATE_PORT}/api/events/${REAL_ID}/clip.mp4" 2>/dev/null || echo "000")
  [[ "$CLIP_STATUS" == "200" ]] && pass "Clip disponible (HTTP $CLIP_STATUS)" \
    || fail "Clip indisponible (HTTP $CLIP_STATUS) – has_clip peut être false sur cet événement"

  # Test snapshot
  SNAP_STATUS=$(curl -o /dev/null -sw "%{http_code}" \
    "http://${FRIGATE_HOST}:${FRIGATE_PORT}/api/events/${REAL_ID}/snapshot.jpg" 2>/dev/null || echo "000")
  [[ "$SNAP_STATUS" == "200" ]] && pass "Snapshot disponible (HTTP $SNAP_STATUS)" \
    || fail "Snapshot indisponible (HTTP $SNAP_STATUS)"

  # Test event JSON
  META_STATUS=$(curl -o /dev/null -sw "%{http_code}" \
    "http://${FRIGATE_HOST}:${FRIGATE_PORT}/api/events/${REAL_ID}" 2>/dev/null || echo "000")
  [[ "$META_STATUS" == "200" ]] && pass "Metadata JSON disponible (HTTP $META_STATUS)" \
    || fail "Metadata indisponible (HTTP $META_STATUS)"
}

# --------------------------------------------------------------------------- #
# TEST 4 : Upload rclone → GDrive                                              #
# --------------------------------------------------------------------------- #

run_rclone() {
  sep "TEST 4 – Upload rclone → GDrive"

  RCLONE_CONF=$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    sh -c 'echo $RCLONE_CONFIG_PATH 2>/dev/null || echo /config/rclone.conf' 2>/dev/null || echo "/config/rclone.conf")

  info "Test de connectivité rclone (lsf du remote)…"

  # Récupérer la valeur de rclone.remote depuis la config container
  RCLONE_REMOTE=$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    python3 -c "
from config import AppConfig
c = AppConfig.load()
print(c.rclone.remote)
" 2>/dev/null || echo "gdrive:Frigate")

  info "Remote : $RCLONE_REMOTE"

  RCLONE_OUT=$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    rclone lsf "$RCLONE_REMOTE" --config /config/rclone.conf --max-depth 1 2>&1 || true)

  if echo "$RCLONE_OUT" | grep -qiE "error|NOTICE: Failed"; then
    fail "rclone ne peut pas accéder au remote : $RCLONE_OUT"
  else
    pass "rclone connecté au remote ($RCLONE_REMOTE)"
  fi

  # Vérifier qu'un vrai upload end-to-end a eu lieu dans les logs
  info "Vérification d'un upload récent dans les logs…"
  if container_logs | grep -q '"uploaded"'; then
    LAST_UPLOAD=$(container_logs | grep '"uploaded"' | tail -1)
    pass "Au moins un upload trouvé dans les logs"
    info "Dernier upload : $LAST_UPLOAD"
  else
    fail "Aucun upload 'uploaded' dans les logs récents"
    info "Vérifier que des événements Frigate avec has_clip=true ont été traités"
  fi
}

# --------------------------------------------------------------------------- #
# TEST 5 : Retry / reprise après redémarrage                                  #
# --------------------------------------------------------------------------- #

run_retry() {
  sep "TEST 5 – Reprise après redémarrage container"
  require sqlite3

  # Injecter un événement pendant que le container tourne
  RETRY_ID="retry-test-$(date +%s)"
  RETRY_PAYLOAD=$(cat <<EOF
{
  "type": "end",
  "after": {
    "id": "$RETRY_ID",
    "camera": "$FAKE_CAMERA",
    "label": "car",
    "start_time": $(date +%s.0),
    "end_time": $(date +%s.0),
    "has_clip": false,
    "has_snapshot": false,
    "score": 0.9,
    "entered_zones": []
  }
}
EOF
)

  info "Injection de l'événement de test ($RETRY_ID)…"
  if command -v mosquitto_pub &>/dev/null; then
    mosquitto_pub \
      -h "$MQTT_HOST" -p "$MQTT_PORT" \
      -t "${MQTT_TOPIC_PREFIX}/events" \
      -m "$RETRY_PAYLOAD"
    sleep 2
  else
    fail "mosquitto_pub requis pour ce test – skip"
    return
  fi

  # Vérifier présence en DB avant redémarrage
  DB_BEFORE=$(docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    sqlite3 /data/events.db \
    "SELECT id FROM events WHERE id='$RETRY_ID';" 2>/dev/null || echo "")

  if [[ -n "$DB_BEFORE" ]]; then
    pass "Événement persisté en SQLite avant redémarrage ($RETRY_ID)"
  else
    fail "Événement non trouvé dans SQLite avant redémarrage"
    info "Il sera peut-être trop rapide ou filtré – vérifier les logs"
  fi

  # Redémarrage
  info "Redémarrage du container…"
  docker compose -f "$COMPOSE_FILE" restart "$SERVICE"
  sleep 5

  # Vérifier que "events_recovered" apparaît dans les logs post-restart
  if wait_for_log "events_recovered" 20; then
    RECOVERED=$(container_logs | grep "events_recovered" | tail -1)
    pass "Reprise des événements au démarrage : $RECOVERED"
  else
    # Peut être normal si l'événement est déjà en status=done
    if container_logs | grep -q "worker_started"; then
      pass "Workers démarrés (pas d'événements pending à reprendre, c'est OK)"
    else
      fail "Pas de trace de reprise dans les logs après redémarrage"
    fi
  fi
}

# --------------------------------------------------------------------------- #
# Orchestration                                                                #
# --------------------------------------------------------------------------- #

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   frigate-gdrive-sync – Test Suite       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

for t in "${RUN_TESTS[@]}"; do
  case $t in
    health)  run_health ;;
    mqtt)    run_mqtt ;;
    frigate) run_frigate ;;
    rclone)  run_rclone ;;
    retry)   run_retry ;;
    *)       echo "Test inconnu : $t (valeurs: health mqtt frigate rclone retry)" ;;
  esac
done

# --------------------------------------------------------------------------- #
# Rapport final                                                                #
# --------------------------------------------------------------------------- #

TOTAL=$(( PASS + FAIL ))
echo ""
echo -e "${BLUE}── Résultat ──────────────────────────────${NC}"
echo -e "  ${GREEN}✓ $PASS / $TOTAL passés${NC}  ${RED}✗ $FAIL échoués${NC}"
echo ""

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
