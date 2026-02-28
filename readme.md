# Frigate Event Backup to Google Drive (rclone)

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![MQTT](https://img.shields.io/badge/MQTT-Mandatory-orange)
![rclone](https://img.shields.io/badge/rclone-v3-blue?logo=rclone)

[Français](#-français) | [English](#-english)

---

<a name="français"></a>
## 🇫🇷 Français

[cite_start]Ce projet permet de sauvegarder automatiquement les clips et snapshots de **Frigate NVR** vers un stockage cloud (Google Drive, etc.) via **rclone**. [cite_start]Il est conçu pour fonctionner comme un compagnon léger à une instance Frigate existante sous Docker[cite: 1, 2].

### ⚠️ Avertissements Critiques

* **MQTT est IMPÉRATIF** : Le système utilise un broker MQTT (ex: Mosquitto) pour deux fonctions vitales :
    * **Déclenchement (Input)** : Le script `watchdog` écoute le topic `frigate/events` pour lancer la sauvegarde dès qu'un événement se termine.
    * [cite_start]**Rapport (Output)** : Le script de backup publie un bilan JSON (statut, espace, erreurs) après chaque synchronisation pour votre monitoring.
* [cite_start]**Dépendance Docker** : Ce projet nécessite que Frigate soit installé sous Docker[cite: 1]. Il est fortement conseillé de faire démarrer ce conteneur **après** Frigate et le broker MQTT via la directive `depends_on` dans votre configuration.

### ✨ Caractéristiques
* **Architecture réactive** : Sauvegarde instantanée déclenchée par les messages MQTT `end` de Frigate.
* **Double Sécurité** : Un balayage périodique automatique (toutes les 10 min) rattrape les éventuels messages MQTT perdus.
* [cite_start]**Filtrage Intelligent** : Ne télécharge que les événements possédant un clip (`has_clip=1`) et validés dans la "Review" Frigate (`review=1`).
* [cite_start]**Nettoyage automatique** : Purge les anciens dossiers sur le cloud après 7 jours pour économiser l'espace.
* [cite_start]**Noms logiques** : Les fichiers (clip .mp4, snapshot .jpg et données .json) sont stockés avec des noms explicites (nom de caméra + horodatage).

### 🚀 Installation
1. [cite_start]**Rclone** : Configurez votre accès avec `rclone config` et placez votre `rclone.conf` dans le dossier.
2. [cite_start]**Environnement** : Copiez `.env.example` vers `.env` et remplissez vos accès MQTT et l'URL de Frigate.
3. **Déploiement** :
    ```bash
    docker compose up -d
    ```

---

<a name="english"></a>
## 🇺🇸 English

[cite_start]Automated backup of **Frigate NVR** clips and snapshots to cloud storage using **rclone**. [cite_start]Designed as a lightweight companion for Frigate running under Docker[cite: 1].

### ⚠️ Critical Warnings

* **MQTT is MANDATORY**: An MQTT broker is required for two vital functions:
    * **Trigger (Input)**: The `watchdog` script monitors the `frigate/events` topic for real-time processing.
    * [cite_start]**Reporting (Output)**: The backup script publishes a JSON report (status, storage, errors) after each sync.
* [cite_start]**Docker Dependency**: This project assumes Frigate is installed via Docker[cite: 1]. It is highly recommended to start this container **after** Frigate and the MQTT broker using the `depends_on` directive.

### ✨ Key Features
* **Event-Driven**: Instant backup triggered via MQTT `end` events.
* **Robustness**: A background safety scan runs every 10 minutes.
* [cite_start]**Smart Filtering**: Only backs up events with video clips (`has_clip=1`) and validated "Review" status (`review=1`).
* [cite_start]**Auto-Cleanup**: Automatically purges remote folders older than 7 days.
* [cite_start]**Clean Naming**: Files are stored using logical naming conventions (camera name + timestamp).

### 🚀 Quick Start
1. [cite_start]**Rclone**: Setup your remote with `rclone config` and put `rclone.conf` in the project folder.
2. [cite_start]**Environment**: Copy `.env.example` to `.env` and fill in MQTT and Frigate URL details.
3. **Deployment**:
    ```bash
    docker compose up -d
    ```