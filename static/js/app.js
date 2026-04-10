// ============================================================================
// SKRIPTORIJ V8 TURBO -- app.js (Enhanced)
// ============================================================================

let pollInterval = null;
let fleetPollInterval = null;
let isRunning = false;
let lastAuditHTML = '';

document.addEventListener('DOMContentLoaded', () => {
    applyStoredTheme();
    loadBooks();
    loadModels();
    checkBackendStatus();

    // Ucitaj fleet kada se otvori panel
    const fleetDetails = document.getElementById('fleet-details');
    if (fleetDetails) {
        fleetDetails.addEventListener('toggle', () => {
            if (fleetDetails.open) {
                updateFleetPool();
                if (!fleetPollInterval) {
                    fleetPollInterval = setInterval(updateFleetPool, 5000);
                }
            } else {
                if (fleetPollInterval) {
                    clearInterval(fleetPollInterval);
                    fleetPollInterval = null;
                }
            }
        });
    }
});

// -- Toast notifikacije -------------------------------------------------------
function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });
    });

    setTimeout(() => {
        toast.classList.remove('toast-visible');
        toast.addEventListener('transitionend', () => toast.remove(), { once: true });
    }, 4000);
}

// -- Tema -- cuvanje u localStorage ------------------------------------------
function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    localStorage.setItem('skriptorij-theme', isLight ? 'light' : 'dark');
}

function applyStoredTheme() {
    if (localStorage.getItem('skriptorij-theme') === 'light') {
        document.body.classList.add('light-theme');
    }
}

// -- Provjera statusa na pocetku ---------------------------------------------
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

// -- Ucitavanje knjiga -------------------------------------------------------
function loadBooks() {
    fetch('/api/books')
        .then(r => r.json())
        .then(d => {
            const select = document.getElementById('book-select');
            if (!select) return;

            select.innerHTML = '<option value="">-- Odaberi knjigu --</option>';

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
        .catch(e => console.error('Greska pri ucitavanju knjiga:', e));
}

// -- Upload knjige -----------------------------------------------------------
function uploadBook(file) {
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    const btn = document.getElementById('btn-start');
    const fileInput = document.getElementById('book-file');

    if (btn) btn.innerText = '\u23F3 Uploadujem...';
    if (btn) btn.disabled = true;

    fetch('/api/upload_book', {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                showToast('\u274C Greska pri uploadu: ' + d.error, 'error');
                if (btn) btn.disabled = false;
                return;
            }

            showToast('\u2705 Uspjesno uploadovano: ' + d.name, 'success');
            loadBooks();

            // Automatski odaberi uploadanu knjigu
            setTimeout(() => {
                const select = document.getElementById('book-select');
                if (select) {
                    Array.from(select.options).forEach(opt => {
                        if (opt.textContent === d.name) {
                            opt.selected = true;
                        }
                    });
                }
            }, 300);

            if (fileInput) fileInput.value = '';
            if (btn) {
                btn.innerText = '\uD83D\uDE80 Pokreni Sistem';
                btn.disabled = false;
            }
        })
        .catch(e => {
            console.error('Upload greska:', e);
            showToast('\u274C Greska pri uploadu: ' + e.message, 'error');
            if (btn) {
                btn.innerText = '\uD83D\uDE80 Pokreni Sistem';
                btn.disabled = false;
            }
        });
}

// -- Ucitavanje modela -------------------------------------------------------
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
            console.error('Greska pri ucitavanju modela:', e);
            const select = document.getElementById('model-select');
            if (select) {
                select.innerHTML = '<option value="QUAD_CORE" selected>QUAD_CORE (Default)</option>';
            }
        });
}

// -- Pokretanje sistema ------------------------------------------------------
function startEngine() {
    const bookSelect = document.getElementById('book-select');
    const modelSelect = document.getElementById('model-select');
    const modeSelect = document.getElementById('mode-select');
    const btn = document.getElementById('btn-start');

    const book = bookSelect ? bookSelect.value : '';
    const model = modelSelect ? modelSelect.value : 'QUAD_CORE';
    const mode = modeSelect ? modeSelect.value : 'PREVOD';

    if (!book || book === '') {
        showToast('\u26A0\uFE0F Odaberi ili uploadaj EPUB fajl prije pokretanja!', 'warning');
        return;
    }

    if (btn) {
        btn.innerText = '\u23F3 Inicijalizacija...';
        btn.disabled = true;
    }

    isRunning = true;

    fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ book: book, model: model, mode: mode })
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                showToast('\u274C Greska pri pokretanju: ' + d.error, 'error');
                if (btn) {
                    btn.innerText = '\uD83D\uDE80 Pokreni Sistem';
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
            console.error('Start greska:', e);
            showToast('\u274C Greska pri spajanju sa serverom: ' + e.message, 'error');
            if (btn) {
                btn.innerText = '\uD83D\uDE80 Pokreni Sistem';
                btn.disabled = false;
            }
            isRunning = false;
        });
}

// -- Prebacivanje na dashboard ------------------------------------------------
function switchToDashboard() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');

    if (setupScreen) setupScreen.classList.add('hidden');
    if (dashboardScreen) dashboardScreen.classList.remove('hidden');
}

// -- Prebacivanje na setup ----------------------------------------------------
function switchToSetup() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');

    if (dashboardScreen) dashboardScreen.classList.add('hidden');
    if (setupScreen) setupScreen.classList.remove('hidden');
}

// -- Komande (Pause, Resume, Reset, Stop) ------------------------------------
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
                    const dlSection = document.getElementById('download-section');
                    if (dlSection) dlSection.classList.add('hidden');
                    setTimeout(() => {
                        switchToSetup();
                        loadBooks();
                        loadModels();
                        const btn = document.getElementById('btn-start');
                        if (btn) {
                            btn.innerText = '\uD83D\uDE80 Pokreni Sistem';
                            btn.disabled = false;
                        }
                    }, 500);
                    break;
            }
        })
        .catch(e => console.error('Komanda greska:', e));
}

// -- Azuriranje dashboard-a --------------------------------------------------
function updateDashboard() {
    fetch('/api/status')
        .then(r => r.json())
        .then(d => {
            _updateEl('ph', d.status || 'IDLE');
            _updateEl('ae', d.active_engine || '---');
            _updateEl('bi', d.current_file || '---');
            _updateEl('ok', d.ok || '0 / 0');
            _updateEl('skp', d.skipped || '0');
            _updateEl('pct', (d.pct || 0) + '%');
            _updateEl('est', d.est || '--:--:--');

            _updateEl('fleet-active', d.fleet_active || 0);
            _updateEl('fleet-cooling', d.fleet_cooling || 0);

            const fill = document.getElementById('fill');
            if (fill) {
                fill.style.width = (d.pct || 0) + '%';
            }

            const audit = document.getElementById('audit');
            if (audit && d.live_audit) {
                if (audit.innerHTML !== d.live_audit) {
                    audit.innerHTML = d.live_audit;
                    lastAuditHTML = d.live_audit;

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

            const dot = document.getElementById('status-dot');
            const statusText = (d.status || '').toUpperCase();

            if (dot) {
                if (statusText.includes('TOKU') || statusText.includes('POKRENUTA')) {
                    dot.className = 'dot dot-active';
                } else if (statusText === 'PAUZIRANO' || statusText.includes('PAUZA')) {
                    dot.className = 'dot dot-paused';
                } else {
                    dot.className = 'dot dot-idle';
                }
            }

            // Download dugme -- prikazuje se kad je output_file postavljen
            const dlSection = document.getElementById('download-section');
            const dlLink = document.getElementById('download-link');
            if (dlSection && dlLink && d.output_file) {
                dlLink.href = '/api/download/' + encodeURIComponent(d.output_file);
                dlLink.textContent = '\u2B07\uFE0F Preuzmi: ' + d.output_file;
                dlSection.classList.remove('hidden');
            }

            if (d.pct >= 100 || statusText.includes('ZAVRSEN')) {
                if (pollInterval) clearInterval(pollInterval);
            }
        })
        .catch(e => console.error('Dashboard greska:', e));
}

// -- Fleet Pool --------------------------------------------------------------
function updateFleetPool() {
    fetch('/api/fleet')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('fleet-pool-content');
            if (!container) return;

            if (data.error) {
                container.innerHTML = '<p style="color: var(--col-danger); font-size:0.85rem;">Greska: ' + data.error + '</p>';
                return;
            }

            const providers = Object.entries(data);
            if (providers.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted); font-size:0.85rem;">Nema konfiguriranih provajdera.</p>';
                return;
            }

            let html = '<table class="fleet-table"><thead><tr>'
                + '<th>Provajder</th><th>\u2705 Aktivni</th><th>\uD83D\uDD25 Hladenje</th><th>Kvota %</th>'
                + '</tr></thead><tbody>';

            for (let i = 0; i < providers.length; i++) {
                const prov = providers[i][0];
                const info = providers[i][1];
                const active = info.active || 0;
                const cooling = info.cooling || 0;
                const total = info.total || (active + cooling) || 1;
                const pct = Math.round((active / total) * 100);
                const barColor = pct > 60 ? 'var(--col-success)' : pct > 30 ? 'var(--col-warning)' : 'var(--col-danger)';

                html += '<tr>'
                    + '<td class="fleet-prov">' + prov + '</td>'
                    + '<td style="color:var(--col-success); font-weight:bold;">' + active + '</td>'
                    + '<td style="color:var(--col-warning); font-weight:bold;">' + cooling + '</td>'
                    + '<td><div class="fleet-bar-bg"><div class="fleet-bar-fill" style="width:' + pct + '%; background:' + barColor + ';"></div></div>'
                    + '<span style="font-size:0.75rem; color:var(--text-muted);">' + pct + '%</span></td>'
                    + '</tr>';
            }

            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(e => {
            const container = document.getElementById('fleet-pool-content');
            if (container) container.innerHTML = '<p style="color: var(--col-danger); font-size:0.85rem;">Greska pri dohvacanju flote: ' + e.message + '</p>';
        });
}

// -- Helper funkcije ---------------------------------------------------------
function _updateEl(id, val) {
    const el = document.getElementById(id);
    if (el && el.innerText !== String(val)) {
        el.innerText = val;
    }
}

// Tastatura shortcut-i
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey || e.metaKey) {
        const setupScreen = document.getElementById('setup-screen');
        if (e.key === 'Enter' && setupScreen && !setupScreen.classList.contains('hidden')) {
            e.preventDefault();
            startEngine();
        }
        if (e.key === ' ') {
            e.preventDefault();
            sendCommand('pause');
        }
    }
});
