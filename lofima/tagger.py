"""
Écriture des tags ID3 (titre, artiste, pochette...) dans un mp3, avec mutagen.

Spotify lit ces tags pour afficher les fichiers locaux.
On sauvegarde en ID3 v2.3 : c'est la version la mieux supportée
(Spotify et Windows affichent mal certaines pochettes en v2.4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TRCK,
    ID3NoHeaderError,
)

from .models import TrackTags

# Encodage 3 = UTF-8 ; en v2.3 mutagen le convertit automatiquement en UTF-16 (compatible).
_UTF8 = 3


def write_tags(mp3_path: Path, tags: TrackTags, cover_path: Optional[Path] = None) -> None:
    """
    Remplace TOUS les tags du mp3 par ceux fournis.

    :param mp3_path: fichier mp3 à modifier (en place)
    :param tags: métadonnées à écrire ; les champs vides ne sont pas écrits
    :param cover_path: image JPEG à intégrer comme pochette (optionnel)
    """
    try:
        id3 = ID3(mp3_path)
    except ID3NoHeaderError:
        id3 = ID3()  # le fichier n'a encore aucun tag

    # On repart de zéro pour éviter de garder des tags obsolètes (ex : ancienne pochette).
    id3.clear()

    # Correspondance champ -> frame ID3. Seuls les champs non vides sont écrits.
    text_frames = {
        TIT2: tags.title,         # Titre
        TPE1: tags.artist,        # Artiste
        TALB: tags.album,         # Album
        TPE2: tags.album_artist,  # Artiste de l'album
        TDRC: tags.year,          # Année (convertie en TYER en v2.3)
        TCON: tags.genre,         # Genre
        TRCK: tags.track_number,  # Numéro de piste
    }
    for frame_class, value in text_frames.items():
        if value:
            id3.add(frame_class(encoding=_UTF8, text=value))

    if tags.comment:
        id3.add(COMM(encoding=_UTF8, lang="eng", desc="", text=tags.comment))

    if cover_path is not None and cover_path.exists():
        id3.add(
            APIC(
                encoding=_UTF8,
                mime="image/jpeg",
                type=3,  # 3 = "Front cover"
                desc="Cover",
                data=cover_path.read_bytes(),
            )
        )

    id3.save(mp3_path, v2_version=3)
