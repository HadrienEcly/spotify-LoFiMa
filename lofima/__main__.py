"""
Point d'entrée : `python -m lofima`

Assemble les dépendances réelles, démarre le serveur local et ouvre le navigateur.
Le serveur écoute uniquement sur 127.0.0.1 : il n'est pas accessible depuis le réseau.
"""

from __future__ import annotations

import argparse
import shutil
import threading
import webbrowser

import uvicorn

from .api import create_app
from .config import AUDIO_DIR, COVERS_DIR, METADATA_DIR, SettingsStore, ensure_archive_dirs
from .downloader import YtDlpDownloader
from .jobs import JobQueue
from .repository import TrackRepository
from .service import LibraryService


def build_app():
    """Crée l'application avec les vraies implémentations."""
    ensure_archive_dirs()
    settings_store = SettingsStore()
    service = LibraryService(
        repository=TrackRepository(METADATA_DIR),
        downloader=YtDlpDownloader(),
        settings_store=settings_store,
        audio_dir=AUDIO_DIR,
        covers_dir=COVERS_DIR,
    )
    # La file appelle le service pour chaque lien ; on ne garde que l'id du résultat.
    job_queue = JobQueue(processor=lambda url, reporter: service.add_from_url(url, reporter).id)
    return create_app(service, settings_store, job_queue)


def main() -> None:
    parser = argparse.ArgumentParser(description="LoFiMa - YouTube vers fichiers locaux Spotify")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("ATTENTION : ffmpeg introuvable dans le PATH, la conversion en mp3 échouera.")
        print("            Windows : lance install.bat (il installe ffmpeg avec winget)")

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        # Petit délai : laisse le serveur démarrer avant d'ouvrir la page.
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"LoFiMa démarré sur {url}  (Ctrl+C pour arrêter)")
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
