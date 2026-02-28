# Frigate Event Backup to Google Drive (rclone)

![License](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![MQTT](https://img.shields.io/badge/MQTT-Mandatory-orange)

[Français](#-français) | [English](#-english)

---

<a name="français"></a>
## 🇫🇷 Français

Ce projet permet de sauvegarder automatiquement les clips et snapshots de **Frigate NVR** vers un stockage cloud (Google Drive, etc.) via **rclone**. Il est conçu pour fonctionner comme un compagnon léger à une instance Frigate existante sous Docker.

### ⚠️ Avertissements Critiques

* **MQTT est IMPÉRATIF** : Le système utilise un broker MQTT (ex: Mosquitto) pour deux fonctions vitales :
    * **Déclenchement (Input)** : Le script `watchdog` écoute le topic `frigate/events` pour lancer la sauvegarde dès qu'un événement se termine.
    * **Rapport (Output)** : Le script de backup publie un bilan JSON (statut, espace, erreurs) après chaque synchronisation pour votre monitoring.
* **Dépendance Docker** : Ce projet part du principe que Frigate est installé via Docker. Il est fortement conseillé de faire démarrer ce conteneur **après** Frigate et le broker MQTT via la directive `depends_on`.

### ✨ Caractéristiques
* **Architecture réactive** : Sauvegarde instantanée dès la fin d'une détection.
* **Double Sécurité** : Un balayage périodique (toutes les 10 min) rattrape les éventuels messages MQTT perdus.
* **Filtrage Intelligent** : Ne télécharge que les événements possédant un clip (`has_clip=1`) et validés dans la "Review" Frigate (`review=1`).
* **Nettoyage automatique** : Purge les anciens dossiers sur le cloud après 7 jours.

### 🚀 Installation
1. **Rclone** : Configurez votre accès avec `rclone config` et placez votre `rclone.conf` dans le dossier.
2. **Environnement** : Copiez `.env.example` vers `.env` et remplissez vos accès MQTT et l'URL de Frigate.
3. **Déploiement** :
```bash
    docker compose up -d
```