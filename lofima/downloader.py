"""
Téléchargement depuis YouTube via yt-dlp.

On isole yt-dlp derrière une petite classe `YtDlpDownloader` : si un jour on change
d'outil (ou pour les tests), il suffit de fournir un autre objet avec les mêmes méthodes
(voir le Protocol `Downloader`).

Pré-requis : ffmpeg doit être installé et accessible dans le PATH
(yt-dlp l'utilise pour convertir l'audio en mp3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import yt_dlp

from .errors import DownloadError


class Downloader(Protocol):
    """Interface attendue par le service. Toute classe avec ces 2 méthodes convient."""

    def fetch_info(self, url: str) -> dict[str, Any]:
        """Retourne les infos de la vidéo SANS télécharger le média."""
        ...

    def download_audio(self, url: str, destination_stem: Path, quality_kbps: int) -> Path:
        """Télécharge l'audio en mp3 vers `<destination_stem>.mp3` et retourne ce chemin."""
        ...


class YtDlpDownloader:
    """Implémentation réelle basée sur yt-dlp + ffmpeg."""

    # Options communes à tous les appels yt-dlp
    _BASE_OPTIONS: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        # Un lien de vidéo dans une playlist (?list=...) ne télécharge QUE la vidéo.
        "noplaylist": True,
    }

    def fetch_info(self, url: str) -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(self._BASE_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(f"Lien illisible ou vidéo indisponible : {exc}") from exc

        if info is None:
            raise DownloadError("Aucune information trouvée pour ce lien.")
        # Sécurité : si malgré tout yt-dlp renvoie une playlist, on refuse clairement.
        if info.get("_type") == "playlist":
            raise DownloadError("Les playlists ne sont pas supportées : colle le lien d'une seule vidéo.")
        return info

    def download_audio(self, url: str, destination_stem: Path, quality_kbps: int) -> Path:
        destination_stem.parent.mkdir(parents=True, exist_ok=True)
        options = {
            **self._BASE_OPTIONS,
            "format": "bestaudio/best",
            # yt-dlp ajoute lui-même l'extension -> on lui donne le chemin sans extension.
            "outtmpl": str(destination_stem) + ".%(ext)s",
            "overwrites": True,
            "postprocessors": [
                {
                    # Conversion en mp3 via ffmpeg
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(quality_kbps),
                }
            ],
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            raise DownloadError(f"Échec du téléchargement : {exc}") from exc

        mp3_path = destination_stem.with_suffix(".mp3")
        if not mp3_path.exists():
            # Typiquement : ffmpeg absent du PATH, la conversion n'a pas eu lieu.
            raise DownloadError(
                "Le mp3 n'a pas été créé. Vérifie que ffmpeg est installé et dans le PATH."
            )
        return mp3_path
