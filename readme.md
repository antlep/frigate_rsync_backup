# Frigate Event Backup to Google Drive (rclone)

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![MQTT](https://img.shields.io/badge/MQTT-Mandatory-orange)
![rclone](https://img.shields.io/badge/rclone-v3-blue?logo=rclone)

[Français](#-français) | [English](#-english)

---

<a name="français"></a>
## 🇫🇷 Français

Ce projet permet de sauvegarder automatiquement les clips et snapshots de **Frigate NVR** vers un stockage cloud (Google Drive, etc.) via **rclone**. Il est conçu pour fonctionner comme un compagnon léger à une instance Frigate existante sous Docker.

### ⚠️ Avertissements Critiques

* **MQTT est IMPÉRATIF** : Le système utilise un broker MQTT (ex: Mosquitto) pour deux fonctions vitales :
    * **Déclenchement (Input)** : Le script `watchdog` écoute le topic `frigate/events` pour lancer la sauvegarde dès qu'un événement se termine.
    * **Rapport (Output)** : Le script de backup publie un bilan JSON (statut, espace, erreurs) après chaque synchronisation pour votre monitoring.
* **Build de l'image** : Ce projet n'utilise pas d'image pré-construite sur un registre. Vous devez **builder** l'image localement lors du premier lancement.
* **Dépendance Docker** : Ce projet nécessite que Frigate soit installé sous Docker. Il est fortement conseillé de faire démarrer ce conteneur **après** Frigate et le broker MQTT via la directive `depends_on`.

### ✨ Caractéristiques
* **Architecture réactive** : Sauvegarde instantanée déclenchée par les messages MQTT de Frigate.
* **Double Sécurité** : Un balayage périodique automatique (toutes les 10 min) rattrape les éventuels messages MQTT perdus.
* **Filtrage Intelligent** : Ne télécharge que les événements possédant un clip (`has_clip=1`) et validés dans la "Review" Frigate (`review=1`).
* **Nettoyage automatique** : Purge les anciens dossiers sur le cloud après 7 jours.
* **Noms logiques** : Les fichiers (.mp4, .jpg, .json) sont stockés avec des noms explicites (caméra + horodatage).

### 🚀 Installation & Build
1. **Rclone** : Configurez votre accès avec `rclone config` et placez votre `rclone.conf` dans le dossier.
2. **Environnement** : Copiez `.env.example` vers `.env` et remplissez vos accès MQTT et l'URL de Frigate.
3. **Construction et Lancement** :
    ```bash
    # Construit l'image locale et lance le conteneur
    docker compose up -d --build
    ```

---

<a name="english"></a>
## 🇺🇸 English

Automated backup of **Frigate NVR** clips and snapshots to cloud storage using **rclone**. Designed as a lightweight companion for Frigate running under Docker.

### ⚠️ Critical Warnings

* **MQTT is MANDATORY**: An MQTT broker is required for two vital functions:
    * **Trigger (Input)** : The `watchdog` script monitors the `frigate/events` topic for real-time processing.
    * **Reporting (Output)** : The backup script publishes a JSON report (status, storage, errors) after each sync.
* **Local Build Required**: This project does not use a pre-built image. You must **build** the image locally from the Dockerfile.
* **Docker Dependency**: It is highly recommended to start this container **after** Frigate and the MQTT broker using the `depends_on` directive.

### ✨ Key Features
* **Event-Driven**: Instant backup triggered via MQTT `end` events.
* **Robustness**: A background safety scan runs every 10 minutes.
* **Smart Filtering**: Only backups events with video clips and validated "Review" status.
* **Auto-Cleanup**: Automatically purges remote folders older than 7 days.

### 🚀 Quick Start
1. **Rclone**: Setup your remote with `rclone config` and put `rclone.conf` in the project folder.
2. **Environment**: Copy `.env.example` to `.env` and fill in MQTT and Frigate URL details.
3. **Build & Deployment**:
    ```bash
    docker compose up -d --build
    ```

---

### 🛠️ Architecture
* **`frigate_watchdog.sh`**: Entry point. Listens to MQTT and manages the 10-min safety timer.
* **`frigate_backup.sh`**: Logic engine. Queries Frigate API, downloads media, and moves them via rclone.

## 🚀 Roadmap & Idées futures

Voici les pistes d'améliorations :

- [ ] **Externalisation de la configuration** : Sortir les paramètres "hardcodés" (ex: boucle de sécurité de 10 min, limites de rétention) pour les rendre configurables via le fichier `.env`.
- [ ] **Notifications multi-canaux** : Intégrer des alertes via Telegram ou Discord en cas d'échec de la synchronisation. Je n'y connais rien donc à vos crayons
- [ ] **Gestion fine par caméra** : Permettre des durées de rétention différentes sur le Cloud selon l'importance de la caméra.
- [ ] **Optimisation du registre** : Passer d'un fichier texte à une micro-base de données (SQLite) pour gérer des milliers d'événements sans ralentissement. A voir si c'est pertinent