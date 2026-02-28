# Frigate Event Backup to Google Drive (rclone)

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![MQTT](https://img.shields.io/badge/MQTT-Mandatory-orange)

[Français](#-français) | [English](#-english)

---

<a name="français"></a>
## 🇫🇷 Français

Ce projet permet de sauvegarder automatiquement les clips et snapshots de **Frigate NVR** vers un stockage cloud (Google Drive, etc.) via **rclone**.

### ⚠️ Avertissement : MQTT est IMPÉRATIF
L'utilisation d'un broker MQTT (ex: Mosquitto) est **obligatoire** pour le bon fonctionnement du système :
* **Déclenchement (Input)** : Le script `watchdog` écoute le topic `frigate/events` pour lancer la sauvegarde dès qu'un événement se termine.
* **Rapport (Output)** : Le script de backup publie un bilan JSON (statut, espace disque, erreurs) après chaque synchronisation.
* *Sans MQTT, le système perd sa réactivité et ses capacités de monitoring.*

### ✨ Caractéristiques
* **Architecture réactive** : Sauvegarde instantanée via MQTT.
* **Sécurité accrue** : Un balayage périodique toutes les 10 min rattrape les éventuels échecs.
* **Filtrage Intelligent** : Seuls les événements avec clips (`has_clip=1`) et validés (`review=1`) sont envoyés.
* **Nettoyage automatique** : Purge les anciens dossiers sur le stockage distant après 7 jours.

### 🚀 Installation rapide
1. **Rclone** : Configurez votre accès avec `rclone config` et placez votre `rclone.conf` dans le dossier.
2. **Environnement** : Copiez `.env.example` vers `.env` et remplissez vos accès MQTT et l'URL de Frigate.
3. **Docker** :
   ```bash
   docker compose up -d