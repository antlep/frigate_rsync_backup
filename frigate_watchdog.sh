#!/bin/bash

MQTT_HOST="${MQTT_BROKER}"
MQTT_USER="${MQTT_USER}"
MQTT_PASS="${MQTT_PASSWORD}"
# On permet aussi d'externaliser le topic si besoin
TOPIC="${MQTT_TOPIC_EVENTS:-frigate/events}"

# --- NOUVEAU : Paramètre de boucle externalisé ---
# Utilise WATCHDOG_INTERVAL s'il existe, sinon 600 secondes (10 min) par défaut
WATCHDOG_SLEEP="${WATCHDOG_INTERVAL:-600}"

echo "🚀 Démarrage du Watchdog de sauvegarde (mode robuste)..."
echo "⏱️ Intervalle de sécurité : ${WATCHDOG_SLEEP} secondes."

# --- FONCTION DE BALAYAGE PÉRIODIQUE ---
periodic_check() {
    while true; do
        # Utilisation de la variable ajustée
        sleep "$WATCHDOG_SLEEP"
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
            sleep 10 
            /bin/bash /app/frigate_backup.sh 2>&1
        fi
    fi
done