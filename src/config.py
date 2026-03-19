"""
Configuration loader.

Priority (highest → lowest):
  1. Environment variables  (FRIGATE_HOST, MQTT_HOST, …)
  2. config.yaml
  3. Built-in defaults

Environment variables are dot-path uppercased with underscores:
  frigate.host  →  FRIGATE_HOST
  mqtt.password →  MQTT_PASSWORD
  sync.workers  →  SYNC_WORKERS
"""
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Host auto-detection                                                          #
# --------------------------------------------------------------------------- #

def _probe_tcp(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Sub-models                                                                   #
# --------------------------------------------------------------------------- #


class FrigateConfig(BaseModel):
    host: str = "localhost"
    host_fallback: Optional[str] = None   # e.g. "192.168.1.x" — used when host is unreachable
    port: int = 5000
    api_timeout: int = 30  # seconds

    def resolved_host(self) -> str:
        """Return host if reachable, otherwise host_fallback.
        On LXC (co-located) → host=127.0.0.1 répond → on l'utilise.
        Sur Mac (dev)        → 127.0.0.1 ne répond pas → fallback IP réseau.
        """
        if self.host_fallback and not _probe_tcp(self.host, self.port):
            return self.host_fallback
        return self.host


class MQTTConfig(BaseModel):
    host: str = "localhost"
    host_fallback: Optional[str] = None   # même logique que Frigate
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    topic_prefix: str = "frigate"
    client_id: str = "frigate-gdrive-sync"
    keepalive: int = 60

    def resolved_host(self) -> str:
        if self.host_fallback and not _probe_tcp(self.host, self.port):
            return self.host_fallback
        return self.host


class RcloneConfig(BaseModel):
    remote: str = "gdrive:Frigate"
    config_path: str = "/config/rclone.conf"
    bwlimit: Optional[str] = None          # e.g. "2M"
    flags: list[str] = Field(default_factory=list)  # extra rclone flags


class SyncConfig(BaseModel):
    workers: int = 4                       # parallel upload workers
    # Path template for remote files. Available variables:
    #   {date}      → 2026-03-15
    #   {datetime}  → 2026-03-15_11-53-01
    #   {camera}    → annke_02
    #   {label}     → person
    #   {id}        → 1773575581.33434-f8r7fs
    #   {score}     → 0.52
    # Default produces: 2026-03-15/annke_02/2026-03-15_11-53-01_person_{id}
    path_template: str = "{date}/{camera}/{datetime}_{label}_{id}"
    retry_attempts: int = 3
    retry_delay: float = 10.0              # seconds (base, then × backoff)
    retry_backoff: float = 2.0
    download_clip: bool = True
    download_snapshot: bool = True
    export_json: bool = True
    skip_if_no_media: bool = True   # ignore events with no clip and no snapshot

    # Polling: how often to ask Frigate API if the clip/snapshot is ready (seconds)
    clip_poll_interval: float = 3.0
    # Polling: max total time to wait for media before giving up (seconds)
    # Should be > your Frigate post_capture + encoding time under load.
    clip_poll_timeout: float = 60.0
    cameras: list[str] = Field(default_factory=list)   # [] = all cameras
    labels: list[str] = Field(default_factory=list)    # [] = all labels
    min_score: float = 0.0
    tmp_dir: str = "/tmp/frigate-sync"
    dry_run: bool = False                  # log uploads but do not execute rclone

    # Folder structure template on the remote.
    # Available variables: {date} {year} {month} {camera} {label} {hour} {id}
    # Default: {date}/{camera}  →  2026-03-15/annke_02/
    path_template: str = "{date}/{camera}"
    # Retention: delete files older than N days from the remote (0 = disabled)
    retention_days: int = 7


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"                   # "json" | "text"


class HealthConfig(BaseModel):
    enabled: bool = True
    port: int = 8080


# --------------------------------------------------------------------------- #
# Root config                                                                  #
# --------------------------------------------------------------------------- #


class AppConfig(BaseModel):
    frigate: FrigateConfig = Field(default_factory=FrigateConfig)
    mqtt: MQTTConfig = Field(default_factory=MQTTConfig)
    rclone: RcloneConfig = Field(default_factory=RcloneConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)

    # ------------------------------------------------------------------ #
    # Loader                                                               #
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: str | None = None) -> AppConfig:
        """Load config from YAML, then apply env var overrides."""
        data: dict[str, Any] = {}

        config_path = path or os.environ.get("CONFIG_PATH", "/config/config.yaml")
        p = Path(config_path)
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f) or {}

        # Env var overrides — flat SECTION_KEY format
        _apply_env_overrides(data)

        return cls(**data)


# --------------------------------------------------------------------------- #
# Env var override helper                                                      #
# --------------------------------------------------------------------------- #

_ENV_MAP: dict[str, tuple[str, str]] = {
    # ENV_VAR                   section       key
    "FRIGATE_HOST":            ("frigate",   "host"),
    "FRIGATE_HOST_FALLBACK":   ("frigate",   "host_fallback"),
    "FRIGATE_PORT":            ("frigate",   "port"),
    "MQTT_HOST":               ("mqtt",      "host"),
    "MQTT_HOST_FALLBACK":      ("mqtt",      "host_fallback"),
    "MQTT_PORT":               ("mqtt",      "port"),
    "MQTT_USERNAME":           ("mqtt",      "username"),
    "MQTT_PASSWORD":           ("mqtt",      "password"),
    "MQTT_TOPIC_PREFIX":       ("mqtt",      "topic_prefix"),
    "RCLONE_REMOTE":           ("rclone",    "remote"),
    "RCLONE_CONFIG_PATH":      ("rclone",    "config_path"),
    "RCLONE_BWLIMIT":          ("rclone",    "bwlimit"),
    "SYNC_WORKERS":            ("sync",      "workers"),
    "SYNC_DRY_RUN":            ("sync",      "dry_run"),
    "SYNC_MIN_SCORE":          ("sync",      "min_score"),
    "LOG_LEVEL":               ("logging",   "level"),
    "LOG_FORMAT":              ("logging",   "format"),
}


def _apply_env_overrides(data: dict[str, Any]) -> None:
    for env_key, (section, key) in _ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        if section not in data:
            data[section] = {}
        # Cast booleans and numbers
        if val.lower() in ("true", "1", "yes"):
            val = True  # type: ignore[assignment]
        elif val.lower() in ("false", "0", "no"):
            val = False  # type: ignore[assignment]
        else:
            try:
                val = int(val)  # type: ignore[assignment]
            except ValueError:
                try:
                    val = float(val)  # type: ignore[assignment]
                except ValueError:
                    pass
        data[section][key] = val