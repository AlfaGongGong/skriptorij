/* ============================================================
   SKRIPTORIJ V8 TURBO — Frontend Application Logic
   ============================================================ */

'use strict';

// ── DOM references ──────────────────────────────────────────
const bookSelect      = document.getElementById('book-select');
const modelSelect     = document.getElementById('model-select');
const uploadInput     = document.getElementById('upload-input');
const uploadBtn       = document.getElementById('upload-btn');
const uploadMsg       = document.getElementById('upload-msg');
const startBtn        = document.getElementById('start-btn');
const pauseBtn        = document.getElementById('pause-btn');
const resumeBtn       = document.getElementById('resume-btn');
const stopBtn         = document.getElementById('stop-btn');
const resetBtn        = document.getElementById('reset-btn');
const statusBadge     = document.getElementById('status-badge');
const statEngine      = document.getElementById('stat-engine');
const statFile        = document.getElementById('stat-file');
const statFiles       = document.getElementById('stat-files');
const statChunks      = document.getElementById('stat-chunks');
const statOk          = document.getElementById('stat-ok');
const statEta         = document.getElementById('stat-eta');
const statFleetActive = document.getElementById('stat-fleet-active');
const statFleetCool   = document.getElementById('stat-fleet-cooling');
const progressBar     = document.getElementById('progress-bar');
const progressPct     = document.getElementById('progress-pct');
const liveAudit       = document.getElementById('live-audit');

// ── State ───────────────────────────────────────────────────
let pollInterval  = null;
let isProcessing  = false;

// ── Helpers ─────────────────────────────────────────────────
function setButtonStates(running, paused) {
    startBtn.disabled  = running;
    pauseBtn.disabled  = !running || paused;
    resumeBtn.disabled = !running || !paused;
    stopBtn.disabled   = !running;
}

function classifyStatus(status) {
    if (!status) return 'idle';
    const s = status.toUpperCase();
    if (s.includes('PAUZI'))  return 'paused';
    if (s.includes('ZAUSTA')) return 'stopped';
    if (s.includes('GREŠKA') || s.includes('GREŠK')) return 'stopped';
    if (s.includes('GOTOV') || s.includes('ZAVRŠEN') || s.includes('KOMPLET')) return 'done';
    if (s === 'IDLE' || s === 'RESETOVANO') return 'idle';
    return 'running';
}

function updateStatusBadge(status) {
    statusBadge.textContent = status || 'IDLE';
    statusBadge.className = 'status-badge ' + classifyStatus(status);
}

// ── API calls ───────────────────────────────────────────────
async function fetchBooks() {
    try {
        const res  = await fetch('/api/books');
        const data = await res.json();
        bookSelect.innerHTML = '';
        if (!data.books || data.books.length === 0) {
            bookSelect.innerHTML = '<option value="">-- Nema knjiga --</option>';
            return;
        }
        data.books.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.name;
            opt.textContent = b.name;
            if (b.name === data.last_book) opt.selected = true;
            bookSelect.appendChild(opt);
        });
    } catch (e) {
        bookSelect.innerHTML = '<option value="">-- Greška pri učitavanju --</option>';
    }
}

async function fetchModels() {
    try {
        const res    = await fetch('/api/dev_models');
        const models = await res.json();
        modelSelect.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            modelSelect.appendChild(opt);
        });
    } catch (e) {
        // keep default option
    }
}

async function fetchStatus() {
    try {
        const res  = await fetch('/api/status');
        const data = await res.json();
        applyStatus(data);
    } catch (e) {
        // silently skip on network error
    }
}

function applyStatus(data) {
    updateStatusBadge(data.status);
    statEngine.textContent      = data.active_engine   || '---';
    statFile.textContent        = data.current_file    || '---';
    statFiles.textContent       = `${data.current_file_idx || 0} / ${data.total_files || 0}`;
    statChunks.textContent      = `${data.current_chunk_idx || 0} / ${data.total_file_chunks || 0}`;
    statOk.textContent          = data.ok              || '0 / 0';
    statEta.textContent         = data.est             || '--:--:--';
    statFleetActive.textContent = data.fleet_active    || 0;
    statFleetCool.textContent   = data.fleet_cooling   || 0;

    const pct = data.pct || 0;
    progressBar.style.width = pct + '%';
    progressPct.textContent  = pct + '%';

    if (data.live_audit !== undefined) {
        liveAudit.textContent = data.live_audit;
        liveAudit.scrollTop   = liveAudit.scrollHeight;
    }

    const cls  = classifyStatus(data.status);
    const running = cls === 'running' || cls === 'paused';
    isProcessing  = running;
    setButtonStates(running, cls === 'paused');
}

async function sendControl(action) {
    try {
        await fetch(`/control/${action}`, { method: 'POST' });
    } catch (e) {
        // ignore
    }
}

// ── Event listeners ─────────────────────────────────────────
startBtn.addEventListener('click', async () => {
    const book  = bookSelect.value;
    const model = modelSelect.value;
    if (!book) {
        uploadMsg.textContent = '⚠ Odaberi knjigu.';
        setTimeout(() => { uploadMsg.textContent = ''; }, 3000);
        return;
    }
    try {
        const res  = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book, model })
        });
        const data = await res.json();
        if (!res.ok) {
            liveAudit.textContent = '❌ ' + (data.error || 'Greška pri pokretanju.');
            return;
        }
        isProcessing = true;
        setButtonStates(true, false);
        startPolling();
    } catch (e) {
        liveAudit.textContent = '❌ Mrežna greška: ' + e.message;
    }
});

pauseBtn.addEventListener('click', async () => {
    await sendControl('pause');
    setButtonStates(true, true);
    updateStatusBadge('PAUZIRANO');
});

resumeBtn.addEventListener('click', async () => {
    await sendControl('resume');
    setButtonStates(true, false);
    updateStatusBadge('OBRADA U TOKU...');
});

stopBtn.addEventListener('click', async () => {
    await sendControl('stop');
    setButtonStates(false, false);
    updateStatusBadge('ZAUSTAVLJENO');
    stopPolling();
});

resetBtn.addEventListener('click', async () => {
    await sendControl('reset');
    isProcessing = false;
    setButtonStates(false, false);
    updateStatusBadge('RESETOVANO');
    progressBar.style.width = '0%';
    progressPct.textContent  = '0%';
    liveAudit.textContent    = 'Sesija resetovana.';
    stopPolling();
});

uploadBtn.addEventListener('click', async () => {
    const file = uploadInput.files[0];
    if (!file) {
        uploadMsg.textContent = '⚠ Odaberi fajl.';
        setTimeout(() => { uploadMsg.textContent = ''; }, 3000);
        return;
    }
    const form = new FormData();
    form.append('file', file);
    uploadMsg.textContent = '⏳ Uploading...';
    try {
        const res  = await fetch('/api/upload_book', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) {
            uploadMsg.textContent = '❌ ' + (data.error || 'Upload greška.');
        } else {
            uploadMsg.textContent = '✔ ' + data.name + ' uploadovan.';
            uploadInput.value = '';
            await fetchBooks();
        }
    } catch (e) {
        uploadMsg.textContent = '❌ Mrežna greška.';
    }
    setTimeout(() => { uploadMsg.textContent = ''; }, 5000);
});

// ── Polling ─────────────────────────────────────────────────
function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(fetchStatus, 1500);
}

function stopPolling() {
    clearInterval(pollInterval);
    pollInterval = null;
}

// ── Init ────────────────────────────────────────────────────
(async function init() {
    await Promise.all([fetchBooks(), fetchModels(), fetchStatus()]);
    if (isProcessing) startPolling();
})();
