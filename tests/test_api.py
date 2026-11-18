"""Tests de bout en bout via l'API HTTP (avec FakeDownloader)."""

import json

from mutagen.id3 import ID3
from PIL import Image

from tests.conftest import make_image_bytes

TRACK_ID = "youtube-abc123XYZ_-"
URL = "https://www.youtube.com/watch?v=abc123XYZ_-"


def add(client):
    response = client.post("/api/tracks", json={"url": URL})
    assert response.status_code == 201, response.text
    return response.json()


def test_add_track_full_pipeline(env):
    track = add(env["client"])
    assert track["id"] == TRACK_ID
    assert track["tags"]["artist"] == "Daft Punk"
    assert track["tags"]["title"] == "One More Time"
    assert track["has_audio"] and track["has_cover"] and track["is_exported"]

    # Le JSON de sauvegarde existe et contient le lien d'origine
    saved = json.loads((env["tmp"] / "archive" / "metadata" / f"{TRACK_ID}.json").read_text())
    assert saved["source"]["url"] == URL

    # Le mp3 exporté porte les tags ID3 v2.3 et une pochette carrée
    exported = env["export_dir"] / "Daft Punk - One More Time.mp3"
    id3 = ID3(exported)
    assert id3.version[:2] == (2, 3)
    assert str(id3["TIT2"]) == "One More Time"
    assert str(id3["TPE1"]) == "Daft Punk"
    assert id3.getall("APIC")
    cover = Image.open(env["tmp"] / "archive" / "covers" / f"{TRACK_ID}.jpg")
    assert cover.size[0] == cover.size[1]


def test_add_twice_returns_409(env):
    add(env["client"])
    assert env["client"].post("/api/tracks", json={"url": URL}).status_code == 409


def test_update_tags_renames_export(env):
    add(env["client"])
    response = env["client"].patch(f"/api/tracks/{TRACK_ID}", json={"title": "  New Title ", "album": "Discovery"})
    assert response.status_code == 200
    body = response.json()
    assert body["tags"]["title"] == "New Title"
    assert body["tags"]["artist"] == "Daft Punk"  # champ non envoyé = inchangé

    names = [p.name for p in env["export_dir"].iterdir()]
    assert names == ["Daft Punk - New Title.mp3"]
    assert str(ID3(env["export_dir"] / names[0])["TALB"]) == "Discovery"


def test_upload_cover_and_reject_invalid(env):
    add(env["client"])
    ok = env["client"].put(f"/api/tracks/{TRACK_ID}/cover",
                           files={"file": ("c.png", make_image_bytes((50, 80)), "image/png")})
    assert ok.status_code == 200
    bad = env["client"].put(f"/api/tracks/{TRACK_ID}/cover", files={"file": ("c.txt", b"nope", "text/plain")})
    assert bad.status_code == 400


def test_remove_keeps_archive_then_reexport(env):
    add(env["client"])
    assert env["client"].delete(f"/api/tracks/{TRACK_ID}").status_code == 204
    assert list(env["export_dir"].iterdir()) == []
    track = env["client"].get(f"/api/tracks/{TRACK_ID}").json()
    assert track["has_audio"] and not track["is_exported"]

    assert env["client"].post(f"/api/tracks/{TRACK_ID}/export").json()["is_exported"]


def test_delete_permanently(env):
    add(env["client"])
    assert env["client"].delete(f"/api/tracks/{TRACK_ID}?keep_archive=false").status_code == 204
    assert env["client"].get(f"/api/tracks/{TRACK_ID}").status_code == 404
    assert env["client"].get("/api/tracks").json() == []


def test_sync_redownloads_missing_audio_and_keeps_edited_tags(env):
    """Scénario "nouveau PC" : seuls les JSON existent (clonés depuis Git)."""
    add(env["client"])
    env["client"].patch(f"/api/tracks/{TRACK_ID}", json={"genre": "House"})
    (env["tmp"] / "archive" / "audio" / f"{TRACK_ID}.mp3").unlink()
    for f in env["export_dir"].iterdir():
        f.unlink()

    report = env["client"].post("/api/sync").json()
    assert report["redownloaded"] == [TRACK_ID] and report["errors"] == {}
    exported = env["export_dir"] / "Daft Punk - One More Time.mp3"
    assert str(ID3(exported)["TCON"]) == "House"
    assert env["downloader"].download_calls == 2


def test_invalid_id_is_rejected(env):
    assert env["client"].get("/api/tracks/..%2Fsettings").status_code == 404


def test_settings_roundtrip(env):
    settings = env["client"].get("/api/settings").json()
    settings["audio_quality_kbps"] = 320
    assert env["client"].put("/api/settings", json=settings).json()["audio_quality_kbps"] == 320
    settings["audio_quality_kbps"] = 9999
    assert env["client"].put("/api/settings", json=settings).status_code == 422


def test_web_ui_is_served(env):
    response = env["client"].get("/")
    assert response.status_code == 200 and "LoFiMa" in response.text
