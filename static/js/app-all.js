// ===== SPOJENI MODULI =====

/**
 * storage.js — LocalStorage wrapper
 */

const storage = {
    get(key, defaultValue = null) {
        try {
            const v = localStorage.getItem(key);
            return v !== null ? JSON.parse(v) : defaultValue;
        } catch {
            return defaultValue;
        }
    },

    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch { /* quota exceeded — ignore */ }
    },

    remove(key) {
        try {
            localStorage.removeItem(key);
        } catch { /* ignore */ }
    },
};


/**
 * theme.js — Upravljanje svjetlosnim/tamnim temom
 */

/**
 * Primijeni sačuvanu temu iz localStorage.
 */
function applyStoredTheme() {
    const stored = localStorage.getItem(LS_THEME);
    if (stored === 'light') {
        document.body.classList.add('light-theme');
        _updateThemeBtn(true);
    } else {
        document.body.classList.remove('light-theme');
        _updateThemeBtn(false);
    }
}

/**
 * Mijenja aktivnu temu i pamti odabir.
 */
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    localStorage.setItem(LS_THEME, isLight ? 'light' : 'dark');
    _updateThemeBtn(isLight);
}

function _updateThemeBtn(isLight) {
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = isLight ? '🌙 Tamna' : '☀️ Svijetla';
}

// Exponiraj toggleTheme na window za inline onclick
window.toggleTheme = toggleTheme;


/**
 * polling.js — Pravi real-time polling za status i fleet
 * ISPRAVLJENA VERZIJA: stub zamijenjen pravom implementacijom
 */


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
function startPolling(onStatus, onFleet) {
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
function stopPolling() {
    if (_statusIntervalId) { clearInterval(_statusIntervalId); _statusIntervalId = null; }
    if (_fleetIntervalId)  { clearInterval(_fleetIntervalId);  _fleetIntervalId  = null; }
    console.log('[Polling] Zaustavljen');
}

/** Da li je polling aktivan? */
function isPolling() {
    return _statusIntervalId !== null;
}


function showToast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    if (!c) return alert(msg);
    const t = document.createElement('div');
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => t.classList.add('toast-visible'), 10);
    setTimeout(() => { t.classList.remove('toast-visible'); setTimeout(() => t.remove(), 300); }, 4000);
}


/**
 * api-client.js — Centralizirani HTTP klijent za sve API pozive
 * ISPRAVLJENA VERZIJA: sve rute sinhronizovane s Flask backend-om
 */

async function apiFetch(url, options = {}) {
    const response = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
}

const apiClient = {
    /** Dohvati status obrade */
    getStatus: () => apiFetch('/api/status'),

    /** Dohvati listu EPUB fajlova iz INPUT_DIR */
    getBooks: () => apiFetch('/api/files'),

    /** Dohvati dostupne modele */
    getModels: () => apiFetch('/api/dev_models'),

    /**
     * Upload knjige — ISPRAVLJENA RUTA: /api/upload_book
     * Flask ruta je definisana u api/routes/books.py
     */
    uploadBook: (formData) =>
        fetch('/api/upload_book', { method: 'POST', body: formData }).then(r => r.json()),

    /** Pokreni obradu */
    startProcessing: (book, model, tool) =>
        apiFetch('/api/start', {
            method: 'POST',
            body: JSON.stringify({ book, model, tool }),
        }),

    /**
     * Kontrola obrade — ISPRAVLJENA RUTA: /control/<action>
     * Flask rute su: /control/pause, /control/resume, /control/stop, /control/reset
     */
    sendControl: (action) =>
        apiFetch(`/control/${action}`, { method: 'POST' }),

    /** Dohvati fleet status (UI format) */
    getFleet: () => apiFetch('/api/fleet'),

    /** Toggle ključa u floti */
    toggleFleetKey: (provider, key) =>
        apiFetch('/api/fleet/toggle', {
            method: 'POST',
            body: JSON.stringify({ provider, key }),
        }),

    /** Dohvati API ključeve (maskirane) */
    getKeys: () => apiFetch('/api/keys'),

    /** Dodaj API ključ za provajdera */
    addKey: (provider, key) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}`, {
            method: 'POST',
            body: JSON.stringify({ key }),
        }),

    /** Obriši ključ po indeksu */
    deleteKey: (provider, index) =>
        apiFetch(`/api/keys/${encodeURIComponent(provider)}/${index}`, { method: 'DELETE' }),

    /** Export izvještaja */
    exportReport: (fmt) => fetch(`/api/export/${fmt}`).then(r => r.blob()),
};


/**
 * ui/fleet.js — Fleet Pool renderer
 */

const PROV_ICONS = {
    GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠',
    MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', GITHUB:'🐙',
    TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗',
    KLUSTER:'🔗', GEMMA:'🔷',
};

function renderFleet(data) {
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

function updateFleetTotalCount(n) {
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

alert("app.js ucitan!");
/**
 * app.js — Booklyfi Turbo Charged — Glavna logika aplikacije
 * Kompletna, funkcionalna verzija.
 */







// Exponiraj globalno za onclick handlere u HTML-u
window.toggleTheme     = toggleTheme;
window.wizardNext      = wizardNext;
window.wizardBack      = wizardBack;
window.startProcessing = startProcessing;
window.sendControl     = sendControl;
window.switchTab       = switchTab;
window.addKey          = addKey;
window.showSetup       = showSetup;

// ═══════════════════════════════════════════════════════════════
//  STATE
// ═══════════════════════════════════════════════════════════════
const state = {
    currentStep:   1,
    selectedBook:  null,
    selectedModel: 'V10_TURBO',
    selectedMode:  'PREVOD',
    isProcessing:  false,
    isPaused:      false,
};

// ═══════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', async () => {
    applyStoredTheme();
    setupModeCards();
    setupUploadZone();
    setupTierPills();

    try {
        await loadBooks();
        await loadModels();
    } catch (e) {
        console.warn('[Init] Greška pri učitavanju podataka:', e);
    }

    // Inicijalni status poll
    try {
        const status = await apiClient.getStatus();
        updateStatus(status);
        if (status.status !== 'IDLE' && status.status !== 'ZAUSTAVLJENO') {
            showDashboard();
        }
    } catch (_) {}

    // Pokreni polling
    startPolling(updateStatus, (fleet) => {
        renderFleet(fleet);
        const total = Object.values(fleet).reduce((s, p) => s + (p.active || 0), 0);
        updateFleetTotalCount(total);
    });

    // Učitaj ključeve kad se klikne tab
    document.querySelectorAll('.tab-btn[data-tab="tab-keys"]').forEach(btn => {
        btn.addEventListener('click', loadKeys);
    });
    document.querySelectorAll('.tab-btn[data-tab="tab-fleet"]').forEach(btn => {
        btn.addEventListener('click', loadFleet);
    });

    // Sačuvaj i vrati zadnju odabranu knjigu
    const lastBook = storage.get('last_book');
    if (lastBook) {
        const sel = document.getElementById('book-select');
        if (sel) sel.value = lastBook;
        state.selectedBook = lastBook;
    }
});

// ═══════════════════════════════════════════════════════════════
//  WIZARD
// ═══════════════════════════════════════════════════════════════
function wizardNext() {
    const sel = document.getElementById('book-select');
    const book = sel?.value;
    if (!book) {
        showToast('Odaberi ili upload-aj knjigu!', 'warning');
        return;
    }
    state.selectedBook = book;
    storage.set('last_book', book);
    setWizardStep(2);
}

function wizardBack() {
    setWizardStep(1);
}

function setWizardStep(n) {
    state.currentStep = n;
    document.getElementById('wizard-page-1')?.classList.toggle('hidden', n !== 1);
    document.getElementById('wizard-page-2')?.classList.toggle('hidden', n !== 2);

    document.getElementById('step-1')?.classList.toggle('active', n === 1);
    document.getElementById('step-1')?.classList.toggle('completed', n > 1);
    document.getElementById('step-2')?.classList.toggle('active', n === 2);
}

function showSetup() {
    document.getElementById('setup-panel')?.classList.remove('hidden');
    document.getElementById('dashboard-panel')?.classList.add('hidden');
    setWizardStep(1);
}

function showDashboard() {
    document.getElementById('setup-panel')?.classList.add('hidden');
    document.getElementById('dashboard-panel')?.classList.remove('hidden');
}

// ═══════════════════════════════════════════════════════════════
//  MODE CARDS
// ═══════════════════════════════════════════════════════════════
function setupModeCards() {
    document.querySelectorAll('.mode-card').forEach(card => {
        card.addEventListener('click', () => {
            document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            const radio = card.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
                state.selectedMode = radio.value;
            }
        });
    });
}

// ═══════════════════════════════════════════════════════════════
//  TIER PILLS
// ═══════════════════════════════════════════════════════════════
const TIER_MAP = {
    fast:    ['CEREBRAS','GROQ','SAMBANOVA'],
    quality: ['GEMINI','MISTRAL','COHERE'],
    free:    ['V10_TURBO','V8_TURBO','OPENROUTER','TOGETHER','FIREWORKS','CHUTES','HUGGINGFACE','KLUSTER','GEMMA'],
};

function setupTierPills() {
    document.querySelectorAll('.tier-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            document.querySelectorAll('.tier-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            filterModels(pill.dataset.tier);
        });
    });
}

function filterModels(tier) {
    const sel = document.getElementById('model-select');
    if (!sel) return;
    const allowed = TIER_MAP[tier];
    Array.from(sel.options).forEach(opt => {
        if (!opt.value) return; // placeholder
        opt.hidden = allowed ? !allowed.some(t => opt.value.toUpperCase().includes(t)) : false;
    });
}

// ═══════════════════════════════════════════════════════════════
//  UPLOAD ZONA
// ═══════════════════════════════════════════════════════════════
function setupUploadZone() {
    const zone   = document.getElementById('upload-zone');
    const input  = document.getElementById('file-input');
    const status = document.getElementById('upload-status');

    if (!zone || !input) return;

    input.addEventListener('change', () => {
        if (input.files[0]) uploadFile(input.files[0]);
    });

    zone.addEventListener('click', (e) => {
        if (!e.target.closest('label')) input.click();
    });

    zone.addEventListener('dragover', e => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) uploadFile(file);
    });

    async function uploadFile(file) {
        const ext = file.name.split('.').pop().toLowerCase();
        if (!['epub','mobi'].includes(ext)) {
            showToast('Podržani formati: EPUB, MOBI', 'error');
            return;
        }
        status.textContent = `⏳ Upload: ${file.name}...`;
        const fd = new FormData();
        fd.append('file', file);
        try {
            const res = await apiClient.uploadBook(fd);
            if (res.error) throw new Error(res.error);
            status.textContent = `✅ ${res.name}`;
            showToast(`Knjiga "${res.name}" uploadana!`, 'success');
            await loadBooks();
            const sel = document.getElementById('book-select');
            if (sel) sel.value = res.name;
            state.selectedBook = res.name;
        } catch (e) {
            status.textContent = `❌ Greška: ${e.message}`;
            showToast('Upload nije uspio: ' + e.message, 'error');
        }
    }
}

// ═══════════════════════════════════════════════════════════════
//  UČITAVANJE PODATAKA
// ═══════════════════════════════════════════════════════════════
async function loadBooks() {
    const sel = document.getElementById('book-select');
    if (!sel) return;
    try {
        const data = await apiClient.getBooks();
        const files = data.files || [];
        sel.innerHTML = '<option value="">— Odaberi knjigu —</option>';
        if (files.length === 0) {
            sel.innerHTML += '<option disabled>Nema EPUB fajlova u INPUT_DIR</option>';
        } else {
            files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.textContent = f;
                sel.appendChild(opt);
            });
        }
        // Vrati zadnji odabir
        const last = storage.get('last_book');
        if (last && files.includes(last)) sel.value = last;
    } catch (e) {
        sel.innerHTML = '<option value="">Greška pri učitavanju...</option>';
        console.error('[loadBooks]', e);
    }
}

async function loadModels() {
    const sel = document.getElementById('model-select');
    if (!sel) return;
    try {
        const models = await apiClient.getModels();
        sel.innerHTML = '';
        (models || []).forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            sel.appendChild(opt);
        });
        state.selectedModel = models[0] || 'V10_TURBO';
    } catch (e) {
        sel.innerHTML = '<option value="V10_TURBO">V10_TURBO</option>';
    }
}

async function loadFleet() {
    try {
        const data = await apiClient.getFleet();
        renderFleet(data);
        const total = Object.values(data).reduce((s, p) => s + (p.active || 0), 0);
        updateFleetTotalCount(total);
    } catch (e) {
        document.getElementById('fleet-cards-container').innerHTML =
            '<p class="tab-hint" style="color:var(--rose)">Greška pri učitavanju flote.</p>';
    }
}

async function loadKeys() {
    const container = document.getElementById('keys-list-container');
    if (!container) return;
    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><span>Učitavam ključeve...</span></div>';
    try {
        const data = await apiClient.getKeys();
        const ICONS = {
            GEMINI:'♊', GROQ:'⚡', CEREBRAS:'🔬', SAMBANOVA:'🧠',
            MISTRAL:'💫', COHERE:'🌐', OPENROUTER:'🔀', GITHUB:'🐙',
            TOGETHER:'🤝', FIREWORKS:'🎆', CHUTES:'🪣', HUGGINGFACE:'🤗',
            KLUSTER:'🔗',
        };
        const entries = Object.entries(data || {});
        if (entries.length === 0) {
            container.innerHTML = '<p class="tab-hint">Nema unesenih API ključeva.</p>';
            return;
        }
        let html = '';
        entries.forEach(([prov, keys]) => {
            keys.forEach((masked, idx) => {
                const icon = ICONS[prov.toUpperCase()] || '🔑';
                html += `
                <div class="key-row">
                    <span class="key-prov-badge">${icon} ${prov}</span>
                    <span class="key-masked">${masked}</span>
                    <button class="key-del-btn" title="Obriši" onclick="deleteKey('${prov}', ${idx})">✕</button>
                </div>`;
            });
        });
        container.innerHTML = html || '<p class="tab-hint">Nema unesenih API ključeva.</p>';
    } catch (e) {
        container.innerHTML = '<p class="tab-hint" style="color:var(--rose)">Greška pri učitavanju ključeva.</p>';
    }
}

// ═══════════════════════════════════════════════════════════════
//  PROCESSING
// ═══════════════════════════════════════════════════════════════
async function startProcessing() {
    const modelSel = document.getElementById('model-select');
    const book  = state.selectedBook;
    const model = modelSel?.value || state.selectedModel;
    const mode  = document.querySelector('input[name="mode"]:checked')?.value || 'PREVOD';

    if (!book) { showToast('Odaberi knjigu!', 'warning'); wizardBack(); return; }
    if (!model) { showToast('Odaberi model!', 'warning'); return; }

    const btn = document.getElementById('btn-start');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Pokrećem...'; }

    try {
        await apiClient.startProcessing(book, model, mode);
        state.isProcessing = true;
        state.isPaused = false;
        showDashboard();
        showToast(`Pokrenuto: ${book} [${model}]`, 'success');
        updateControlBtns();
    } catch (e) {
        showToast('Greška pri pokretanju: ' + e.message, 'error');
        if (btn) { btn.disabled = false; btn.textContent = '🚀 Pokreni Sistem'; }
    }
}

async function sendControl(action) {
    try {
        await apiClient.sendControl(action);
        if (action === 'pause')  { state.isPaused = true;  showToast('Pauzirano', 'info'); }
        if (action === 'resume') { state.isPaused = false; showToast('Nastavljeno', 'success'); }
        if (action === 'stop')   {
            state.isProcessing = false;
            showToast('Zaustavljeno', 'warning');
        }
        if (action === 'reset')  {
            state.isProcessing = false;
            state.isPaused = false;
            showToast('Sistem resetovan', 'info');
            showSetup();
        }
        updateControlBtns();
    } catch (e) {
        showToast('Greška: ' + e.message, 'error');
    }
}

function updateControlBtns() {
    const btnPause  = document.getElementById('btn-pause');
    const btnResume = document.getElementById('btn-resume');
    if (btnPause)  btnPause.classList.toggle('hidden', state.isPaused);
    if (btnResume) btnResume.classList.toggle('hidden', !state.isPaused);
}

// ═══════════════════════════════════════════════════════════════
//  STATUS UPDATE (iz pollinga)
// ═══════════════════════════════════════════════════════════════
function updateStatus(s) {
    if (!s) return;

    // Status dot
    const dot  = document.getElementById('status-dot');
    const txt  = document.getElementById('status-text');
    const st   = (s.status || 'IDLE').toUpperCase();

    if (dot) {
        dot.className = 'dot';
        if (st === 'IDLE' || st === 'ZAUSTAVLJENO') dot.classList.add('dot-idle');
        else if (st === 'PAUZIRANO')                 dot.classList.add('dot-paused');
        else if (st.includes('GREŠKA'))              dot.classList.add('dot-error');
        else                                          dot.classList.add('dot-active');
    }
    if (txt) txt.textContent = st;

    // Stats
    setText('stat-engine',       s.active_engine   || '---');
    setText('stat-file',         s.current_file     || '---');
    setText('stat-ok',           s.ok               || '0 / 0');
    setText('stat-skipped',      s.skipped          || '0');
    setText('stat-fleet-active', s.fleet_active     || '0');
    setText('stat-fleet-cooling',s.fleet_cooling    || '0');

    // Progress
    const pct = Math.min(100, Math.max(0, s.pct || 0));
    const bar = document.getElementById('progress-bar');
    if (bar) bar.style.width = pct + '%';
    setText('progress-pct-text', `Završeno: ${pct}%`);
    setText('progress-eta',      `ETA: ${s.est || '--:--:--'}`);

    // Pipeline steps
    updatePipelineSteps(st, pct);

    // Live preview (iz audit loga — izvuci zadnji EN/HR par)
    if (s.live_audit) {
        updateAuditLog(s.live_audit);
        extractLivePreview(s.live_audit);
    }

    // Download strip
    const strip = document.getElementById('download-strip');
    if (strip) strip.classList.toggle('hidden', !s.output_file);

    // Ako je završeno — prikaži setup btn
    if (pct >= 100 || st === 'ZAUSTAVLJENO' || st === 'IDLE') {
        if (st !== 'OBRADA U TOKU...' && st !== 'POKRETANJE...') {
            state.isProcessing = false;
            updateControlBtns();
        }
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function updatePipelineSteps(status, pct) {
    const steps = ['pipe-analiza', 'pipe-prevod', 'pipe-lektor', 'pipe-gotovo'];
    steps.forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.classList.remove('active','done'); }
    });
    if (status.includes('ANALIZ')) {
        document.getElementById('pipe-analiza')?.classList.add('active');
    } else if (status.includes('PREVOD') || pct < 40) {
        document.getElementById('pipe-analiza')?.classList.add('done');
        document.getElementById('pipe-prevod')?.classList.add('active');
    } else if (pct < 80) {
        ['pipe-analiza','pipe-prevod'].forEach(id => document.getElementById(id)?.classList.add('done'));
        document.getElementById('pipe-lektor')?.classList.add('active');
    } else if (pct >= 100) {
        steps.forEach(id => document.getElementById(id)?.classList.add('done'));
    }
}

function updateAuditLog(html) {
    const log = document.getElementById('audit-log');
    if (!log) return;
    log.innerHTML = html;
    log.scrollTop = log.scrollHeight;
}

function extractLivePreview(html) {
    // Pokušaj izvući EN/HR par iz audit loga
    const match = html.match(/EN:\s*([^<\n]{5,80}).*?HR:\s*([^<\n]{5,80})/s);
    if (match) {
        setText('preview-en', match[1].trim());
        setText('preview-hr', match[2].trim());
    }
}

// ═══════════════════════════════════════════════════════════════
//  TABS
// ═══════════════════════════════════════════════════════════════
function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('tab-active', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
        const isTarget = panel.id === tabId;
        panel.classList.toggle('hidden', !isTarget);
        panel.classList.toggle('tab-panel-active', isTarget);
    });
}

// ═══════════════════════════════════════════════════════════════
//  API KEYS
// ═══════════════════════════════════════════════════════════════
async function addKey() {
    const provSel = document.getElementById('key-provider-select');
    const keyInp  = document.getElementById('key-value-input');
    const prov    = provSel?.value;
    const key     = keyInp?.value?.trim();

    if (!prov) { showToast('Odaberi provajdera!', 'warning'); return; }
    if (!key || key.length < 8) { showToast('Ključ mora imati bar 8 znakova.', 'warning'); return; }

    const btn = document.getElementById('btn-add-key');
    if (btn) { btn.disabled = true; btn.textContent = '⏳'; }

    try {
        const res = await apiClient.addKey(prov, key);
        if (res.error) throw new Error(res.error);
        showToast(`Ključ za ${prov} dodan!`, 'success');
        if (keyInp) keyInp.value = '';
        await loadKeys();
        await checkFleetHealth();
    } catch (e) {
        showToast('Greška: ' + e.message, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '➕ Dodaj'; }
    }
}

window.deleteKey = async function(provider, index) {
    if (!confirm(`Obrisati ključ #${index} za ${provider}?`)) return;
    try {
        await apiClient.deleteKey(provider, index);
        showToast(`Ključ za ${provider} obrisan.`, 'info');
        await loadKeys();
    } catch (e) {
        showToast('Greška pri brisanju: ' + e.message, 'error');
    }
};

async function checkFleetHealth() {
    try {
        const fleet = await apiClient.getFleet();
        const active = Object.values(fleet).reduce((s, p) => s + (p.active || 0), 0);
        const warn = document.getElementById('no-keys-warning');
        if (warn) warn.classList.toggle('hidden', active > 0);
        updateFleetTotalCount(active);
    } catch (_) {}
}
// ========== EKSPORTUJ SVE FUNKCIJE ZA ONCLICK ==========
window.toggleTheme = toggleTheme;
window.showSetup = showSetup;
window.wizardNext = wizardNext;
window.wizardBack = wizardBack;
window.startProcessing = startProcessing;
window.sendControl = sendControl;
window.switchTab = switchTab;
window.addKey = addKey;
window.deleteKey = deleteKey;
console.log('✅ Funkcije eksportovane na window');

// ===== EKSPORT ZA ONCLICK (MORA BITI GLOBALNO) =====
window.toggleTheme = toggleTheme;
window.showSetup = showSetup;
window.wizardNext = wizardNext;
window.wizardBack = wizardBack;
window.startProcessing = startProcessing;
window.sendControl = sendControl;
window.switchTab = switchTab;
window.addKey = addKey;
window.deleteKey = deleteKey;
console.log('✅ Sve funkcije eksportovane na window');

// ===== ALIASI ZA STARI HTML =====
window.nextSetupStep = wizardNext;
window.prevSetupStep = wizardBack;
window.startEngine = startProcessing;
window.toggleSetup = showSetup;
window.loadBookCover = function() {}; // placeholder
console.log('✅ Aliasi dodani za stari HTML');

// ===== BOOK COVER PREVIEW =====
window.loadBookCover = function(bookPath) {
    const preview = document.getElementById('book-preview');
    if (!bookPath) {
        preview?.classList.add('hidden');
        return;
    }
    fetch('/api/books')
        .then(r => r.json())
        .then(data => {
            const book = (data.books || []).find(b => b.path === bookPath || b.name === bookPath);
            if (book) {
                preview?.classList.remove('hidden');
                document.getElementById('book-title').textContent = book.name.replace(/\.[^/.]+$/, '');
                document.getElementById('book-size').textContent = `${((book.size_bytes || 0) / 1024).toFixed(0)} KB`;
            }
        })
        .catch(() => preview?.classList.add('hidden'));
};
console.log('✅ loadBookCover implementiran');


console.log('✅ app-all.js ucitan (bez modula)');

// ===== DIREKTNI UPLOAD HANDLER =====
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('file-input');
    const uploadStatus = document.getElementById('upload-status');
    
    if (!fileInput) {
        console.error('❌ #file-input nije pronadjen!');
        return;
    }
    
    fileInput.addEventListener('change', async function(e) {
        const file = e.target.files[0];
        if (!file) return;
        
        console.log('📤 Upload pokrenut:', file.name);
        if (uploadStatus) uploadStatus.textContent = '⏳ Upload: ' + file.name + '...';
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const resp = await fetch('/api/upload_book', {
                method: 'POST',
                body: formData
            });
            const data = await resp.json();
            
            if (data.error) throw new Error(data.error);
            
            if (uploadStatus) uploadStatus.textContent = '✅ ' + data.name;
            console.log('✅ Upload uspjesan:', data.name);
            
            // Osvježi listu knjiga
            if (typeof loadBooks === 'function') {
                loadBooks();
            } else {
                // Ručno osvježi select
                const booksResp = await fetch('/api/books');
                const booksData = await booksResp.json();
                const select = document.getElementById('book-select');
                if (select && booksData.books) {
                    select.innerHTML = '<option value="">-- Odaberi knjigu --</option>';
                    booksData.books.forEach(b => {
                        select.add(new Option(b.name, b.path));
                    });
                    select.value = data.name || file.name;
                }
            }
        } catch (err) {
            console.error('❌ Upload greška:', err);
            if (uploadStatus) uploadStatus.textContent = '❌ ' + err.message;
        }
    });
    
    console.log('✅ Upload handler postavljen');
});

// ===== INICIJALIZACIJA =====
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 DOMContentLoaded - pokrecem inicijalizaciju');
    
    // Učitaj knjige
    fetch('/api/books')
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('book-select');
            if (select && data.books) {
                select.innerHTML = '<option value="">-- Odaberi knjigu --</option>';
                data.books.forEach(b => select.add(new Option(b.name, b.path)));
                console.log('✅ Knjige učitane:', data.books.length);
            }
        })
        .catch(e => console.error('❌ Greška pri učitavanju knjiga:', e));
    
    // Učitaj modele
    fetch('/api/dev_models')
        .then(r => r.json())
        .then(models => {
            const select = document.getElementById('model-select');
            if (select && Array.isArray(models)) {
                select.innerHTML = '';
                models.forEach(m => select.add(new Option(m, m)));
                select.value = 'V10_TURBO';
                console.log('✅ Modeli učitani:', models.length);
            }
        })
        .catch(e => console.error('❌ Greška pri učitavanju modela:', e));
    
    console.log('✅ Inicijalizacija završena');
});

// ===== EKSPORTUJ SVE FUNKCIJE NA WINDOW (ZA ONCLICK) =====
window.toggleTheme = toggleTheme;
window.showSetup = showSetup;
window.wizardNext = wizardNext;
window.wizardBack = wizardBack;
window.startProcessing = startProcessing;
window.sendControl = sendControl;
window.switchTab = switchTab;
window.addKey = addKey;
window.deleteKey = deleteKey;
window.loadBookCover = function() {}; // placeholder

console.log('✅ Sve funkcije eksportovane na window');
console.log('toggleTheme:', typeof window.toggleTheme);
console.log('wizardNext:', typeof window.wizardNext);
console.log('startProcessing:', typeof window.startProcessing);

// ===== AUTO-DASHBOARD NAKON STARTA =====
document.addEventListener('DOMContentLoaded', function() {
    const btnStart = document.getElementById('btn-start');
    if (!btnStart) return;
    
    // Override postojećeg listenera
    btnStart.addEventListener('click', async function(e) {
        e.preventDefault();
        
        const book = document.getElementById('book-select')?.value;
        const model = document.getElementById('model-select')?.value || 'V8_TURBO';
        const modeRadio = document.querySelector('input[name="mode"]:checked');
        const mode = modeRadio ? modeRadio.value : 'PREVOD';
        
        if (!book) { alert('⚠️ Odaberi knjigu!'); return; }
        
        btnStart.textContent = '⏳ Inicijalizacija...';
        btnStart.disabled = true;
        
        try {
            const resp = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ book, model, mode })
            });
            const data = await resp.json();
            
            if (data.status === 'Started') {
                // PREBACI NA DASHBOARD
                document.getElementById('setup-panel')?.classList.add('hidden');
                document.getElementById('dashboard-panel')?.classList.remove('hidden');
                
                // Pokreni polling svake 2 sekunde
                setInterval(async function() {
                    const statusResp = await fetch('/api/status');
                    const statusData = await statusResp.json();
                    
                    document.getElementById('stat-engine').textContent = statusData.active_engine || '---';
                    document.getElementById('stat-file').textContent = statusData.current_file || '---';
                    document.getElementById('stat-ok').textContent = statusData.ok || '0/0';
                    document.getElementById('stat-skipped').textContent = statusData.skipped || '0';
                    document.getElementById('stat-fleet-active').textContent = statusData.fleet_active || '0';
                    document.getElementById('stat-fleet-cooling').textContent = statusData.fleet_cooling || '0';
                    
                    const pct = statusData.pct || 0;
                    document.getElementById('progress-pct-text').textContent = 'Završeno: ' + pct + '%';
                    document.getElementById('progress-bar').style.width = pct + '%';
                    
                    if (statusData.live_audit) {
                        document.getElementById('audit-log').innerHTML = statusData.live_audit;
                    }
                    
                    document.getElementById('status-text').textContent = statusData.status || 'IDLE';
                    const dot = document.getElementById('status-dot');
                    if (dot && statusData.status) {
                        dot.className = 'dot ' + (statusData.status.toUpperCase().includes('TOKU') ? 'dot-active' : 'dot-idle');
                    }
                }, 2000);
                
                alert('✅ Sistem pokrenut!');
            } else {
                alert('❌ Greška: ' + (data.error || 'Nepoznata greška'));
                btnStart.textContent = '🚀 Pokreni Sistem';
                btnStart.disabled = false;
            }
        } catch (e) {
            alert('❌ ' + e.message);
            btnStart.textContent = '🚀 Pokreni Sistem';
            btnStart.disabled = false;
        }
    });
    
    console.log('✅ Dashboard auto-switch dodat');
});

// ===== DIREKTNO UČITAVANJE FLOTE =====
async function loadFleetDirect() {
    try {
        const resp = await fetch('/api/fleet');
        const data = await resp.json();
        
        const container = document.getElementById('fleet-cards-container');
        if (!container) return;
        
        let html = '';
        let totalActive = 0;
        
        for (const [provider, info] of Object.entries(data)) {
            const active = info.active || 0;
            const total = info.total || 0;
            totalActive += active;
            
            html += '<details class="fleet-card" style="margin-bottom:8px;">';
            html += '<summary class="fleet-header" style="cursor:pointer;padding:10px;display:flex;justify-content:space-between;">';
            html += '<span><b>' + provider + '</b></span>';
            html += '<span>' + active + '/' + total + ' ključeva</span>';
            html += '</summary>';
            html += '<div class="fleet-keys" style="padding:10px;">';
            
            const keys = info.keys || [];
            keys.forEach(k => {
                const status = k.available ? '🟢' : (k.cooldown_remaining > 0 ? '🟡' : '🔴');
                const toggleBtn = '<button onclick="toggleKeyDirect(\'' + provider + '\', \'' + k.masked + '\')" style="margin-left:8px;cursor:pointer;background:none;border:1px solid #555;border-radius:4px;color:#aaa;">' + (k.available ? '🔴' : '🟢') + '</button>';
                html += '<div style="display:inline-block;margin:4px;padding:6px 10px;border:1px solid #444;border-radius:20px;font-size:0.8rem;">';
                html += k.masked + ' ' + status + toggleBtn;
                html += '</div>';
            });
            
            html += '</div></details>';
        }
        
        container.innerHTML = html || '<p>Nema provajdera</p>';
        document.getElementById('fleet-total-count').textContent = totalActive;
        
    } catch (e) {
        console.error('Fleet load error:', e);
    }
}

// Toggle ključa direktno
async function toggleKeyDirect(provider, maskedKey) {
    try {
        const resp = await fetch('/api/fleet/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, key: maskedKey })
        });
        const result = await resp.json();
        if (result.ok) {
            loadFleetDirect(); // Osvježi prikaz
        }
    } catch (e) {
        console.error('Toggle error:', e);
    }
}

// Učitaj flotu pri prvom otvaranju taba
document.addEventListener('DOMContentLoaded', function() {
    // Učitaj flotu nakon 1 sekunde
    setTimeout(loadFleetDirect, 1000);
    
    // Osvježi flotu kad se klikne tab
    document.querySelectorAll('.tab-btn[onclick*="tab-fleet"]').forEach(btn => {
        btn.addEventListener('click', loadFleetDirect);
    });
    
    // Periodično osvježavanje svakih 15 sekundi
    setInterval(loadFleetDirect, 15000);
});

console.log('✅ Fleet direktno učitavanje dodato');

// ===== SPREMANJE STANJA NA REFRESH =====
function saveAppState() {
    const state = {
        book: document.getElementById('book-select')?.value || '',
        model: document.getElementById('model-select')?.value || 'V8_TURBO',
        mode: document.querySelector('input[name="mode"]:checked')?.value || 'PREVOD',
        step2: !document.getElementById('wizard-page-2')?.classList.contains('hidden'),
        dashboard: !document.getElementById('dashboard-panel')?.classList.contains('hidden'),
        theme: document.body.classList.contains('light-theme') ? 'light' : 'dark'
    };
    localStorage.setItem('booklyfi_state_v2', JSON.stringify(state));
}

function restoreAppState() {
    const saved = localStorage.getItem('booklyfi_state_v2');
    if (!saved) return;
    try {
        const s = JSON.parse(saved);
        
        // Tema
        if (s.theme === 'light') document.body.classList.add('light-theme');
        
        setTimeout(() => {
            if (s.book) {
                const sel = document.getElementById('book-select');
                if (sel && Array.from(sel.options).some(o => o.value === s.book)) {
                    sel.value = s.book;
                }
            }
            if (s.model) {
                const sel = document.getElementById('model-select');
                if (sel) sel.value = s.model;
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
            }
        }, 300);
    } catch (e) {}
}

// Auto-save na promjene
window.addEventListener('beforeunload', saveAppState);
setInterval(saveAppState, 5000);

// Spremi na promjenu selectova
document.addEventListener('change', function(e) {
    if (e.target.matches('#book-select, #model-select, input[name="mode"]')) {
        saveAppState();
    }
});

// Vrati stanje pri učitavanju
document.addEventListener('DOMContentLoaded', function() {
    restoreAppState();
});

console.log('✅ Spremanje stanja dodato');

// ===== ETA I PROTEKLO VRIJEME =====
let _processingStartTime = null;
function formatTime(seconds) {
    if (seconds < 0 || !isFinite(seconds)) return '--:--:--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h.toString().padStart(2,'0')}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
}
function updateETA(pct, okText) {
    const match = okText.match(/(\d+)\s*\/\s*(\d+)/);
    if (!match || !_processingStartTime || pct <= 0 || pct >= 100) {
        document.getElementById('progress-eta').textContent = 'ETA: --:--:--';
        return;
    }
    const processed = parseInt(match[1]), total = parseInt(match[2]);
    const elapsed = (Date.now() - _processingStartTime) / 1000;
    if (processed > 0 && elapsed > 5) {
        const eta = formatTime((total - processed) / (processed / elapsed));
        document.getElementById('progress-eta').textContent = 'ETA: ' + eta;
        let el = document.getElementById('elapsed-time');
        if (!el) {
            el = document.createElement('span');
            el.id = 'elapsed-time';
            el.style.cssText = 'margin-left:10px;color:var(--text-secondary);font-family:monospace;';
            document.getElementById('progress-eta').parentNode.appendChild(el);
        }
        el.textContent = ' | Proteklо: ' + formatTime(elapsed);
    }
}
// Patch status polling da prati start time
const _origPoll = setInterval;
setInterval = function(fn, ms) {
    if (ms === 2000 && fn.toString().includes('statusResp')) {
        const origFn = fn;
        fn = async function() {
            const statusResp = await fetch('/api/status');
            const d = await statusResp.json();
            if ((d.status||'').toUpperCase().includes('TOKU') && !_processingStartTime) _processingStartTime = Date.now();
            if ((d.status||'').toUpperCase().includes('ZAVRŠEN')) _processingStartTime = null;
            updateETA(d.pct||0, d.ok||'0/0');
            origFn();
        };
    }
    return _origPoll(fn, ms);
};
console.log('✅ ETA i proteklo vrijeme dodati');

// ===== NEON ANIMACIJA =====
(function(){
    const colors = ['#60a5fa','#a78bfa','#4ade80','#fbbf24','#f87171','#06b6d4'];
    const letters = document.querySelectorAll('#app-logo-title');
    if (!letters.length) return;
    let timer;
    function flash() {
        const el = letters[0]; // cijeli h1
        const col = colors[Math.floor(Math.random()*colors.length)];
        el.style.textShadow = `0 0 8px ${col}, 0 0 20px ${col}, 0 0 40px ${col}`;
        setTimeout(() => { el.style.textShadow = ''; }, 200+Math.random()*300);
        timer = setTimeout(flash, 150+Math.random()*500);
    }
    setTimeout(flash, 600);
    window.addEventListener('beforeunload', () => clearTimeout(timer));
})();
console.log('✅ Neon animacija dodata');
