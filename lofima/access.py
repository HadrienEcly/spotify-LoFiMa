"""
Accès depuis les autres appareils du Wi-Fi : code secret, adresse du PC, QR code.

Règles de sécurité :
  - le PC lui-même (adresse 127.0.0.1 / ::1) a toujours accès ;
  - tout autre appareil doit présenter le code secret, une fois via le QR code
    (`?token=...` dans l'URL), puis via un cookie posé à ce moment-là ;
  - certaines routes (réglages, code d'accès, liste des appareils) sont réservées au PC.
"""

from __future__ import annotations

import io
import secrets
import socket
from typing import Optional

import qrcode
import qrcode.image.svg

# Noms des cookies
TOKEN_COOKIE = "lofima_token"
DEVICE_COOKIE = "lofima_device"
# Durée de vie des cookies : 1 an (l'appareil reste connecté)
COOKIE_MAX_AGE = 365 * 24 * 3600

# Adresses considérées comme "le PC lui-même"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def token_matches(provided: Optional[str], expected: str) -> bool:
    """
    Compare deux codes en temps constant (`compare_digest`) : empêche de deviner
    le code caractère par caractère en mesurant le temps de réponse.
    """
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided.encode(), expected.encode())


def lan_ip() -> str:
    """
    Adresse IP du PC sur le réseau local (ex : 192.168.1.20).

    Astuce classique : on "connecte" une socket UDP vers une adresse externe. Aucun paquet
    n'est envoyé (UDP sans données), mais le système choisit l'interface réseau qui
    serait utilisée, et donc notre IP locale. Repli sur 127.0.0.1 si pas de réseau.
    Attention : avec un VPN actif, l'IP retournée peut être celle du VPN.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def pairing_url(port: int, token: str, host: Optional[str] = None) -> str:
    """URL à ouvrir sur le téléphone (contenue dans le QR code)."""
    return f"http://{host or lan_ip()}:{port}/?token={token}"


def qr_svg(data: str) -> str:
    """QR code au format SVG (texte), affichable directement dans une page web."""
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


# Page affichée à un appareil qui n'a pas (ou plus) le bon code.
# Volontairement autonome (CSS inclus) : les fichiers de l'UI sont eux aussi protégés.
LOGIN_PAGE_HTML = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LoFiMa - Connexion</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #121212;
         color: #f1f1f1; font: 16px/1.5 system-ui, -apple-system, sans-serif; padding: 16px; box-sizing: border-box; }
  main { max-width: 380px; width: 100%; }
  input { width: 100%; box-sizing: border-box; padding: 12px; border-radius: 8px; border: 0;
          background: #2a2a2a; color: inherit; font: inherit; margin: 12px 0; }
  button { width: 100%; padding: 12px; border: 0; border-radius: 999px; background: #1db954;
           font: inherit; font-weight: 600; }
  p { color: #a7a7a7; }
</style></head>
<body><main>
  <h1>LoFiMa</h1>
  <p>Scanne le QR code affiché sur le PC (LoFiMa › Réglages › Accès depuis le téléphone),
     ou colle le code d'accès ci-dessous.</p>
  <form method="get" action="/">
    <input name="token" placeholder="Code d'accès" autocomplete="off" required>
    <button type="submit">Se connecter</button>
  </form>
</main></body></html>
"""
