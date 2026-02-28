#!/bin/bash

start_time=$(date +%s)

# --- CONFIGURATION ---
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root
export RCLONE_CONFIG_READONLY=true

FRIGATE_URL="http://localhost:5000"
SOURCE_TEMP="/root/media/temp_export"
if [ -d "/app" ]; then
    REGISTRY="/app/synced_events.txt"
else
    REGISTRY="$(dirname "$0")/synced_events.txt"
fi
RCLONE_CONF="/root/.config/rclone/rclone.conf"

DATE_JOUR=$(date +%Y-%m-%d)
LOG_DIR="/root/log_sauvegarde"
LOG_FILE="$LOG_DIR/frigate_sync_$DATE_JOUR.log"

DEST_ROOT="gdrive:Frigate_Backups"
DEST_JOUR="$DEST_ROOT/$DATE_JOUR"

MQTT_HOST="${MQTT_BROKER}"
MQTT_USER="${MQTT_USER}"
MQTT_PASS="${MQTT_PASSWORD}"
MQTT_TOPIC="${MQTT_TOPIC}"

RCLONE_OPTS="--config $RCLONE_CONF"

mkdir -p "$LOG_DIR"
mkdir -p "$SOURCE_TEMP"
touch "$REGISTRY"

log_message() {
    local message="$1"
    local color_code="$2"
    echo "$(date '+%H:%M:%S') $message" >> "$LOG_FILE"
    echo -e "\e[${color_code:-0}m$(date '+%H:%M:%S') $message\e[0m"
}

log_message "🚀 DÉBUT EXPORT (Mode Simple - Noms Logiques)" "36"

EVENTS_JSON=$(curl -s "$FRIGATE_URL/api/events?limit=10&has_clip=1&review=1")

SUCCESS_COUNT=0
SKIP_COUNT=0
ERROR_COUNT=0

while read -r ROW; do
    [ -z "$ROW" ] || [ "$ROW" == "null" ] && continue
    
    ID=$(echo "$ROW" | cut -d'|' -f1)
    CAMERA=$(echo "$ROW" | cut -d'|' -f2)
    START=$(echo "$ROW" | cut -d'|' -f3 | cut -d'.' -f1)
    END=$(echo "$ROW" | cut -d'|' -f4 | cut -d'.' -f1)

    if grep -q "$ID" "$REGISTRY"; then
        ((SKIP_COUNT++))
        continue
    fi

    if [ "$END" == "null" ] || [ -z "$END" ]; then
        log_message "⚠️ Événement $ID sans fin. Utilisation de l'heure actuelle." "33"
        END=$(date +%s)
    else
        END=$((END + 10))
    fi

    UNIX_TIME=$(echo "$ID" | cut -d'.' -f1)
    SUFFIX=$(echo "$ID" | cut -d'-' -f2)
    HUMAN_TIME=$(date -d "@$UNIX_TIME" +%H%M 2>/dev/null || echo "event")
    FOLDER_NAME="${HUMAN_TIME}_${SUFFIX}"
    FILE_STAMP=$(date -d "@$UNIX_TIME" +%Y%m%d_%H%M%S)

    EVENT_DIR_LOCAL="$SOURCE_TEMP/$CAMERA/$FOLDER_NAME"
    EVENT_DIR_REMOTE="$DEST_JOUR/$CAMERA/$FOLDER_NAME"
    mkdir -p "$EVENT_DIR_LOCAL"
    
    ATTEMPT=1
    DOWNLOADED=false
    
    # Noms de fichiers propres
    FILE_MP4="${CAMERA}_${FILE_STAMP}.mp4"
    FILE_JPG="${CAMERA}_${FILE_STAMP}.jpg"
    FILE_JSON="${CAMERA}_${FILE_STAMP}.json"

    while [ $ATTEMPT -le 6 ]; do
        curl -s -f -o "$EVENT_DIR_LOCAL/$FILE_MP4" "$FRIGATE_URL/api/$CAMERA/start/$START/end/$END/clip.mp4"
        if [ -s "$EVENT_DIR_LOCAL/$FILE_MP4" ] && [ $(stat -c%s "$EVENT_DIR_LOCAL/$FILE_MP4") -gt 102400 ]; then
            DOWNLOADED=true
            break
        fi
        log_message "⏳ Clip $ID non prêt ($ATTEMPT/6)..." "33"
        ((ATTEMPT++))
        sleep 10
    done

    if [ "$DOWNLOADED" = true ]; then
        # 1. Téléchargement du JSON d'origine
        curl -s -f -o "$EVENT_DIR_LOCAL/$FILE_JSON" "$FRIGATE_URL/api/events/$ID"

        # 2. Téléchargement du snapshot Frigate (avec BBox et qualité forcée)
        curl -s -f -o "$EVENT_DIR_LOCAL/$FILE_JPG" "$FRIGATE_URL/api/events/$ID/snapshot.jpg?bbox=1&quality=100"

        # 3. Envoi vers GDrive
        if rclone move "$EVENT_DIR_LOCAL" "$EVENT_DIR_REMOTE" $RCLONE_OPTS --quiet; then
            echo "$ID" >> "$REGISTRY"
            ((SUCCESS_COUNT++))
            log_message "✅ Envoyé: $CAMERA ($FILE_STAMP)" "32"
        else
            ((ERROR_COUNT++))
            log_message "❌ Erreur Rclone sur $ID" "31"
        fi
    else
        log_message "⚠️ Clip $ID ignoré (incomplet)." "31"
        rm -rf "$EVENT_DIR_LOCAL"
    fi

done < <(echo "$EVENTS_JSON" | jq -r '.[] | "\(.id)|\(.camera)|\(.start_time)|\(.end_time)"' 2>/dev/null)

# --- NETTOYAGE GDRIVE (Conservation de 7 jours) ---
LIMIT_TS=$(( $(date +%s) - (7 * 86400) ))
DATE_LIMITE=$(date -d "@$LIMIT_TS" +%Y-%m-%d)
log_message "🧹 Nettoyage GDrive (Avant ou égal au $DATE_LIMITE)..." "35"

rclone lsf "$DEST_ROOT" $RCLONE_OPTS --dirs-only | while read -r FOLDER; do
    FOLDER_CLEAN=${FOLDER%/}
    if [[ -n "$FOLDER_CLEAN" ]] && [[ "$FOLDER_CLEAN" < "$DATE_LIMITE" || "$FOLDER_CLEAN" == "$DATE_LIMITE" ]]; then
        log_message "🗑️ Purge de $FOLDER_CLEAN" "33"
        rclone purge "$DEST_ROOT/$FOLDER_CLEAN" $RCLONE_OPTS --quiet
    fi
done

end_time=$(date +%s)
duration=$((end_time - start_time))

# --- MQTT STATS ---
STATUS="💤 Déjà synchronisé"
LOG_DETAILS="Aucun nouvel événement"

if [ $SUCCESS_COUNT -gt 0 ] || [ $ERROR_COUNT -gt 0 ]; then
    [ $SUCCESS_COUNT -gt 0 ] && STATUS="✅ $SUCCESS_COUNT clips envoyés"
    [ $ERROR_COUNT -gt 0 ] && STATUS="⚠️ Erreur sur $ERROR_COUNT clip(s)"
    LOG_DETAILS="Sync: $SUCCESS_COUNT | Skip: $SKIP_COUNT"
fi

DRIVE_SIZE_BYTES=$(rclone size "$DEST_ROOT" $RCLONE_OPTS --json 2>/dev/null | jq '.bytes' || echo "0")
LAST_SYNC=$(date '+%d/%m %H:%M')

# Construction du JSON pour MQTT
MSG_PAYLOAD=$(jq -n \
    --arg st "$STATUS" \
    --arg sz "$DRIVE_SIZE_BYTES" \
    --arg ls "$LAST_SYNC" \
    --arg lg "$LOG_DETAILS" \
    --argjson du "$duration" \
    '{status: $st, size: $sz, last_sync: $ls, log: $lg, duration_seconds: $du}')

mosquitto_pub -h "$MQTT_HOST" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$MQTT_TOPIC" -m "$MSG_PAYLOAD" -q 1

if [ -f "$REGISTRY" ]; then
    # On garde les 500 derniers IDs pour garantir la rapidité du grep
    tail -n 500 "$REGISTRY" > "$REGISTRY.tmp" && mv "$REGISTRY.tmp" "$REGISTRY"
    log_message "🧹 Historique local limité aux 500 derniers événements." "35"
fi
log_message "🏁 Fin." "32"