/**
 * fleet.js — Fleet Pool renderer  (V2.0 — quota/usage po ključu)
 *
 * renderFleet(data)        — glavni entry point, poziva se iz main.js
 * updateFleetTotalCount(n) — ažurira badge u tabu
 *
 * Svaki provajder je <details> dropdown.
 * Unutar njega: tabela s po-ključnim podacima (RPM, RPD, TPD, cooldown).
 */

const PROV_ICONS = {
    GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠',
    MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', GITHUB:'🐙',
    TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗',
    KLUSTER:'🔗', GEMMA:'🔷',
};

const PROV_CONSOLE_URLS = {
    GEMINI:      'https://aistudio.google.com/',
    GROQ:        'https://console.groq.com/',
    CEREBRAS:    'https://cloud.cerebras.ai/',
    SAMBANOVA:   'https://cloud.sambanova.ai/',
    MISTRAL:     'https://console.mistral.ai/',
    COHERE:      'https://dashboard.cohere.com/',
    OPENROUTER:  'https://openrouter.ai/settings/keys',
    GITHUB:      'https://github.com/settings/tokens',
    TOGETHER:    'https://api.together.xyz/settings/api-keys',
    FIREWORKS:   'https://fireworks.ai/account/api-keys',
    CHUTES:      'https://chutes.ai/app/api-keys',
    HUGGINGFACE: 'https://huggingface.co/settings/tokens',
    KLUSTER:     'https://kluster.ai/settings/api-keys',
    GEMMA:       'https://aistudio.google.com/',
};

// ─── Pomoćne ────────────────────────────────────────────────────────────────

function escHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function fmtCooldown(s) {
    if (!s || s <= 0) return '';
    if (s < 60)  return `${Math.round(s)}s`;
    if (s < 3600) return `${Math.floor(s/60)}m ${Math.round(s%60)}s`;
    return `${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;
}

function fmtNum(n) {
    if (n == null) return '—';
    if (n >= 1_000_000) return (n/1_000_000).toFixed(1) + 'M';
    if (n >= 1_000)     return (n/1_000).toFixed(1) + 'k';
    return String(n);
}

/** Vraća CSS klasu na osnovu popunjenosti (current/safe). */
function quotaCls(current, safe) {
    if (!safe) return '';
    const pct = current / safe;
    if (pct >= 0.95) return 'quota-crit';
    if (pct >= 0.75) return 'quota-warn';
    return 'quota-ok';
}

/** Mini progress bar za kvotu. */
function quotaBar(current, safe) {
    if (!safe) return '';
    const pct = Math.min(100, Math.round((current / safe) * 100));
    const cls = pct >= 95 ? 'crit' : pct >= 75 ? 'warn' : 'ok';
    return `<div class="fq-bar"><div class="fq-bar-fill ${cls}" style="width:${pct}%"></div></div>`;
}

// ─── Per-key redak u tabeli ──────────────────────────────────────────────────

function renderKeyRow(k) {
    const avail    = k.available !== false;
    const sr       = k.success_rate ?? 1.0;
    const srPct    = Math.round(sr * 100);
    const srCls    = sr >= 0.8 ? 'good' : sr >= 0.5 ? 'warn' : 'low';

    // status indikator
    let statusIcon, statusCls;
    if (!avail && k.cooldown_s > 0) {
        statusIcon = '❄';
        statusCls  = 'key-status-cool';
    } else if (!avail) {
        statusIcon = '✕';
        statusCls  = 'key-status-err';
    } else {
        statusIcon = '●';
        statusCls  = 'key-status-ok';
    }

    // rejected breakdown (samo 429 i 5xx)
    const rej = k.calls_rejected || {};
    const r429 = rej['429'] || 0;
    const r5xx = Object.entries(rej)
        .filter(([code]) => Number(code) >= 500)
        .reduce((s, [, v]) => s + v, 0);

    // cooldown cell
    const cdSecs = k.cooldown_s || 0;
    const cdText = cdSecs > 0
        ? `<span class="fq-cooldown" title="${k.cooldown_reason || ''}">${fmtCooldown(cdSecs)}</span>`
        : '<span class="fq-none">—</span>';

    // RPM cell
    const rpmText = (k.rpm_safe > 0)
        ? `<span class="${quotaCls(k.rpm, k.rpm_safe)}">${k.rpm ?? 0}</span>` +
          `<span class="fq-safe">/${k.rpm_safe}</span>` +
          quotaBar(k.rpm, k.rpm_safe)
        : `<span>${k.rpm ?? 0}</span>`;

    // RPD cell
    const rpdText = (k.rpd_safe > 0)
        ? `<span class="${quotaCls(k.rpd, k.rpd_safe)}">${fmtNum(k.rpd)}</span>` +
          `<span class="fq-safe">/${fmtNum(k.rpd_safe)}</span>` +
          quotaBar(k.rpd, k.rpd_safe)
        : `<span>${fmtNum(k.rpd ?? 0)}</span>`;

    // TPD cell
    const tpdText = (k.tpd != null && k.tpd > 0)
        ? `<span>${fmtNum(k.tpd)}</span>`
        : '<span class="fq-none">—</span>';

    return `
    <tr class="fq-row${avail ? '' : ' fq-row-unavail'}">
      <td class="fq-td fq-td-status">
        <span class="fq-status-dot ${statusCls}">${statusIcon}</span>
      </td>
      <td class="fq-td fq-td-key">
        <span class="fq-key-masked">${k.masked || k.key}</span>
      </td>
      <td class="fq-td fq-td-sr">
        <div class="fq-sr-wrap">
          <span class="fq-sr-val fleet-health-fill-text ${srCls}">${srPct}%</span>
          <div class="fleet-health-bar fq-srbar">
            <div class="fleet-health-fill ${srCls}" style="width:${srPct}%"></div>
          </div>
        </div>
      </td>
      <td class="fq-td fq-td-metric">${rpmText}</td>
      <td class="fq-td fq-td-metric">${rpdText}</td>
      <td class="fq-td fq-td-metric">${tpdText}</td>
      <td class="fq-td fq-td-calls">
        <span class="fq-ok">${fmtNum(k.calls_ok ?? 0)}</span>
        ${r429 > 0 ? `<span class="fq-429" title="Rate limit hits">·${fmtNum(r429)}</span>` : ''}
        ${r5xx > 0 ? `<span class="fq-5xx" title="Server errors">·${fmtNum(r5xx)}</span>` : ''}
        ${(k.calls_failed || 0) > 0 ? `<span class="fq-fail" title="Network failures">·${fmtNum(k.calls_failed)}</span>` : ''}
      </td>
      <td class="fq-td fq-td-cool">${cdText}</td>
    </tr>`;
}

// ─── Provider blok (details/summary + tabela) ────────────────────────────────

function renderProviderBlock(prov, info, isExpert = false) {
    const keys    = info.keys || [];
    const total   = info.total || keys.length;
    const icon    = PROV_ICONS[prov.toUpperCase()] || '🔑';
    const srPct   = Math.round((info.success_rate ?? 1.0) * 100);
    const barCls  = srPct >= 80 ? 'good' : srPct >= 50 ? 'warn' : 'low';

    // koliko ključeva je na cooldownu
    const cooling = keys.filter(k => (k.cooldown_s || 0) > 0).length;
    const unavail = keys.filter(k => k.available === false).length;
    const coolBadge = cooling > 0
        ? `<span class="fq-prov-badge fq-badge-cool" title="${cooling} ključ${cooling===1?'':'a'} na cooldownu">❄ ${cooling}</span>`
        : '';
    const unavailBadge = unavail > 0 && cooling === 0
        ? `<span class="fq-prov-badge fq-badge-unavail" title="${unavail} nedostupno">✕ ${unavail}</span>`
        : '';

    const extraStyle = isExpert ? 'margin-bottom:6px;' : '';

    const tableHtml = keys.length > 0 ? `
      <div class="fq-table-wrap">
        <table class="fq-table">
          <thead>
            <tr>
              <th class="fq-th"></th>
              <th class="fq-th">Ključ</th>
              <th class="fq-th">SR%</th>
              <th class="fq-th" title="Requests Per Minute (tekući/limit)">RPM</th>
              <th class="fq-th" title="Requests Per Day (tekući/limit)">RPD</th>
              <th class="fq-th" title="Tokens Per Day (tekući)">TPD</th>
              <th class="fq-th" title="Uspješni · 429 · 5xx · mrežne greške">Pozivi</th>
              <th class="fq-th">Cooldown</th>
            </tr>
          </thead>
          <tbody>
            ${keys.map(k => renderKeyRow(k)).join('')}
          </tbody>
        </table>
      </div>` : '<div class="fq-empty">Nema ključeva</div>';

    return `
    <details class="fleet-provider fq-details" style="${extraStyle}">
      <summary class="fleet-provider-header fq-summary">
        <span class="fq-chevron">▸</span>
        <span class="fq-prov-icon">${icon}</span>
        ${PROV_CONSOLE_URLS[prov.toUpperCase()]
            ? `<a class="fq-prov-name" href="${PROV_CONSOLE_URLS[prov.toUpperCase()]}" target="_blank" rel="noopener noreferrer" title="Otvori konzolu ${escHtml(prov)}">${escHtml(prov)}</a>`
            : `<span class="fq-prov-name">${escHtml(prov)}</span>`}
        <div class="fleet-health-bar fq-hbar">
          <div class="fleet-health-fill ${barCls}" style="width:${srPct}%"></div>
        </div>
        <span class="fq-prov-count">${total} ključ${total===1?'':'a'}</span>
        ${coolBadge}${unavailBadge}
      </summary>
      <div class="fq-body">
        ${tableHtml}
      </div>
    </details>`;
}

// ─── Glavni export ───────────────────────────────────────────────────────────

function renderFleet(data) {
    const c        = document.getElementById('fleet-cards-container');
    const simpleOk  = document.getElementById('fleet-ok-count');
    const simpleCol = document.getElementById('fleet-cooling-count');
    const simpleErr = document.getElementById('fleet-err-count');
    if (!c) return;

    const entries = Object.entries(data || {});
    if (entries.length === 0) {
        c.innerHTML = '<div class="fq-empty fq-empty-full">Nema provajdera u floti.</div>';
        if (simpleOk)  simpleOk.textContent  = 0;
        if (simpleCol) simpleCol.textContent = 0;
        if (simpleErr) simpleErr.textContent = 0;
        return;
    }

    // Agregirane brojke za summary boxes
    let totalKeys = 0, totalLowSr = 0, totalFailed = 0;
    for (const [, info] of entries) {
        const keys = info.keys || [];
        totalKeys += info.total || keys.length;
        for (const k of keys) {
            const sr = k.success_rate ?? 1.0;
            if ((k.total_requests || 0) > 0 && sr < 0.5) totalLowSr++;
            totalFailed += (k.calls_failed || 0);
        }
    }

    if (simpleOk)  simpleOk.textContent  = totalKeys;
    if (simpleCol) simpleCol.textContent = totalLowSr;
    if (simpleErr) simpleErr.textContent = totalFailed;
    document.getElementById('fleet-total-count').textContent = totalKeys;

    // Health badge u expert tabu
    let totalWeightedSr = 0;
    for (const [, info] of entries) {
        (info.keys || []).forEach(k => { totalWeightedSr += (k.success_rate ?? 1.0); });
    }
    if (typeof updateExpertFleetHealthBadge === 'function') {
        updateExpertFleetHealthBadge(Math.round(totalWeightedSr), totalKeys);
    }

    // Fleet tab — provider dropdowni
    c.innerHTML = entries.map(([prov, info]) => renderProviderBlock(prov, info, false)).join('');

    // Animacija chevron-a na open/close
    c.querySelectorAll('.fq-details').forEach(det => {
        det.addEventListener('toggle', () => {
            const ch = det.querySelector('.fq-chevron');
            if (ch) ch.style.transform = det.open ? 'rotate(90deg)' : '';
        });
    });

    // Expert tab — isti blokovi
    const expertC = document.getElementById('expert-fleet-container');
    if (expertC) {
        if (entries.length === 0) {
            expertC.innerHTML = '<div class="fq-empty fq-empty-full">Nema provajdera u floti.</div>';
        } else {
            expertC.innerHTML = entries.map(([prov, info]) => renderProviderBlock(prov, info, true)).join('');
            expertC.querySelectorAll('.fq-details').forEach(det => {
                det.addEventListener('toggle', () => {
                    const ch = det.querySelector('.fq-chevron');
                    if (ch) ch.style.transform = det.open ? 'rotate(90deg)' : '';
                });
            });
        }
    }
}

function updateFleetTotalCount(n) {
    const b = document.getElementById('fleet-total-count');
    if (b) b.textContent = n;
}
