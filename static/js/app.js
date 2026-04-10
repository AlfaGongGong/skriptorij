// ============================================================================
// SKRIPTORIJ V8 TURBO — app.js (Enhanced)
// ============================================================================

let pollInterval = null;
let isRunning = false;
let lastAuditHTML = '';

document.addEventListener('DOMContentLoaded', () => {
    loadBooks();
    loadModels();
    checkBackendStatus();
});

// ── Provjera statusa na početku ──────────────────────────────────────────
function checkBackendStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(d => {
            if (d.status && d.status.toUpperCase() !== 'IDLE') {
                switchToDashboard();
                updateDashboard();
                if (pollInterval) clearInterval(pollInterval);
                pollInterval = setInterval(updateDashboard, 1500);
            }
        })
        .catch(e => console.error('Status check error:', e));
}

// ── Učitavanje knjiga ────────────────────────────────────────────────────
function loadBooks() {
    fetch('/api/books')
        .then(r => r.json())
        .then(d => {
            const select = document.getElementById('book-select');
            if (!select) return;

            select.innerHTML = '<option value="">— Odaberi knjigu —</option>';

            if (d.books && d.books.length > 0) {
                d.books.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.path;
                    opt.textContent = b.name;
                    if (d.last_book && b.path === d.last_book) {
                        opt.selected = true;
                    }
                    select.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'Nema dostupnih EPUB fajlova';
                opt.disabled = true;
                select.appendChild(opt);
            }
        })
        .catch(e => console.error('Greška pri učitavanju knjiga:', e));
}

// ── Upload knjige ─────────────���──────────────────────────────────────────
function uploadBook(file) {
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const btn = document.getElementById('btn-start');
    const fileInput = document.getElementById('book-file');

    if (btn) btn.innerText = '⏳ Uploadujem...';
    if (btn) btn.disabled = true;

    fetch('/api/upload_book', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                alert('❌ Greška: ' + d.error);
                if (btn) btn.disabled = false;
                return;
            }

            alert('✅ Uspješno uploadovano: ' + d.name);
            loadBooks();

            // Automatski odaberi uploadanu knjugu
            const select = document.getElementById('book-select');
            if (select) {
                Array.from(select.options).forEach(opt => {
                    if (opt.textContent === d.name) {
                        opt.selected = true;
                    }
                });
            }

            if (fileInput) fileInput.value = '';
            if (btn) {
                btn.innerText = '🚀 Pokreni Sistem';
                btn.disabled = false;
            }
        })
        .catch(e => {
            console.error('Upload greška:', e);
            alert('❌ Greška pri uploadu: ' + e.message);
            if (btn) {
                btn.innerText = '🚀 Pokreni Sistem';
                btn.disabled = false;
            }
        });
}

// ── Učitavanje modela ────────────────────────────────────────────────────
function loadModels() {
    fetch('/api/dev_models')
        .then(r => r.json())
        .then(models => {
            const select = document.getElementById('model-select');
            if (!select) return;

            select.innerHTML = '';

            if (Array.isArray(models) && models.length > 0) {
                models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    if (m === 'QUAD_CORE') opt.selected = true;
                    select.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.value = 'QUAD_CORE';
                opt.textContent = 'QUAD_CORE (Default)';
                opt.selected = true;
                select.appendChild(opt);
            }
        })
        .catch(e => {
            console.error('Greška pri učitavanju modela:', e);
            const select = document.getElementById('model-select');
            if (select) {
                select.innerHTML = '<option value="QUAD_CORE" selected>QUAD_CORE (Default)</option>';
            }
        });
}

// ── Pokretanje sistema ───────────────────────────────────────────────────
function startEngine() {
    const bookSelect = document.getElementById('book-select');
    const modelSelect = document.getElementById('model-select');
    const btn = document.getElementById('btn-start');

    const book = bookSelect ? bookSelect.value : '';
    const model = modelSelect ? modelSelect.value : 'QUAD_CORE';

    if (!book || book === '') {
        alert('⚠️ Odaberi ili uploadaj EPUB fajl prije pokretanja!');
        return;
    }

    if (btn) {
        btn.innerText = '⏳ Inicijalizacija...';
        btn.disabled = true;
    }

    isRunning = true;

    fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book, model })
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                alert('❌ Greška pri pokretanju: ' + d.error);
                if (btn) {
                    btn.innerText = '🚀 Pokreni Sistem';
                    btn.disabled = false;
                }
                isRunning = false;
                return;
            }

            switchToDashboard();

            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(updateDashboard, 1500);

            updateDashboard();
        })
        .catch(e => {
            console.error('Start greška:', e);
            alert('�� Greška pri spajanju sa serverom: ' + e.message);
            if (btn) {
                btn.innerText = '🚀 Pokreni Sistem';
                btn.disabled = false;
            }
            isRunning = false;
        });
}

// ── Prebacivanje na dashboard ────────────────────────────────────────────
function switchToDashboard() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');

    if (setupScreen) setupScreen.classList.add('hidden');
    if (dashboardScreen) dashboardScreen.classList.remove('hidden');
}

// ── Prebacivanje na setup ────────────────────────────────────────────────
function switchToSetup() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');

    if (dashboardScreen) dashboardScreen.classList.add('hidden');
    if (setupScreen) setupScreen.classList.remove('hidden');
}

// ── Komande (Pause, Resume, Reset, Stop) ─────────────────────────────────
function sendCommand(cmd) {
    fetch('/control/' + cmd, {
        method: 'POST'
    })
        .then(r => r.json())
        .then(d => {
            const dot = document.getElementById('status-dot');

            switch (cmd) {
                case 'pause':
                    if (dot) dot.className = 'dot dot-paused';
                    break;
                case 'resume':
                    if (dot) dot.className = 'dot dot-active';
                    break;
                case 'stop':
                    if (dot) dot.className = 'dot dot-idle';
                    if (pollInterval) clearInterval(pollInterval);
                    isRunning = false;
                    break;
                case 'reset':
                    if (pollInterval) clearInterval(pollInterval);
                    isRunning = false;
                    if (dot) dot.className = 'dot dot-idle';
                    setTimeout(() => {
                        switchToSetup();
                        loadBooks();
                        loadModels();
                        const btn = document.getElementById('btn-start');
                        if (btn) {
                            btn.innerText = '🚀 Pokreni Sistem';
                            btn.disabled = false;
                        }
                    }, 500);
                    break;
            }
        })
        .catch(e => console.error('Komanda greška:', e));
}

// ── Ažuriranje dashboard-a ───────────────────────────────────────────────
function updateDashboard() {
    fetch('/api/status')
        .then(r => r.json())
        .then(d => {
            // Osnovna polja
            _updateEl('ph', d.status || 'IDLE');
            _updateEl('ae', d.active_engine || '---');
            _updateEl('bi', d.current_file || '---');
            _updateEl('ok', d.ok || '0 / 0');
            _updateEl('skp', d.skipped || '0');
            _updateEl('pct', (d.pct || 0) + '%');
            _updateEl('est', d.est || '--:--:--');

            // Fleet status
            _updateEl('fleet-active', d.fleet_active || 0);
            _updateEl('fleet-cooling', d.fleet_cooling || 0);

            // Progress bar
            const fill = document.getElementById('fill');
            if (fill) {
                fill.style.width = (d.pct || 0) + '%';
            }

            // Audit log
            const audit = document.getElementById('audit');
            if (audit && d.live_audit) {
                if (audit.innerHTML !== d.live_audit) {
                    audit.innerHTML = d.live_audit;
                    lastAuditHTML = d.live_audit;

                    // Auto-scroll na kraj (osim ako korisnik čita)
                    const isScrolledToBottom =
                        audit.scrollHeight - audit.clientHeight <=
                        audit.scrollTop + 50;

                    if (isScrolledToBottom) {
                        setTimeout(() => {
                            audit.scrollTop = audit.scrollHeight;
                        }, 50);
                    }
                }
            }

            // Status dot
            const dot = document.getElementById('status-dot');
            const statusText = (d.status || '').toUpperCase();

            if (dot) {
                if (
                    statusText.includes('TOKU') ||
                    statusText.includes('POKRENUTA')
                ) {
                    dot.className = 'dot dot-active';
                } else if (
                    statusText === 'PAUZIRANO' ||
                    statusText.includes('PAUZA')
                ) {
                    dot.className = 'dot dot-paused';
                } else {
                    dot.className = 'dot dot-idle';
                }
            }

            // Automatski stop polling-a
            if (d.pct >= 100 || statusText.includes('ZAVRŠEN')) {
                if (pollInterval) clearInterval(pollInterval);
            }
        })
        .catch(e => console.error('Dashboard greška:', e));
}

// ── Helper funkcije ─────────────────────────────────────────────────────
function _updateEl(id, val) {
    const el = document.getElementById(id);
    if (el && el.innerText !== String(val)) {
        el.innerText = val;
    }
}

// Tastatura shortcut-i
document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey) {
        if (e.key === 'Enter' && !document.getElementById('setup-screen').classList.contains('hidden')) {
            e.preventDefault();
            startEngine();
        }
        if (e.key === ' ') {
            e.preventDefault();
            sendCommand('pause');
        }
    }
});
