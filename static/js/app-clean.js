// ===== BOOKLYFI - KOMPLETAN JS =====
let _startTime = null;

// ---------- OSNOVNE FUNKCIJE ----------
function toggleTheme() {
    document.body.classList.toggle('light-theme');
    localStorage.setItem('theme', document.body.classList.contains('light-theme') ? 'light' : 'dark');
    saveAppState();
}
function showSetup() {
    document.getElementById('setup-panel')?.classList.remove('hidden');
    document.getElementById('dashboard-panel')?.classList.add('hidden');
    saveAppState();
}
function wizardNext() {
    const book = document.getElementById('book-select')?.value;
    if (!book) { alert('Odaberi knjigu!'); return; }
    document.getElementById('wizard-page-1')?.classList.add('hidden');
    document.getElementById('wizard-page-2')?.classList.remove('hidden');
    document.getElementById('step-1')?.classList.remove('active');
    document.getElementById('step-2')?.classList.add('active');
    saveAppState();
}
function wizardBack() {
    document.getElementById('wizard-page-2')?.classList.add('hidden');
    document.getElementById('wizard-page-1')?.classList.remove('hidden');
    document.getElementById('step-2')?.classList.remove('active');
    document.getElementById('step-1')?.classList.add('active');
    saveAppState();
}
function switchTab(tabId) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('tab-active'));
    const panel = document.getElementById(tabId);
    if (panel) panel.classList.remove('hidden');
    const btn = document.querySelector(`[onclick="switchTab('${tabId}')"]`);
    if (btn) btn.classList.add('tab-active');
    if (tabId === 'tab-fleet') loadFleetComplete();
    saveAppState();
}
function sendControl(cmd) { fetch('/control/'+cmd, {method:'POST'}); }
function addKey() { alert('Dodavanje ključeva - implementirajte'); }

// ---------- SPREMANJE STANJA ----------
function saveAppState() {
    try {
        const state = {
            book: document.getElementById('book-select')?.value || '',
            model: document.getElementById('model-select')?.value || '',
            mode: document.querySelector('input[name="mode"]:checked')?.value || 'PREVOD',
            step2: document.getElementById('wizard-page-2') ? !document.getElementById('wizard-page-2').classList.contains('hidden') : false,
            dashboard: document.getElementById('dashboard-panel') ? !document.getElementById('dashboard-panel').classList.contains('hidden') : false,
            theme: document.body.classList.contains('light-theme') ? 'light' : 'dark'
        };
        localStorage.setItem('bf_state', JSON.stringify(state));
    } catch(e) {}
}

function restoreAppState() {
    try {
        const raw = localStorage.getItem('bf_state');
        if (!raw) return;
        const s = JSON.parse(raw);
        
        if (s.theme === 'light') document.body.classList.add('light-theme');
        
        const check = setInterval(function() {
            const bs = document.getElementById('book-select');
            const ms = document.getElementById('model-select');
            
            if (bs && bs.options.length > 1 && ms && ms.options.length > 0) {
                if (s.book && Array.from(bs.options).some(o => o.value === s.book)) bs.value = s.book;
                if (s.model && Array.from(ms.options).some(o => o.value === s.model)) ms.value = s.model;
                if (s.mode) {
                    const r = document.querySelector(`input[name="mode"][value="${s.mode}"]`);
                    if (r) r.checked = true;
                }
                if (s.step2) {
                    document.getElementById('wizard-page-1')?.classList.add('hidden');
                    document.getElementById('wizard-page-2')?.classList.remove('hidden');
                    document.getElementById('step-1')?.classList.remove('active');
                    document.getElementById('step-2')?.classList.add('active');
                }
                if (s.dashboard) {
                    document.getElementById('setup-panel')?.classList.add('hidden');
                    document.getElementById('dashboard-panel')?.classList.remove('hidden');
                    // Pokreni dashboard polling
                    startDashboardPolling();
                }
                clearInterval(check);
            }
        }, 200);
        setTimeout(() => clearInterval(check), 10000);
    } catch(e) {}
}

// ---------- UPLOAD ----------
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    
    if (fileInput) {
        fileInput.addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            uploadStatus.textContent = '⏳ Upload: ' + file.name + '...';
            const fd = new FormData(); fd.append('file', file);
            try {
                const resp = await fetch('/api/upload_book', { method: 'POST', body: fd });
                const data = await resp.json();
                if (data.error) throw new Error(data.error);
                uploadStatus.textContent = '✅ ' + data.name;
                // Osvježi listu knjiga
                const booksResp = await fetch('/api/books');
                const booksData = await booksResp.json();
                const select = document.getElementById('book-select');
                if (select && booksData.books) {
                    select.innerHTML = '<option value="">-- Odaberi knjigu --</option>';
                    booksData.books.forEach(b => select.add(new Option(b.name, b.path)));
                    select.value = data.name || file.name;
                    saveAppState();
                }
            } catch (e) {
                uploadStatus.textContent = '❌ ' + e.message;
            }
        });
    }
    
    // Učitaj knjige i modele
    loadBooksAndModels();
    
    // Vrati stanje
    setTimeout(restoreAppState, 600);
    
    // Spremi stanje na svaki događaj
    document.addEventListener('click', saveAppState);
    document.addEventListener('change', saveAppState);
    setInterval(saveAppState, 3000);
    window.addEventListener('beforeunload', saveAppState);
});

// ---------- UČITAVANJE KNJIGA I MODELA ----------
async function loadBooksAndModels() {
    try {
        const [booksResp, modelsResp] = await Promise.all([
            fetch('/api/books'),
            fetch('/api/dev_models')
        ]);
        const booksData = await booksResp.json();
        const models = await modelsResp.json();
        
        const bs = document.getElementById('book-select');
        if (bs && booksData.books) {
            bs.innerHTML = '<option value="">-- Odaberi knjigu --</option>';
            booksData.books.forEach(b => bs.add(new Option(b.name, b.path)));
        }
        
        const ms = document.getElementById('model-select');
        if (ms && Array.isArray(models)) {
            ms.innerHTML = '';
            models.forEach(m => ms.add(new Option(m, m)));
            ms.value = 'V8_TURBO';
        }
    } catch(e) {
        console.error('Load error:', e);
    }
}

// ---------- POKRETANJE SISTEMA ----------
document.addEventListener('DOMContentLoaded', function() {
    const btnStart = document.getElementById('btn-start');
    if (!btnStart) return;
    
    btnStart.addEventListener('click', async function(e) {
        e.preventDefault();
        const book = document.getElementById('book-select')?.value;
        const model = document.getElementById('model-select')?.value || 'V8_TURBO';
        const mode = document.querySelector('input[name="mode"]:checked')?.value || 'PREVOD';
        
        if (!book) { alert('Odaberi knjigu!'); return; }
        
        btnStart.textContent = '⏳ Pokrećem...';
        btnStart.disabled = true;
        
        try {
            const resp = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ book, model, mode })
            });
            const data = await resp.json();
            if (data.error) throw new Error(data.error);
            
            document.getElementById('setup-panel')?.classList.add('hidden');
            document.getElementById('dashboard-panel')?.classList.remove('hidden');
            saveAppState();
            startDashboardPolling();
        } catch(e) {
            alert('❌ ' + e.message);
            btnStart.textContent = '🚀 Pokreni Sistem';
            btnStart.disabled = false;
        }
    });
});

// ---------- DASHBOARD POLLING ----------
let dashboardInterval = null;
function startDashboardPolling() {
    if (dashboardInterval) clearInterval(dashboardInterval);
    dashboardInterval = setInterval(async function() {
        try {
            const resp = await fetch('/api/status');
            const d = await resp.json();
            
            document.getElementById('stat-engine').textContent = d.active_engine || '---';
            document.getElementById('stat-file').textContent = d.current_file || '---';
            document.getElementById('stat-ok').textContent = d.ok || '0/0';
            document.getElementById('stat-skipped').textContent = d.skipped || '0';
            document.getElementById('stat-fleet-active').textContent = d.fleet_active || '0';
            document.getElementById('stat-fleet-cooling').textContent = d.fleet_cooling || '0';
            
            const pct = d.pct || 0;
            document.getElementById('progress-pct-text').textContent = 'Završeno: ' + pct + '%';
            document.getElementById('progress-bar').style.width = pct + '%';
            
            if (d.live_audit) {
                document.getElementById('audit-log').innerHTML = d.live_audit;
            }
            
            // Status dot
            const statusText = (d.status || '').toUpperCase();
            const dot = document.getElementById('status-dot');
            if (dot) {
                dot.className = 'dot ' + (statusText.includes('TOKU') ? 'dot-active' : 'dot-idle');
            }
            document.getElementById('status-text').textContent = d.status || 'IDLE';
            
            // ETA
            if (statusText.includes('TOKU') && !_startTime) _startTime = Date.now();
            if (statusText.includes('ZAVRŠEN') || statusText === 'IDLE') _startTime = null;
            if (_startTime && pct > 0 && pct < 100) {
                const match = (d.ok || '').match(/(\d+)\s*\/\s*(\d+)/);
                if (match) {
                    const done = +match[1], total = +match[2];
                    const elapsed = (Date.now() - _startTime) / 1000;
                    if (done > 0 && elapsed > 3) {
                        const eta = (total - done) / (done / elapsed);
                        const h = Math.floor(eta/3600), m = Math.floor((eta%3600)/60), s = Math.floor(eta%60);
                        document.getElementById('progress-eta').textContent = 'ETA: ' + 
                            `${h.toString().padStart(2,'0')}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
                        const eh = Math.floor(elapsed/3600), em = Math.floor((elapsed%3600)/60), es = Math.floor(elapsed%60);
                        let el = document.getElementById('elapsed-time');
                        if (!el) {
                            el = document.createElement('span'); el.id = 'elapsed-time';
                            el.style.cssText = 'margin-left:10px;color:var(--text-secondary);font-family:monospace;';
                            document.getElementById('progress-eta').parentNode.appendChild(el);
                        }
                        el.textContent = ' | Proteklо: ' + 
                            `${eh.toString().padStart(2,'0')}:${em.toString().padStart(2,'0')}:${es.toString().padStart(2,'0')}`;
                    }
                }
            }
        } catch(e) {}
    }, 2000);
}

// ---------- FLEET ----------
async function loadFleetComplete() {
    try {
        const resp = await fetch('/api/fleet');
        const data = await resp.json();
        const container = document.getElementById('fleet-cards-container');
        if (!container) return;
        
        let totalActive = 0, html = '';
        for (const [provider, info] of Object.entries(data)) {
            const active = info.active || 0;
            const total = info.total || 0;
            totalActive += active;
            const keys = info.keys || [];
            const avgHealth = keys.length > 0 ? Math.round(keys.reduce((s,k) => s + (k.health||0), 0) / keys.length) : 0;
            const healthColor = avgHealth > 60 ? '#10b981' : (avgHealth > 30 ? '#f59e0b' : '#ef4444');
            
            html += `<details class="fleet-card" style="margin-bottom:8px;border:1px solid var(--border);border-radius:8px;">
                <summary style="padding:12px;cursor:pointer;display:flex;align-items:center;gap:8px;">
                    <span>${active>0?'🟢':((total-active)>0?'🟡':'🔴')}</span>
                    <b>${provider}</b>
                    <span style="font-size:0.8rem;">${active}/${total}</span>
                    <span style="width:60px;height:6px;background:var(--border);border-radius:4px;margin-left:auto;">
                        <span style="display:block;height:100%;width:${avgHealth}%;background:${healthColor};border-radius:4px;"></span>
                    </span>
                    <span style="font-size:0.7rem;color:${healthColor};">${avgHealth}%</span>
                </summary>
                <div style="padding:8px;display:flex;flex-wrap:wrap;gap:6px;max-height:200px;overflow-y:auto;">`;
            keys.forEach(k => {
                const status = k.available ? '✅' : (k.cooldown_remaining > 0 ? '⏳' : '🔴');
                html += `<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border:1px solid ${k.available?'#10b981':'#f59e0b'};border-radius:12px;font-size:0.7rem;font-family:monospace;">
                    ${k.masked} ${status}
                    <button onclick="toggleKeyDirect('${provider}','${k.masked}')" style="background:none;border:none;cursor:pointer;">${k.available?'🔴':'🟢'}</button>
                </span>`;
            });
            html += '</div></details>';
        }
        container.innerHTML = html || '<p>Nema provajdera</p>';
        document.getElementById('fleet-total-count').textContent = totalActive;
    } catch(e) {}
}

async function toggleKeyDirect(provider, key) {
    await fetch('/api/fleet/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, key })
    });
    loadFleetComplete();
}

// ---------- NEON ANIMACIJA ----------
(function(){
    const title = document.getElementById('app-logo-title');
    if(!title) return;
    const colors = ['#60a5fa','#a78bfa','#4ade80','#fbbf24','#f87171','#06b6d4'];
    let timer;
    function flash(){
        const c = colors[Math.floor(Math.random()*colors.length)];
        title.style.textShadow = `0 0 8px ${c}, 0 0 20px ${c}, 0 0 40px ${c}`;
        setTimeout(()=>{title.style.textShadow='';},200+Math.random()*300);
        timer=setTimeout(flash,150+Math.random()*500);
    }
    setTimeout(flash,600);
})();

// ---------- INICIJALIZACIJA FLEET ----------
setTimeout(loadFleetComplete, 1500);
setInterval(loadFleetComplete, 20000);

// ---------- EXPORT ----------
window.toggleTheme = toggleTheme;
window.showSetup = showSetup;
window.wizardNext = wizardNext;
window.wizardBack = wizardBack;
window.switchTab = switchTab;
window.sendControl = sendControl;
window.addKey = addKey;
window.toggleKeyDirect = toggleKeyDirect;

// ===== DODATNE FUNKCIJE ZA NOVI HTML =====

// Mode select (za radio kartice)
function selectMode(card, mode) {
    document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('active'));
    card.classList.add('active');
    const r = card.querySelector('input[type="radio"]');
    if (r) r.checked = true;
    STATE.mode = mode;
    saveAppState();
}

// Model tier filter
const TIER_MAP = {
    fast: ['CEREBRAS','GROQ','SAMBANOVA'],
    quality: ['GEMINI','MISTRAL','COHERE'],
    free: ['V10_TURBO','V8_TURBO','OPENROUTER','TOGETHER','FIREWORKS','CHUTES','HUGGINGFACE','KLUSTER','GEMMA'],
};

function filterTier(btn, tier) {
    document.querySelectorAll('#tier-pills .btn').forEach(b => {
        b.classList.remove('btn-primary','active-tier');
        b.classList.add('btn-ghost');
    });
    btn.classList.remove('btn-ghost');
    btn.classList.add('btn-primary','active-tier');

    const sel = document.getElementById('model-select');
    if (!sel) return;
    const allowed = TIER_MAP[tier] || null;
    Array.from(sel.options).forEach(opt => {
        if (!opt.value) return;
        opt.hidden = allowed ? !allowed.some(t => opt.value.toUpperCase().includes(t)) : false;
    });
}

// Trigger upload dialog
function triggerUpload() {
    document.getElementById('file-input')?.click();
}

// On book change
function onBookChange(val) {
    STATE.book = val;
    if (val) localStorage.setItem('bf_last_book', val);
}

// Global state object (koristi se u selectMode i drugde)
const STATE = {
    book: null,
    model: 'V10_TURBO',
    mode: 'PREVOD',
    processing: false,
    paused: false,
    startTime: null,
};

// Override postojećeg startProcessing da koristi STATE
const origStartProcessing = startProcessing;
window.startProcessing = async function() {
    const book = STATE.book || document.getElementById('book-select')?.value;
    const model = document.getElementById('model-select')?.value || STATE.model;
    const modeEl = document.querySelector('input[name="mode"]:checked');
    const mode = modeEl ? modeEl.value : STATE.mode;

    if (!book) { showToast?.('Odaberi knjigu!', 'warning') || alert('Odaberi knjigu!'); return; }

    const btn = document.getElementById('btn-start');
    if (btn) { btn.disabled = true; btn.textContent = 'Pokrecem...'; }

    try {
        const r = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book, model, mode })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        STATE.processing = true;
        STATE.paused = false;
        STATE.startTime = Date.now();
        document.getElementById('setup-panel')?.classList.add('hidden');
        document.getElementById('dashboard-panel')?.classList.remove('hidden');
        saveAppState();
        startDashboardPolling();
        showToast?.('Pokrenuto: ' + book, 'success') || alert('Pokrenuto!');
    } catch(e) {
        showToast?.('Greska: ' + e.message, 'error') || alert('Greska: ' + e.message);
        if (btn) { btn.disabled = false; btn.textContent = '🚀 Pokreni Sistem'; }
    }
};

// Override sendControl da koristi STATE
const origSendControl = sendControl;
window.sendControl = async function(action) {
    try {
        await fetch('/control/' + action, { method: 'POST' });
        if (action === 'pause') STATE.paused = true;
        if (action === 'resume') STATE.paused = false;
        if (action === 'stop') STATE.processing = false;
        if (action === 'reset') { STATE.processing = false; STATE.paused = false; STATE.startTime = null; showSetup(); }
        updateControlBtns();
    } catch(e) { console.error(e); }
};

function updateControlBtns() {
    document.getElementById('btn-pause')?.classList.toggle('hidden', STATE.paused);
    document.getElementById('btn-resume')?.classList.toggle('hidden', !STATE.paused);
}

// API Keys management
async function loadKeys() {
    const container = document.getElementById('keys-list-container');
    if (!container) return;
    try {
        const r = await fetch('/api/keys');
        const data = await r.json();
        const entries = Object.entries(data || {});
        if (entries.length === 0) {
            container.innerHTML = '<div style="color:var(--tx-3);">Nema unesenih API kljuceva.</div>';
            return;
        }
        const PROV_ICONS = { GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠', MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗', KLUSTER:'🔗' };
        let html = '';
        entries.forEach(([prov, keys]) => {
            (keys || []).forEach((masked, idx) => {
                html += `<div class="key-row">
                    <span class="key-provider-badge">${PROV_ICONS[prov.toUpperCase()] || '🔑'} ${prov}</span>
                    <span class="key-value">${masked}</span>
                    <button class="key-del" onclick="deleteKey('${prov}', ${idx})">✕</button>
                </div>`;
            });
        });
        container.innerHTML = html;
    } catch(e) { container.innerHTML = '<div style="color:var(--rose);">Greska</div>'; }
}

async function addNewKey() {
    const prov = document.getElementById('key-provider-select')?.value;
    const key = document.getElementById('key-value-input')?.value?.trim();
    if (!prov) { alert('Odaberi provajdera!'); return; }
    if (!key || key.length < 8) { alert('Kljuc mora imati bar 8 znakova.'); return; }
    try {
        const r = await fetch('/api/keys/' + encodeURIComponent(prov), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        document.getElementById('key-value-input').value = '';
        await loadKeys();
        pollFleet();
    } catch(e) { alert('Greska: ' + e.message); }
}

async function deleteKey(provider, index) {
    if (!confirm('Obrisati kljuc?')) return;
    try {
        await fetch('/api/keys/' + encodeURIComponent(provider) + '/' + index, { method: 'DELETE' });
        await loadKeys();
        pollFleet();
    } catch(e) { alert('Greska: ' + e.message); }
}

// Poboljšani fleet render sa stilovima iz novog HTML-a
const PROV_ICONS = { GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠', MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', GITHUB:'🐙', TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗', KLUSTER:'🔗', GEMMA:'🔷' };

async function renderFleetStyled() {
    try {
        const resp = await fetch('/api/fleet');
        const data = await resp.json();
        const container = document.getElementById('fleet-cards-container');
        if (!container) return;
        
        let totalActive = 0, html = '';
        for (const [prov, info] of Object.entries(data)) {
            const active = info.active || 0;
            const total = info.total || 0;
            const keys = info.keys || [];
            totalActive += active;
            const pct = total > 0 ? Math.round((active / total) * 100) : 0;
            const barCls = pct >= 60 ? 'good' : (pct >= 30 ? 'warn' : 'low');
            const icon = PROV_ICONS[prov.toUpperCase()] || '🔑';
            
            html += `<details class="fleet-provider">
                <summary class="fleet-provider-header" style="list-style:none;cursor:pointer;">
                    <span class="fleet-prov-icon">${icon}</span>
                    <span class="fleet-prov-name">${prov}</span>
                    <div class="fleet-health-bar"><div class="fleet-health-fill ${barCls}" style="width:${pct}%"></div></div>
                    <span class="fleet-prov-count">${active}/${total}</span>
                    <span class="fleet-chevron">▾</span>
                </summary>
                <div class="fleet-keys-grid">`;
            
            keys.forEach(k => {
                const avail = k.available && !k.disabled;
                const cooling = !k.available && !k.disabled && k.cooldown_remaining > 0;
                const cls = avail ? 'ok' : (cooling ? 'warn' : 'err');
                html += `<div class="key-pill ${cls}" onclick="toggleKey('${prov}','${k.masked}')">
                    <span class="key-dot"></span>
                    <span>${k.masked}</span>
                    <span style="opacity:0.6;font-size:0.62rem">${avail ? '✓' : (cooling ? '⏳'+Math.ceil(k.cooldown_remaining)+'s' : '✕')}</span>
                </div>`;
            });
            
            html += '</div></details>';
        }
        container.innerHTML = html || '<div>Nema provajdera</div>';
        document.getElementById('fleet-total-count').textContent = totalActive;
    } catch(e) {}
}

// Override loadFleetComplete sa stilizovanom verzijom
loadFleetComplete = renderFleetStyled;

// Poll fleet periodično
function pollFleet() { loadFleetComplete(); }
setInterval(pollFleet, 20000);

// Exportuj dodatne funkcije
window.selectMode = selectMode;
window.filterTier = filterTier;
window.triggerUpload = triggerUpload;
window.onBookChange = onBookChange;
window.addKey = addNewKey;
window.deleteKey = deleteKey;
window.loadKeys = loadKeys;
window.toggleKey = toggleKeyDirect;
window.setState = function(book) { STATE.book = book; };

// Podrška za FUSION mod (Prevod+Lektura u jednom prolazu)
window.STATE = window.STATE || {};
window.STATE.mode = 'FUSION'; // default

// Override startProcessing da šalje FUSION mod
const _origStart = window.startProcessing;
window.startProcessing = async function() {
    const book = (window.STATE && window.STATE.book) || document.getElementById('book-select')?.value;
    const model = document.getElementById('model-select')?.value || 'V10_TURBO';
    const modeEl = document.querySelector('input[name="mode"]:checked');
    const mode = modeEl ? modeEl.value : (window.STATE ? window.STATE.mode : 'FUSION');

    if (!book) { alert('Odaberi knjigu!'); return; }

    const btn = document.getElementById('btn-start');
    if (btn) { btn.disabled = true; btn.textContent = 'Pokrecem...'; }

    try {
        const r = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book, model, mode })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        
        if (window.STATE) {
            window.STATE.processing = true;
            window.STATE.paused = false;
            window.STATE.startTime = Date.now();
        }
        
        document.getElementById('setup-panel')?.classList.add('hidden');
        document.getElementById('dashboard-panel')?.classList.remove('hidden');
        
        if (typeof saveAppState === 'function') saveAppState();
        if (typeof startDashboardPolling === 'function') startDashboardPolling();
        
        alert('Pokrenuto: ' + book + ' [' + mode + ']');
    } catch(e) {
        alert('Greska: ' + e.message);
        if (btn) { btn.disabled = false; btn.textContent = '🚀 Pokreni Sistem'; }
    }
};

console.log('✅ FUSION mod dodat');
