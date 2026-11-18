"""
Persistance de la bibliothèque : un fichier JSON par musique dans `archive/metadata/`.

Pourquoi un fichier par musique (et pas une base de données) ?
  - lisible et modifiable à la main ;
  - diff Git clair (une musique ajoutée = un fichier ajouté) ;
  - pas de conflit de merge sur un gros fichier unique.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

from .errors import TrackNotFoundError
from .models import Track

# Un identifiant ne doit contenir que des caractères sûrs : empêche qu'un id malveillant
# comme "../../settings" sorte du dossier metadata.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_track_id(track_id: str) -> str:
    """Lève TrackNotFoundError si l'id contient des caractères non autorisés."""
    if not _SAFE_ID.match(track_id):
        raise TrackNotFoundError(f"Identifiant invalide : {track_id!r}")
    return track_id


class TrackRepository:
    """Lecture/écriture des `Track` sous forme de fichiers JSON."""

    def __init__(self, metadata_dir: Path) -> None:
        self._dir = metadata_dir
        self._lock = threading.Lock()

    def _path(self, track_id: str) -> Path:
        return self._dir / f"{validate_track_id(track_id)}.json"

    def list(self) -> list[Track]:
        """Toutes les musiques, de la plus récente à la plus ancienne."""
        tracks = [
            Track.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self._dir.glob("*.json")
        ]
        return sorted(tracks, key=lambda t: t.created_at, reverse=True)

    def find(self, track_id: str) -> Optional[Track]:
        """La musique demandée, ou None si absente."""
        path = self._path(track_id)
        if not path.exists():
            return None
        return Track.model_validate_json(path.read_text(encoding="utf-8"))

    def get(self, track_id: str) -> Track:
        """Comme `find`, mais lève TrackNotFoundError si absente."""
        track = self.find(track_id)
        if track is None:
            raise TrackNotFoundError(f"Musique introuvable : {track_id}")
        return track

    def exists(self, track_id: str) -> bool:
        return self._path(track_id).exists()

    def save(self, track: Track) -> Track:
        """Crée ou remplace le JSON de la musique (écriture atomique)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(track.id)
        temp_path = path.with_suffix(".json.tmp")
        with self._lock:
            temp_path.write_text(track.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(path)
        return track

    def delete(self, track_id: str) -> None:
        self._path(track_id).unlink(missing_ok=True)
