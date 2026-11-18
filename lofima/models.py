"""
Modèles de données (Pydantic).

`Track` est l'objet central : une musique de la bibliothèque.
Il est sérialisé tel quel dans `archive/metadata/<id>.json`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    """Date/heure actuelle en ISO 8601 (UTC), utilisée pour created_at / updated_at."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class TrackTags(BaseModel):
    """
    Métadonnées MODIFIABLES par l'utilisateur.
    Ce sont exactement celles écrites dans les tags ID3 du mp3 (lues par Spotify).
    """

    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    year: str = ""          # string pour accepter "" (inconnu) ou "2021"
    genre: str = ""
    track_number: str = ""  # ex : "3" ou "3/12"
    comment: str = ""


class TrackTagsUpdate(BaseModel):
    """
    Corps d'une requête de modification : tous les champs sont optionnels,
    seuls ceux envoyés sont mis à jour (PATCH partiel).
    """

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    track_number: Optional[str] = None
    comment: Optional[str] = None


class SourceInfo(BaseModel):
    """
    Infos d'origine (YouTube), NON modifiables.
    Conservées pour pouvoir re-télécharger si le fichier local est perdu,
    et pour garder une trace si la vidéo disparaît.
    """

    url: str
    video_id: str
    extractor: str = "youtube"
    channel: str = ""
    original_title: str = ""
    upload_date: str = ""        # format yt-dlp : "YYYYMMDD"
    duration_seconds: int = 0
    thumbnail_url: str = ""
    description: str = ""


class Track(BaseModel):
    """Une musique de la bibliothèque."""

    # Identifiant interne = "<extractor>-<video_id>", stable et unique.
    id: str
    source: SourceInfo
    tags: TrackTags = Field(default_factory=TrackTags)

    # Nom du fichier actuellement présent dans le dossier d'export Spotify
    # (permet de le renommer/supprimer proprement si le titre change).
    exported_filename: str = ""

    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)

    def touch(self) -> None:
        """Met à jour la date de modification."""
        self.updated_at = _now_iso()


class TrackView(Track):
    """
    Vue envoyée à l'UI : le Track + des infos calculées à la volée
    (présence des fichiers sur disque). Jamais écrite dans le JSON.
    """

    has_audio: bool = False
    has_cover: bool = False
    is_exported: bool = False


class AddTrackRequest(BaseModel):
    """Corps de POST /api/tracks."""

    url: str
