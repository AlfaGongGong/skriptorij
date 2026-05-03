

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
        const active  = info.active  || 0;
        const total   = info.total   || 0;
        const keys    = info.keys    || [];
        const icon    = PROV_ICONS[prov.toUpperCase()] || '🔑';
        const pct     = total > 0 ? Math.round((active / total) * 100) : 0;
        const barCls  = pct >= 60 ? '' : pct >= 30 ? 'warn' : 'low';

        html += `
        <details class="fleet-card">
          <summary class="fleet-card-header">
            <span class="fleet-prov-icon">${icon}</span>
            <span class="fleet-card-name">${prov}</span>
            <div class="fleet-card-bar">
              <div class="fleet-card-bar-fill ${barCls}" style="width:${pct}%"></div>
            </div>
            <span class="fleet-card-count">${active}/${total}</span>
            <span class="fleet-chevron">▾</span>
          </summary>
          <div class="fleet-keys-grid">
            ${keys.length === 0
                ? '<span style="color:var(--tx-3);font-size:0.78rem">Nema ključeva</span>'
                : keys.map(k => renderKeyPill(prov, k)).join('')}
          </div>
        </details>`;
    }
    c.innerHTML = html;
}

function renderKeyPill(prov, k) {
    const available = k.available && !k.disabled;
    const cooling   = !k.available && !k.disabled && k.cooldown_remaining > 0;
    const disabled  = k.disabled;
    const error     = !k.available && !k.disabled && !cooling;

    let cls   = 'fleet-key-ok';
    let label = `✓ ${k.masked}`;
    let extra = '';

    if (disabled) {
        cls   = 'fleet-key-off';
        label = `○ ${k.masked}`;
    } else if (cooling) {
        cls   = 'fleet-key-warn';
        const s = Math.ceil(k.cooldown_remaining);
        label = `⏳ ${k.masked}`;
        extra = `<span style="font-size:0.68rem;opacity:0.7">${s}s</span>`;
    } else if (error) {
        cls   = 'fleet-key-err';
        label = `✕ ${k.masked}`;
    }

    const health = k.health != null
        ? `<span style="font-size:0.68rem;opacity:0.6">${k.health}%</span>`
        : '';

    return `
    <div class="fleet-key-pill ${cls} ${disabled ? 'disabled' : ''}"
         title="Toggle ključ"
         onclick="toggleFleetKey('${prov}','${k.masked}')">
      <span class="key-dot"></span>
      <span>${label}</span>
      ${health}
      ${extra}
    </div>`;
}

export function updateFleetTotalCount(n) {
    const b = document.getElementById('fleet-total-count');
    if (b) b.textContent = n;
}

// Global za onclick iz HTML-a
window.toggleFleetKey = async function(provider, key) {
    try {
        const { showToast } = await import('./notifications.js');
        const { apiClient } = await import('../api-client.js');
        const res = await apiClient.toggleFleetKey(provider, key);
        const msg = res.disabled ? `${provider} ključ onemogućen` : `${provider} ključ aktiviran`;
        showToast(msg, res.disabled ? 'warning' : 'success');
        // Refresh fleet prikaz
        const fleet = await apiClient.getFleet();
        renderFleet(fleet);
        updateFleetTotalCount(
            Object.values(fleet).reduce((s,p) => s + (p.active||0), 0)
        );
    } catch (e) {
        console.error('[toggleFleetKey]', e);
    }
};


