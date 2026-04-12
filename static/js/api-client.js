/**
 * api-client.js — Centralizirani HTTP klijent za sve API pozive
 */

/**
 * Generički fetch wrapper s error handlingom.
 * @param {string} url
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
}

export const apiClient = {
    /** Dohvati status obrade */
    getStatus: () => apiFetch('/api/status'),

    /** Dohvati listu knjiga */
    getBooks: () => apiFetch('/api/books'),

    /** Dohvati dostupne modele */
    getModels: () => apiFetch('/api/dev_models'),

    /** Upload knjige */
    uploadBook: (formData) => fetch('/api/upload_book', { method: 'POST', body: formData }).then(r => r.json()),

    /** Pokreni obradu */
    startProcessing: (book, model, mode) =>
        apiFetch('/api/start', {
            method: 'POST',
            body: JSON.stringify({ book, model, mode }),
        }),

    /** Kontrola obrade (pause, resume, stop, reset) */
    sendControl: (action) =>
        apiFetch(`/control/${action}`, { method: 'POST' }),

    /** Dohvati fleet status */
    getFleet: () => apiFetch('/api/fleet'),

    /** Toggle ključ u floti */
    toggleFleetKey: (provider, key) =>
        apiFetch('/api/fleet/toggle', {
            method: 'POST',
            body: JSON.stringify({ provider, key }),
        }),

    /** Dohvati API ključeve */
    getKeys: () => apiFetch('/api/keys'),

    /** Dodaj API ključ */
    addKey: (provider, key) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}`, {
            method: 'POST',
            body: JSON.stringify({ key }),
        }),

    /** Obriši API ključ */
    deleteKey: (provider, idx) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}/${idx}`, {
            method: 'DELETE',
        }),
};
