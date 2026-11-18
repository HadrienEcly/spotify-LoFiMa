"""
Traitement des pochettes (images).

Utilisé à la fois pour la miniature YouTube et pour une image envoyée par l'utilisateur :
on convertit toujours en JPEG (format le mieux supporté par les tags ID3 / Spotify)
et on recadre en carré si demandé.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .errors import DownloadError, InvalidCoverError

# Taille max du côté de la pochette : 1000 px est largement suffisant pour Spotify
# et garde des mp3 légers (la pochette est intégrée dans chaque fichier).
MAX_COVER_SIZE = 1000
JPEG_QUALITY = 90


def fetch_image_bytes(url: str, timeout: float = 20.0) -> bytes:
    """Télécharge une image depuis une URL et retourne ses octets bruts."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except OSError as exc:  # URLError hérite de OSError
        raise DownloadError(f"Impossible de télécharger la miniature : {exc}") from exc


def crop_to_square(image: Image.Image) -> Image.Image:
    """Recadre l'image en carré centré (coupe les bords gauche/droite d'une image 16:9)."""
    width, height = image.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))


def process_cover(raw: bytes, destination: Path, square: bool = True) -> Path:
    """
    Convertit des octets d'image (jpg, png, webp...) en JPEG prêt à être intégré au mp3.

    :param raw: contenu brut de l'image
    :param destination: chemin du .jpg à écrire
    :param square: True pour recadrer en carré
    :raises InvalidCoverError: si les octets ne sont pas une image lisible
    """
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidCoverError("Le fichier fourni n'est pas une image valide.") from exc

    # JPEG ne gère pas la transparence ni les palettes : conversion en RVB.
    image = image.convert("RGB")
    if square:
        image = crop_to_square(image)
    image.thumbnail((MAX_COVER_SIZE, MAX_COVER_SIZE))  # réduit sans déformer

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="JPEG", quality=JPEG_QUALITY)
    return destination
