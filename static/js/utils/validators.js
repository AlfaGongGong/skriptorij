

/**
 * validators.js — Validacija korisničkog unosa
 */

/**
 * Provjerava da li je API ključ vidno popunjen.
 * @param {string} key
 * @returns {boolean}
 */
export function isValidApiKey(key) {
    return typeof key === 'string' && key.trim().length >= 8;
}

/**
 * Provjerava da li je provajder validan naziv.
 * @param {string} provider
 * @returns {boolean}
 */
export function isValidProvider(provider) {
    return typeof provider === 'string' && /^[A-Z0-9_]{2,32}$/.test(provider.toUpperCase());
}


