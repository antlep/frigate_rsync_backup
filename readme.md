# frigate-gdrive-sync

> 🇫🇷 [Français](#français) | 🇬🇧 [English](#english)

---

## Français

### Présentation

**frigate-gdrive-sync** est un service Docker qui écoute les événements de détection de [Frigate NVR](https://frigate.video) via MQTT et sauvegarde automatiquement les clips vidéo, snapshots et métadonnées sur Google Drive via [rclone](https://rclone.org).

Il est conçu pour tourner en colocalisé avec Frigate dans un LXC Proxmox, mais fonctionne aussi depuis n'importe quelle machine du réseau (Mac, autre serveur).

### Fonctionnalités

- **Écoute MQTT** avec reconnexion automatique
- **Téléchargement** des clips (.mp4), snapshots (.jpg) et métadonnées (.json) depuis l'API Frigate
- **Upload via rclone** vers Google Drive (ou tout autre remote rclone)
- **Workers parallèles** — N caméras traitées simultanément (configurable)
- **Queue persistante SQLite** — aucun événement perdu après un redémarrage
- **Retry avec backoff exponentiel** — gère les clips pas encore encodés par Frigate
- **Rétention automatique** — suppression des fichiers plus vieux que N jours sur Google Drive
- **Arborescence personnalisable** via template de chemin (`{date}/{camera}`, `{camera}/{label}`, etc.)
- **Fallback d'hôte** — détection automatique si Frigate est local ou distant (pratique pour le dev)
- **Health check HTTP** sur `/health` (port 8080)
- **Dry-run** — simule les uploads sans rien écrire sur Drive
- **Logs structurés JSON** (ou texte coloré pour le dev)

### Architecture

```
Broker MQTT ──► MQTTListener ──► asyncio.Queue ──► Worker Pool (N workers)
                                       │                    │
                               SQLite (durabilité)   Frigate HTTP API
                                                           │
                                                        rclone → Google Drive
```

### Structure Google Drive (par défaut)

```
Frigate/
  2026-03-15/
    annke_02/
      2026-03-15_14-32-07_person_abc123.mp4
      2026-03-15_14-32-07_person_abc123.jpg
      2026-03-15_14-32-07_person_abc123.json
    foscam/
      ...
```

### Prérequis

- Docker + Docker Compose
- Un broker MQTT (ex: Mosquitto dans Home Assistant)
- Frigate NVR avec MQTT activé
- `rclone.conf` configuré avec un remote Google Drive

### Installation

```bash
# 1. Cloner la branche principale
git clone https://github.com/ton-user/ton-repo.git
cd ton-repo

# 2. Initialiser la configuration
make init
# → crée config/config.yaml depuis config/config.example.yaml

# 3. Copier le rclone.conf
cp ~/.config/rclone/rclone.conf config/rclone.conf

# 4. Éditer config/config.yaml
nano config/config.yaml

# 5. Builder et lancer
make build
make run

# 6. Suivre les logs
make logs
```

### Configuration

Voir [`config/config.example.yaml`](config/config.example.yaml) pour la documentation complète de chaque option.

| Variable d'environnement | Équivalent YAML         | Description                        |
|--------------------------|-------------------------|------------------------------------|
| `FRIGATE_HOST`           | `frigate.host`          | IP/hostname de Frigate             |
| `MQTT_HOST`              | `mqtt.host`             | IP/hostname du broker MQTT         |
| `MQTT_USERNAME`          | `mqtt.username`         | Identifiant MQTT                   |
| `MQTT_PASSWORD`          | `mqtt.password`         | Mot de passe MQTT                  |
| `RCLONE_REMOTE`          | `rclone.remote`         | Remote rclone (ex: `gdrive:Frigate`) |
| `SYNC_WORKERS`           | `sync.workers`          | Nombre de workers parallèles       |
| `SYNC_DRY_RUN`           | `sync.dry_run`          | Mode simulation (true/false)       |
| `LOG_LEVEL`              | `logging.level`         | DEBUG / INFO / WARNING / ERROR     |

### Template d'arborescence

La structure des dossiers sur Google Drive est entièrement personnalisable :

```yaml
sync:
  path_template: "{date}/{camera}"        # défaut → 2026-03-15/annke_02/
  # path_template: "{camera}/{date}"      # → annke_02/2026-03-15/
  # path_template: "{date}/{camera}/{label}" # → 2026-03-15/annke_02/person/
```

Variables disponibles : `{date}`, `{year}`, `{month}`, `{hour}`, `{camera}`, `{label}`, `{id}`, `{stem}`

### Rétention

```yaml
sync:
  retention_days: 7   # supprime les fichiers > 7 jours (0 = désactivé)
```

Le nettoyage s'effectue au démarrage puis toutes les 24h.

### Health check

```bash
curl http://localhost:8080/health
# {"status": "ok", "mqtt_connected": true, "pending": 0, "done": 142, "failed": 0}
```

### Dev local (Mac)

```bash
make init   # crée aussi docker-compose.override.yml
# éditer les host_fallback dans config/config.yaml
make build
make dev    # logs en temps réel
```

### Commandes utiles

```bash
make build    # construire l'image
make run      # démarrer en arrière-plan
make dev      # démarrer avec logs en direct
make stop     # arrêter
make logs     # suivre les logs
make shell    # ouvrir un shell dans le container
```

---

## English

### Overview

**frigate-gdrive-sync** is a Docker service that listens to detection events from [Frigate NVR](https://frigate.video) via MQTT and automatically backs up video clips, snapshots, and metadata to Google Drive using [rclone](https://rclone.org).

Designed to run alongside Frigate in a Proxmox LXC container, but works from any machine on the network (Mac, other server).

### Features

- **MQTT listener** with automatic reconnection
- **Downloads** clips (.mp4), snapshots (.jpg) and metadata (.json) from the Frigate HTTP API
- **Uploads via rclone** to Google Drive (or any rclone remote)
- **Parallel workers** — N cameras processed simultaneously (configurable)
- **SQLite persistent queue** — no events lost after a restart
- **Retry with exponential backoff** — handles clips not yet encoded by Frigate
- **Automatic retention** — deletes files older than N days from Google Drive
- **Customizable folder structure** via path template (`{date}/{camera}`, `{camera}/{label}`, etc.)
- **Host fallback** — auto-detects whether Frigate is local or remote (useful for dev)
- **HTTP health check** on `/health` (port 8080)
- **Dry-run mode** — simulates uploads without writing to Drive
- **Structured JSON logs** (or colored text for dev)

### Architecture

```
MQTT Broker ──► MQTTListener ──► asyncio.Queue ──► Worker Pool (N workers)
                                       │                    │
                               SQLite (durability)   Frigate HTTP API
                                                           │
                                                        rclone → Google Drive
```

### Google Drive structure (default)

```
Frigate/
  2026-03-15/
    annke_02/
      2026-03-15_14-32-07_person_abc123.mp4
      2026-03-15_14-32-07_person_abc123.jpg
      2026-03-15_14-32-07_person_abc123.json
    foscam/
      ...
```

### Requirements

- Docker + Docker Compose
- A MQTT broker (e.g. Mosquitto in Home Assistant)
- Frigate NVR with MQTT enabled
- `rclone.conf` configured with a Google Drive remote

### Installation

```bash
# 1. Clone the main branch
git clone https://github.com/your-user/your-repo.git
cd your-repo

# 2. Initialize configuration
make init
# → creates config/config.yaml from config/config.example.yaml

# 3. Copy your rclone.conf
cp ~/.config/rclone/rclone.conf config/rclone.conf

# 4. Edit config/config.yaml
nano config/config.yaml

# 5. Build and start
make build
make run

# 6. Follow logs
make logs
```

### Configuration

See [`config/config.example.yaml`](config/config.example.yaml) for full documentation of each option.

| Environment variable | YAML equivalent         | Description                          |
|----------------------|-------------------------|--------------------------------------|
| `FRIGATE_HOST`       | `frigate.host`          | Frigate IP/hostname                  |
| `MQTT_HOST`          | `mqtt.host`             | MQTT broker IP/hostname              |
| `MQTT_USERNAME`      | `mqtt.username`         | MQTT username                        |
| `MQTT_PASSWORD`      | `mqtt.password`         | MQTT password                        |
| `RCLONE_REMOTE`      | `rclone.remote`         | rclone remote (e.g. `gdrive:Frigate`) |
| `SYNC_WORKERS`       | `sync.workers`          | Number of parallel workers           |
| `SYNC_DRY_RUN`       | `sync.dry_run`          | Simulation mode (true/false)         |
| `LOG_LEVEL`          | `logging.level`         | DEBUG / INFO / WARNING / ERROR       |

### Path template

The Google Drive folder structure is fully customizable:

```yaml
sync:
  path_template: "{date}/{camera}"           # default → 2026-03-15/annke_02/
  # path_template: "{camera}/{date}"         # → annke_02/2026-03-15/
  # path_template: "{date}/{camera}/{label}" # → 2026-03-15/annke_02/person/
```

Available variables: `{date}`, `{year}`, `{month}`, `{hour}`, `{camera}`, `{label}`, `{id}`, `{stem}`

### Retention

```yaml
sync:
  retention_days: 7   # delete files older than 7 days (0 = disabled)
```

Cleanup runs at startup then every 24 hours.

### Health check

```bash
curl http://localhost:8080/health
# {"status": "ok", "mqtt_connected": true, "pending": 0, "done": 142, "failed": 0}
```

### Local dev (Mac)

```bash
make init   # also creates docker-compose.override.yml
# edit host_fallback values in config/config.yaml
make build
make dev    # live logs
```

### Useful commands

```bash
make build    # build the image
make run      # start in background
make dev      # start with live logs
make stop     # stop
make logs     # follow logs
make shell    # open a shell in the container
```

### Project structure

```
.
├── config/
│   └── config.example.yaml   # annotated configuration template
├── scripts/
│   └── test.sh               # integration test suite
├── src/
│   ├── main.py               # entry point, task orchestration
│   ├── config.py             # Pydantic config (YAML + env vars)
│   ├── models.py             # FrigateEvent dataclass
│   ├── mqtt_listener.py      # MQTT subscriber with auto-reconnect
│   ├── event_queue.py        # asyncio.Queue + SQLite persistence
│   ├── worker.py             # download + upload worker
│   ├── frigate_client.py     # Frigate HTTP API client
│   ├── rclone_uploader.py    # async rclone subprocess wrapper
│   ├── retention.py          # periodic GDrive cleanup
│   └── health.py             # HTTP health check server
├── Dockerfile
├── docker-compose.yml
└── Makefile
```