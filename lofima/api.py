"""
Couche HTTP (FastAPI) : traduit les requêtes web en appels au `LibraryService`.

Aucune logique métier ici : uniquement validation des entrées, appel du service,
et conversion des exceptions métier en codes HTTP.

Note : les routes sont des fonctions `def` (et non `async def`) : FastAPI les exécute
dans un thread séparé, donc un téléchargement long ne bloque pas les autres requêtes.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, SettingsStore, WEB_DIR
from .errors import (
    DownloadError,
    InvalidCoverError,
    LofimaError,
    TrackAlreadyExistsError,
    TrackNotFoundError,
)
from .models import AddTrackRequest, TrackTagsUpdate, TrackView
from .service import LibraryService

# Taille max d'une pochette envoyée (évite de saturer la mémoire avec un énorme fichier)
MAX_COVER_UPLOAD_BYTES = 15 * 1024 * 1024

# Exception métier -> code HTTP
_ERROR_STATUS: dict[type[LofimaError], int] = {
    TrackNotFoundError: 404,
    TrackAlreadyExistsError: 409,
    DownloadError: 422,
    InvalidCoverError: 400,
}


def create_app(service: LibraryService, settings_store: SettingsStore) -> FastAPI:
    """Construit l'application. Les dépendances sont injectées (tests = faux service)."""
    app = FastAPI(title="LoFiMa - Local File Manager")

    @app.exception_handler(LofimaError)
    def handle_lofima_error(_: Request, exc: LofimaError) -> JSONResponse:
        status = next((code for cls, code in _ERROR_STATUS.items() if isinstance(exc, cls)), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    # ----------------------------- Musiques ----------------------------- #

    @app.get("/api/tracks", response_model=list[TrackView])
    def list_tracks():
        return service.list_tracks()

    @app.post("/api/tracks", response_model=TrackView, status_code=201)
    def add_track(body: AddTrackRequest):
        return service.add_from_url(body.url)

    @app.get("/api/tracks/{track_id}", response_model=TrackView)
    def get_track(track_id: str):
        return service.get_track(track_id)

    @app.patch("/api/tracks/{track_id}", response_model=TrackView)
    def update_track(track_id: str, body: TrackTagsUpdate):
        return service.update_tags(track_id, body)

    @app.delete("/api/tracks/{track_id}", status_code=204)
    def delete_track(track_id: str, keep_archive: bool = True):
        # Par défaut on GARDE l'archive : supprimer définitivement doit être explicite.
        service.delete_track(track_id, keep_archive=keep_archive)

    @app.post("/api/tracks/{track_id}/export", response_model=TrackView)
    def export_track(track_id: str):
        return service.export_track(track_id)

    @app.post("/api/tracks/{track_id}/redownload", response_model=TrackView)
    def redownload_track(track_id: str):
        return service.redownload(track_id)

    # ------------------------- Fichiers (média) ------------------------- #

    @app.get("/api/tracks/{track_id}/cover")
    def get_cover(track_id: str):
        service.get_track(track_id)  # 404 si l'id est inconnu ou invalide
        path = service.cover_path(track_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Pas de pochette.")
        return FileResponse(path, media_type="image/jpeg")

    @app.put("/api/tracks/{track_id}/cover", response_model=TrackView)
    def upload_cover(track_id: str, file: UploadFile = File(...)):
        raw = file.file.read(MAX_COVER_UPLOAD_BYTES + 1)
        if len(raw) > MAX_COVER_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image trop lourde (15 Mo max).")
        return service.replace_cover(track_id, raw)

    @app.get("/api/tracks/{track_id}/audio")
    def get_audio(track_id: str):
        """Permet d'écouter la musique directement dans l'UI."""
        service.get_track(track_id)
        path = service.audio_path(track_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Pas de mp3 dans l'archive.")
        return FileResponse(path, media_type="audio/mpeg")

    # ------------------------- Réglages & sync -------------------------- #

    @app.get("/api/settings", response_model=Settings)
    def get_settings():
        return settings_store.load()

    @app.put("/api/settings", response_model=Settings)
    def update_settings(body: Settings):
        return settings_store.save(body)

    @app.post("/api/sync")
    def sync_all():
        return asdict(service.sync_all())

    # ----------------------- Interface web (statique) ------------------- #
    # Monté en DERNIER : sinon "/" intercepterait les routes /api.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app
