/**
 * polling.js — Upravljanje intervalnim provjeram statusa
 */

const _intervals = {};

/**
 * Pokreće periodično ispitivanje.
 * @param {string} id - Unique identifier for this poll
 * @param {Function} fn - Function to call on each tick
 * @param {number} intervalMs - Interval in milliseconds
 */
export function startPolling(id, fn, intervalMs) {
    stopPolling(id);
    fn(); // Immediately call once
    _intervals[id] = setInterval(fn, intervalMs);
}

/**
 * Zaustavi polling za dati ID.
 * @param {string} id
 */
export function stopPolling(id) {
    if (_intervals[id]) {
        clearInterval(_intervals[id]);
        delete _intervals[id];
    }
}

/**
 * Provjeri da li je polling aktivan.
 * @param {string} id
 * @returns {boolean}
 */
export function isPolling(id) {
    return Boolean(_intervals[id]);
}
