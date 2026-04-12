/**
 * main.js — Ulazna tačka za modularne JavaScript module
 *
 * NAPOMENA: Ovaj fajl koristi ES Module syntax (type="module").
 * Trenutna app.js je monolitna verzija koja ostaje kao fallback.
 * Ovi moduli su dostupni za buduću integraciju / build alat (Vite/Webpack).
 */

import { applyStoredTheme, toggleTheme } from './services/theme.js';
import { showToast } from './ui/notifications.js';
import { updateFleetPool } from './ui/fleet.js';
import { apiClient } from './api-client.js';
import { LS_INTRO_SHOWN, POLL_INTERVAL_MS, FLEET_POLL_INTERVAL_MS } from './utils/constants.js';

let pollInterval     = null;
let fleetPollActive  = false;

document.addEventListener('DOMContentLoaded', () => {
    // ── Intro handling ─────────────────────────────────────────────────────
    const introOverlay = document.getElementById('intro-overlay');
    const mainUI       = document.getElementById('main-ui-wrapper');

    if (introOverlay) {
        if (localStorage.getItem(LS_INTRO_SHOWN)) {
            introOverlay.remove();
            if (mainUI) { mainUI.style.display = 'block'; mainUI.style.opacity = '1'; }
            document.body.style.overflow = 'auto';
        } else {
            localStorage.setItem(LS_INTRO_SHOWN, 'true');
            setTimeout(() => {
                const overlay = document.getElementById('intro-overlay');
                const ui      = document.getElementById('main-ui-wrapper');
                if (overlay) overlay.remove();
                if (ui) { ui.style.display = 'block'; ui.style.opacity = '1'; }
                document.body.style.overflow = 'auto';
            }, 13000);
        }
    }

    applyStoredTheme();

    // ── Fleet pool panel ────────────────────────────────────────────────────
    const fleetDetails = document.getElementById('fleet-details');
    if (fleetDetails) {
        fleetDetails.addEventListener('toggle', () => {
            if (fleetDetails.open && !fleetPollActive) {
                fleetPollActive = true;
                updateFleetPool();
                setInterval(updateFleetPool, FLEET_POLL_INTERVAL_MS);
            }
        });
    }
});

// Exponiraj na window radi backwards compat s inline onclick
window.toggleTheme = toggleTheme;
window.showToast   = showToast;
