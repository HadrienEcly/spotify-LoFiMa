// Panneau "File d'attente" : envoi des liens, suivi de l'avancement, barres de progression.
//
// Le serveur traite les liens un par un en arrière-plan. Ici on l'interroge
// régulièrement (polling) tant qu'au moins un téléchargement n'est pas terminé.

import { jobsApi } from "./api.js";
import { $, toast } from "./ui.js";

const POLL_INTERVAL_MS = 600;

// Libellé affiché pour chaque étape (valeurs de JobStatus dans lofima/models.py)
const STATUS_LABELS = {
  queued: "En attente",
  fetching: "Analyse du lien…",
  downloading: "Téléchargement",
  converting: "Conversion en mp3…",
  finalizing: "Pochette et tags…",
  done: "Terminé",
  failed: "Erreur",
  cancelled: "Annulé",
};

// Chaque étape occupe une portion de la barre globale : [début, fin] en %.
// Le téléchargement est la plus longue, d'où la plus grande portion.
const STATUS_RANGES = {
  queued: [0, 0],
  fetching: [0, 5],
  downloading: [5, 85],
  converting: [85, 95],
  finalizing: [95, 100],
  done: [100, 100],
};

const FINISHED = new Set(["done", "failed", "cancelled"]);

let pollTimer = null;
const announced = new Set(); // ids des jobs déjà signalés comme terminés
let callbacks = { onTrackAdded: () => {}, onEdit: () => {} };

/**
 * Avancement global (0-100) d'un job, ou null si l'étape en cours n'a pas
 * de pourcentage connu (la barre est alors animée en "indéterminé").
 */
function overallPercent(job) {
  const range = STATUS_RANGES[job.status];
  if (!range) return 100; // failed / cancelled : barre pleine (colorée en rouge)
  const [start, end] = range;
  if (start === end) return start;
  if (job.progress === null || job.progress === undefined) {
    // Pas de % : downloading -> indéterminé ; autres étapes -> début de la portion
    return job.status === "downloading" ? null : start;
  }
  return start + (end - start) * job.progress;
}

function statusText(job) {
  const label = STATUS_LABELS[job.status] ?? job.status;
  if (job.status === "downloading" && job.progress !== null) {
    return `${label} ${Math.round(job.progress * 100)} %`;
  }
  if (job.status === "failed") return `${label} : ${job.error}`;
  return label;
}

// Lignes déjà affichées, par id de job. On les MET À JOUR au lieu de les recréer :
// sinon un clic sur "Annuler" pourrait tomber pendant un rafraîchissement et être perdu.
const rows = new Map();

/** Met à jour une ligne existante avec l'état du job. */
function updateRow(node, job) {
  node.dataset.status = job.status; // utilisé par le CSS (couleurs)
  const title = node.querySelector(".job-title");
  title.textContent = job.title || job.url;
  title.title = job.url;
  node.querySelector(".job-status").textContent = statusText(job);

  const percent = overallPercent(job);
  node.querySelector(".progress").classList.toggle("indeterminate", percent === null);
  node.querySelector(".progress-fill").style.width = percent === null ? "" : `${percent}%`;

  // Bouton contextuel : annuler (en attente), modifier (terminé), retirer (erreur)
  // `onclick =` (et pas addEventListener) remplace le gestionnaire précédent.
  const action = node.querySelector(".job-action");
  action.hidden = false;
  if (job.status === "queued") {
    action.textContent = "Annuler";
    action.onclick = () => removeJob(job.id);
  } else if (job.status === "done") {
    action.textContent = "Modifier";
    action.onclick = () => callbacks.onEdit(job.track_id);
  } else if (FINISHED.has(job.status)) {
    action.textContent = "Retirer";
    action.onclick = () => removeJob(job.id);
  } else {
    action.hidden = true; // en cours : non interruptible
  }
}

function render(jobs) {
  const list = $("#queue-list");
  const ids = new Set(jobs.map((job) => job.id));

  // 1. Retirer les lignes des jobs qui n'existent plus
  for (const [id, node] of rows) {
    if (!ids.has(id)) {
      node.remove();
      rows.delete(id);
    }
  }
  // 2. Créer les nouvelles lignes / mettre à jour les autres, dans l'ordre de la file
  for (const job of jobs) {
    let node = rows.get(job.id);
    if (!node) {
      node = $("#job-template").content.firstElementChild.cloneNode(true);
      rows.set(job.id, node);
    }
    updateRow(node, job);
    list.append(node); // append d'un nœud déjà présent = simple déplacement
  }

  $("#queue").hidden = jobs.length === 0;
  $("#queue-clear").hidden = !jobs.some((job) => FINISHED.has(job.status));
}

/** Prévient l'app des musiques qui viennent d'être ajoutées (une seule fois par job). */
function announceFinished(jobs) {
  for (const job of jobs) {
    if (announced.has(job.id) || !FINISHED.has(job.status)) continue;
    announced.add(job.id);
    if (job.status === "done") callbacks.onTrackAdded(job);
    if (job.status === "failed") toast(`${job.title || job.url} : ${job.error}`, "error");
  }
}

/** Récupère l'état de la file, l'affiche, et reprogramme un appel si besoin. */
async function refresh() {
  clearTimeout(pollTimer);
  try {
    const jobs = await jobsApi.list();
    render(jobs);
    announceFinished(jobs);
    if (jobs.some((job) => !FINISHED.has(job.status))) {
      pollTimer = setTimeout(refresh, POLL_INTERVAL_MS);
    }
  } catch (error) {
    toast(`File d'attente : ${error.message}`, "error");
    pollTimer = setTimeout(refresh, POLL_INTERVAL_MS * 5); // on réessaie plus tard
  }
}

async function removeJob(id) {
  try {
    await jobsApi.remove(id);
  } catch (error) {
    toast(error.message, "error");
  }
  refresh();
}

async function onSubmit(event) {
  event.preventDefault();
  const textarea = $("#add-urls");
  const text = textarea.value.trim();
  if (!text) return;
  try {
    const jobs = await jobsApi.add([text]); // le serveur découpe ligne par ligne
    textarea.value = "";
    autoGrow(textarea);
    toast(`${jobs.length} lien(s) ajouté(s) à la file`);
    refresh();
  } catch (error) {
    toast(error.message, "error");
  }
}

/** Agrandit la zone de texte selon le nombre de lignes (max ~6 lignes). */
function autoGrow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
}

/**
 * Branche le panneau. À appeler une fois au démarrage.
 * @param {object} options
 * @param {(job) => void} options.onTrackAdded  appelé quand un téléchargement réussit
 * @param {(trackId) => void} options.onEdit    appelé au clic sur "Modifier"
 */
export function initQueue(options) {
  callbacks = { ...callbacks, ...options };
  const textarea = $("#add-urls");

  $("#add-form").addEventListener("submit", onSubmit);
  textarea.addEventListener("input", () => autoGrow(textarea));
  textarea.addEventListener("keydown", (event) => {
    // Entrée = envoyer ; Maj+Entrée = nouvelle ligne
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      $("#add-form").requestSubmit();
    }
  });
  // Après un collage de plusieurs lignes, on adapte la hauteur
  textarea.addEventListener("paste", () => setTimeout(() => autoGrow(textarea)));

  $("#queue-clear").addEventListener("click", async () => {
    await jobsApi.clearFinished().catch((error) => toast(error.message, "error"));
    refresh();
  });

  // Au chargement de la page : les jobs déjà terminés ne doivent pas être ré-annoncés
  jobsApi
    .list()
    .then((jobs) => jobs.filter((j) => FINISHED.has(j.status)).forEach((j) => announced.add(j.id)))
    .catch(() => {})
    .finally(refresh);
}
