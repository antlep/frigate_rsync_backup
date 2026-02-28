Frigate Event Backup to Google Drive (rclone)

Français | English

<a name="français"></a>

🇫🇷 Français
Ce projet permet de sauvegarder automatiquement les clips et snapshots de Frigate NVR vers un stockage distant (Google Drive, etc.) en utilisant rclone. Il utilise une architecture basée sur les événements MQTT pour une réactivité instantanée.

✨ Caractéristiques

Réactivité en temps réel : Déclenchement de la sauvegarde dès qu'un événement Frigate se termine via MQTT.

Balayage de sécurité : Un scan périodique toutes les 10 minutes pour ne rater aucun événement.

Intelligence de filtrage : Utilise les API Frigate pour ne sauvegarder que les événements validés (review=1) et possédant un clip vidéo (has_clip=1).

Noms de fichiers explicites : Inclut le nom de la caméra et l'horodatage (camera_YYYYMMDD_HHMMSS.mp4).

Nettoyage automatique : Purge les anciens dossiers sur le stockage distant après 7 jours.

Notifications MQTT : Envoie l'état de la synchronisation et les statistiques vers Home Assistant.

🚀 Installation

Configurez votre accès Google Drive avec rclone config et placez le fichier rclone.conf dans le dossier.

Copiez .env.example vers .env et remplissez vos identifiants MQTT et l'URL de Frigate.

Lancez le conteneur :
\`\`\` Bash
docker compose up -d
\`\`\`
<a name="english"></a>

🇺🇸 English
This project automatically backs up Frigate NVR clips and snapshots to remote storage (Google Drive, etc.) using rclone. It features an event-driven architecture based on MQTT for instant processing.

✨ Features

Real-time processing: Backup starts immediately when a Frigate event ends via MQTT.

Safety Scan: Periodic background scan every 10 minutes to ensure no events are missed.

Smart Filtering: Uses Frigate APIs to only backup validated events (review=1) with an associated video clip (has_clip=1).

Clean Filenames: Includes camera name and timestamp (camera_YYYYMMDD_HHMMSS.mp4).

Auto-Cleanup: Automatically purges remote folders older than 7 days.

MQTT Status: Sends sync status and storage statistics to Home Assistant.

🚀 Setup

Configure your Google Drive access with rclone config and place the rclone.conf file in the directory.

Copy .env.example to .env and fill in your MQTT credentials and Frigate URL.

Start the container:

\`\`\` bash
docker compose up -d
\`\`\`

🛠️ Architecture

frigate_watchdog.sh: The entry point. It listens to the MQTT topic frigate/events and triggers the backup script.

frigate_backup.sh: The logic engine. It queries the Frigate API, downloads media, and moves them to the cloud via rclone.