// Logique de l'interface. Organisation :
//   1. état + raccourcis DOM
//   2. helpers (toasts, boutons occupés)
//   3. liste des musiques
//   4. ajout d'un lien
//   5. fenêtre "Modifier"
//   6. fenêtre "Réglages"
//   7. démarrage

import { api } from "./api.js";

// ---------------------------------------------------------------- 1. État
const state = {
  tracks: [],        // dernière liste reçue du serveur (TrackView[])
  editing: null,     // musique ouverte dans la fenêtre "Modifier"
};

const $ = (selector) => document.querySelector(selector);

// Champs éditables : doivent correspondre à TrackTags dans lofima/models.py
const TAG_FIELDS = ["title", "artist", "album", "album_artist", "year", "track_number", "genre", "comment"];

// ---------------------------------------------------------------- 2. Helpers

/** Affiche une notification qui disparaît seule. type = "info" | "error" */
function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), type === "error" ? 8000 : 3500);
}

/**
 * Désactive un bouton pendant une action async et affiche un libellé d'attente.
 * Évite les doubles clics (ex : lancer deux fois le même téléchargement).
 */
async function withBusy(button, busyLabel, action) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await action();
  } catch (error) {
    toast(error.message, "error");
    return undefined;
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

/** Formate une durée en secondes -> "3:07" */
function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

// ---------------------------------------------------------------- 3. Liste

async function loadTracks() {
  try {
    state.tracks = await api.listTracks();
    renderTracks();
  } catch (error) {
    toast(`Impossible de charger la bibliothèque : ${error.message}`, "error");
  }
}

/** Remplace une musique dans l'état local après une modification, puis réaffiche. */
function upsertTrack(track) {
  const index = state.tracks.findIndex((t) => t.id === track.id);
  if (index >= 0) state.tracks[index] = track;
  else state.tracks.unshift(track);
  renderTracks();
}

function matchesSearch(track, query) {
  if (!query) return true;
  const haystack = [track.tags.title, track.tags.artist, track.tags.album, track.source.original_title]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function renderTracks() {
  const query = $("#search").value.trim().toLowerCase();
  const visible = state.tracks.filter((t) => matchesSearch(t, query));
  const list = $("#track-list");
  const template = $("#track-template");

  list.replaceChildren(
    ...visible.map((track) => {
      const node = template.content.firstElementChild.cloneNode(true);
      const cover = node.querySelector(".cover");
      if (track.has_cover) cover.src = api.coverUrl(track);
      else cover.classList.add("placeholder");

      node.querySelector(".title").textContent = track.tags.title || track.source.original_title;
      node.querySelector(".artist").textContent =
        [track.tags.artist, track.tags.album].filter(Boolean).join(" · ") +
        (track.source.duration_seconds ? ` · ${formatDuration(track.source.duration_seconds)}` : "");

      node.querySelector(".badges").append(...buildBadges(track));

      const play = node.querySelector(".play");
      play.disabled = !track.has_audio;
      play.addEventListener("click", () => playTrack(track));
      node.querySelector(".edit").addEventListener("click", () => openEdit(track));
      return node;
    }),
  );

  $("#count").textContent = `${visible.length} / ${state.tracks.length} musique(s)`;
  $("#empty").hidden = state.tracks.length > 0;
}

/** Petites étiquettes d'état : exporté vers Spotify ? mp3 présent dans l'archive ? */
function buildBadges(track) {
  const badges = [];
  const make = (label, cls, title) => {
    const span = document.createElement("span");
    span.className = `badge ${cls}`;
    span.textContent = label;
    span.title = title;
    return span;
  };
  if (track.is_exported) badges.push(make("Spotify", "ok", `Fichier : ${track.exported_filename}`));
  else badges.push(make("Non exporté", "warn", "Pas dans le dossier Spotify"));
  if (!track.has_audio) badges.push(make("mp3 manquant", "warn", "Utilise « Re-télécharger »"));
  return badges;
}

function playTrack(track) {
  const player = $("#player");
  player.hidden = false;
  player.src = api.audioUrl(track);
  player.play();
}

// ---------------------------------------------------------------- 4. Ajout

function setAddStatus(message) {
  const status = $("#add-status");
  status.hidden = !message;
  status.textContent = message || "";
}

async function onAddSubmit(event) {
  event.preventDefault();
  const input = $("#add-url");
  const url = input.value.trim();
  if (!url) return;

  setAddStatus("Téléchargement en cours… (peut prendre quelques dizaines de secondes)");
  const track = await withBusy($("#add-submit"), "…", () => api.addTrack(url));
  setAddStatus("");

  if (track) {
    input.value = "";
    upsertTrack(track);
    toast(`Ajouté : ${track.tags.artist} - ${track.tags.title}`);
    openEdit(track); // on propose directement de vérifier/corriger les métadonnées
  }
}

// ---------------------------------------------------------------- 5. Modifier

function openEdit(track) {
  state.editing = track;
  const form = $("#edit-form");
  for (const field of TAG_FIELDS) form.elements[field].value = track.tags[field] ?? "";

  const cover = $("#edit-cover");
  cover.src = track.has_cover ? api.coverUrl(track) : "";
  cover.classList.toggle("placeholder", !track.has_cover);

  renderSource(track.source);
  $("#edit-export").disabled = !track.has_audio;
  $("#edit-remove").disabled = !track.is_exported;
  $("#edit-dialog").showModal();
}

/** Affiche les infos d'origine (lecture seule). */
function renderSource(source) {
  const rows = [
    ["Lien", source.url],
    ["Chaîne", source.channel],
    ["Titre d'origine", source.original_title],
    ["Mise en ligne", source.upload_date],
  ];
  const dl = $("#edit-source");
  dl.replaceChildren();
  for (const [label, value] of rows) {
    if (!value) continue;
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (label === "Lien") {
      const a = document.createElement("a");
      a.href = value;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = value;
      dd.append(a);
    } else {
      dd.textContent = value;
    }
    dl.append(dt, dd);
  }
}

/** Après chaque action sur la musique ouverte : met à jour la liste ET la fenêtre. */
function refreshEditing(track) {
  if (!track) return;
  upsertTrack(track);
  openEdit(track);
}

async function onEditSave(event) {
  event.preventDefault();
  const form = $("#edit-form");
  const tags = Object.fromEntries(TAG_FIELDS.map((f) => [f, form.elements[f].value]));
  const track = await withBusy($("#edit-save"), "Enregistrement…", () =>
    api.updateTrack(state.editing.id, tags),
  );
  if (track) {
    upsertTrack(track);
    $("#edit-dialog").close();
    toast("Métadonnées enregistrées");
  }
}

async function onCoverSelected(event) {
  const file = event.target.files[0];
  event.target.value = ""; // permet de re-sélectionner le même fichier plus tard
  if (!file) return;
  try {
    refreshEditing(await api.uploadCover(state.editing.id, file));
    toast("Pochette mise à jour");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function onRedownload(event) {
  const track = await withBusy(event.currentTarget, "Téléchargement…", () =>
    api.redownloadTrack(state.editing.id),
  );
  if (track) {
    refreshEditing(track);
    toast("Re-téléchargé (tes métadonnées sont conservées)");
  }
}

async function onExport(event) {
  const track = await withBusy(event.currentTarget, "Export…", () => api.exportTrack(state.editing.id));
  if (track) {
    refreshEditing(track);
    toast(`Exporté : ${track.exported_filename}`);
  }
}

/** keepArchive=true : retire seulement du dossier Spotify ; false : supprime tout. */
async function onDelete(keepArchive) {
  const track = state.editing;
  const message = keepArchive
    ? "Retirer cette musique du dossier Spotify ?\nLa copie de sauvegarde est conservée."
    : "Supprimer DÉFINITIVEMENT cette musique (mp3, pochette et métadonnées) ?";
  if (!confirm(message)) return;

  try {
    await api.deleteTrack(track.id, keepArchive);
    $("#edit-dialog").close();
    toast(keepArchive ? "Retirée de Spotify" : "Supprimée");
    await loadTracks();
  } catch (error) {
    toast(error.message, "error");
  }
}

// ---------------------------------------------------------------- 6. Réglages

async function openSettings() {
  try {
    const settings = await api.getSettings();
    const form = $("#settings-form");
    form.elements.export_dir.value = settings.export_dir;
    form.elements.audio_quality_kbps.value = String(settings.audio_quality_kbps);
    form.elements.crop_cover_square.checked = settings.crop_cover_square;
    $("#settings-dialog").showModal();
  } catch (error) {
    toast(error.message, "error");
  }
}

async function onSettingsSave(event) {
  event.preventDefault();
  const form = $("#settings-form");
  try {
    await api.saveSettings({
      export_dir: form.elements.export_dir.value.trim(),
      audio_quality_kbps: Number(form.elements.audio_quality_kbps.value),
      crop_cover_square: form.elements.crop_cover_square.checked,
    });
    $("#settings-dialog").close();
    toast("Réglages enregistrés. Pense à « Resynchroniser tout » si tu as changé de dossier.");
    await loadTracks(); // le statut "exporté" dépend du dossier
  } catch (error) {
    toast(error.message, "error");
  }
}

async function onSyncAll(event) {
  const report = await withBusy(event.currentTarget, "Synchronisation…", () => api.syncAll());
  if (!report) return;
  const errors = Object.entries(report.errors);
  toast(`${report.exported.length} exportée(s), ${report.redownloaded.length} re-téléchargée(s)`);
  for (const [id, message] of errors) toast(`${id} : ${message}`, "error");
  await loadTracks();
}

// ---------------------------------------------------------------- 7. Démarrage

function bindEvents() {
  $("#add-form").addEventListener("submit", onAddSubmit);
  $("#search").addEventListener("input", renderTracks);

  $("#edit-form").addEventListener("submit", onEditSave);
  $("#edit-cancel").addEventListener("click", () => $("#edit-dialog").close());
  $("#edit-cover-input").addEventListener("change", onCoverSelected);
  $("#edit-redownload").addEventListener("click", onRedownload);
  $("#edit-export").addEventListener("click", onExport);
  $("#edit-remove").addEventListener("click", () => onDelete(true));
  $("#edit-delete").addEventListener("click", () => onDelete(false));

  $("#open-settings").addEventListener("click", openSettings);
  $("#settings-form").addEventListener("submit", onSettingsSave);
  $("#settings-cancel").addEventListener("click", () => $("#settings-dialog").close());
  $("#sync-all").addEventListener("click", onSyncAll);
}

bindEvents();
loadTracks();
