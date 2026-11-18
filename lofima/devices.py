"""
Appareils (PC, iPhone...) et suivi de ce que chacun a déjà récupéré.

Chaque navigateur qui ouvre l'appli reçoit un identifiant (cookie) et devient un "appareil".
Un appareil a un MODE de récupération des musiques :
  - EXPORT_FOLDER : les mp3 sont copiés automatiquement dans le dossier d'export du PC
                    (le fonctionnement historique, pour le Spotify du PC) ;
  - DOWNLOAD      : l'appareil récupère les mp3 en les téléchargeant via le navigateur
                    (iPhone : Safari les range dans l'app Fichiers).

Pour les appareils en mode DOWNLOAD, on retient la version (updated_at) de chaque musique
téléchargée, pour savoir ce qui est nouveau ou modifié depuis.

Stockage : `devices.json` à la racine (ignoré par Git, propre à chaque PC).
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import Track

# Un id d'appareil vient d'un cookie (donc du client) : on vérifie son format.
_SAFE_DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Précision de `last_seen` (en secondes)
_LAST_SEEN_RESOLUTION_S = 60


def _seconds_since(iso_date: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso_date)).total_seconds()


def new_device_id() -> str:
    return secrets.token_urlsafe(12)


def is_valid_device_id(device_id: Optional[str]) -> bool:
    return bool(device_id) and bool(_SAFE_DEVICE_ID.match(device_id))


class DeviceMode(str, Enum):
    EXPORT_FOLDER = "export_folder"
    DOWNLOAD = "download"


class DownloadState(str, Enum):
    """État d'une musique POUR un appareil donné (affiché en badge dans l'UI)."""

    NEW = "new"                # jamais récupérée sur cet appareil
    OUTDATED = "outdated"      # récupérée, mais modifiée depuis (tags, pochette...)
    DOWNLOADED = "downloaded"  # à jour sur cet appareil


class Device(BaseModel):
    id: str
    name: str
    mode: DeviceMode
    # track_id -> valeur de `Track.updated_at` au moment du téléchargement
    downloaded: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now_iso)
    last_seen: str = Field(default_factory=_now_iso)

    def state_of(self, track: Track) -> DownloadState:
        version = self.downloaded.get(track.id)
        if version is None:
            return DownloadState.NEW
        # On compare de vraies dates (les anciens JSON sont précis à la seconde, les
        # nouveaux à la microseconde : comparer les textes serait trompeur).
        if datetime.fromisoformat(track.updated_at) > datetime.fromisoformat(version):
            return DownloadState.OUTDATED
        return DownloadState.DOWNLOADED


class DeviceUpdate(BaseModel):
    """Corps de PATCH /api/me : ce que l'utilisateur peut changer sur son appareil."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    mode: Optional[DeviceMode] = None


def guess_device_name(user_agent: str) -> str:
    """Nom par défaut lisible, déduit du navigateur ("iPhone", "Windows"...)."""
    ua = user_agent or ""
    for keyword, name in (
        ("iPhone", "iPhone"),
        ("iPad", "iPad"),
        ("Android", "Android"),
        ("Windows", "PC Windows"),
        ("Macintosh", "Mac"),
        ("Linux", "Linux"),
    ):
        if keyword in ua:
            return name
    return "Appareil"


class DeviceRegistry:
    """Lecture/écriture de devices.json (toutes les opérations sous verrou)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    # --- accès bas niveau au fichier (à appeler sous verrou) ---
    def _read(self) -> dict[str, Device]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {device_id: Device(**data) for device_id, data in raw.items()}

    def _write(self, devices: dict[str, Device]) -> None:
        data = {device_id: device.model_dump(mode="json") for device_id, device in devices.items()}
        temp = self._path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(self._path)

    # --- API publique ---
    def list(self) -> list[Device]:
        with self._lock:
            return sorted(self._read().values(), key=lambda d: d.last_seen, reverse=True)

    def get(self, device_id: str) -> Optional[Device]:
        with self._lock:
            return self._read().get(device_id)

    def touch(self, device_id: str, user_agent: str, is_local: bool) -> Device:
        """
        Retourne l'appareil (le crée à sa 1re visite) et met à jour `last_seen`.
        Mode par défaut : le PC lui-même -> dossier d'export ; un autre appareil -> téléchargement.
        """
        with self._lock:
            devices = self._read()
            device = devices.get(device_id)
            if device is None:
                device = Device(
                    id=device_id,
                    name=guess_device_name(user_agent),
                    mode=DeviceMode.EXPORT_FOLDER if is_local else DeviceMode.DOWNLOAD,
                )
                devices[device_id] = device
                self._write(devices)
            elif _seconds_since(device.last_seen) > _LAST_SEEN_RESOLUTION_S:
                # L'UI interroge le serveur souvent : on n'écrit last_seen qu'1 fois/minute
                # pour ne pas réécrire le fichier à chaque requête.
                device.last_seen = _now_iso()
                self._write(devices)
            return device

    def update(self, device_id: str, changes: DeviceUpdate) -> Device:
        with self._lock:
            devices = self._read()
            device = devices[device_id]
            if changes.name is not None:
                device.name = changes.name.strip()
            if changes.mode is not None:
                device.mode = changes.mode
            self._write(devices)
            return device

    def mark_downloaded(self, device_id: str, track: Track) -> None:
        """Retient que l'appareil possède maintenant cette version de la musique."""
        with self._lock:
            devices = self._read()
            if device_id in devices:
                devices[device_id].downloaded[track.id] = track.updated_at
                self._write(devices)

    def forget_track(self, track_id: str) -> None:
        """Musique supprimée définitivement : on la retire du suivi de tous les appareils."""
        with self._lock:
            devices = self._read()
            for device in devices.values():
                device.downloaded.pop(track_id, None)
            self._write(devices)

    def remove(self, device_id: str) -> bool:
        with self._lock:
            devices = self._read()
            if devices.pop(device_id, None) is None:
                return False
            self._write(devices)
            return True
