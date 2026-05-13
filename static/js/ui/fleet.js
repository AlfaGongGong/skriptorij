

/**
 * ui/fleet.js — Fleet Pool renderer
 */

const PROV_ICONS = {
    GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠',
    MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', GITHUB:'🐙',
    TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗',
    KLUSTER:'🔗', GEMMA:'🔷',
};

export function renderFleet(data) {
    const c = document.getElementById('fleet-cards-container');
    if (!c) return;

    const entries = Object.entries(data || {});
    if (entries.length === 0) {
        c.innerHTML = '<p class="tab-hint">Nema provajdera u floti.</p>';
        return;
    }

    let html = '';
    for (const [prov, info] of entries) {
        const total   = info.total   || 0;
        const keys    = info.keys    || [];
        const icon    = PROV_ICONS[prov.toUpperCase()] || '🔑';
        const srPct   = Math.round((info.success_rate ?? 1.0) * 100);
        const barCls  = srPct >= 80 ? '' : srPct >= 50 ? 'warn' : 'low';

        html += `
        <details class="fleet-card">
          <summary class="fleet-card-header">
            <span class="fleet-prov-icon">${icon}</span>
            <span class="fleet-card-name">${prov}</span>
            <div class="fleet-card-bar">
              <div class="fleet-card-bar-fill ${barCls}" style="width:${srPct}%"></div>
            </div>
            <span class="fleet-card-count">${total} ključ${total === 1 ? '' : 'a'}</span>
            <span class="fleet-chevron">▾</span>
          </summary>
          <div class="fleet-keys-grid">
            ${keys.length === 0
                ? '<span style="color:var(--tx-3);font-size:0.78rem">Nema ključeva</span>'
                : keys.map(k => renderKeyPill(k)).join('')}
          </div>
        </details>`;
    }
    c.innerHTML = html;
}

function renderKeyPill(k) {
    const sr     = k.success_rate ?? 1.0;
    const srPct  = Math.round(sr * 100);
    const total  = k.total_requests || 0;
    const failed = k.calls_failed || 0;

    let cls   = 'fleet-key-ok';
    let label = `✓ ${k.masked}`;

    if (total > 0 && sr < 0.5) {
        cls   = 'fleet-key-err';
        label = `✕ ${k.masked}`;
    } else if (total > 0 && sr < 0.8) {
        cls   = 'fleet-key-warn';
        label = `⚠ ${k.masked}`;
    }

    const statsStr = total > 0
        ? `<span style="font-size:0.68rem;opacity:0.6">${srPct}% · ${total} poz.</span>`
        : '';

    return `
    <div class="fleet-key-pill ${cls}"
         title="${k.calls_ok || 0} ok / ${failed} greš. / ${total} ukupno">
      <span class="key-dot"></span>
      <span>${label}</span>
      ${statsStr}
    </div>`;
}

export function updateFleetTotalCount(n) {
    const b = document.getElementById('fleet-total-count');
    if (b) b.textContent = n;
}

