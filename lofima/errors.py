"""
Exceptions métier.

Les modules internes lèvent ces exceptions ; seule la couche API (api.py)
les traduit en codes HTTP. Ainsi la logique métier ne dépend pas du web.
"""


class LofimaError(Exception):
    """Classe de base de toutes les erreurs de l'application."""


class TrackNotFoundError(LofimaError):
    """Aucune musique avec cet identifiant dans la bibliothèque."""


class TrackAlreadyExistsError(LofimaError):
    """La vidéo a déjà été ajoutée (même identifiant)."""

    def __init__(self, track_id: str) -> None:
        super().__init__(f"Cette musique est déjà dans la bibliothèque ({track_id}).")
        self.track_id = track_id


class DownloadError(LofimaError):
    """Échec du téléchargement (lien invalide, vidéo supprimée/privée, réseau...)."""


class InvalidCoverError(LofimaError):
    """Le fichier fourni comme pochette n'est pas une image lisible."""
