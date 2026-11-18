# LoFiMa — Local File Manager

Transforme un lien YouTube en **fichier local Spotify** : mp3 + métadonnées (titre, artiste, album…) + pochette (miniature de la vidéo), le tout modifiable depuis une interface web locale.

Une **copie de sauvegarde** de chaque musique est conservée dans `archive/` : si la vidéo disparaît un jour, tu gardes le mp3 et toutes ses infos.

## Installation (Windows)

1. Installer **Python 3.11+** (https://www.python.org, cocher « Add python.exe to PATH »).
2. Double-cliquer sur **`install.bat`**. Il :
   - crée l'environnement virtuel `.venv` ;
   - installe/met à jour les dépendances Python dedans ;
   - installe **ffmpeg** avec `winget` s'il n'est pas déjà présent (ferme ensuite la fenêtre pour que le PATH soit pris en compte).
3. Double-cliquer sur **`start.bat`** → l'appli démarre et le navigateur s'ouvre sur http://127.0.0.1:8000. Fermer la fenêtre arrête l'appli.

Options : `start.bat --port 8080 --no-browser`.

> YouTube change souvent son fonctionnement : si les téléchargements échouent, relance `install.bat` (il met yt-dlp à jour).

## Brancher Spotify

1. Dans LoFiMa › **Réglages**, choisis le dossier d'export (par défaut `%USERPROFILE%\Music\LoFiMa`).
2. Dans Spotify desktop › Paramètres › **Fichiers locaux** : active « Afficher les fichiers locaux » et **ajoute ce dossier comme source**.
3. Les musiques apparaissent dans *Ta bibliothèque › Fichiers locaux*.

### Sur iPhone (accès depuis le téléphone)
Spotify iOS lit les fichiers audio présents dans l'app **Fichiers**. LoFiMa peut y envoyer les mp3 :

1. Sur le PC : **Réglages › Accès depuis le téléphone** › coche « Autoriser les appareils du Wi-Fi » › Enregistrer.
2. **Relance l'appli** (ferme la fenêtre, puis `start.bat`). Windows demande d'autoriser Python dans le pare-feu : coche **Réseaux privés**.
3. Rouvre les Réglages : un **QR code** s'affiche. Scanne-le avec l'appareil photo de l'iPhone (même Wi-Fi que le PC). L'iPhone reste connecté ensuite.
4. Sur l'iPhone : Réglages › Apps › Safari › **Téléchargements** › choisis le dossier lu par Spotify.
5. Dans LoFiMa sur l'iPhone : la barre **« N musique(s) à récupérer »** liste les nouveautés et les musiques modifiées → *Télécharger la suivante* (un fichier par appui : Safari bloque les téléchargements en rafale).

Tu peux aussi ajouter des liens directement depuis l'iPhone : le téléchargement se fait sur le PC.

**Appareils** : chaque navigateur est un appareil (bouton 📱 en haut) avec son nom et son mode :
- *Dossier d'export du PC* : copie automatique dans le dossier Spotify du PC (mode par défaut du PC) ;
- *Téléchargement sur cet appareil* : l'appli retient ce que l'appareil a récupéré (badges *Nouveau* / *Modifié* / *Sur l'appareil*). Mode par défaut des autres appareils.

**Sécurité** : par défaut l'appli n'est accessible que depuis le PC. Avec l'accès activé, les autres appareils doivent présenter le **code d'accès** (dans le QR code). *Régénérer le code* déconnecte tous les appareils. Les réglages ne sont modifiables que depuis le PC. La connexion n'est pas chiffrée (HTTP) : à n'activer que sur ton Wi-Fi personnel.

### Google Drive (optionnel)
Choisis comme dossier d'export un dossier de **Google Drive pour ordinateur** (ex : `G:\Mon Drive\LoFiMa`) : les mp3 sont alors aussi synchronisés sur Drive, sans config supplémentaire.

## Utilisation

| Action | Effet |
|---|---|
| **Ajouter** un ou plusieurs liens (un par ligne) | Les liens rejoignent la **file d'attente**, traitée un par un avec une barre de progression. Chaque lien : mp3 + miniature, métadonnées devinées, export vers le dossier Spotify |
| **Annuler** (file d'attente) | Retire un lien pas encore commencé |
| **Modifier** | Corrige tags / pochette → le mp3 est retagué et renommé `Artiste - Titre.mp3` |
| **Recadrer** | Choisit quelle partie de la miniature d'origine sert de pochette carrée. Le cadrage est mémorisé (réappliqué après un re-téléchargement). *Cadrage auto* = carré centré |
| **Retirer de Spotify** | Supprime le fichier du dossier Spotify, **garde la sauvegarde** |
| **Réexporter** | Remet une musique retirée dans le dossier Spotify |
| **Re-télécharger** | Récupère à nouveau le mp3 depuis le lien d'origine (tes tags sont conservés) |
| **Supprimer définitivement** | Efface tout (sauvegarde comprise) |
| Réglages › **Resynchroniser tout** | Re-télécharge les mp3 manquants et réexporte tout (nouveau PC, changement de dossier) |

## Archive et Git

```
archive/
  metadata/<id>.json   ← versionné dans Git (lien, infos d'origine, tags modifiés)
  audio/<id>.mp3       ← ignoré par Git (lourd + droits d'auteur)
  covers/<id>.jpg         ← pochette finale, ignorée par Git
  covers/<id>.source.jpg  ← miniature d'origine non recadrée, ignorée par Git
```
La file d'attente est en mémoire : si tu fermes l'appli, les liens pas encore traités sont perdus (les musiques terminées, elles, sont bien sauvegardées).

Pense à **commit `archive/metadata/`** régulièrement. Sur un nouveau PC : clone le dépôt, lance l'app, puis *Resynchroniser tout*.

⚠️ Les mp3 ne sont **pas** dans Git : si une vidéo est supprimée de YouTube, seul ton dossier `archive/audio/` local la conserve. Sauvegarde-le (disque externe, Drive…). Garde le dépôt **privé**.

## Architecture

```
lofima/
  __main__.py    point d'entrée : assemble les dépendances, lance le serveur
  api.py         routes HTTP (FastAPI) — aucune logique métier
  service.py     orchestration : ajout, modif, recadrage, export, sync
  jobs.py        file d'attente (thread d'arrière-plan, un lien à la fois)
  progress.py    interface de remontée d'avancement (service/downloader -> file)
  downloader.py  yt-dlp (derrière une interface `Downloader`)
  metadata.py    déduction des tags depuis le titre YouTube (fonctions pures)
  tagger.py      écriture des tags ID3 v2.3 (mutagen)
  covers.py      image d'origine + rendu de la pochette recadrée (Pillow)
  exporter.py    copie vers le dossier Spotify (interface `Exporter`, extensible à Drive API)
  repository.py  stockage JSON, un fichier par musique
  config.py      chemins + réglages utilisateur (settings.json, contient le code d'accès)
  access.py      accès Wi-Fi : code secret, IP du PC, QR code, page de connexion
  devices.py     appareils (devices.json) + suivi de ce que chacun a récupéré
  models.py      modèles Pydantic (Track, TrackTags…)
  errors.py      exceptions métier → codes HTTP dans api.py
web/             interface (HTML/CSS/JS sans framework)
  app.js         liste, fenêtres Modifier / Réglages
  queue.js       file d'attente + barres de progression (polling de /api/jobs)
  cropper.js     outil de recadrage
  devices.js     appareil courant (nom, mode) — pairing.js : QR code / appareils dans Réglages
  api.js / ui.js client HTTP / utilitaires partagés
tests/           pytest, hors ligne (faux downloader)
```

Tests :
```bash
pip install -r requirements-dev.txt
python -m pytest
```
