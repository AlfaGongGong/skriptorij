// ============================================================================
// SKRIPTORIJ V8 TURBO -- app.js (Enhanced)
// ============================================================================

let pollInterval = null;
let fleetPollInterval = null;
let isRunning = false;
let lastAuditHTML = '';

const FLEET_BAR_HIGH = 60;
const FLEET_BAR_MID = 30;

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

    // #14: Ucitaj ključeve kada se otvori key management panel
    const keysDetails = document.getElementById('keys-details');
    if (keysDetails) {
        keysDetails.addEventListener('toggle', () => {
            if (keysDetails.open) {
                loadApiKeys();
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
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = isLight ? '🌙 Tema' : '☀️ Tema';
}

function applyStoredTheme() {
    if (localStorage.getItem('skriptorij-theme') === 'light') {
        document.body.classList.add('light-theme');
        const btn = document.getElementById('btn-theme');
        if (btn) btn.textContent = '🌙 Tema';
    }
}

// -- Setup Toggle (dostupan i tokom rada) ------------------------------------
function toggleSetup() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');
    if (!setupScreen) return;

    const isHidden = setupScreen.classList.contains('hidden');
    if (isHidden) {
        // Prikaži setup overlay (čuva dashboard ispod)
        setupScreen.classList.remove('hidden');
        setupScreen.classList.add('setup-overlay-active');
    } else {
        setupScreen.classList.add('hidden');
        setupScreen.classList.remove('setup-overlay-active');
    }
}

// -- Provjera statusa na pocetku ---------------------------------------------
function checkBackendStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(d => {
            // Uvijek ažuriraj header dot i status tekst
            updateDashboard();

            if (d.status && d.status.toUpperCase() !== 'IDLE' && d.status.toUpperCase() !== 'RESETOVANO') {
                switchToDashboard();
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
                    opt.textContent = m === 'V8_TURBO' ? '⚡ V8 TURBO (Preporučeno)' : m;
                    if (m === 'V8_TURBO') opt.selected = true;
                    select.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.value = 'V8_TURBO';
                opt.textContent = '⚡ V8 TURBO (Default)';
                opt.selected = true;
                select.appendChild(opt);
            }
        })
        .catch(e => {
            console.error('Greska pri ucitavanju modela:', e);
            const select = document.getElementById('model-select');
            if (select) {
                select.innerHTML = '<option value="V8_TURBO" selected>⚡ V8 TURBO (Default)</option>';
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
    const model = modelSelect ? modelSelect.value : 'V8_TURBO';
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

    if (setupScreen) {
        setupScreen.classList.add('hidden');
        setupScreen.classList.remove('setup-overlay-active');
    }
    if (dashboardScreen) dashboardScreen.classList.remove('hidden');
}

// -- Prebacivanje na setup ----------------------------------------------------
function switchToSetup() {
    const setupScreen = document.getElementById('setup-screen');
    const dashboardScreen = document.getElementById('dashboard-screen');

    if (dashboardScreen) dashboardScreen.classList.add('hidden');
    if (setupScreen) {
        setupScreen.classList.remove('hidden');
        setupScreen.classList.remove('setup-overlay-active');
    }
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
                const safeAudit = (typeof DOMPurify !== 'undefined')
                    ? DOMPurify.sanitize(d.live_audit, { USE_PROFILES: { html: true } })
                    : d.live_audit;
                if (audit.innerHTML !== safeAudit) {
                    audit.innerHTML = safeAudit;
                    lastAuditHTML = safeAudit;

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
            const statusEl = document.getElementById('ph');
            const statusText = (d.status || '').toUpperCase();

            // Semaphore: GREEN = u toku, YELLOW = idle/upozorenje, RED = greška
            if (dot) {
                if (statusText.includes('TOKU') || statusText.includes('POKRENUTA') || statusText.includes('POKRETANJE')) {
                    dot.className = 'dot dot-active';
                } else if (statusText === 'PAUZIRANO' || statusText.includes('PAUZA')) {
                    dot.className = 'dot dot-paused';
                } else if (
                    statusText.includes('GREŠKA') || statusText.includes('GRESKA') ||
                    statusText.includes('ERROR') || statusText.includes('ZAUSTAVLJENO')
                ) {
                    dot.className = 'dot dot-error';
                } else {
                    dot.className = 'dot dot-idle';
                }
            }

            // Status tekst boja — dinamički semaphore
            if (statusEl) {
                statusEl.classList.remove('status-idle', 'status-ok', 'status-warning', 'status-error');
                if (
                    statusText.includes('TOKU') || statusText.includes('POKRENUTA') ||
                    statusText.includes('ZAVRŠEN') || statusText.includes('ZAVRSEN')
                ) {
                    statusEl.classList.add('status-ok');
                } else if (
                    statusText.includes('GREŠKA') || statusText.includes('GRESKA') ||
                    statusText.includes('ERROR') || statusText.includes('ZAUSTAVLJENO')
                ) {
                    statusEl.classList.add('status-error');
                } else if (statusText === 'PAUZIRANO' || statusText.includes('PAUZA')) {
                    statusEl.classList.add('status-warning');
                } else {
                    statusEl.classList.add('status-idle');
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

            if (d.pct >= 100 || statusText.includes('ZAVRSEN') || statusText.includes('ZAVRŠEN')) {
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
                const p = document.createElement('p');
                p.style.cssText = 'color: var(--col-danger); font-size:0.85rem;';
                p.textContent = 'Greška: ' + data.error;
                container.replaceChildren(p);
                return;
            }

            const providers = Object.entries(data);
            if (providers.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted); font-size:0.85rem;">Nema konfiguriranih provajdera.</p>';
                return;
            }

            const table = document.createElement('table');
            table.className = 'fleet-table';

            const thead = document.createElement('thead');
            thead.innerHTML = '<tr>'
                + '<th>Provajder</th>'
                + '<th>Ključ</th>'
                + '<th style="color:var(--col-success);">Stanje</th>'
                + '<th>Zahtjevi</th>'
                + '<th>Greške</th>'
                + '<th>Limit/min</th>'
                + '<th>Preost./min</th>'
                + '<th>Kvota %</th>'
                + '</tr>';
            table.appendChild(thead);

            const tbody = document.createElement('tbody');

            for (const [prov, info] of providers) {
                const active = info.active || 0;
                const total = info.total || 1;
                const pct = Math.round((active / total) * 100);
                const barColor = pct > FLEET_BAR_HIGH
                    ? 'var(--col-success)'
                    : pct > FLEET_BAR_MID ? 'var(--col-warning)' : 'var(--col-danger)';

                const keys = info.keys || [];

                if (keys.length === 0) {
                    // Samo prikaz sažetka bez ključeva
                    const tr = document.createElement('tr');
                    const tdProv = document.createElement('td');
                    tdProv.className = 'fleet-prov';
                    tdProv.textContent = prov;
                    const tdSum = document.createElement('td');
                    tdSum.colSpan = 7;
                    tdSum.style.color = 'var(--text-muted)';
                    tdSum.textContent = active + ' / ' + total + ' aktivno';
                    tr.append(tdProv, tdSum);
                    tbody.appendChild(tr);
                    continue;
                }

                keys.forEach((k, idx) => {
                    const tr = document.createElement('tr');

                    // Provajder (samo u prvom redu)
                    const tdProv = document.createElement('td');
                    tdProv.className = 'fleet-prov';
                    tdProv.textContent = idx === 0 ? prov : '';
                    tr.appendChild(tdProv);

                    // Maskirani ključ
                    const tdKey = document.createElement('td');
                    tdKey.style.cssText = 'font-family:monospace; color:var(--text-accent); font-size:0.8rem;';
                    tdKey.textContent = k.masked || '***';
                    tr.appendChild(tdKey);

                    // Stanje (Aktivan / Hlađenje N s)
                    const tdState = document.createElement('td');
                    if (k.available) {
                        tdState.innerHTML = '<span style="color:var(--col-success);">✅ Aktivan</span>';
                    } else {
                        const secs = k.cooldown_remaining > 0 ? Math.ceil(k.cooldown_remaining) + 's' : '';
                        tdState.innerHTML = '<span style="color:var(--col-warning);">🔥 Hlađenje ' + secs + '</span>';
                    }
                    tr.appendChild(tdState);

                    // Ukupni zahtjevi
                    const tdReq = document.createElement('td');
                    tdReq.style.color = 'var(--text-muted)';
                    tdReq.textContent = k.total_requests != null ? k.total_requests : '—';
                    tr.appendChild(tdReq);

                    // Greške
                    const tdErr = document.createElement('td');
                    tdErr.style.color = (k.errors > 0) ? 'var(--col-danger)' : 'var(--text-muted)';
                    tdErr.textContent = k.errors != null ? k.errors : '—';
                    tr.appendChild(tdErr);

                    // Limit/min
                    const tdLim = document.createElement('td');
                    tdLim.style.color = 'var(--text-muted)';
                    tdLim.textContent = k.rate_limit_minute != null ? k.rate_limit_minute : '—';
                    tr.appendChild(tdLim);

                    // Preostalo/min
                    const tdRem = document.createElement('td');
                    if (k.remaining_minute != null) {
                        const remPct = k.rate_limit_minute > 0
                            ? Math.round((k.remaining_minute / k.rate_limit_minute) * 100)
                            : null;
                        tdRem.textContent = k.remaining_minute;
                        tdRem.style.color = remPct != null
                            ? (remPct > 50 ? 'var(--col-success)' : remPct > 20 ? 'var(--col-warning)' : 'var(--col-danger)')
                            : 'var(--text-muted)';
                    } else {
                        tdRem.textContent = '—';
                        tdRem.style.color = 'var(--text-muted)';
                    }
                    tr.appendChild(tdRem);

                    // Kvota % (progress bar) — prikazuje se samo u prvom redu provajdera
                    const tdBar = document.createElement('td');
                    if (idx === 0) {
                        tdBar.innerHTML = '<div class="fleet-bar-bg"><div class="fleet-bar-fill" style="width:' + pct + '%; background:' + barColor + ';"></div></div>'
                            + '<span style="font-size:0.75rem; color:var(--text-muted);">' + pct + '%</span>';
                    }
                    tr.appendChild(tdBar);

                    tbody.appendChild(tr);
                });
            }

            table.appendChild(tbody);
            container.replaceChildren(table);
        })
        .catch(e => {
            const container = document.getElementById('fleet-pool-content');
            if (container) {
                const p = document.createElement('p');
                p.style.cssText = 'color: var(--col-danger); font-size:0.85rem;';
                p.textContent = 'Greška pri dohvaćanju flote.';
                container.replaceChildren(p);
            }
        });
}

// -- Helper funkcije ---------------------------------------------------------
function _updateEl(id, val) {
    const el = document.getElementById(id);
    if (el && el.innerText !== String(val)) {
        el.innerText = val;
    }
}

// -- #14: API Key Management ------------------------------------------------
function loadApiKeys() {
    fetch('/api/keys')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('keys-list');
            if (!container) return;

            if (data.error) {
                const p = document.createElement('p');
                p.style.cssText = 'color: var(--col-danger); font-size:0.85rem;';
                p.textContent = 'Greška: ' + data.error;
                container.replaceChildren(p);
                return;
            }

            const entries = Object.entries(data);
            if (entries.length === 0) {
                const p = document.createElement('p');
                p.style.cssText = 'color: var(--text-muted); font-size:0.85rem;';
                p.textContent = 'Nema konfiguriranih ključeva. Dodajte prvi ključ gore.';
                container.replaceChildren(p);
                return;
            }

            // Build table using DOM to prevent XSS from server-supplied provider names
            const table = document.createElement('table');
            table.className = 'fleet-table';
            table.innerHTML = '<thead><tr><th>Provajder</th><th>Klju\u010devi</th><th>Akcija</th></tr></thead>';
            const tbody = document.createElement('tbody');

            for (const [prov, keys] of entries) {
                if (keys.length === 0) {
                    const tr = document.createElement('tr');
                    const tdp = document.createElement('td');
                    tdp.className = 'fleet-prov';
                    tdp.textContent = prov;
                    const td2 = document.createElement('td');
                    td2.colSpan = 2;
                    td2.style.color = 'var(--text-muted)';
                    td2.textContent = 'Nema klju\u010deva';
                    tr.append(tdp, td2);
                    tbody.appendChild(tr);
                    continue;
                }
                keys.forEach((masked, idx) => {
                    const tr = document.createElement('tr');
                    const tdp = document.createElement('td');
                    tdp.className = 'fleet-prov';
                    tdp.textContent = idx === 0 ? prov : '';
                    const tdm = document.createElement('td');
                    tdm.style.cssText = 'font-family:monospace; color:var(--text-accent);';
                    tdm.textContent = masked;
                    const tda = document.createElement('td');
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-danger';
                    btn.style.cssText = 'padding:3px 10px; font-size:0.75rem;';
                    btn.textContent = '\uD83D\uDDD1 Obri\u0161i';
                    btn.addEventListener('click', () => deleteApiKey(prov, idx));
                    tda.appendChild(btn);
                    tr.append(tdp, tdm, tda);
                    tbody.appendChild(tr);
                });
            }

            table.appendChild(tbody);
            container.replaceChildren(table);
        })
        .catch(() => {
            const container = document.getElementById('keys-list');
            if (container) {
                const p = document.createElement('p');
                p.style.cssText = 'color: var(--col-danger); font-size:0.85rem;';
                p.textContent = 'Greška pri dohvaćanju ključeva.';
                container.replaceChildren(p);
            }
        });
}

function addApiKey() {
    const provSelect = document.getElementById('key-provider-select');
    const keyInput = document.getElementById('key-input');
    const provider = provSelect ? provSelect.value : '';
    const key = keyInput ? keyInput.value.trim() : '';

    if (!provider) {
        showToast('\u26A0\uFE0F Odaberi provajdera!', 'warning');
        return;
    }
    if (!key) {
        showToast('\u26A0\uFE0F Unesi API ključ!', 'warning');
        return;
    }

    fetch('/api/keys/' + encodeURIComponent(provider), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key })
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                showToast('\u274C ' + d.error, 'error');
                return;
            }
            showToast('\u2705 Klju\u010d dodan za ' + d.provider + ': ' + d.masked, 'success');
            if (keyInput) keyInput.value = '';
            loadApiKeys();
            loadModels();
        })
        .catch(() => showToast('\u274C Gre\u0161ka pri dodavanju klju\u010da.', 'error'));
}

function deleteApiKey(provider, idx) {
    if (!confirm('Obrisati ovaj API ključ?')) return;
    fetch('/api/keys/' + encodeURIComponent(provider) + '/' + idx, {
        method: 'DELETE'
    })
        .then(r => r.json())
        .then(d => {
            if (d.error) {
                showToast('\u274C ' + d.error, 'error');
                return;
            }
            showToast('\u2705 Klju\u010d obrisan za ' + d.provider, 'success');
            loadApiKeys();
            loadModels();
        })
        .catch(() => showToast('\u274C Gre\u0161ka pri brisanju klju\u010da.', 'error'));
}

// -- Drag and Drop za upload --------------------------------------------------
function handleDrop(event) {
    event.preventDefault();
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) dropZone.classList.remove('drag-over');
    const files = event.dataTransfer.files;
    if (files && files.length > 0) {
        uploadBook(files[0]);
    }
}

// Tastatura shortcut-i
document.addEventListener('keydown', e => {
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
