"""
Traitement des pochettes (images).

Deux fichiers par musique (dans archive/covers/) :
  - `<id>.source.jpg` : l'image D'ORIGINE, non recadrée (miniature YouTube 16:9 ou image
                        envoyée). On la garde pour pouvoir recadrer autrement plus tard.
  - `<id>.jpg`        : la pochette FINALE (carrée), intégrée dans le mp3.

Flux : octets bruts --save_source()--> source.jpg --render_cover(cadrage)--> pochette.jpg
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from .errors import DownloadError, InvalidCoverError
from .models import CropBox

# Taille max du côté de la pochette finale : largement suffisant pour Spotify
# et garde des mp3 légers (la pochette est intégrée dans chaque fichier).
MAX_COVER_SIZE = 1000
# L'image d'origine est gardée un peu plus grande pour recadrer sans perte.
MAX_SOURCE_SIZE = 2000
JPEG_QUALITY = 90


def fetch_image_bytes(url: str, timeout: float = 20.0) -> bytes:
    """Télécharge une image depuis une URL et retourne ses octets bruts."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except OSError as exc:  # URLError hérite de OSError
        raise DownloadError(f"Impossible de télécharger la miniature : {exc}") from exc


def _open_image(raw: bytes) -> Image.Image:
    """Ouvre des octets d'image (jpg, png, webp...) et les convertit en RVB."""
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidCoverError("Le fichier fourni n'est pas une image valide.") from exc
    # JPEG ne gère pas la transparence ni les palettes : conversion en RVB.
    return image.convert("RGB")


def _save_jpeg(image: Image.Image, destination: Path, max_size: int) -> Path:
    image.thumbnail((max_size, max_size))  # réduit sans déformer (n'agrandit jamais)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="JPEG", quality=JPEG_QUALITY)
    return destination


def save_source(raw: bytes, destination: Path) -> Path:
    """
    Enregistre l'image d'origine (sans recadrage) en JPEG.
    :raises InvalidCoverError: si les octets ne sont pas une image lisible
    """
    return _save_jpeg(_open_image(raw), destination, MAX_SOURCE_SIZE)


def crop_box_to_pixels(width: int, height: int, crop: CropBox) -> tuple[int, int, int, int]:
    """
    Convertit un CropBox (fractions) en rectangle en pixels (gauche, haut, droite, bas).
    Le carré est décalé si besoin pour rester entièrement dans l'image.
    """
    side = max(1, round(crop.size * min(width, height)))
    left = min(round(crop.left * width), width - side)
    top = min(round(crop.top * height), height - side)
    left, top = max(0, left), max(0, top)
    return left, top, left + side, top + side


def center_square(width: int, height: int) -> CropBox:
    """Le plus grand carré centré (cadrage automatique par défaut)."""
    side = min(width, height)
    return CropBox(left=(width - side) / 2 / width, top=(height - side) / 2 / height, size=1.0)


def render_cover(
    source: Path,
    destination: Path,
    crop: Optional[CropBox] = None,
    square: bool = True,
) -> Path:
    """
    Génère la pochette finale depuis l'image d'origine.

    :param crop: cadrage choisi par l'utilisateur ; prioritaire sur `square`
    :param square: si pas de cadrage choisi : True = carré centré, False = image entière
    """
    image = _open_image(source.read_bytes())
    width, height = image.size
    if crop is None and square:
        crop = center_square(width, height)
    if crop is not None:
        image = image.crop(crop_box_to_pixels(width, height, crop))
    return _save_jpeg(image, destination, MAX_COVER_SIZE)
