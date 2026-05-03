

/**
 * formatters.js — Formatiranje brojeva, vremena i teksta
 */

/**
 * Formatira sekunde u HH:MM:SS string.
 * @param {number} seconds
 * @returns {string}
 */
export function formatTime(seconds) {
    if (!isFinite(seconds) || seconds < 0) return '--:--:--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/**
 * Maskira API ključ prikazujući samo zadnjih 6 znakova.
 * @param {string} key
 * @returns {string}
 */
export function maskKey(key) {
    if (!key || key.length <= 6) return '***';
    return `...${key.slice(-6)}`;
}

/**
 * Formatira bajte u čitljivu veličinu.
 * @param {number} bytes
 * @returns {string}
 */
export function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}


