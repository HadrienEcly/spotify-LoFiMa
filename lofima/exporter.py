"""
Export des mp3 finaux vers le dossier lu par Spotify.

`Exporter` est une classe abstraite : aujourd'hui seule `LocalFolderExporter` existe,
mais on pourrait ajouter plus tard un `GoogleDriveExporter` (API Drive) avec les mêmes
méthodes, sans toucher au reste du code.
"""

from __future__ import annotations

import re
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

# Caractères interdits dans les noms de fichiers Windows (+ caractères de contrôle)
_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Noms réservés par Windows (même avec une extension, "CON.mp3" est invalide)
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}
# Limite prudente : Windows limite le chemin complet à ~260 caractères par défaut.
_MAX_STEM_LENGTH = 150


def safe_filename(stem: str, extension: str = ".mp3") -> str:
    """
    Transforme un texte libre ("AC/DC - Back In Black?") en nom de fichier valide
    sous Windows ("AC_DC - Back In Black_.mp3").
    """
    cleaned = _FORBIDDEN_CHARS.sub("_", stem)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Windows interdit un nom finissant par un point ou un espace
    cleaned = cleaned.rstrip(". ")[:_MAX_STEM_LENGTH].rstrip(". ")
    if not cleaned:
        cleaned = "Sans titre"
    if cleaned.upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned + extension


class Exporter(ABC):
    """Interface d'une destination d'export."""

    @abstractmethod
    def export(self, source: Path, wanted_name: str, previous_name: str = "") -> str:
        """
        Copie `source` vers la destination sous le nom `wanted_name`.
        Supprime l'ancienne copie `previous_name` si le nom a changé.
        Retourne le nom réellement utilisé (peut différer en cas de doublon).
        """

    @abstractmethod
    def remove(self, name: str) -> None:
        """Supprime la copie exportée (sans erreur si elle n'existe pas)."""

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Indique si la copie exportée existe."""


class LocalFolderExporter(Exporter):
    """Export vers un dossier local (éventuellement synchronisé par Google Drive pour ordinateur)."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, name: str) -> Path:
        return self.directory / name

    def _unique_name(self, wanted_name: str, previous_name: str) -> str:
        """
        Évite d'écraser le fichier d'une AUTRE musique qui aurait le même nom.
        "Titre.mp3" -> "Titre (2).mp3" -> "Titre (3).mp3"...
        Le fichier précédent de la même musique (`previous_name`) peut être réutilisé.
        """
        candidate = wanted_name
        stem, suffix = Path(wanted_name).stem, Path(wanted_name).suffix
        counter = 2
        while self._path(candidate).exists() and candidate != previous_name:
            candidate = f"{stem} ({counter}){suffix}"
            counter += 1
        return candidate

    def export(self, source: Path, wanted_name: str, previous_name: str = "") -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        final_name = self._unique_name(wanted_name, previous_name)

        # Copie via un fichier temporaire puis remplacement : Spotify ne voit jamais
        # un mp3 à moitié écrit.
        temp_path = self._path(final_name + ".part")
        shutil.copyfile(source, temp_path)
        temp_path.replace(self._path(final_name))

        if previous_name and previous_name != final_name:
            self.remove(previous_name)
        return final_name

    def remove(self, name: str) -> None:
        if name:
            self._path(name).unlink(missing_ok=True)

    def exists(self, name: str) -> bool:
        return bool(name) and self._path(name).exists()
