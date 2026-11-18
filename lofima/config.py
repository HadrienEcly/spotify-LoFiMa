"""
Configuration de l'application.

Deux types de réglages :
  1. Les chemins FIXES du projet (dossier archive, dossier web...) -> constantes ci-dessous.
  2. Les réglages UTILISATEUR modifiables depuis l'UI (dossier d'export Spotify, etc.)
     -> stockés dans `settings.json` à la racine (ignoré par Git car propre à chaque machine).
"""

from __future__ import annotations

import json
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


# --------------------------------------------------------------------------- #
# Réglages utilisateur
# --------------------------------------------------------------------------- #

class Settings(BaseModel):
    """Réglages modifiables depuis l'UI. Chaque champ a une valeur par défaut."""

    # Dossier où sont copiés les mp3 finaux, à ajouter dans
    # Spotify > Paramètres > Fichiers locaux > "Ajouter une source".
    # Astuce : mettre ici un dossier de "Google Drive pour ordinateur" pour avoir la synchro Drive.
    export_dir: str = Field(default=str(Path.home() / "Music" / "LoFiMa"))

    # Qualité mp3 en kbps (passée à ffmpeg via yt-dlp).
    audio_quality_kbps: int = Field(default=192, ge=64, le=320)

    # Recadrer la miniature YouTube (16:9) en carré, format attendu par Spotify.
    crop_cover_square: bool = True


class SettingsStore:
    """
    Lecture/écriture de `settings.json`.
    Le verrou évite que deux requêtes écrivent le fichier en même temps.
    """

    def __init__(self, path: Path = SETTINGS_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self) -> Settings:
        """Retourne les réglages ; les valeurs par défaut si le fichier n'existe pas."""
        if not self._path.exists():
            return Settings()
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Settings(**data)

    def save(self, settings: Settings) -> Settings:
        """Écrit les réglages sur disque et les retourne."""
        with self._lock:
            self._path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        return settings


def ensure_archive_dirs() -> None:
    """Crée les dossiers de l'archive s'ils n'existent pas (ex : après un clone)."""
    for directory in (METADATA_DIR, AUDIO_DIR, COVERS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
