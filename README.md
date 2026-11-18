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

### Sur iPhone
Spotify ne permet qu'une méthode : sur le PC, ajoute les musiques à une **playlist** ; sur l'iPhone (même réseau Wi-Fi que le PC, Spotify ouvert sur les deux, « Fichiers locaux » activé dans les réglages iOS), ouvre cette playlist et **télécharge-la**.

### Google Drive (optionnel)
Choisis comme dossier d'export un dossier de **Google Drive pour ordinateur** (ex : `G:\Mon Drive\LoFiMa`) : les mp3 sont alors aussi synchronisés sur Drive, sans config supplémentaire.

## Utilisation

| Action | Effet |
|---|---|
| **Ajouter** un lien | Télécharge le mp3 et la miniature, devine les métadonnées, exporte vers le dossier Spotify |
| **Modifier** | Corrige tags / pochette → le mp3 est retagué et renommé `Artiste - Titre.mp3` |
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
  covers/<id>.jpg      ← ignoré par Git
```
Pense à **commit `archive/metadata/`** régulièrement. Sur un nouveau PC : clone le dépôt, lance l'app, puis *Resynchroniser tout*.

⚠️ Les mp3 ne sont **pas** dans Git : si une vidéo est supprimée de YouTube, seul ton dossier `archive/audio/` local la conserve. Sauvegarde-le (disque externe, Drive…). Garde le dépôt **privé**.

## Architecture

```
lofima/
  __main__.py    point d'entrée : assemble les dépendances, lance le serveur
  api.py         routes HTTP (FastAPI) — aucune logique métier
  service.py     orchestration : ajout, modif, export, sync
  downloader.py  yt-dlp (derrière une interface `Downloader`)
  metadata.py    déduction des tags depuis le titre YouTube (fonctions pures)
  tagger.py      écriture des tags ID3 v2.3 (mutagen)
  covers.py      conversion/recadrage des pochettes (Pillow)
  exporter.py    copie vers le dossier Spotify (interface `Exporter`, extensible à Drive API)
  repository.py  stockage JSON, un fichier par musique
  config.py      chemins + réglages utilisateur (settings.json)
  models.py      modèles Pydantic (Track, TrackTags…)
  errors.py      exceptions métier → codes HTTP dans api.py
web/             interface (HTML/CSS/JS sans framework)
tests/           pytest, hors ligne (faux downloader)
```

Tests :
```bash
pip install -r requirements-dev.txt
python -m pytest
```
