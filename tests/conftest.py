"""
Fixtures partagées des tests.

On remplace le téléchargement réel (réseau) par `FakeDownloader`, qui génère un vrai
petit mp3 avec ffmpeg : on teste ainsi toute la chaîne (tags, pochette, export) hors ligne.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lofima.api import create_app
from lofima.config import Settings, SettingsStore
from lofima.jobs import JobQueue
from lofima.models import JobStatus
from lofima.progress import NULL_REPORTER
from lofima.repository import TrackRepository
from lofima.service import LibraryService

FAKE_INFO: dict[str, Any] = {
    "id": "abc123XYZ_-",
    "extractor_key": "Youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abc123XYZ_-",
    "title": "Daft Punk - One More Time (Official Video)",
    "channel": "Daft Punk",
    "upload_date": "20090101",
    "duration": 1,
    "thumbnail": "https://example.invalid/thumb.webp",
}


def make_image_bytes(size=(320, 180), color=(200, 30, 30), fmt="PNG") -> bytes:
    """Image factice 16:9 en mémoire."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def sample_mp3(tmp_path_factory) -> Path:
    """Un mp3 d'1 seconde de silence, généré une seule fois pour toute la session."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg requis pour ces tests")
    path = tmp_path_factory.mktemp("media") / "sample.mp3"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", "1", "-q:a", "9", str(path)],
        check=True,
    )
    return path


class FakeDownloader:
    """Respecte le Protocol `Downloader` sans réseau."""

    def __init__(self, sample_mp3: Path, info: dict[str, Any] | None = None) -> None:
        self.sample_mp3 = sample_mp3
        self.info = dict(info or FAKE_INFO)
        self.download_calls = 0

    def fetch_info(self, url: str) -> dict[str, Any]:
        return self.info

    def download_audio(self, url, destination_stem: Path, quality_kbps: int, reporter=NULL_REPORTER) -> Path:
        # Simule l'avancement comme le ferait yt-dlp
        for fraction in (0.0, 0.5, 1.0):
            reporter.step(JobStatus.DOWNLOADING, fraction)
        reporter.step(JobStatus.CONVERTING, None)
        self.download_calls += 1
        destination = destination_stem.with_suffix(".mp3")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.sample_mp3, destination)
        return destination


@pytest.fixture
def env(tmp_path, sample_mp3):
    """Service complet branché sur des dossiers temporaires."""
    export_dir = tmp_path / "spotify"
    settings_store = SettingsStore(tmp_path / "settings.json")
    settings_store.save(Settings(export_dir=str(export_dir)))
    downloader = FakeDownloader(sample_mp3)
    service = LibraryService(
        repository=TrackRepository(tmp_path / "archive" / "metadata"),
        downloader=downloader,
        settings_store=settings_store,
        audio_dir=tmp_path / "archive" / "audio",
        covers_dir=tmp_path / "archive" / "covers",
        fetch_image=lambda url: make_image_bytes(),
    )
    job_queue = JobQueue(processor=lambda url, reporter: service.add_from_url(url, reporter).id)
    client = TestClient(create_app(service, settings_store, job_queue))
    return {
        "service": service,
        "client": client,
        "downloader": downloader,
        "queue": job_queue,
        "export_dir": export_dir,
        "tmp": tmp_path,
    }
