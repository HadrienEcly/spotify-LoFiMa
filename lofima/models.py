"""
Modèles de données (Pydantic).

`Track` est l'objet central : une musique de la bibliothèque.
Il est sérialisé tel quel dans `archive/metadata/<id>.json`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
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


class CropBox(BaseModel):
    """
    Zone carrée à garder dans l'image d'origine (miniature YouTube ou image envoyée).

    Les valeurs sont des FRACTIONS (0 à 1) et non des pixels : le cadrage reste valable
    si l'image d'origine est re-téléchargée dans une autre résolution.
      - left : position du bord gauche, en fraction de la LARGEUR de l'image
      - top  : position du bord haut, en fraction de la HAUTEUR de l'image
      - size : côté du carré, en fraction du PLUS PETIT côté de l'image
               (size = 1 -> le plus grand carré possible)
    """

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    size: float = Field(gt=0, le=1)


class Track(BaseModel):
    """Une musique de la bibliothèque."""

    # Identifiant interne = "<extractor>-<video_id>", stable et unique.
    id: str
    source: SourceInfo
    tags: TrackTags = Field(default_factory=TrackTags)

    # Nom du fichier actuellement présent dans le dossier d'export Spotify
    # (permet de le renommer/supprimer proprement si le titre change).
    exported_filename: str = ""

    # Cadrage choisi par l'utilisateur. None = cadrage automatique
    # (carré centré, ou image entière si le réglage "recadrer en carré" est désactivé).
    cover_crop: Optional[CropBox] = None

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
    has_cover_source: bool = False  # image d'origine dispo -> recadrage possible
    is_exported: bool = False


class AddTrackRequest(BaseModel):
    """Corps de POST /api/tracks."""

    url: str


# --------------------------------------------------------------------------- #
# File d'attente des téléchargements
# --------------------------------------------------------------------------- #

class JobStatus(str, Enum):
    """
    Étapes d'un téléchargement, dans l'ordre. Hérite de `str` pour être
    sérialisé en texte lisible dans le JSON ("downloading", etc.).
    """

    QUEUED = "queued"            # en attente dans la file
    FETCHING_INFO = "fetching"   # lecture des infos de la vidéo
    DOWNLOADING = "downloading"  # téléchargement de l'audio (progress = 0..1)
    CONVERTING = "converting"    # conversion en mp3 par ffmpeg
    FINALIZING = "finalizing"    # pochette, tags, export
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_finished(self) -> bool:
        """True si le job ne bougera plus (terminé, en erreur ou annulé)."""
        return self in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)


class Job(BaseModel):
    """Un lien dans la file d'attente."""

    id: str
    url: str
    status: JobStatus = JobStatus.QUEUED
    # Avancement de l'étape en cours (0 à 1), ou None si inconnu (barre "indéterminée").
    progress: Optional[float] = None
    title: str = ""              # titre de la vidéo dès qu'il est connu
    track_id: Optional[str] = None  # rempli quand le job est terminé avec succès
    error: str = ""
    created_at: str = Field(default_factory=_now_iso)


class AddJobsRequest(BaseModel):
    """Corps de POST /api/jobs : un ou plusieurs liens."""

    urls: list[str]
