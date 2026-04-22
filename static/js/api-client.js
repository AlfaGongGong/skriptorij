/**
 * api-client.js — Centralizirani HTTP klijent za sve API pozive
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

    /** Dohvati listu knjiga (ISPRAVLJENA RUTA) */
    getBooks: () => apiFetch('/api/files'),

    /** Dohvati dostupne modele */
    getModels: () => apiFetch('/api/dev_models'),

    /** Upload knjige (ISPRAVLJENA RUTA) */
    uploadBook: (formData) => fetch('/api/upload', { method: 'POST', body: formData }).then(r => r.json()),

    /** Pokreni obradu (ISPRAVLJEN PARAMETAR) */
    startProcessing: (book, model, tool) =>
        apiFetch('/api/start', {
            method: 'POST',
            body: JSON.stringify({ book, model, tool }),
        }),

    /** Kontrola obrade (pause, resume, stop, reset) (ISPRAVLJENA RUTA) */
    sendControl: (action) =>
        apiFetch(`/api/${action}`, { method: 'POST' }),

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

    /** Obriši ključ */
    deleteKey: (provider, index) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}/${index}`, { method: 'DELETE' }),
};
