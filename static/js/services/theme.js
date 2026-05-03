

/**
 * theme.js — Upravljanje svjetlosnim/tamnim temom
 */
import { LS_THEME } from '../utils/constants.js';

/**
 * Primijeni sačuvanu temu iz localStorage.
 */
export function applyStoredTheme() {
    const stored = localStorage.getItem(LS_THEME);
    if (stored === 'light') {
        document.body.classList.add('light');
        _updateThemeBtn(true);
    } else {
        document.body.classList.remove('light');
        _updateThemeBtn(false);
    }
}

/**
 * Mijenja aktivnu temu i pamti odabir.
 */
export function toggleTheme() {
    const isLight = document.body.classList.toggle('light');
    localStorage.setItem(LS_THEME, isLight ? 'light' : 'dark');
    _updateThemeBtn(isLight);
}

function _updateThemeBtn(isLight) {
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = isLight ? '🌙 Tamna' : '☀️ Svijetla';
}

// Exponiraj toggleTheme na window za inline onclick
window.toggleTheme = toggleTheme;


