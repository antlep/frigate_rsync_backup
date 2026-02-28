#!/bin/bash

MQTT_HOST="${MQTT_BROKER}"
MQTT_USER="${MQTT_USER}"
MQTT_PASS="${MQTT_PASSWORD}"
TOPIC="frigate/events"

echo "🚀 Démarrage du Watchdog de sauvegarde (mode robuste)..."

# --- FONCTION DE BALAYAGE PÉRIODIQUE ---
# Cette fonction tourne en arrière-plan et lance le backup toutes les 10 min
periodic_check() {
    while true; do
        sleep 600 # 10 minutes
        echo "$(date '+%H:%M:%S') - 🕒 Balayage périodique des événements reportés..."
        /bin/bash /app/frigate_backup.sh >/dev/null 2>&1
    done
}

# Lancement du balayage périodique en arrière-plan
periodic_check &

# --- BOUCLE MQTT PRINCIPALE ---
mosquitto_sub -h "$MQTT_HOST" -u "$MQTT_USER" -P "$MQTT_PASS" -t "$TOPIC" | while read -r PAYLOAD
do
    if echo "$PAYLOAD" | jq -e . >/dev/null 2>&1; then
        EVENT_TYPE=$(echo "$PAYLOAD" | jq -r '.type')

        if [ "$EVENT_TYPE" == "end" ]; then
            ID=$(echo "$PAYLOAD" | jq -r '.after.id')
            CAMERA=$(echo "$PAYLOAD" | jq -r '.after.camera')
            
            echo "$(date '+%H:%M:%S') - 🎥 Événement terminé ($CAMERA : $ID). Vérification..."
            sleep 10 # Attente pour s'assurer que les fichiers sont bien écrits
            /bin/bash /app/frigate_backup.sh 2>&1
        fi
    fi
done