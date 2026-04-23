alert("app.js ucitan!");
/**
 * app.js — Booklyfi Turbo Charged — Glavna logika aplikacije
 * Kompletna, funkcionalna verzija.
 */

import { apiClient }        from './api-client.js';
import { startPolling, stopPolling } from './services/polling.js';
import { applyStoredTheme, toggleTheme } from './services/theme.js';
import { renderFleet, updateFleetTotalCount } from './ui/fleet.js';
import { showToast }        from './ui/notifications.js';
import { storage }          from './services/storage.js';

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
