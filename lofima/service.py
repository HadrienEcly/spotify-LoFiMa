"""
Service principal : orchestre les modules (téléchargement, tags, pochette, archive, export).

C'est le SEUL endroit qui connaît l'enchaînement des étapes. L'API web (api.py) ne fait
qu'appeler ces méthodes. Toutes les dépendances sont injectées dans le constructeur,
ce qui permet de les remplacer par des faux objets dans les tests.

Cycle de vie d'une musique :
    lien YouTube
      -> fetch_info (métadonnées)            -> archive/metadata/<id>.json
      -> download_audio (mp3)                -> archive/audio/<id>.mp3
      -> miniature (jpg carré)               -> archive/covers/<id>.jpg
      -> write_tags (tags ID3 + pochette dans le mp3 de l'archive)
      -> export (copie "Artiste - Titre.mp3") -> dossier Spotify
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import covers, metadata, tagger
from .config import Settings, SettingsStore
from .downloader import Downloader
from .errors import DownloadError, LofimaError, TrackAlreadyExistsError
from .exporter import Exporter, LocalFolderExporter, safe_filename
from .models import Track, TrackTagsUpdate, TrackView
from .repository import TrackRepository


@dataclass
class SyncReport:
    """Résultat d'une resynchronisation globale (affiché dans l'UI)."""

    exported: list[str] = field(default_factory=list)      # ids réexportés
    redownloaded: list[str] = field(default_factory=list)  # ids dont le mp3 manquait
    errors: dict[str, str] = field(default_factory=dict)   # id -> message d'erreur


def _default_exporter_factory(settings: Settings) -> Exporter:
    """Par défaut : export vers le dossier local défini dans les réglages."""
    return LocalFolderExporter(Path(settings.export_dir))


class LibraryService:
    def __init__(
        self,
        repository: TrackRepository,
        downloader: Downloader,
        settings_store: SettingsStore,
        audio_dir: Path,
        covers_dir: Path,
        exporter_factory: Callable[[Settings], Exporter] = _default_exporter_factory,
        fetch_image: Callable[[str], bytes] = covers.fetch_image_bytes,
    ) -> None:
        self._repo = repository
        self._downloader = downloader
        self._settings_store = settings_store
        self._audio_dir = audio_dir
        self._covers_dir = covers_dir
        self._exporter_factory = exporter_factory
        self._fetch_image = fetch_image
        # Verrou global des MODIFICATIONS (tags, export) : évite que deux requêtes
        # réécrivent le même mp3 en même temps. Les téléchargements réseau, eux,
        # se font hors verrou pour ne pas bloquer l'UI.
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Chemins & helpers
    # ------------------------------------------------------------------ #

    def audio_path(self, track_id: str) -> Path:
        return self._audio_dir / f"{track_id}.mp3"

    def cover_path(self, track_id: str) -> Path:
        return self._covers_dir / f"{track_id}.jpg"

    def _settings(self) -> Settings:
        return self._settings_store.load()

    def _exporter(self) -> Exporter:
        # Recréé à chaque fois : prend en compte un changement de dossier dans les réglages.
        return self._exporter_factory(self._settings())

    @staticmethod
    def _export_name(track: Track) -> str:
        """Nom du fichier dans le dossier Spotify : "Artiste - Titre.mp3"."""
        tags = track.tags
        stem = f"{tags.artist} - {tags.title}" if tags.artist else (tags.title or track.id)
        return safe_filename(stem)

    def to_view(self, track: Track) -> TrackView:
        """Ajoute à un Track les infos de présence des fichiers (pour l'UI)."""
        return TrackView(
            **track.model_dump(),
            has_audio=self.audio_path(track.id).exists(),
            has_cover=self.cover_path(track.id).exists(),
            is_exported=self._exporter().exists(track.exported_filename),
        )

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #

    def list_tracks(self) -> list[TrackView]:
        return [self.to_view(t) for t in self._repo.list()]

    def get_track(self, track_id: str) -> TrackView:
        return self.to_view(self._repo.get(track_id))

    # ------------------------------------------------------------------ #
    # Ajout
    # ------------------------------------------------------------------ #

    def add_from_url(self, url: str) -> TrackView:
        """Télécharge une vidéo et l'ajoute à la bibliothèque. Étape la plus longue."""
        url = url.strip()
        if not url:
            raise DownloadError("Le lien est vide.")

        info = self._downloader.fetch_info(url)
        source = metadata.build_source_info(info, url)
        track_id = f"{source.extractor}-{source.video_id}"
        if self._repo.exists(track_id):
            raise TrackAlreadyExistsError(track_id)

        track = Track(id=track_id, source=source, tags=metadata.guess_tags(info))

        try:
            self._download_files(track)
            with self._lock:
                self._apply_tags_and_export(track)
                self._repo.save(track)
        except Exception:
            # Échec en cours de route : on ne laisse pas de fichiers orphelins.
            self.audio_path(track_id).unlink(missing_ok=True)
            self.cover_path(track_id).unlink(missing_ok=True)
            raise
        return self.to_view(track)

    def _download_files(self, track: Track) -> None:
        """Télécharge le mp3 et la miniature dans l'archive."""
        settings = self._settings()
        self._downloader.download_audio(
            track.source.url,
            self._audio_dir / track.id,  # sans extension, yt-dlp ajoute ".mp3"
            settings.audio_quality_kbps,
        )
        if track.source.thumbnail_url:
            try:
                raw = self._fetch_image(track.source.thumbnail_url)
                covers.process_cover(raw, self.cover_path(track.id), settings.crop_cover_square)
            except LofimaError:
                # Une miniature manquante ne doit pas faire échouer tout l'ajout :
                # l'utilisateur pourra en envoyer une depuis l'UI.
                pass

    def _apply_tags_and_export(self, track: Track) -> None:
        """Écrit les tags dans le mp3 de l'archive puis le copie vers le dossier Spotify."""
        mp3 = self.audio_path(track.id)
        tagger.write_tags(mp3, track.tags, self.cover_path(track.id))
        track.exported_filename = self._exporter().export(
            mp3, self._export_name(track), previous_name=track.exported_filename
        )

    # ------------------------------------------------------------------ #
    # Modification
    # ------------------------------------------------------------------ #

    def update_tags(self, track_id: str, update: TrackTagsUpdate) -> TrackView:
        """Modifie les métadonnées (champs envoyés uniquement), retague et réexporte."""
        with self._lock:
            track = self._repo.get(track_id)
            changes = update.model_dump(exclude_none=True)
            track.tags = track.tags.model_copy(update={k: v.strip() for k, v in changes.items()})
            track.touch()
            if self.audio_path(track_id).exists():
                self._apply_tags_and_export(track)
            self._repo.save(track)
        return self.to_view(track)

    def replace_cover(self, track_id: str, raw_image: bytes) -> TrackView:
        """Remplace la pochette par une image envoyée par l'utilisateur."""
        with self._lock:
            track = self._repo.get(track_id)
            covers.process_cover(raw_image, self.cover_path(track_id), self._settings().crop_cover_square)
            track.touch()
            if self.audio_path(track_id).exists():
                self._apply_tags_and_export(track)
            self._repo.save(track)
        return self.to_view(track)

    # ------------------------------------------------------------------ #
    # Suppression
    # ------------------------------------------------------------------ #

    def delete_track(self, track_id: str, keep_archive: bool) -> None:
        """
        Retire la musique du dossier Spotify.
        :param keep_archive: True  -> garde la copie de sauvegarde (JSON + mp3 + pochette)
                                      et on pourra la réexporter plus tard ;
                             False -> supprime tout définitivement.
        """
        with self._lock:
            track = self._repo.get(track_id)
            self._exporter().remove(track.exported_filename)
            if keep_archive:
                track.exported_filename = ""
                track.touch()
                self._repo.save(track)
            else:
                self.audio_path(track_id).unlink(missing_ok=True)
                self.cover_path(track_id).unlink(missing_ok=True)
                self._repo.delete(track_id)

    # ------------------------------------------------------------------ #
    # Restauration / synchronisation
    # ------------------------------------------------------------------ #

    def export_track(self, track_id: str) -> TrackView:
        """(Ré)exporte une musique de l'archive vers le dossier Spotify."""
        with self._lock:
            track = self._repo.get(track_id)
            if not self.audio_path(track_id).exists():
                raise DownloadError("Le mp3 n'est pas dans l'archive : utilise « Re-télécharger ».")
            self._apply_tags_and_export(track)
            track.touch()
            self._repo.save(track)
        return self.to_view(track)

    def redownload(self, track_id: str) -> TrackView:
        """
        Re-télécharge le mp3/la pochette depuis le lien d'origine, en CONSERVANT les
        métadonnées modifiées. Utile après un clone du dépôt (seuls les JSON sont versionnés).
        """
        track = self._repo.get(track_id)
        self._download_files(track)
        return self.export_track(track_id)

    def sync_all(self) -> SyncReport:
        """
        Pour chaque musique : re-télécharge le mp3 s'il manque, puis réexporte.
        À lancer après un changement de dossier d'export ou un clone sur un nouveau PC.
        Les musiques retirées de Spotify (exported_filename vide) sont ignorées.
        """
        report = SyncReport()
        for track in self._repo.list():
            if not track.exported_filename:
                continue  # retirée volontairement de Spotify
            try:
                if not self.audio_path(track.id).exists():
                    self.redownload(track.id)
                    report.redownloaded.append(track.id)
                else:
                    self.export_track(track.id)
                report.exported.append(track.id)
            except LofimaError as exc:
                report.errors[track.id] = str(exc)
        return report
