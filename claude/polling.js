/**
 * polling.js — Pravi real-time polling za status i fleet
 * ISPRAVLJENA VERZIJA: stub zamijenjen pravom implementacijom
 */

import { apiClient } from '../api-client.js';

let _statusIntervalId  = null;
let _fleetIntervalId   = null;
let _onStatusCallback  = null;
let _onFleetCallback   = null;

const POLL_STATUS_MS = 1500;
const POLL_FLEET_MS  = 6000;

/**
 * Pokreni polling status-a i fleet-a.
 * @param {Function} onStatus - callback(statusData)
 * @param {Function} onFleet  - callback(fleetData)
 */
export function startPolling(onStatus, onFleet) {
    stopPolling(); // osiguraj da nema duplikata

    _onStatusCallback = onStatus;
    _onFleetCallback  = onFleet;

    // Status — svake 1.5s
    _statusIntervalId = setInterval(async () => {
        try {
            const data = await apiClient.getStatus();
            if (_onStatusCallback) _onStatusCallback(data);
        } catch (e) {
            console.warn('[Polling] Status greška:', e.message);
        }
    }, POLL_STATUS_MS);

    // Fleet — svake 6s
    _fleetIntervalId = setInterval(async () => {
        try {
            const data = await apiClient.getFleet();
            if (_onFleetCallback) _onFleetCallback(data);
        } catch (e) {
            console.warn('[Polling] Fleet greška:', e.message);
        }
    }, POLL_FLEET_MS);

    console.log('[Polling] Pokrenut — status svake', POLL_STATUS_MS, 'ms, fleet svake', POLL_FLEET_MS, 'ms');
}

/** Zaustavi sav polling. */
export function stopPolling() {
    if (_statusIntervalId) { clearInterval(_statusIntervalId); _statusIntervalId = null; }
    if (_fleetIntervalId)  { clearInterval(_fleetIntervalId);  _fleetIntervalId  = null; }
    console.log('[Polling] Zaustavljen');
}

/** Da li je polling aktivan? */
export function isPolling() {
    return _statusIntervalId !== null;
}
