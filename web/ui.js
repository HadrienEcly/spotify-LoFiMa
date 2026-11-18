// Petits utilitaires d'interface partagés par app.js, queue.js et cropper.js.

/** Raccourci pour document.querySelector */
export const $ = (selector) => document.querySelector(selector);

/** Affiche une notification qui disparaît seule. type = "info" | "error" */
export function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), type === "error" ? 8000 : 3500);
}

/**
 * Désactive un bouton pendant une action async et affiche un libellé d'attente.
 * Évite les doubles clics. En cas d'erreur : toast + retourne undefined.
 */
export async function withBusy(button, busyLabel, action) {
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
