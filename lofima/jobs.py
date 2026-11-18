"""
File d'attente des téléchargements.

Principe :
  - `submit()` ajoute un ou plusieurs liens et rend la main IMMÉDIATEMENT ;
  - un thread "worker" en arrière-plan traite les liens UN PAR UN (dans l'ordre d'ajout) ;
  - l'UI interroge régulièrement `list()` pour afficher les barres de progression.

Pourquoi un seul téléchargement à la fois ? C'est plus simple, ça évite de se faire
limiter par YouTube, et ffmpeg utilise déjà bien le processeur.

La file est en MÉMOIRE : si l'appli est fermée, les liens encore en attente sont perdus
(les musiques déjà terminées, elles, sont bien enregistrées dans l'archive).
"""

from __future__ import annotations

import threading
import uuid
from typing import Callable, Optional

from .errors import LofimaError
from .models import Job, JobStatus
from .progress import ProgressReporter

# Fonction qui traite un lien : (url, reporter) -> id de la musique créée.
# En pratique : un adaptateur autour de LibraryService.add_from_url (voir __main__.py).
Processor = Callable[[str, ProgressReporter], str]


class _JobReporter:
    """Reporter qui écrit l'avancement dans un Job (sous le verrou de la file)."""

    def __init__(self, job: Job, lock: threading.Lock) -> None:
        self._job = job
        self._lock = lock

    def step(self, status: JobStatus, progress: Optional[float] = None) -> None:
        with self._lock:
            self._job.status = status
            self._job.progress = progress

    def set_title(self, title: str) -> None:
        with self._lock:
            self._job.title = title


def split_urls(raw_urls: list[str]) -> list[str]:
    """
    Nettoie la liste reçue de l'UI : un élément peut contenir plusieurs liens séparés
    par des retours à la ligne ou des espaces (copier-coller d'une liste).
    Retire les vides et les doublons en gardant l'ordre.
    """
    urls: list[str] = []
    for chunk in raw_urls:
        for url in chunk.split():
            if url not in urls:
                urls.append(url)
    return urls


class JobQueue:
    def __init__(self, processor: Processor, autostart: bool = True) -> None:
        """
        :param processor: fonction qui télécharge un lien (voir `Processor`)
        :param autostart: False dans certains tests pour contrôler le démarrage du worker
        """
        self._processor = processor
        self._jobs: list[Job] = []  # ordre d'ajout = ordre de traitement
        self._lock = threading.Lock()
        # Condition = verrou + mécanisme "réveille-toi" : le worker dort tant que
        # la file est vide, et `submit()` le réveille.
        self._wakeup = threading.Condition(self._lock)
        self._busy = False  # True pendant le traitement d'un job
        self._worker: Optional[threading.Thread] = None
        if autostart:
            self.start()

    # ------------------------------------------------------------------ #
    # API publique (appelée par les routes HTTP)
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Démarre le thread worker (daemon : il s'arrête avec l'application)."""
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name="lofima-jobs", daemon=True)
            self._worker.start()

    def submit(self, raw_urls: list[str]) -> list[Job]:
        """Ajoute des liens à la file et retourne les jobs créés."""
        created = [Job(id=uuid.uuid4().hex[:12], url=url) for url in split_urls(raw_urls)]
        with self._wakeup:
            self._jobs.extend(created)
            self._wakeup.notify()
            return [job.model_copy() for job in created]

    def list(self) -> list[Job]:
        """Copie de tous les jobs (copie = l'appelant ne peut pas modifier la file)."""
        with self._lock:
            return [job.model_copy() for job in self._jobs]

    def remove(self, job_id: str) -> bool:
        """
        Annule un job en attente, ou retire de la liste un job terminé.
        Un job EN COURS ne peut pas être interrompu (retourne False).
        """
        with self._lock:
            for job in self._jobs:
                if job.id != job_id:
                    continue
                # En attente (= annulation) ou déjà terminé : on peut le retirer.
                if job.status == JobStatus.QUEUED or job.status.is_finished:
                    self._jobs.remove(job)
                    return True
                return False  # en cours de traitement
        return False

    def clear_finished(self) -> int:
        """Retire de la liste tous les jobs terminés/en erreur/annulés. Retourne leur nombre."""
        with self._lock:
            before = len(self._jobs)
            self._jobs = [job for job in self._jobs if not job.status.is_finished]
            return before - len(self._jobs)

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Attend que la file soit vide et inactive (utile pour les tests)."""
        with self._wakeup:
            return self._wakeup.wait_for(lambda: not self._busy and self._next_queued() is None, timeout)

    # ------------------------------------------------------------------ #
    # Worker (thread d'arrière-plan)
    # ------------------------------------------------------------------ #

    def _next_queued(self) -> Optional[Job]:
        """Premier job en attente (à appeler sous verrou)."""
        return next((job for job in self._jobs if job.status == JobStatus.QUEUED), None)

    def _run(self) -> None:
        while True:
            # 1. Attendre un job (sans consommer de CPU)
            with self._wakeup:
                self._wakeup.wait_for(lambda: self._next_queued() is not None)
                job = self._next_queued()
                job.status = JobStatus.FETCHING_INFO
                self._busy = True

            # 2. Le traiter HORS verrou (peut durer longtemps)
            self._process(job)

            # 3. Signaler la fin (réveille `wait_idle`)
            with self._wakeup:
                self._busy = False
                self._wakeup.notify_all()

    def _process(self, job: Job) -> None:
        reporter = _JobReporter(job, self._lock)
        try:
            track_id = self._processor(job.url, reporter)
        except LofimaError as exc:
            self._finish(job, JobStatus.FAILED, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - le worker ne doit JAMAIS mourir
            self._finish(job, JobStatus.FAILED, error=f"Erreur inattendue : {exc}")
        else:
            self._finish(job, JobStatus.DONE, track_id=track_id)

    def _finish(self, job: Job, status: JobStatus, error: str = "", track_id: Optional[str] = None) -> None:
        with self._lock:
            job.status = status
            job.progress = 1.0 if status == JobStatus.DONE else None
            job.error = error
            job.track_id = track_id
