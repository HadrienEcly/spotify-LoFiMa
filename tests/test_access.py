"""Tests de l'accès réseau (code secret, routes réservées au PC) et du suivi par appareil."""

from urllib.parse import unquote

from lofima.config import UserSettings

TRACK_ID = "youtube-abc123XYZ_-"
URL = "https://www.youtube.com/watch?v=abc123XYZ_-"


def enable_lan(env) -> str:
    """Active l'accès réseau et retourne le code d'accès."""
    store = env["settings_store"]
    settings = store.load()
    store.update(UserSettings(**{**settings.model_dump(), "lan_access": True}))
    return store.load().access_token


def test_remote_is_refused_when_lan_access_disabled(env):
    assert env["remote_client"]().get("/api/tracks").status_code == 403


def test_remote_needs_token_then_gets_cookie(env):
    token = enable_lan(env)
    phone = env["remote_client"]()

    # Sans code : page de connexion (UI) ou 401 (API)
    assert phone.get("/").status_code == 401
    assert "Code d'accès" in phone.get("/").text
    assert phone.get("/api/tracks").status_code == 401
    # Mauvais code
    assert phone.get("/?token=faux").status_code == 401

    # Bon code (QR) : redirection vers l'URL sans le code + cookie posé
    response = phone.get(f"/?token={token}", follow_redirects=False)
    assert response.status_code == 303
    assert "token" not in response.headers["location"]
    assert phone.get("/api/tracks").status_code == 200  # le cookie suffit désormais


def test_regenerating_token_disconnects_phone(env):
    token = enable_lan(env)
    phone = env["remote_client"]()
    phone.get(f"/?token={token}")
    assert env["client"].post("/api/pairing/regenerate").status_code == 200
    assert phone.get("/api/tracks").status_code == 401


def test_settings_and_pairing_are_pc_only(env):
    token = enable_lan(env)
    phone = env["remote_client"]()
    phone.get(f"/?token={token}")
    assert phone.get("/api/settings").status_code == 403
    assert phone.get("/api/pairing").status_code == 403
    assert phone.post("/api/pairing/regenerate").status_code == 403
    assert phone.get("/api/devices").status_code == 403


def test_saving_settings_keeps_token(env):
    token = enable_lan(env)
    settings = env["client"].get("/api/settings").json()
    settings["audio_quality_kbps"] = 320
    env["client"].put("/api/settings", json=settings)
    assert env["settings_store"].load().access_token == token


def test_pairing_info(env):
    enable_lan(env)
    info = env["client"].get("/api/pairing", params={"host": "192.168.1.20"}).json()
    assert info["url"].startswith("http://192.168.1.20:")
    assert info["url"].endswith(info["token"])
    assert info["restart_needed"] is True  # activé, mais serveur démarré sans le réseau
    assert info["qr_svg"].lstrip().startswith("<?xml") or "<svg" in info["qr_svg"]


def test_device_modes_and_download_tracking(env):
    token = enable_lan(env)
    pc = env["client"]
    pc.post("/api/tracks", json={"url": URL})

    # Le PC est en mode "dossier d'export" : pas d'état de téléchargement
    assert pc.get("/api/me").json()["device"]["mode"] == "export_folder"
    assert pc.get("/api/tracks").json()[0]["device_state"] is None

    # Le téléphone est en mode "téléchargement" : la musique est nouvelle pour lui
    phone = env["remote_client"]()
    phone.get(f"/?token={token}")
    me = phone.get("/api/me").json()
    assert me["device"]["mode"] == "download" and me["is_local"] is False
    assert phone.get("/api/tracks").json()[0]["device_state"] == "new"

    # Téléchargement : bon nom de fichier, puis la musique est "à jour" sur le téléphone
    response = phone.get(f"/api/tracks/{TRACK_ID}/download")
    assert response.status_code == 200
    # Nom encodé (RFC 6266 : filename*=utf-8''...) pour supporter accents et espaces
    assert "Daft Punk - One More Time.mp3" in unquote(response.headers["content-disposition"])
    assert phone.get("/api/tracks").json()[0]["device_state"] == "downloaded"

    # Modification des tags (depuis le PC) -> "modifiée" pour le téléphone
    pc.patch(f"/api/tracks/{TRACK_ID}", json={"genre": "House"})
    assert phone.get("/api/tracks").json()[0]["device_state"] == "outdated"

    # Un simple réexport ne compte PAS comme une modification
    phone.get(f"/api/tracks/{TRACK_ID}/download")
    pc.post(f"/api/tracks/{TRACK_ID}/export")
    assert phone.get("/api/tracks").json()[0]["device_state"] == "downloaded"

    # Changement de nom / mode par l'appareil lui-même
    updated = phone.patch("/api/me", json={"name": "Mon iPhone", "mode": "export_folder"}).json()
    assert updated["name"] == "Mon iPhone" and updated["mode"] == "export_folder"
    assert {d["name"] for d in pc.get("/api/devices").json()} >= {"Mon iPhone"}


def test_permanent_delete_forgets_track_on_devices(env):
    pc = env["client"]
    pc.post("/api/tracks", json={"url": URL})
    pc.patch("/api/me", json={"mode": "download"})
    pc.get(f"/api/tracks/{TRACK_ID}/download")
    pc.delete(f"/api/tracks/{TRACK_ID}?keep_archive=false")
    assert all(TRACK_ID not in d["downloaded"] for d in pc.get("/api/devices").json())
