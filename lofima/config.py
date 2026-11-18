"""
Configuration de l'application.

Deux types de réglages :
  1. Les chemins FIXES du projet (dossier archive, dossier web...) -> constantes ci-dessous.
  2. Les réglages UTILISATEUR modifiables depuis l'UI (dossier d'export Spotify, etc.)
     -> stockés dans `settings.json` à la racine (ignoré par Git car propre à chaque machine).
"""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Chemins fixes du projet
# --------------------------------------------------------------------------- #

# Racine du dépôt (= dossier parent du package `lofima`)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Archive interne : copie de sauvegarde de tout ce qui est téléchargé.
ARCHIVE_DIR: Path = PROJECT_ROOT / "archive"
METADATA_DIR: Path = ARCHIVE_DIR / "metadata"  # versionné dans Git (*.json)
AUDIO_DIR: Path = ARCHIVE_DIR / "audio"        # ignoré par Git (*.mp3)
COVERS_DIR: Path = ARCHIVE_DIR / "covers"      # ignoré par Git (*.jpg)

# Fichiers statiques de l'interface web
WEB_DIR: Path = PROJECT_ROOT / "web"

# Fichier des réglages utilisateur
SETTINGS_FILE: Path = PROJECT_ROOT / "settings.json"

# Appareils connus (téléphone, PC...) et ce que chacun a déjà récupéré
DEVICES_FILE: Path = PROJECT_ROOT / "devices.json"


# --------------------------------------------------------------------------- #
# Réglages utilisateur
# --------------------------------------------------------------------------- #

def generate_access_token() -> str:
    """Code secret aléatoire (~22 caractères) qui protège l'accès depuis le Wi-Fi."""
    return secrets.token_urlsafe(16)


class UserSettings(BaseModel):
    """
    Réglages modifiables depuis le formulaire "Réglages" de l'UI.
    (Le code d'accès n'en fait PAS partie : il ne se change que via "Régénérer".)
    """

    # Dossier où sont copiés les mp3 finaux, à ajouter dans
    # Spotify > Paramètres > Fichiers locaux > "Ajouter une source".
    # Astuce : mettre ici un dossier de "Google Drive pour ordinateur" pour avoir la synchro Drive.
    export_dir: str = Field(default=str(Path.home() / "Music" / "LoFiMa"))

    # Qualité mp3 en kbps (passée à ffmpeg via yt-dlp).
    audio_quality_kbps: int = Field(default=192, ge=64, le=320)

    # Recadrer la miniature YouTube (16:9) en carré, format attendu par Spotify.
    crop_cover_square: bool = True

    # Rendre l'appli accessible depuis les autres appareils du Wi-Fi (téléphone...).
    # Pris en compte au DÉMARRAGE (start.bat) : il faut relancer l'appli après changement.
    lan_access: bool = False


class Settings(UserSettings):
    """Tous les réglages, y compris ceux que le formulaire ne modifie pas."""

    # Code secret exigé des appareils autres que le PC (contenu dans le QR code).
    access_token: str = Field(default_factory=generate_access_token)


class SettingsStore:
    """
    Lecture/écriture de `settings.json`.
    Le verrou évite que deux requêtes écrivent le fichier en même temps.
    """

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> Settings:
        """
        Retourne les réglages ; les valeurs par défaut si le fichier n'existe pas.
        Si le code d'accès vient d'être généré, il est enregistré tout de suite :
        sinon il changerait à chaque lecture.
        """
        data = json.loads(self._path.read_text(encoding="utf-8")) if self._path.exists() else {}
        settings = Settings(**data)
        if "access_token" not in data:
            self.save(settings)
        return settings

    def update(self, changes: UserSettings) -> Settings:
        """Applique les réglages du formulaire en CONSERVANT le code d'accès."""
        current = self.load()
        return self.save(Settings(**changes.model_dump(), access_token=current.access_token))

    def regenerate_token(self) -> Settings:
        """Nouveau code d'accès : les appareils déjà connectés devront rescanner le QR code."""
        return self.save(self.load().model_copy(update={"access_token": generate_access_token()}))

    def save(self, settings: Settings) -> Settings:
        """Écrit les réglages sur disque et les retourne."""
        with self._lock:
            self._path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        return settings


def ensure_archive_dirs() -> None:
    """Crée les dossiers de l'archive s'ils n'existent pas (ex : après un clone)."""
    for directory in (METADATA_DIR, AUDIO_DIR, COVERS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
