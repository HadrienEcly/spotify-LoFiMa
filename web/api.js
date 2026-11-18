// Client de l'API REST (voir lofima/api.py).
// Toutes les fonctions renvoient une Promise et lèvent une Error avec le message
// du serveur ("detail") en cas d'échec, pour l'afficher directement à l'utilisateur.

async function request(method, path, body) {
  const options = { method, headers: {} };

  if (body instanceof FormData) {
    options.body = body; // le navigateur gère lui-même l'en-tête multipart
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  if (response.status === 204) return null; // pas de contenu (ex : suppression)

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI renvoie { detail: "..." } ou { detail: [ {msg: ...} ] } pour les erreurs de validation
    const detail = data?.detail;
    const message = Array.isArray(detail) ? detail.map((d) => d.msg).join(", ") : detail;
    throw new Error(message || `Erreur ${response.status}`);
  }
  return data;
}

const enc = encodeURIComponent;

export const api = {
  listTracks: () => request("GET", "/api/tracks"),
  addTrack: (url) => request("POST", "/api/tracks", { url }),
  updateTrack: (id, tags) => request("PATCH", `/api/tracks/${enc(id)}`, tags),
  deleteTrack: (id, keepArchive) =>
    request("DELETE", `/api/tracks/${enc(id)}?keep_archive=${keepArchive}`),
  exportTrack: (id) => request("POST", `/api/tracks/${enc(id)}/export`),
  redownloadTrack: (id) => request("POST", `/api/tracks/${enc(id)}/redownload`),
  uploadCover: (id, file) => {
    const form = new FormData();
    form.append("file", file);
    return request("PUT", `/api/tracks/${enc(id)}/cover`, form);
  },
  getSettings: () => request("GET", "/api/settings"),
  saveSettings: (settings) => request("PUT", "/api/settings", settings),
  syncAll: () => request("POST", "/api/sync"),

  // URLs directes (pour <img> et <audio>). `version` force le navigateur à
  // recharger l'image quand la musique est modifiée (cache-busting).
  coverUrl: (track) => `/api/tracks/${enc(track.id)}/cover?v=${enc(track.updated_at)}`,
  audioUrl: (track) => `/api/tracks/${enc(track.id)}/audio?v=${enc(track.updated_at)}`,
};
