"""
Remontée de l'avancement d'un téléchargement.

Le service et le downloader ne connaissent PAS la file d'attente : ils reçoivent juste
un objet `ProgressReporter` à qui ils signalent l'étape en cours. La file d'attente
(jobs.py) fournit un reporter qui met à jour le Job ; ailleurs on utilise `NullReporter`
qui ignore tout. Ainsi les modules restent indépendants les uns des autres.
"""

from __future__ import annotations

from typing import Optional, Protocol

from .models import JobStatus


class ProgressReporter(Protocol):
    def step(self, status: JobStatus, progress: Optional[float] = None) -> None:
        """Signale l'étape en cours et, si connu, son avancement (0 à 1)."""
        ...

    def set_title(self, title: str) -> None:
        """Signale le titre de la vidéo dès qu'il est connu (affichage dans la file)."""
        ...


class NullReporter:
    """Reporter qui ne fait rien : utilisé quand personne n'écoute l'avancement."""

    def step(self, status: JobStatus, progress: Optional[float] = None) -> None:
        pass

    def set_title(self, title: str) -> None:
        pass


# Instance partagée (sans état, donc réutilisable partout)
NULL_REPORTER = NullReporter()
