/**
 * constants.js — Magični stringovi i konfiguracija
 */

// Ikone po provajderu
export const FLEET_PROV_ICONS = {
    GROQ: '⚡', GEMINI: '♊', SAMBANOVA: '🧠', OPENROUTER: '🔀',
    MISTRAL: '💫', COHERE: '🌐', CEREBRAS: '🔬', GITHUB: '🐙',
};

// Pragovi zdravlja flote
export const FLEET_BAR_HIGH = 60;
export const FLEET_BAR_MID  = 30;

// Poliranje statusa
export const POLL_INTERVAL_MS       = 1000;
export const FLEET_POLL_INTERVAL_MS = 5000;

// LocalStorage ključevi
export const LS_INTRO_SHOWN = 'skriptorij_intro_shown';
export const LS_THEME       = 'skriptorij_theme';
