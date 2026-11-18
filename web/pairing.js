// Section "Accès depuis le téléphone" de la fenêtre Réglages (PC uniquement) :
// QR code de connexion, code d'accès, liste des appareils connus.

import { deviceApi, pairingApi } from "./api.js";
import { $, toast } from "./ui.js";

const MODE_LABELS = { export_folder: "dossier du PC", download: "téléchargement" };

/** Date ISO -> "18/11 16:05" */
function shortDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

async function renderDevices() {
  const devices = await deviceApi.list();
  const list = $("#device-list");
  list.replaceChildren(
    ...devices.map((device) => {
      const li = document.createElement("li");
      const text = document.createElement("span");
      const count = Object.keys(device.downloaded).length;
      text.textContent =
        `${device.name} · ${MODE_LABELS[device.mode]}` +
        (device.mode === "download" ? ` · ${count} récupérée(s)` : "") +
        ` · vu le ${shortDate(device.last_seen)}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn ghost small";
      remove.textContent = "Oublier";
      remove.title = "Efface son suivi. Pour lui couper l'accès : « Régénérer le code ».";
      remove.addEventListener("click", async () => {
        await deviceApi.remove(device.id).catch((error) => toast(error.message, "error"));
        renderDevices();
      });
      li.append(text, remove);
      return li;
    }),
  );
}

/**
 * Met à jour la section à partir de l'état du serveur.
 * Le QR code n'est affiché que si l'accès réseau est réellement actif.
 */
export async function renderPairing() {
  try {
    const info = await pairingApi.get();
    $("#settings-form").elements.lan_access.checked = info.lan_access;
    $("#pairing-restart").hidden = !info.restart_needed;
    $("#pairing-details").hidden = !(info.lan_access && info.listening_on_lan);
    // Le SVG vient de notre propre serveur (généré par la lib qrcode) : innerHTML sûr ici.
    $("#pairing-qr").innerHTML = info.qr_svg;
    const link = $("#pairing-url");
    link.href = info.url;
    link.textContent = info.url;
    await renderDevices();
  } catch (error) {
    toast(`Accès téléphone : ${error.message}`, "error");
  }
}

export function initPairing() {
  $("#pairing-regenerate").addEventListener("click", async () => {
    if (!confirm("Générer un nouveau code ? Les appareils connectés devront rescanner le QR code.")) return;
    try {
      await pairingApi.regenerate();
      toast("Nouveau code généré");
      renderPairing();
    } catch (error) {
      toast(error.message, "error");
    }
  });
}
