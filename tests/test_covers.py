"""Tests du recadrage des pochettes (covers.py + routes /cover/crop)."""

import io

from PIL import Image

from lofima.covers import center_square, crop_box_to_pixels, render_cover
from lofima.models import CropBox
from tests.conftest import make_image_bytes

TRACK_ID = "youtube-abc123XYZ_-"
URL = "https://www.youtube.com/watch?v=abc123XYZ_-"


def test_center_square_on_16_9():
    crop = center_square(320, 180)
    assert crop_box_to_pixels(320, 180, crop) == (70, 0, 250, 180)


def test_crop_is_clamped_inside_image():
    # Carré trop à droite : il est recalé pour rester dans l'image
    assert crop_box_to_pixels(320, 180, CropBox(left=0.9, top=0.5, size=1)) == (140, 0, 320, 180)
    assert crop_box_to_pixels(320, 180, CropBox(left=0, top=0, size=0.5)) == (0, 0, 90, 90)


def test_render_cover_without_square_keeps_full_image(tmp_path):
    source = tmp_path / "s.jpg"
    source.write_bytes(make_image_bytes((320, 180), fmt="JPEG"))
    out = render_cover(source, tmp_path / "c.jpg", crop=None, square=False)
    assert Image.open(out).size == (320, 180)


def _left_half_red_image() -> bytes:
    """Image 320x180 : moitié gauche rouge, moitié droite bleue."""
    image = Image.new("RGB", (320, 180), (0, 0, 255))
    image.paste((255, 0, 0), (0, 0, 160, 180))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_api_crop_then_reset(env):
    client = env["client"]
    client.post("/api/tracks", json={"url": URL})
    client.put(f"/api/tracks/{TRACK_ID}/cover", files={"file": ("c.png", _left_half_red_image(), "image/png")})

    # Cadrage collé à gauche -> pochette majoritairement rouge
    crop = {"left": 0, "top": 0, "size": 1}
    track = client.put(f"/api/tracks/{TRACK_ID}/cover/crop", json=crop).json()
    assert track["cover_crop"] == crop and track["has_cover_source"]
    cover = Image.open(env["tmp"] / "archive" / "covers" / f"{TRACK_ID}.jpg")
    assert cover.size == (180, 180)
    assert cover.getpixel((20, 90))[0] > 200  # rouge à gauche

    # Le cadrage est réappliqué après un re-téléchargement de la miniature
    client.post(f"/api/tracks/{TRACK_ID}/redownload")
    assert client.get(f"/api/tracks/{TRACK_ID}").json()["cover_crop"] == crop

    # Retour au cadrage automatique
    assert client.delete(f"/api/tracks/{TRACK_ID}/cover/crop").json()["cover_crop"] is None
    assert client.get(f"/api/tracks/{TRACK_ID}/cover/source").status_code == 200

    # Valeurs hors limites refusées
    assert client.put(f"/api/tracks/{TRACK_ID}/cover/crop", json={"left": 2, "top": 0, "size": 1}).status_code == 422


def test_crop_works_for_old_tracks_without_source(env):
    """Musique ajoutée avant la fonctionnalité : l'image d'origine est recréée."""
    client = env["client"]
    client.post("/api/tracks", json={"url": URL})
    source = env["tmp"] / "archive" / "covers" / f"{TRACK_ID}.source.jpg"
    source.unlink()
    # L'outil de recadrage demande l'image d'origine : elle est recréée à la volée
    assert client.get(f"/api/tracks/{TRACK_ID}/cover/source").status_code == 200
    source.unlink()
    response = client.put(f"/api/tracks/{TRACK_ID}/cover/crop", json={"left": 0, "top": 0, "size": 0.5})
    assert response.status_code == 200 and response.json()["has_cover_source"]
