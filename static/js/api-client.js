

/**
 * api-client.js — Centralizirani HTTP klijent za sve API pozive
 * ISPRAVLJENA VERZIJA: sve rute sinhronizovane s Flask backend-om
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

    /** Dohvati listu EPUB fajlova iz INPUT_DIR */
    getBooks: () => apiFetch('/api/files'),

    /** Dohvati dostupne modele */
    getModels: () => apiFetch('/api/dev_models'),

    /**
     * Upload knjige — ISPRAVLJENA RUTA: /api/upload_book
     * Flask ruta je definisana u api/routes/books.py
     */
    uploadBook: (formData) =>
        fetch('/api/upload_book', { method: 'POST', body: formData }).then(r => r.json()),

    /** Pokreni obradu */
    startProcessing: (book, model, tool) =>
        apiFetch('/api/start', {
            method: 'POST',
            body: JSON.stringify({ book, model, tool }),
        }),

    /**
     * Kontrola obrade — ISPRAVLJENA RUTA: /control/<action>
     * Flask rute su: /control/pause, /control/resume, /control/stop, /control/reset
     */
    sendControl: (action) =>
        apiFetch(`/control/${action}`, { method: 'POST' }),

    /** Dohvati fleet status (UI format) */
    getFleet: () => apiFetch('/api/fleet'),

    /** Toggle ključa u floti */
    toggleFleetKey: (provider, key) =>
        apiFetch('/api/fleet/toggle', {
            method: 'POST',
            body: JSON.stringify({ provider, key }),
        }),

    /** Dohvati API ključeve (maskirane) */
    getKeys: () => apiFetch('/api/keys'),

    /** Dodaj API ključ za provajdera */
    addKey: (provider, key) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}`, {
            method: 'POST',
            body: JSON.stringify({ key }),
        }),

    /** Obriši ključ po indeksu */
    deleteKey: (provider, index) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}/${index}`, { method: 'DELETE' }),

    /** Export izvještaja */
    exportReport: (fmt) => fetch(`/api/export/${fmt}`).then(r => r.blob()),
};


