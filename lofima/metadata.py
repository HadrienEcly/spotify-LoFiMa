"""
Déduction des métadonnées à partir des infos brutes de yt-dlp.

Fonctions PURES (aucun accès disque/réseau) -> faciles à tester (voir tests/test_metadata.py).
Le résultat n'est qu'une proposition : l'utilisateur peut tout corriger dans l'UI.
"""

from __future__ import annotations

import re
from typing import Any

from .models import SourceInfo, TrackTags

# Séparateurs courants entre artiste et titre dans les titres YouTube : "Artiste - Titre"
_ARTIST_TITLE_SEPARATORS = (" - ", " – ", " — ", " | ")

# Mentions parasites à retirer du titre : "(Official Video)", "[Lyrics]", "(Audio)", etc.
# On ne retire que ce qui est entre parenthèses/crochets ET contient un mot-clé connu,
# pour ne pas supprimer des infos utiles comme "(feat. X)" ou "(Remix)".
_NOISE_KEYWORDS = (
    r"official|officiel|video|vid[ée]o|clip|audio|lyrics?|paroles|visuali[sz]er"
    r"|hd|hq|4k|mv|m/v|full album"
)
_NOISE_PATTERN = re.compile(
    rf"\s*[\(\[][^\)\]]*\b(?:{_NOISE_KEYWORDS})\b[^\)\]]*[\)\]]",
    flags=re.IGNORECASE,
)

# Les chaînes auto-générées par YouTube Music s'appellent "Artiste - Topic"
_TOPIC_SUFFIX = re.compile(r"\s*-\s*Topic$", flags=re.IGNORECASE)


def clean_title(raw_title: str) -> str:
    """Retire les mentions parasites et les espaces superflus d'un titre."""
    cleaned = _NOISE_PATTERN.sub("", raw_title)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def split_artist_title(raw_title: str) -> tuple[str, str]:
    """
    Sépare "Artiste - Titre" en (artiste, titre).
    Retourne ("", titre) si aucun séparateur n'est trouvé.
    """
    for separator in _ARTIST_TITLE_SEPARATORS:
        if separator in raw_title:
            artist, title = raw_title.split(separator, 1)
            return artist.strip(), title.strip()
    return "", raw_title.strip()


def build_source_info(info: dict[str, Any], url: str) -> SourceInfo:
    """Construit les infos d'origine (non modifiables) depuis le dict yt-dlp."""
    return SourceInfo(
        url=info.get("webpage_url") or url,
        video_id=str(info.get("id", "")),
        extractor=str(info.get("extractor_key") or info.get("extractor") or "youtube").lower(),
        channel=info.get("channel") or info.get("uploader") or "",
        original_title=info.get("title") or "",
        upload_date=info.get("upload_date") or "",
        duration_seconds=int(info.get("duration") or 0),
        thumbnail_url=info.get("thumbnail") or "",
        description=info.get("description") or "",
    )


def guess_tags(info: dict[str, Any]) -> TrackTags:
    """
    Propose des tags ID3 à partir des infos yt-dlp.

    Priorité :
      1. Champs "musique" fournis par YouTube Music (track, artist, album, release_year).
      2. Sinon, découpage du titre de la vidéo "Artiste - Titre".
      3. Sinon, nom de la chaîne comme artiste.
    """
    raw_title = info.get("title") or ""
    channel = _TOPIC_SUFFIX.sub("", info.get("channel") or info.get("uploader") or "")

    # --- Titre & artiste ---
    if info.get("track"):
        title = info["track"]
        # yt-dlp peut renvoyer "A, B" dans `artist` ; on garde tel quel (lisible dans Spotify)
        artist = info.get("artist") or info.get("creator") or channel
    else:
        artist, title = split_artist_title(clean_title(raw_title))
        if not artist:
            artist = channel

    # --- Année : date de sortie si connue, sinon date de mise en ligne ---
    year = ""
    if info.get("release_year"):
        year = str(info["release_year"])
    elif info.get("upload_date"):
        year = str(info["upload_date"])[:4]

    return TrackTags(
        title=clean_title(title),
        artist=artist.strip(),
        album=info.get("album") or "",
        album_artist="",
        year=year,
        genre=info.get("genre") or "",
        track_number="",
        # On garde le lien d'origine dans le commentaire : visible dans les lecteurs mp3.
        comment=info.get("webpage_url") or "",
    )
