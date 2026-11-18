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
from .jobs import JobQueue
from .models import AddJobsRequest, AddTrackRequest, CropBox, Job, TrackTagsUpdate, TrackView
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


def create_app(service: LibraryService, settings_store: SettingsStore, job_queue: JobQueue) -> FastAPI:
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
        """Ajout SYNCHRONE (attend la fin du téléchargement). L'UI utilise plutôt /api/jobs."""
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

    # ------------------------- File d'attente --------------------------- #

    @app.get("/api/jobs", response_model=list[Job])
    def list_jobs():
        return job_queue.list()

    @app.post("/api/jobs", response_model=list[Job], status_code=202)
    def add_jobs(body: AddJobsRequest):
        """Ajoute des liens à la file ; répond tout de suite (202 = accepté, traité plus tard)."""
        jobs = job_queue.submit(body.urls)
        if not jobs:
            raise HTTPException(status_code=422, detail="Aucun lien fourni.")
        return jobs

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def remove_job(job_id: str):
        if not job_queue.remove(job_id):
            raise HTTPException(status_code=409, detail="Ce téléchargement est en cours ou introuvable.")

    @app.post("/api/jobs/clear")
    def clear_finished_jobs():
        return {"removed": job_queue.clear_finished()}

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

    @app.get("/api/tracks/{track_id}/cover/source")
    def get_cover_source(track_id: str):
        """
        Image d'origine non recadrée (affichée dans l'outil de recadrage).
        Pour les musiques ajoutées avant cette fonctionnalité, elle est recréée à la volée
        (miniature YouTube re-téléchargée, sinon pochette actuelle) ; 400 si aucune image.
        """
        return FileResponse(service.ensure_cover_source(track_id), media_type="image/jpeg")

    @app.put("/api/tracks/{track_id}/cover/crop", response_model=TrackView)
    def crop_cover(track_id: str, body: CropBox):
        return service.set_cover_crop(track_id, body)

    @app.delete("/api/tracks/{track_id}/cover/crop", response_model=TrackView)
    def reset_cover_crop(track_id: str):
        """Revient au cadrage automatique (carré centré)."""
        return service.set_cover_crop(track_id, None)

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
