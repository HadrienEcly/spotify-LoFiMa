// Appareil courant : nom, mode de récupération ("dossier du PC" ou "téléchargement").
//
// Le serveur identifie chaque navigateur par un cookie. Ici on récupère ces infos
// (/api/me), on adapte l'en-tête, et on gère la fenêtre "Cet appareil".

import { deviceApi } from "./api.js";
import { $, toast } from "./ui.js";

// Dernières infos reçues : { device: {id, name, mode, ...}, is_local: bool }
let me = null;
let onChange = () => {};

/** Infos de l'appareil courant (null tant que non chargées). */
export const getMe = () => me;

/** True si cet appareil récupère les musiques par téléchargement. */
export const isDownloadMode = () => me?.device.mode === "download";

function renderHeader() {
  $("#device-name").textContent = me.device.name;
  // Les réglages (dossier d'export, code d'accès...) ne sont modifiables que depuis le PC
  $("#open-settings").hidden = !me.is_local;
}

function openDialog() {
  const form = $("#device-form");
  form.elements.name.value = me.device.name;
  form.elements.mode.value = me.device.mode; // coche le bon bouton radio
  $("#device-dialog").showModal();
}

async function onSubmit(event) {
  event.preventDefault();
  const form = $("#device-form");
  try {
    const device = await deviceApi.updateMe({
      name: form.elements.name.value.trim(),
      mode: form.elements.mode.value,
    });
    me = { ...me, device };
    renderHeader();
    $("#device-dialog").close();
    toast("Appareil enregistré");
    onChange(); // le mode change l'affichage de la liste
  } catch (error) {
    toast(error.message, "error");
  }
}

/** Recharge les infos de l'appareil (ex : après un téléchargement). */
export async function refreshMe() {
  me = await deviceApi.me();
  renderHeader();
  return me;
}

/**
 * À appeler une fois au démarrage, AVANT d'afficher la liste (elle dépend du mode).
 * @param {() => void} onDeviceChange appelé quand l'utilisateur change de mode
 */
export async function initDevice(onDeviceChange) {
  onChange = onDeviceChange;
  $("#open-device").addEventListener("click", openDialog);
  $("#device-form").addEventListener("submit", onSubmit);
  $("#device-cancel").addEventListener("click", () => $("#device-dialog").close());
  await refreshMe();
}
