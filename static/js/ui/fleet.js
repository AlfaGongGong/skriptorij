/**
 * fleet.js — Fleet Pool prikaz (neon naljepnice + toggle po ključu)
 */
import { FLEET_PROV_ICONS, FLEET_BAR_HIGH, FLEET_BAR_MID } from '../utils/constants.js';
import { showToast } from './notifications.js';
import { apiClient } from '../api-client.js';

function _fleetKeyStatus(k) {
    if (k.disabled) return { cls: 'blokiran', label: 'BLOKIRAN', icon: '🔴' };
    if (k.available) return { cls: 'aktivan', label: 'AKTIVAN', icon: '✅' };
    // Na cooldownu (rate-limit ili privremena greška)
    const secs = k.cooldown_remaining > 0 ? ` ${Math.ceil(k.cooldown_remaining)}s` : '';
    return { cls: 'limitiran', label: `LIMITIRAN${secs}`, icon: '⏳' };
}

function _fleetHealthColor(pct) {
    if (pct > FLEET_BAR_HIGH) return '#00FF41';
    if (pct > FLEET_BAR_MID)  return '#f59e0b';
    return '#ff2a00';
}

export function renderFleetPool(data) {
    const container = document.getElementById('fleet-pool-content');
    if (!container) return;

    if (data.error) {
        container.innerHTML = `<p style="color:var(--col-danger);font-size:0.85rem;">Greška: ${data.error}</p>`;
        return;
    }

    const providers = Object.entries(data);
    if (providers.length === 0) {
        container.innerHTML = '<p style="color:var(--text-muted);font-size:0.85rem;">Nema konfiguriranih provajdera.</p>';
        return;
    }

    // Preserve open state
    const openStates = {};
    container.querySelectorAll('.fleet-card[data-prov]').forEach(el => {
        openStates[el.dataset.prov] = el.open;
    });

    const wrapper = document.createElement('div');
    wrapper.className = 'fleet-cards';

    for (const [prov, info] of providers) {
        const active = info.active || 0;
        const total  = info.total  || 1;
        const pct    = Math.round((active / total) * 100);
        const color  = _fleetHealthColor(pct);
        const keys   = info.keys || [];
        const icon   = FLEET_PROV_ICONS[prov] || '🛡️';
        const keyWord = total === 1 ? 'ključ' : total < 5 ? 'ključa' : 'ključeva';

        const card = document.createElement('details');
        card.className = 'fleet-card';
        card.dataset.prov = prov;
        if (openStates[prov]) card.open = true;

        const summary = document.createElement('summary');
        summary.className = 'fleet-card-header';
        summary.innerHTML =
            `<div class="fleet-card-title">
                <span class="fleet-card-icon">${icon}</span>
                <span class="fleet-card-name">${prov}</span>
                <span class="fleet-card-count">[${total}\u00a0${keyWord}]</span>
            </div>
            <div class="fleet-card-meta">
                <div class="fleet-health-bar-wrap">
                    <div class="fleet-health-bar-bg">
                        <div class="fleet-health-bar-fill" style="width:${pct}%;background:${color};"></div>
                    </div>
                </div>
                <span class="fleet-health-pct" style="color:${color};">${pct}%</span>
                <span class="fleet-chevron">▼</span>
            </div>`;
        card.appendChild(summary);

        const keysDiv = document.createElement('div');
        keysDiv.className = 'fleet-keys-grid';

        if (keys.length === 0) {
            keysDiv.innerHTML = `<span style="color:var(--text-muted);font-size:0.8rem;">${active}\u00a0/\u00a0${total} aktivno</span>`;
        } else {
            keys.forEach(k => {
                const st = _fleetKeyStatus(k);
                let ratePct = null;
                if (k.rate_limit_minute && k.remaining_minute !== null && k.remaining_minute !== undefined) {
                    ratePct = Math.round((k.remaining_minute / k.rate_limit_minute) * 100);
                }

                const rateBar = ratePct != null
                    ? `<div class="fleet-rate-bar-bg"><div class="fleet-rate-bar-fill" style="width:${ratePct}%;"></div></div>`
                    : '';

                const statsArr = [];
                if (k.total_requests != null) statsArr.push(`REQ\u00a0${k.total_requests}`);
                if (k.remaining_minute != null) statsArr.push(`REM\u00a0${k.remaining_minute}`);
                if (k.errors > 0) statsArr.push(`<span style="color:var(--col-danger);">ERR\u00a0${k.errors}</span>`);

                const pill = document.createElement('div');
                pill.className = `fleet-key-pill fleet-key-${st.cls}${k.disabled ? ' fleet-key-disabled' : ''}`;
                pill.dataset.key  = k.key  || '';
                pill.dataset.prov = prov;

                const toggleTitle = k.disabled ? 'Uključi ključ' : 'Isključi ključ';
                const toggleIcon  = k.disabled ? '🟢' : '🔴';
                pill.innerHTML =
                    `<div class="fleet-key-top">
                        <span class="fleet-key-mask">${k.masked || '***'}</span>
                        <span class="fleet-key-status-badge fleet-badge-${st.cls}">${st.icon}\u00a0${st.label}</span>
                        <button class="fleet-toggle-btn" title="${toggleTitle}" aria-label="${toggleTitle}">${toggleIcon}</button>
                    </div>
                    ${rateBar}
                    ${statsArr.length ? `<div class="fleet-key-stats">${statsArr.join('<span class="fleet-stat-sep">·</span>')}</div>` : ''}`;

                pill.querySelector('.fleet-toggle-btn').addEventListener('click', function(e) {
                    e.stopPropagation();
                    const keyVal  = pill.dataset.key;
                    const provVal = pill.dataset.prov;
                    if (!keyVal) return;
                    apiClient.toggleFleetKey(provVal, keyVal)
                        .then(() => updateFleetPool())
                        .catch(() => showToast('Greška pri toggleu ključa', 'error'));
                });

                keysDiv.appendChild(pill);
            });
        }

        card.appendChild(keysDiv);
        wrapper.appendChild(card);
    }

    container.replaceChildren(wrapper);
}

export function updateFleetPool() {
    apiClient.getFleet()
        .then(data => renderFleetPool(data))
        .catch(() => {
            const container = document.getElementById('fleet-pool-content');
            if (container) {
                container.innerHTML = '<p style="color:var(--col-danger);font-size:0.85rem;">Greška pri dohvaćanju flote.</p>';
            }
        });
}
