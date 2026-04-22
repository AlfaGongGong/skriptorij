export function renderFleet(data) {
    const c = document.getElementById('fleet-cards-container');
    if (!c) return;
    let h = '';
    for (const [p, info] of Object.entries(data)) {
        h += `<details class="fleet-card"><summary class="fleet-card-header"><span class="fleet-card-name">${p}</span><span class="fleet-card-count">${info.active||0}/${info.total||0}</span></summary><div class="fleet-keys-grid">`;
        (info.keys||[]).forEach(k => h += `<div class="fleet-key-pill"><span>${k.masked}</span><span>${k.available?'✅':'⏳'}</span></div>`);
        h += '</div></details>';
    }
    c.innerHTML = h || '<p>Nema provajdera</p>';
}
export async function fetchFleet() { const r = await fetch('/api/fleet'); return r.json(); }
export function updateFleetTotalCount(n) { const b = document.getElementById('fleet-total-count'); if (b) b.textContent = n; }
