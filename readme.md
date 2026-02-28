# Frigate Event Backup to Google Drive (rclone)

![Docker](https://img.shields.io/badge/Docker-Supported-blue)

[Français](#-français) | [English](#-english)

---

<a name="français"></a>
## 🇫🇷 Français

Ce projet automatise la sauvegarde des clips de **Frigate NVR** vers un stockage cloud (Google Drive) via **rclone**.

### ✨ Points Forts
* **Architecture réactive** : Le script `frigate_watchdog.sh` écoute les événements MQTT de Frigate pour agir instantanément dès qu'une vidéo est prête.
* **Double Sécurité** : Un balayage automatique est effectué toutes les 10 minutes pour ne rater aucun clip, même en cas de coupure MQTT.
* **Filtrage Intelligent** : Seuls les événements validés avec clips (`has_clip=1`) et présents dans la "Review" Frigate sont sauvegardés.
* **Statistiques MQTT** : Envoie le statut de la sauvegarde et l'espace disque utilisé vers Home Assistant.

### 🛠 Configuration
1. Créez un fichier `.env` à partir du modèle `.env.example`.
2. Montez votre fichier `rclone.conf` dans le conteneur via le `docker-compose.yml`.

---

<a name="english"></a>
## 🇺🇸 English

Automated backup of **Frigate NVR** clips to cloud storage (Google Drive) using **rclone**.

### ✨ Key Features
* **Event Driven**: `frigate_watchdog.sh` monitors MQTT events for immediate backup processing.
* **Reliability**: Background scan every 10 minutes ensures 100% sync coverage.
* **Optimized Storage**: Only backs up events with video clips and validated "Review" status.
* **Monitoring**: Integrated MQTT reporting for Home Assistant dashboards.

### 🚀 Quick Start
\`\`\`bash
# Clone the repository
git clone https://github.com/antlep/frigate_rsync_backup.git

# Configure your .env and rclone.conf
# Start the service
docker compose up -d
\`\`\`

---

## ⚠️ Configuration MQTT Obligatoire / Mandatory MQTT Broker

**Français :**
L'utilisation d'un broker MQTT (ex: Mosquitto) est **indispensable** pour deux raisons critiques :
1. **Entrée (Trigger)** : Le script `watchdog` s'abonne au topic `frigate/events` pour lancer la sauvegarde instantanément dès la fin d'un événement.
2. **Sortie (Reporting)** : Le script de backup publie un rapport JSON après chaque exécution pour permettre un monitoring dans Home Assistant (statut, espace disque utilisé, erreurs).
*Sans broker MQTT, le système perd sa réactivité et ses capacités de reporting.*

**English:**
An MQTT broker (e.g., Mosquitto) is **mandatory** for two critical reasons:
1. **Input (Trigger)**: The `watchdog` script subscribes to the `frigate/events` topic to trigger backups instantly as soon as an event ends.
2. **Output (Reporting)**: The backup script publishes a JSON report after each run to allow monitoring in Home Assistant (status, disk space used, errors).
*Without an MQTT broker, the system loses both its real-time responsiveness and reporting capabilities.*

---