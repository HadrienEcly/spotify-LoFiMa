"""
Couche HTTP (FastAPI) : traduit les requêtes web en appels au `LibraryService`.

Aucune logique métier ici : uniquement contrôle d'accès, validation des entrées,
appel du service, et conversion des exceptions métier en codes HTTP.

Note : les routes sont des fonctions `def` (et non `async def`) : FastAPI les exécute
dans un thread séparé, donc un téléchargement long ne bloque pas les autres requêtes.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import access
from .config import Settings, SettingsStore, UserSettings, WEB_DIR
from .devices import Device, DeviceMode, DeviceRegistry, DeviceUpdate, is_valid_device_id, new_device_id
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


def create_app(
    service: LibraryService,
    settings_store: SettingsStore,
    job_queue: JobQueue,
    devices: DeviceRegistry,
    *,
    local_hosts: frozenset[str] = access.LOOPBACK_HOSTS,
    listening_on_lan: bool = False,
) -> FastAPI:
    """
    Construit l'application. Les dépendances sont injectées (tests = faux objets).

    :param local_hosts: adresses considérées comme "le PC lui-même" (modifiable pour les tests)
    :param listening_on_lan: True si le serveur a été démarré en écoute sur le réseau local
                             (sert à prévenir l'UI qu'un redémarrage est nécessaire)
    """
    app = FastAPI(title="LoFiMa - Local File Manager")

    @app.exception_handler(LofimaError)
    def handle_lofima_error(_: Request, exc: LofimaError) -> JSONResponse:
        status = next((code for cls, code in _ERROR_STATUS.items() if isinstance(exc, cls)), 500)
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    # ===================================================================== #
    # Contrôle d'accès (exécuté AVANT chaque requête, y compris les fichiers web)
    # ===================================================================== #

    @app.middleware("http")
    async def access_control(request: Request, call_next):
        client_host = request.client.host if request.client else ""
        is_local = client_host in local_hosts

        if not is_local:
            # Lecture de fichier -> dans un thread pour ne pas bloquer le serveur
            settings = await run_in_threadpool(settings_store.load)
            if not settings.lan_access:
                return JSONResponse(status_code=403, content={"detail": "Accès réseau désactivé."})

            # 1re connexion via le QR code : ?token=... -> on pose le cookie puis on
            # redirige vers la même page SANS le code dans l'URL (historique, captures...).
            url_token = request.query_params.get("token")
            if url_token is not None and request.method == "GET":
                if not access.token_matches(url_token, settings.access_token):
                    return HTMLResponse(access.LOGIN_PAGE_HTML, status_code=401)
                clean_url = request.url.remove_query_params("token")
                response = RedirectResponse(str(clean_url), status_code=303)
                response.set_cookie(
                    access.TOKEN_COOKIE, url_token,
                    max_age=access.COOKIE_MAX_AGE, httponly=True, samesite="lax",
                )
                return response

            if not access.token_matches(request.cookies.get(access.TOKEN_COOKIE), settings.access_token):
                if request.url.path.startswith("/api/"):
                    return JSONResponse(status_code=401, content={"detail": "Code d'accès manquant ou invalide."})
                return HTMLResponse(access.LOGIN_PAGE_HTML, status_code=401)

        # Identification de l'appareil (cookie posé à la 1re visite)
        device_id = request.cookies.get(access.DEVICE_COOKIE)
        is_new_device = not is_valid_device_id(device_id)
        if is_new_device:
            device_id = new_device_id()
        device = await run_in_threadpool(
            devices.touch, device_id, request.headers.get("user-agent", ""), is_local
        )
        request.state.device = device
        request.state.is_local = is_local

        response = await call_next(request)
        if is_new_device:
            response.set_cookie(
                access.DEVICE_COOKIE, device_id,
                max_age=access.COOKIE_MAX_AGE, httponly=True, samesite="lax",
            )
        return response

    def require_local(request: Request) -> None:
        """Dépendance FastAPI : réserve une route au PC lui-même."""
        if not request.state.is_local:
            raise HTTPException(status_code=403, detail="Action possible uniquement depuis le PC.")

    def current_device(request: Request) -> Device:
        """Dépendance FastAPI : l'appareil qui fait la requête (posé par le middleware)."""
        return request.state.device

    def for_device(view: TrackView, device: Device) -> TrackView:
        """Ajoute à la vue l'état de la musique pour un appareil en mode téléchargement."""
        if device.mode == DeviceMode.DOWNLOAD:
            view.device_state = device.state_of(view).value
        return view

    # ===================================================================== #
    # Musiques
    # ===================================================================== #

    @app.get("/api/tracks", response_model=list[TrackView])
    def list_tracks(device: Device = Depends(current_device)):
        # Relecture de l'appareil : `downloaded` a pu changer depuis le début de la requête
        device = devices.get(device.id) or device
        return [for_device(view, device) for view in service.list_tracks()]

    @app.post("/api/tracks", response_model=TrackView, status_code=201)
    def add_track(body: AddTrackRequest, device: Device = Depends(current_device)):
        """Ajout SYNCHRONE (attend la fin du téléchargement). L'UI utilise plutôt /api/jobs."""
        return for_device(service.add_from_url(body.url), device)

    @app.get("/api/tracks/{track_id}", response_model=TrackView)
    def get_track(track_id: str, device: Device = Depends(current_device)):
        device = devices.get(device.id) or device
        return for_device(service.get_track(track_id), device)

    @app.patch("/api/tracks/{track_id}", response_model=TrackView)
    def update_track(track_id: str, body: TrackTagsUpdate, device: Device = Depends(current_device)):
        return for_device(service.update_tags(track_id, body), device)

    @app.delete("/api/tracks/{track_id}", status_code=204)
    def delete_track(track_id: str, keep_archive: bool = True):
        # Par défaut on GARDE l'archive : supprimer définitivement doit être explicite.
        service.delete_track(track_id, keep_archive=keep_archive)
        if not keep_archive:
            devices.forget_track(track_id)

    @app.post("/api/tracks/{track_id}/export", response_model=TrackView)
    def export_track(track_id: str, device: Device = Depends(current_device)):
        return for_device(service.export_track(track_id), device)

    @app.post("/api/tracks/{track_id}/redownload", response_model=TrackView)
    def redownload_track(track_id: str, device: Device = Depends(current_device)):
        return for_device(service.redownload(track_id), device)

    # ===================================================================== #
    # File d'attente
    # ===================================================================== #

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

    # ===================================================================== #
    # Fichiers (média)
    # ===================================================================== #

    @app.get("/api/tracks/{track_id}/cover")
    def get_cover(track_id: str):
        service.get_track(track_id)  # 404 si l'id est inconnu ou invalide
        path = service.cover_path(track_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Pas de pochette.")
        return FileResponse(path, media_type="image/jpeg")

    @app.put("/api/tracks/{track_id}/cover", response_model=TrackView)
    def upload_cover(track_id: str, file: UploadFile = File(...), device: Device = Depends(current_device)):
        raw = file.file.read(MAX_COVER_UPLOAD_BYTES + 1)
        if len(raw) > MAX_COVER_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image trop lourde (15 Mo max).")
        return for_device(service.replace_cover(track_id, raw), device)

    @app.get("/api/tracks/{track_id}/cover/source")
    def get_cover_source(track_id: str):
        """
        Image d'origine non recadrée (affichée dans l'outil de recadrage).
        Pour les musiques ajoutées avant cette fonctionnalité, elle est recréée à la volée
        (miniature YouTube re-téléchargée, sinon pochette actuelle) ; 400 si aucune image.
        """
        return FileResponse(service.ensure_cover_source(track_id), media_type="image/jpeg")

    @app.put("/api/tracks/{track_id}/cover/crop", response_model=TrackView)
    def crop_cover(track_id: str, body: CropBox, device: Device = Depends(current_device)):
        return for_device(service.set_cover_crop(track_id, body), device)

    @app.delete("/api/tracks/{track_id}/cover/crop", response_model=TrackView)
    def reset_cover_crop(track_id: str, device: Device = Depends(current_device)):
        """Revient au cadrage automatique (carré centré)."""
        return for_device(service.set_cover_crop(track_id, None), device)

    @app.get("/api/tracks/{track_id}/audio")
    def get_audio(track_id: str):
        """Permet d'écouter la musique directement dans l'UI (lecture, pas téléchargement)."""
        service.get_track(track_id)
        path = service.audio_path(track_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Pas de mp3 dans l'archive.")
        return FileResponse(path, media_type="audio/mpeg")

    @app.get("/api/tracks/{track_id}/download")
    def download_track(track_id: str, device: Device = Depends(current_device)):
        """
        Télécharge le mp3 (avec tags et pochette) sous son nom "Artiste - Titre.mp3",
        et retient que cet appareil possède maintenant cette version.
        """
        track = service.get_track(track_id)
        path = service.audio_path(track_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Pas de mp3 dans l'archive.")
        devices.mark_downloaded(device.id, track)
        # `filename` -> en-tête Content-Disposition: attachment (le navigateur enregistre le fichier)
        return FileResponse(path, media_type="audio/mpeg", filename=service.export_name(track))

    # ===================================================================== #
    # Appareils
    # ===================================================================== #

    @app.get("/api/me")
    def get_me(request: Request, device: Device = Depends(current_device)):
        """Infos sur l'appareil courant (l'UI s'adapte : mode, boutons réservés au PC...)."""
        return {
            "device": devices.get(device.id) or device,
            "is_local": request.state.is_local,
        }

    @app.patch("/api/me", response_model=Device)
    def update_me(body: DeviceUpdate, device: Device = Depends(current_device)):
        return devices.update(device.id, body)

    @app.get("/api/devices", response_model=list[Device], dependencies=[Depends(require_local)])
    def list_devices():
        return devices.list()

    @app.delete("/api/devices/{device_id}", status_code=204, dependencies=[Depends(require_local)])
    def remove_device(device_id: str):
        """Oublie un appareil (son suivi). Pour lui couper l'accès : régénérer le code."""
        if not devices.remove(device_id):
            raise HTTPException(status_code=404, detail="Appareil introuvable.")

    # ===================================================================== #
    # Réglages, accès réseau & sync (réglages et code : PC uniquement)
    # ===================================================================== #

    @app.get("/api/settings", response_model=Settings, dependencies=[Depends(require_local)])
    def get_settings():
        return settings_store.load()

    @app.put("/api/settings", response_model=Settings, dependencies=[Depends(require_local)])
    def update_settings(body: UserSettings):
        return settings_store.update(body)

    @app.get("/api/pairing", dependencies=[Depends(require_local)])
    def get_pairing(request: Request, host: Optional[str] = None):
        """
        Infos pour connecter un téléphone : URL + QR code.
        `restart_needed` : l'accès réseau est activé dans les réglages, mais le serveur
        a été démarré avant -> il faut relancer start.bat.
        """
        settings = settings_store.load()
        url = access.pairing_url(request.url.port or 80, settings.access_token, host)
        return {
            "lan_access": settings.lan_access,
            "listening_on_lan": listening_on_lan,
            "restart_needed": settings.lan_access != listening_on_lan,
            "url": url,
            "token": settings.access_token,
            "qr_svg": access.qr_svg(url),
        }

    @app.post("/api/pairing/regenerate", dependencies=[Depends(require_local)])
    def regenerate_token():
        settings_store.regenerate_token()
        return {"ok": True}

    @app.post("/api/sync")
    def sync_all():
        return asdict(service.sync_all())

    # ===================================================================== #
    # Interface web (statique)
    # ===================================================================== #
    # Monté en DERNIER : sinon "/" intercepterait les routes /api.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app
