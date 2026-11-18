// Outil de recadrage : un carré déplaçable / redimensionnable sur l'image d'origine.
//
// Usage :
//   const result = await openCropper(imageUrl, track.cover_crop);
//   result === null      -> annulé
//   result === "auto"    -> l'utilisateur veut revenir au cadrage automatique
//   result = {left, top, size} -> cadrage choisi (fractions, voir CropBox dans models.py)
//
// Interne : la sélection est gardée en PIXELS DE L'IMAGE D'ORIGINE (x, y, side),
// puis convertie en fractions à la validation. L'affichage applique juste une échelle.

import { $ } from "./ui.js";

const MIN_ZOOM_PERCENT = 20; // le carré ne descend pas sous 20 % du petit côté

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

/**
 * Ouvre la fenêtre de recadrage et attend le choix de l'utilisateur.
 * @param {string} imageUrl     URL de l'image d'origine
 * @param {object|null} initial cadrage actuel ({left, top, size}) ou null
 * @returns {Promise<object|"auto"|null>}
 */
export async function openCropper(imageUrl, initial) {
  const dialog = $("#crop-dialog");
  const image = $("#crop-image");
  const box = $("#crop-box");
  const zoom = $("#crop-zoom");
  const preview = $("#crop-preview");

  // Charger l'image AVANT d'ouvrir (on a besoin de ses dimensions réelles)
  image.src = imageUrl;
  await image.decode();
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  const minSide = Math.min(width, height);

  // Sélection courante en pixels de l'image d'origine
  const sel = initial
    ? { x: initial.left * width, y: initial.top * height, side: initial.size * minSide }
    : { side: minSide, x: (width - minSide) / 2, y: (height - minSide) / 2 };

  /** Garde le carré entièrement dans l'image. */
  function keepInside() {
    sel.side = clamp(sel.side, (minSide * MIN_ZOOM_PERCENT) / 100, minSide);
    sel.x = clamp(sel.x, 0, width - sel.side);
    sel.y = clamp(sel.y, 0, height - sel.side);
  }

  /** Met à jour le carré affiché, le curseur de zoom et l'aperçu. */
  function render() {
    keepInside();
    const scale = image.clientWidth / width; // pixels écran par pixel d'image
    Object.assign(box.style, {
      left: `${sel.x * scale}px`,
      top: `${sel.y * scale}px`,
      width: `${sel.side * scale}px`,
      height: `${sel.side * scale}px`,
    });
    zoom.value = String(Math.round((sel.side / minSide) * 100));
    const ctx = preview.getContext("2d");
    ctx.drawImage(image, sel.x, sel.y, sel.side, sel.side, 0, 0, preview.width, preview.height);
  }

  /** Change la taille du carré en gardant son centre fixe. */
  function resize(newSide) {
    const centerX = sel.x + sel.side / 2;
    const centerY = sel.y + sel.side / 2;
    sel.side = clamp(newSide, (minSide * MIN_ZOOM_PERCENT) / 100, minSide);
    sel.x = centerX - sel.side / 2;
    sel.y = centerY - sel.side / 2;
    render();
  }

  // Tous les écouteurs sont liés à ce contrôleur : un seul abort() les retire tous
  // à la fermeture (sinon ils s'accumuleraient à chaque ouverture).
  const listeners = new AbortController();
  const opts = { signal: listeners.signal };

  // --- Glisser le carré (souris, doigt ou stylet grâce aux "pointer events")
  let drag = null;
  box.addEventListener(
    "pointerdown",
    (event) => {
      event.preventDefault();
      box.setPointerCapture(event.pointerId); // continue à suivre même hors du carré
      drag = { startX: event.clientX, startY: event.clientY, x: sel.x, y: sel.y };
    },
    opts,
  );
  box.addEventListener(
    "pointermove",
    (event) => {
      if (!drag) return;
      const scale = image.clientWidth / width;
      sel.x = drag.x + (event.clientX - drag.startX) / scale;
      sel.y = drag.y + (event.clientY - drag.startY) / scale;
      render();
    },
    opts,
  );
  box.addEventListener("pointerup", () => (drag = null), opts);
  box.addEventListener("pointercancel", () => (drag = null), opts);

  // --- Zoom : curseur ou molette
  zoom.addEventListener("input", () => resize((Number(zoom.value) / 100) * minSide), opts);
  $("#crop-stage").addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      resize(sel.side * (event.deltaY > 0 ? 1.05 : 0.95));
    },
    { ...opts, passive: false },
  );

  window.addEventListener("resize", render, opts);

  // --- Fermeture : on renvoie le résultat via une Promise
  return new Promise((resolve) => {
    const finish = (result) => {
      listeners.abort();
      dialog.close();
      resolve(result);
    };
    $("#crop-apply").addEventListener(
      "click",
      () =>
        finish({
          left: sel.x / width,
          top: sel.y / height,
          size: sel.side / minSide,
        }),
      opts,
    );
    $("#crop-reset").addEventListener("click", () => finish("auto"), opts);
    $("#crop-cancel").addEventListener("click", () => finish(null), opts);
    // Touche Échap
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(null);
    }, opts);

    dialog.showModal();
    render(); // après showModal : l'image a maintenant sa taille affichée
  });
}
