"""
Point d'entrée : `python -m lofima`

Assemble les dépendances réelles, démarre le serveur local et ouvre le navigateur.

Par défaut le serveur écoute uniquement sur 127.0.0.1 (le PC lui-même).
Si "Accès depuis le téléphone" est activé dans les réglages, il écoute sur 0.0.0.0
(toutes les interfaces réseau) : les autres appareils du Wi-Fi peuvent s'y connecter,
avec le code d'accès (voir access.py). Windows demandera alors d'autoriser Python
dans le pare-feu : cocher "Réseaux privés".
"""

from __future__ import annotations

import argparse
import shutil
import threading
import webbrowser

import uvicorn

from . import access
from .api import create_app
from .config import AUDIO_DIR, COVERS_DIR, DEVICES_FILE, METADATA_DIR, SettingsStore, ensure_archive_dirs
from .devices import DeviceRegistry
from .downloader import YtDlpDownloader
from .jobs import JobQueue
from .repository import TrackRepository
from .service import LibraryService


def build_app(settings_store: SettingsStore, listening_on_lan: bool):
    """Crée l'application avec les vraies implémentations."""
    ensure_archive_dirs()
    service = LibraryService(
        repository=TrackRepository(METADATA_DIR),
        downloader=YtDlpDownloader(),
        settings_store=settings_store,
        audio_dir=AUDIO_DIR,
        covers_dir=COVERS_DIR,
    )
    # La file appelle le service pour chaque lien ; on ne garde que l'id du résultat.
    job_queue = JobQueue(processor=lambda url, reporter: service.add_from_url(url, reporter).id)
    return create_app(
        service,
        settings_store,
        job_queue,
        DeviceRegistry(DEVICES_FILE),
        listening_on_lan=listening_on_lan,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="LoFiMa - YouTube vers fichiers locaux Spotify")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None:
        print("ATTENTION : ffmpeg introuvable dans le PATH, la conversion en mp3 échouera.")
        print("            Windows : lance install.bat (il installe ffmpeg avec winget)")

    settings_store = SettingsStore()
    lan = settings_store.load().lan_access
    host = "0.0.0.0" if lan else "127.0.0.1"

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        # Petit délai : laisse le serveur démarrer avant d'ouvrir la page.
        threading.Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"LoFiMa démarré sur {url}  (Ctrl+C pour arrêter)")
    if lan:
        print(f"Accès téléphone ACTIVÉ sur http://{access.lan_ip()}:{args.port}")
        print("  -> scanne le QR code dans Réglages › Accès depuis le téléphone")
    uvicorn.run(build_app(settings_store, lan), host=host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
