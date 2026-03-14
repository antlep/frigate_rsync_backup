# frigate-gdrive-sync

Écoute le flux MQTT de Frigate et sauvegarde les événements (clip, snapshot, JSON) sur Google Drive via rclone.

```
MQTT Listener ──► asyncio.Queue ──► Worker Pool (N workers)
                       │                    │
               SQLite (durabilité)   Frigate HTTP API
                                           │
                                        rclone → Google Drive
```

## Structure Google Drive

```
{remote}/
  {camera}/
    {YYYY-MM}/
      {YYYY-MM-DD}/
        2024-12-25_14-32-07_person_abc123.mp4
        2024-12-25_14-32-07_person_abc123.jpg
        2024-12-25_14-32-07_person_abc123.json
```

## Démarrage rapide

```bash
# 1. Créer la config
make init

# 2. Copier votre rclone.conf
cp ~/.config/rclone/rclone.conf ./config/rclone.conf

# 3. Éditer config/config.yaml (IPs, filtres, etc.)
# 4. Build & run
make build
make run

# Logs live
make logs
```

## Configuration

Voir [`config/config.example.yaml`](config/config.example.yaml) pour toutes les options.

Toutes les valeurs sont également surchargeables via variables d'environnement :

| Variable           | Équivalent YAML          |
|--------------------|--------------------------|
| `FRIGATE_HOST`     | `frigate.host`           |
| `MQTT_HOST`        | `mqtt.host`              |
| `MQTT_USERNAME`    | `mqtt.username`          |
| `MQTT_PASSWORD`    | `mqtt.password`          |
| `RCLONE_REMOTE`    | `rclone.remote`          |
| `SYNC_WORKERS`     | `sync.workers`           |
| `SYNC_DRY_RUN`     | `sync.dry_run`           |
| `LOG_LEVEL`        | `logging.level`          |

## Scalabilité multi-caméras

Les workers traitent les événements de toutes les caméras en parallèle. Pour 8 caméras actives, `sync.workers: 8` (ou plus) est recommandé.

Filtrer par caméra si besoin :
```yaml
sync:
  cameras: ["front_door", "backyard"]
```

## Durabilité

Les événements sont persistés dans SQLite (`/data/events.db`) dès leur réception MQTT. Si le container redémarre en cours de traitement, les événements `pending`/`processing` sont automatiquement ré-enqueués au démarrage.

## Health check

```bash
curl http://localhost:8080/health
# {"status": "ok", "mqtt_connected": true, "pending": 0, "done": 142, ...}
```

## Dry run (test sans upload)

```bash
SYNC_DRY_RUN=true docker compose up
```

## Volumes

| Volume                | Contenu                               |
|-----------------------|---------------------------------------|
| `./config`            | `config.yaml` + `rclone.conf` (ro)   |
| `frigate-sync-data`   | SQLite persistence                    |
| `/tmp/frigate-sync`   | Staging tmpfs (éphémère)              |
