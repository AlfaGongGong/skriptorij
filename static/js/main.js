"use strict";

// ═══════════════════════════════════════════════════════════
// BOOKLYFI TURBO CHARGED — main.js
// Spojeno iz app.js, app-clean.js i svih inline blokova.
// Jedinstveni entry point za frontend.
// ═══════════════════════════════════════════════════════════

// ═══════════════ STATE ══════════════════════════════════
const STATE = {
    step: 1,
    book: null,
    model: "V10_TURBO",
    mode: "FUSION",
    ttsMode: false,
    processing: false,
    paused: false,
    startTime: null,
    lastPct: 0,
    qualityLoaded: false,
    currentPct: 0,
    epubChapters: [],
    epubChapterIdx: 0
};

// ═══════════════ SESSION ══════════════════════════════════
const SESSION_KEY = "bf_session";
function saveSession(d) {
    try {
        localStorage.setItem(
            SESSION_KEY,
            JSON.stringify({ ...d, ts: Date.now() })
        );
    } catch (_) {}
}
function loadSession() {
    try {
        const r = localStorage.getItem(SESSION_KEY);
        if (!r) return null;
        const s = JSON.parse(r);
        if (Date.now() - s.ts > 48 * 3600 * 1000) {
            localStorage.removeItem(SESSION_KEY);
            return null;
        }
        return s;
    } catch (_) {
        return null;
    }
}
function clearSession() {
    localStorage.removeItem(SESSION_KEY);
    clearOverrides();
}
function getOverrides() {
    try {
        return JSON.parse(localStorage.getItem("bf_overrides") || "{}");
    } catch (_) {
        return {};
    }
}
function setOverride(s, v) {
    const o = getOverrides();
    o[s] = v;
    localStorage.setItem("bf_overrides", JSON.stringify(o));
}
function clearOverrides() {
    localStorage.removeItem("bf_overrides");
}

// ═══════════════ HISTORIJA ═══════════════════════════════
const HISTORY_KEY = "bf_history";
const HISTORY_SELECTED = new Set();
function getHistory() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    } catch (_) {
        return [];
    }
}
function saveHistory(h) {
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 20)));
    } catch (_) {}
}

function addHistoryEntry(book, model, avg) {
    const h = getHistory();
    h.unshift({
        book,
        model,
        avg,
        date: new Date().toISOString(),
        id: Date.now()
    });
    saveHistory(h);
    renderHistory();
}

function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function historyEntryId(entry, idx) {
    return String(entry.id ?? `${entry.date || "history"}-${idx}`);
}

function getHistoryWithIds() {
    return getHistory().map((entry, idx) => ({
        ...entry,
        _id: historyEntryId(entry, idx)
    }));
}

function syncHistoryControls(entries = getHistoryWithIds()) {
    const controlsEl = document.getElementById("history-controls");
    const selectAllEl = document.getElementById("history-select-all");
    const selectedCountEl = document.getElementById("history-selected-count");
    const deleteBtn = document.getElementById("btn-history-delete-selected");
    const total = entries.length;
    const selected = entries.filter(entry => HISTORY_SELECTED.has(entry._id)).length;
    if (controlsEl) controlsEl.classList.toggle("hidden", total === 0);
    if (selectAllEl) {
        selectAllEl.disabled = total === 0;
        selectAllEl.checked = total > 0 && selected === total;
        selectAllEl.indeterminate = selected > 0 && selected < total;
    }
    if (deleteBtn) deleteBtn.disabled = selected === 0;
    if (selectedCountEl) {
        selectedCountEl.textContent =
            selected > 0 ? `${selected}/${total} označeno` : `${total} zapisa`;
    }
}

function handleHistorySelectAllChange(e) {
    const checked = Boolean(e?.target?.checked);
    const entries = getHistoryWithIds();
    if (checked) {
        entries.forEach(entry => HISTORY_SELECTED.add(entry._id));
    } else {
        HISTORY_SELECTED.clear();
    }
    document.querySelectorAll("#history-list .history-checkbox").forEach(chk => {
        chk.checked = checked;
        chk.closest(".history-item")?.classList.toggle("selected", checked);
    });
    syncHistoryControls(entries);
}

function handleHistoryDeleteSelectedClick() {
    if (HISTORY_SELECTED.size === 0) return;
    const filtered = getHistory().filter((entry, idx) => {
        const id = historyEntryId(entry, idx);
        return !HISTORY_SELECTED.has(id);
    });
    saveHistory(filtered);
    HISTORY_SELECTED.clear();
    renderHistory();
    showToast("Obrisani označeni zapisi iz historije.", "success");
}

function renderHistory() {
    const listEl = document.getElementById("history-list");
    const emptyEl = document.getElementById("history-empty");
    const selectAllEl = document.getElementById("history-select-all");
    const deleteBtn = document.getElementById("btn-history-delete-selected");
    const h = getHistoryWithIds();

    const validIds = new Set(h.map(entry => entry._id));
    for (const id of Array.from(HISTORY_SELECTED)) {
        if (!validIds.has(id)) HISTORY_SELECTED.delete(id);
    }

    if (!listEl) return;
    if (h.length === 0) {
        HISTORY_SELECTED.clear();
        emptyEl?.classList.remove("hidden");
        listEl.innerHTML = "";
        syncHistoryControls(h);
        return;
    }
    emptyEl?.classList.add("hidden");
    const gradeInfo = avg => {
        if (avg == null) return { cls: "", emoji: "—", text: "Nema podataka" };
        if (avg >= 8.5)
            return {
                cls: "excellent",
                emoji: "🌟",
                text: "Odlično (" + avg.toFixed(1) + "/10)"
            };
        if (avg >= 6.5)
            return {
                cls: "good",
                emoji: "✅",
                text: "Dobro (" + avg.toFixed(1) + "/10)"
            };
        if (avg >= 4.0)
            return {
                cls: "poor",
                emoji: "⚠",
                text: "Treba doradu (" + avg.toFixed(1) + "/10)"
            };
        return {
            cls: "poor",
            emoji: "🔴",
            text: "Slabo (" + avg.toFixed(1) + "/10)"
        };
    };
    listEl.innerHTML = h
        .map(entry => {
            const gi = gradeInfo(entry.avg);
            const d = new Date(entry.date);
            const dateStr =
                d.toLocaleDateString("bs-BA") +
                " " +
                d.toLocaleTimeString("bs-BA", {
                    hour: "2-digit",
                    minute: "2-digit"
                });
            const checked = HISTORY_SELECTED.has(entry._id) ? "checked" : "";
            return `<div class="history-item ${checked ? "selected" : ""}" data-id="${entry._id}">
                <label class="history-select" title="Označi zapis">
                    <input type="checkbox" class="history-checkbox" data-id="${entry._id}" ${checked} />
                </label>
                <div class="history-icon">📘</div>
                <div class="history-info">
                    <div class="history-title">${escapeHtml(entry.book)}</div>
                    <div class="history-meta">${escapeHtml(entry.model)} · ${dateStr}</div>
                </div>
                <div class="history-grade ${gi.cls}" title="${escapeHtml(`${gi.emoji} ${gi.text}`)}">${gi.emoji} ${gi.text}</div>
            </div>`;
        })
        .join("");

    const entriesById = new Map(h.map(entry => [entry._id, entry]));

    listEl.querySelectorAll(".history-checkbox").forEach(chk => {
        chk.addEventListener("click", e => e.stopPropagation());
        chk.addEventListener("change", () => {
            if (chk.checked) HISTORY_SELECTED.add(chk.dataset.id);
            else HISTORY_SELECTED.delete(chk.dataset.id);
            chk.closest(".history-item")?.classList.toggle("selected", chk.checked);
            syncHistoryControls(h);
        });
    });

    listEl.querySelectorAll(".history-item").forEach(item => {
        item.addEventListener("click", e => {
            if (e.target.closest(".history-select")) return;
            const entry = entriesById.get(item.dataset.id);
            if (entry) loadFromHistory(entry.book, entry.model);
        });
    });

    if (selectAllEl) {
        if (!selectAllEl.dataset.listenerBound) {
            selectAllEl.addEventListener("change", handleHistorySelectAllChange);
            selectAllEl.dataset.listenerBound = "1";
        }
    }
    if (deleteBtn) {
        if (!deleteBtn.dataset.listenerBound) {
            deleteBtn.addEventListener("click", handleHistoryDeleteSelectedClick);
            deleteBtn.dataset.listenerBound = "1";
        }
    }
    syncHistoryControls(h);
}

function loadFromHistory(book, model) {
    STATE.book = book;
    STATE.model = model;
    const sel = document.getElementById("book-select");
    if (sel) sel.value = book;
    const msel = document.getElementById("model-select");
    if (msel && Array.from(msel.options).some(o => o.value === model))
        msel.value = model;
    showSetup();
    setWizardStep(2);
    updateSelectedBookDisplay(book);
    showToast("Učitano iz historije: " + book, "info");
}

// ═══════════════ TEMA & TOAST ═══════════════════════════
(function initTheme() {
    const s = localStorage.getItem("bf_theme");
    if (s === "light") {
        document.body.classList.add("light");
    }
    document.getElementById("theme-btn").textContent =
        s === "light" ? "🌙" : "☀";
})();

function toggleTheme() {
    const l = document.body.classList.toggle("light");
    localStorage.setItem("bf_theme", l ? "light" : "dark");
    document.getElementById("theme-btn").textContent = l ? "🌙" : "☀";
    saveAppState();
}

function showToast(msg, type = "info", d = 3500) {
    const tc = document.getElementById("toast-container");
    const t = document.createElement("div");
    t.className = `toast toast-${type}`;
    t.textContent = msg;
    tc.appendChild(t);
    setTimeout(() => {
        t.style.opacity = "0";
        setTimeout(() => t.remove(), 300);
    }, d);
}

// ═══════════════ WIZARD & UI NAVIGACIJA ═════════════════
function setWizardStep(n) {
    STATE.step = n;
    document
        .getElementById("wizard-page-1")
        ?.classList.toggle("hidden", n !== 1);
    document
        .getElementById("wizard-page-2")
        ?.classList.toggle("hidden", n !== 2);
    const step1 = document.getElementById("step-1");
    const step2 = document.getElementById("step-2");
    if (step1) {
        step1.classList.toggle("active", n === 1);
        step1.classList.toggle("done", n > 1);
    }
    if (step2) {
        step2.classList.toggle("active", n === 2);
    }
}

function wizardNext() {
    const book = document.getElementById("book-select")?.value;
    if (!book) {
        showToast("Odaberi ili učitaj knjigu!", "warning");
        return;
    }
    STATE.book = book;
    localStorage.setItem("bf_last_book", book);
    updateSelectedBookDisplay(book);
    setWizardStep(2);
    saveAppState();
}

function wizardBack() {
    setWizardStep(1);
    saveAppState();
}

function updateSelectedBookDisplay(name) {
    const el = document.getElementById("selected-book-name");
    if (el) el.textContent = name || "—";
}

function showSetup() {
    document.getElementById("setup-panel")?.classList.remove("hidden");
    document.getElementById("dashboard-panel")?.classList.add("hidden");
    saveAppState();
    _updateReturnToDashboardBtn();
}

function showDashboard(startPolling = true) {
    document.getElementById("setup-panel")?.classList.add("hidden");
    document.getElementById("dashboard-panel")?.classList.remove("hidden");
    if (startPolling) startDashboardPolling();
    saveAppState();
}

async function _updateReturnToDashboardBtn() {
    let existing = document.getElementById("btn-return-dashboard");
    try {
        const resp = await fetch("/api/status");
        const s = await resp.json();
        const active =
            s &&
            s.pct > 0 &&
            s.pct < 100 &&
            s.status !== "IDLE" &&
            s.status !== "ZAUSTAVLJENO";
        if (active) {
            if (!existing) {
                const btn = document.createElement("button");
                btn.id = "btn-return-dashboard";
                btn.className = "btn btn-primary";
                btn.style.cssText = "width:100%;margin-bottom:12px";
                btn.textContent = "🔙 Vrati na Dashboard (obrada u toku)";
                const setupPanel = document.getElementById("setup-panel");
                if (setupPanel)
                    setupPanel.insertBefore(btn, setupPanel.firstChild);
            } else {
                existing.style.display = "";
            }
        } else {
            if (existing) existing.style.display = "none";
        }
    } catch (_) {
        if (existing) existing.style.display = "none";
    }
}

function onBookChange(val) {
    STATE.book = val;
    if (val) localStorage.setItem("bf_last_book", val);
}

// TTS mode
function selectTTSMode() {
    STATE.ttsMode = true;
    document.getElementById("tts-panel")?.classList.remove("hidden");
    document.getElementById("auto-mode-display").style.opacity = "0.4";
    showToast("TTS mod aktiviran", "info");
}

function cancelTTSMode() {
    STATE.ttsMode = false;
    document.getElementById("tts-panel")?.classList.add("hidden");
    document.getElementById("auto-mode-display").style.opacity = "";
}

// Tier filter
const TIER_MAP = {
    fast: ["CEREBRAS", "GROQ", "SAMBANOVA"],
    quality: ["GEMINI", "MISTRAL", "COHERE"],
    free: [
        "V12_TURBO",
        "OPENROUTER",
        "TOGETHER",
        "FIREWORKS",
        "CHUTES",
        "HUGGINGFACE",
        "KLUSTER",
        "GEMMA"
    ]
};

function filterTier(tier) {
    const btn = document.querySelector(`.tier-pill[data-tier="${tier}"]`);
    if (!btn) return;
    document
        .querySelectorAll(".tier-pill")
        .forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const sel = document.getElementById("model-select");
    if (!sel) return;
    const allowed = TIER_MAP[tier];
    Array.from(sel.options).forEach(opt => {
        if (!opt.value) return;
        opt.hidden = allowed
            ? !allowed.some(t => opt.value.toUpperCase().includes(t))
            : false;
    });
}

// ═══════════════ UPLOAD ═════════════════════════════════
function triggerUpload() {
    document.getElementById("file-input")?.click();
}

(function setupUpload() {
    const zone = document.getElementById("upload-zone");
    const input = document.getElementById("file-input");
    const status = document.getElementById("upload-status");
    if (!zone || !input) return;
    input.addEventListener("change", () => {
        if (input.files[0]) doUpload(input.files[0]);
    });
    zone.addEventListener("dragover", e => {
        e.preventDefault();
        zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () =>
        zone.classList.remove("drag-over")
    );
    zone.addEventListener("drop", e => {
        e.preventDefault();
        zone.classList.remove("drag-over");
        if (e.dataTransfer.files[0]) doUpload(e.dataTransfer.files[0]);
    });
    async function doUpload(file) {
        const ext = file.name.split(".").pop().toLowerCase();
        if (!["epub", "mobi"].includes(ext)) {
            showToast("Podržani formati: EPUB, MOBI", "error");
            return;
        }
        status.textContent = `⏳ Učitavam: ${file.name}…`;
        status.style.color = "var(--tx-2)";
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await fetch("/api/upload_book", {
                method: "POST",
                body: fd
            });
            const d = await r.json();
            if (d.error) throw new Error(d.error);
            status.textContent = `✅ ${d.name || file.name}`;
            status.style.color = "var(--emerald)";
            showToast(`"${d.name || file.name}" uspješno učitana!`, "success");
            document
                .getElementById("guide-after-upload")
                ?.classList.remove("hidden");
            await loadBooks();
            const sel = document.getElementById("book-select");
            if (sel) {
                sel.value = d.name || file.name;
                STATE.book = sel.value;
            }
        } catch (e) {
            status.textContent = `❌ ${e.message}`;
            status.style.color = "var(--rose)";
            showToast("Upload nije uspio: " + e.message, "error");
        }
    }
})();

async function loadBooks() {
    const sel = document.getElementById("book-select");
    if (!sel) return;
    try {
        let files = [];
        try {
            const r = await fetch("/api/books");
            const d = await r.json();
            files = d.books ? d.books.map(b => b.name || b) : d.files || [];
        } catch (_) {
            const r2 = await fetch("/api/files");
            const d2 = await r2.json();
            files = d2.files || [];
        }
        const last = localStorage.getItem("bf_last_book");
        sel.innerHTML = '<option value="">— Odaberi knjigu —</option>';
        files.forEach(f => {
            const name = typeof f === "string" ? f : f.name || f.path || f;
            const path = typeof f === "string" ? f : f.path || f.name || f;
            sel.appendChild(new Option(name, path));
        });
        if (last && Array.from(sel.options).some(o => o.value === last)) {
            sel.value = last;
            STATE.book = last;
        }
    } catch (_) {}
}

async function loadModels() {
    const sel = document.getElementById("model-select");
    if (!sel) return;
    try {
        const r = await fetch("/api/dev_models");
        const models = await r.json();
        sel.innerHTML = "";
        (models || []).forEach(m => sel.appendChild(new Option(m, m)));
        if (sel.options.length > 0) {
            sel.value =
                Array.from(sel.options).find(o => o.value.includes("TURBO"))
                    ?.value || sel.options[0].value;
            STATE.model = sel.value;
        }
    } catch (_) {
        sel.innerHTML = '<option value="V10_TURBO">V10_TURBO</option>';
    }
}

// ═══════════════ POKRETANJE ═════════════════════════════
async function startProcessing() {
    const book = STATE.book || document.getElementById("book-select")?.value;
    const model = document.getElementById("model-select")?.value || STATE.model;
    const mode = STATE.ttsMode ? "TTS" : "FUSION";

    if (!book) {
        showToast("Odaberi ili učitaj knjigu!", "warning");
        setWizardStep(1);
        return;
    }
    if (!model) {
        showToast("Odaberi model!", "warning");
        return;
    }
    clearOverrides();
    const btn = document.getElementById("btn-start");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳ Pokrećem…";
    }
    try {
        const r = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ book, model, mode })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        STATE.processing = true;
        STATE.paused = false;
        STATE.startTime = Date.now();
        STATE.lastPct = 0;
        saveSession({ book, model, mode, status: "POKRETANJE..." });
        showDashboard();
        showToast(`Pokrenuto: ${book} [${model}]`, "success");
        updateControlBtns();
        STATE.qualityLoaded = false;
        document.getElementById("quality-content")?.classList.add("hidden");
        document.getElementById("quality-loading")?.classList.remove("hidden");
        if (document.getElementById("quality-loading"))
            document.getElementById("quality-loading").textContent =
                "Obrada u toku — ocjene se generišu...";
    } catch (e) {
        showToast("Greška: " + e.message, "error");
        if (btn) {
            btn.disabled = false;
            btn.textContent = "🚀 Pokreni";
        }
    }
}

async function sendControl(action) {
    if (action === "reset") {
        const book =
            STATE.book || document.getElementById("book-select")?.value || "";
        const btn = document.getElementById("btn-reset");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "⏳ Resetujem...";
        }
        fetch("/api/reset_full", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ book })
        })
            .then(r => r.json())
            .then(d => {
                if (d.error) {
                    showToast("Reset greška: " + d.error, "error");
                } else {
                    stopDashboardPolling();
                    stopQualityPolling();
                    STATE.processing = false;
                    STATE.paused = false;
                    STATE.startTime = null;
                    clearSession();
                    showSetup();
                    showToast(
                        d.reset?.obrisano_dir
                            ? "🗑️ Reset završen — checkpointi obrisani."
                            : "🔄 Reset završen.",
                        "success"
                    );
                }
            })
            .catch(e => showToast("Reset greška: " + e.message, "error"))
            .finally(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = "🔄 Reset";
                }
            });
        return;
    }

    // Ostale kontrole
    try {
        await fetch(`/control/${action}`, { method: "POST" });
        if (action === "pause") STATE.paused = true;
        if (action === "resume") STATE.paused = false;
        if (action === "stop") {
            STATE.processing = false;
            clearSession();
            stopDashboardPolling();
        }
        updateControlBtns();
        if (action === "stop" || action === "reset") {
            stopQualityPolling();
        }
    } catch (e) {
        showToast("Greška: " + e.message, "error");
    }
}

function updateControlBtns() {
    const btnPause = document.getElementById("btn-pause");
    const btnResume = document.getElementById("btn-resume");
    if (btnPause) btnPause.classList.toggle("hidden", STATE.paused);
    if (btnResume) btnResume.classList.toggle("hidden", !STATE.paused);
}

// ═══════════════ POLLING ═══════════════════════════════
let _pollTimer = null;
function startDashboardPolling() {
    if (_pollTimer) clearInterval(_pollTimer);
    _pollTimer = setInterval(pollStatus, 2000);
    pollStatus();
    pollFleet();
}
function stopDashboardPolling() {
    if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
    }
}

let _qualityPollTimer = null;
function startQualityPolling() {
    if (_qualityPollTimer) return;
    _qualityPollTimer = setInterval(loadQualityScores, 15000);
}
function stopQualityPolling() {
    if (_qualityPollTimer) {
        clearInterval(_qualityPollTimer);
        _qualityPollTimer = null;
    }
}

async function pollStatus() {
    try {
        const r = await fetch("/api/status");
        if (!r.ok) return;
        const d = await r.json();
        updateStatus(d);
    } catch (_) {}
}

async function pollFleet() {
    try {
        const r = await fetch("/api/fleet");
        if (!r.ok) return;
        const d = await r.json();
        renderFleet(d);
    } catch (_) {}
}

// ═══════════════ STATUS UPDATE ═════════════════════════
let _auditAutoScroll = true;

function auditResumeScroll() {
    _auditAutoScroll = true;
    const log = document.getElementById("audit-log");
    if (log) log.scrollTop = log.scrollHeight;
    const ind = document.getElementById("audit-scroll-indicator");
    if (ind) ind.style.display = "none";
}

function setVal(id, val) {
    const el = document.getElementById(id);
    if (el && el.textContent !== String(val)) el.textContent = val;
}

function updateStatus(s) {
    if (!s) return;
    const st = (s.status || "IDLE").toUpperCase();
    const dot = document.getElementById("status-dot");
    const txt = document.getElementById("status-text");
    const logo = document.getElementById("brand-logo");

    if (dot) {
        dot.className = "dot";
        if (st.includes("TOKU") || st.includes("POKRETANJE")) {
            dot.classList.add("dot-active");
            logo?.classList.add("engine-active");
        } else if (st === "PAUZIRANO") {
            dot.classList.add("dot-paused");
            logo?.classList.remove("engine-active");
        } else if (st.includes("GREŠKA")) {
            dot.classList.add("dot-error");
            logo?.classList.remove("engine-active");
        } else {
            dot.classList.add("dot-idle");
            logo?.classList.remove("engine-active");
        }
    }

    const statusLabels = {
        IDLE: "SPREMAN",
        POKRETANJE: "POKRETANJE...",
        ZAUSTAVLJENO: "ZAUSTAVLJENO",
        PAUZIRANO: "PAUZIRANO"
    };
    if (txt) txt.textContent = statusLabels[st] || st;

    if (STATE.processing || st.includes("TOKU") || st.includes("POKRETANJE"))
        saveSession({
            book: s.current_file || STATE.book,
            model: s.active_engine || STATE.model,
            status: st,
            pct: s.pct || 0
        });
    if (st === "IDLE" || st === "ZAUSTAVLJENO" || st.includes("ZAVRŠEN")) {
        clearSession();
        if (st.includes("ZAVRŠEN") && STATE.book) {
            const scores = s.quality_scores || {};
            const vals = Object.values(scores);
            const avg =
                vals.length > 0
                    ? vals.reduce((a, b) => a + b, 0) / vals.length
                    : null;
            addHistoryEntry(STATE.book, STATE.model || "—", avg);
        }
    }

    setVal("stat-engine", s.active_engine || "---");
    // FIX 1.2 — truncate long filename, show full in tooltip
    (function () {
        const raw = s.current_file || "---";
        if (s.current_file) window._currentBook = s.current_file;
        const el = document.getElementById("stat-file");
        if (!el) return;
        el.textContent =
            raw.length > 26 ? raw.slice(0, 11) + "…" + raw.slice(-11) : raw;
        el.title = raw;
        el.style.cssText +=
            ";overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%;display:block;";
    })();
    setVal("stat-ok", s.ok || "0 / 0");
    setVal("stat-skipped", s.skipped || "0");
    setVal("stat-fleet-active", s.fleet_active || "0");

    const scores = s.quality_scores || {};
    const overrides = getOverrides();
    for (const [stem, ostatus] of Object.entries(overrides)) {
        if (ostatus === "deleted") delete scores[stem];
        else if (ostatus === "fixed" && scores[stem] !== undefined)
            scores[stem] = 10.0;
    }
    const vals = Object.values(scores);
    if (vals.length > 0) {
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        const avgEl = document.getElementById("stat-avg-quality");
        if (avgEl) {
            let label;
            if (avg >= 8.5) label = "🌟 Odlično";
            else if (avg >= 6.5) label = "✅ Dobro";
            else if (avg >= 4) label = "⚠ Treba retro";
            else label = "🔴 Slabo";
            avgEl.textContent = label;
            avgEl.style.color =
                avg >= 8.5
                    ? "var(--emerald)"
                    : avg >= 6.5
                      ? "var(--accent-2)"
                      : avg >= 4
                        ? "var(--amber)"
                        : "var(--rose)";
        }
    }

    const pct = Math.min(100, Math.max(0, s.pct || 0));
    STATE.currentPct = pct;
    const bar = document.getElementById("progress-bar");
    if (bar) bar.style.width = pct + "%";
    setVal("progress-pct-text", `Završeno: ${pct}%`);
    if (STATE.startTime && pct > 0 && pct < 100) {
        const elapsed = (Date.now() - STATE.startTime) / 1000;
        const eta = elapsed / (pct / 100) - elapsed;
        document.getElementById("progress-eta").textContent =
            `ETA: ${fmtTime(eta)} | ⏱ ${fmtTime(elapsed)}`;
    } else if (s.est) {
        document.getElementById("progress-eta").textContent = `ETA: ${s.est}`;
    }
    updatePipeline(st, pct);

    // ── Relektura banner ───────────────────────────────────────────────────
    (function () {
        const banner = document.getElementById("qs-relektura-banner");
        if (!banner) return;
        const refixScores = s.refix_scores || {};
        const refixActive = !!s.refix_active;
        const vals = Object.values(refixScores).filter(v => typeof v === "number");
        if (refixActive || vals.length > 0) {
            const avgEl = document.getElementById("qs-relektura-avg");
            const countEl = document.getElementById("qs-relektura-count");
            const labelEl = document.getElementById("qs-relektura-label");
            const iconEl = document.getElementById("qs-relektura-status-icon");
            if (vals.length > 0) {
                const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
                if (avgEl) avgEl.textContent = avg.toFixed(1) + "/10";
                // Pluralizacija za bosanski/hrvatski: 1→blok, 2-4→bloka, 0/5+→blokova
                const n = vals.length;
                const suffix = n === 1 ? "blok" : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) ? "bloka" : "blokova";
                if (countEl) countEl.textContent = n + " " + suffix + " završeno";
            }
            if (refixActive) {
                if (labelEl) labelEl.textContent = "Relektura u toku…";
                if (iconEl) iconEl.textContent = "🔄";
            } else {
                if (labelEl) labelEl.textContent = "Relektura završena";
                if (iconEl) iconEl.textContent = "✅";
            }
            banner.style.display = "flex";
            // Ažuriraj quality-badge da pokazuje relektura progres
            const qualBadge = document.getElementById("quality-badge");
            if (qualBadge && refixActive) {
                qualBadge.textContent = vals.length;
                qualBadge.classList.remove("hidden");
            }
        } else {
            banner.style.display = "none";
        }
    })();

    if (s.live_audit) {
        updateAuditLog(s.live_audit);
        extractPreview(s.live_audit);
    }

    const km = s.knjiga_mode;
    if (km) {
        const icons = {
            PREVOD: "🌐",
            LEKTURA: "✍️",
            "AUTO-RETRO": "🔁",
            FUSION: "⚡",
            TTS: "🔊"
        };
        const descs = {
            PREVOD: "Prevod: EN → BS/HR",
            LEKTURA: "Samo lektura",
            "AUTO-RETRO": "Auto re-lektura loših blokova",
            FUSION: "Prevod + lektura u jednom prolazu",
            TTS: "TTS filter mod"
        };
        setVal("auto-mode-icon", icons[km] || "🤖");
        setVal("auto-mode-label", km);
        setVal("auto-mode-desc", descs[km] || "Sistem određuje mod");
    }

    const isFinished =
        pct >= 100 ||
        st === "ZAUSTAVLJENO" ||
        st === "IDLE" ||
        st.includes("ZAVRŠEN");
    const hasOutput = !!s.output_file;
    const strip = document.getElementById("download-strip");
    if (strip) {
        if (hasOutput || (!isFinished && pct > 5)) {
            strip.classList.remove("hidden");
            const titleEl = document.getElementById("download-strip-title");
            const subtitleEl = document.getElementById(
                "download-strip-subtitle"
            );
            const finalBtn = document.getElementById("btn-download-final");
            if (hasOutput && isFinished) {
                titleEl.textContent = "✅ Prijevod završen!";
                subtitleEl.textContent = "EPUB je spreman za preuzimanje";
                strip.style.borderColor = "rgba(16,185,129,0.3)";
                strip.style.background =
                    "linear-gradient(135deg,rgba(16,185,129,0.1),rgba(6,182,212,0.1))";
                finalBtn?.classList.remove("hidden");
                loadEpubPreview();
            } else if (!isFinished && pct > 5) {
                titleEl.textContent = `⏳ U toku — ${pct}%`;
                subtitleEl.textContent = "Djelimičan pregled dostupan";
                strip.style.borderColor = "rgba(245,158,11,0.3)";
                strip.style.background = "rgba(245,158,11,0.06)";
                finalBtn?.classList.add("hidden");
            }
        } else {
            strip.classList.add("hidden");
        }
    }

    const engineActive =
        st !== "IDLE" &&
        st !== "ZAUSTAVLJENO" &&
        !st.includes("GREŠKA") &&
        pct < 100;
    if (engineActive) {
        startQualityPolling();
    } else {
        stopQualityPolling();
        if (pct >= 100 || st === "ZAUSTAVLJENO" || st === "IDLE") {
            if (st !== "OBRADA U TOKU..." && st !== "POKRETANJE...") {
                STATE.processing = false;
                stopDashboardPolling();
            }
        }
    }

    if (pct >= 100 || st === "ZAUSTAVLJENO" || st === "IDLE") {
        STATE.processing = false;
        const btn = document.getElementById("btn-start");
        if (btn) {
            btn.disabled = false;
            btn.textContent = "🚀 Pokreni";
        }
    }
}

function _auditClass(text) {
    // Određuje CSS klasu i badge na osnovu sadržaja log retka
    const t = text || "";
    if (/GREŠKA|❌|ERROR|kritično/i.test(t))   return { cls: "log-critical", badge: "ERR" };
    if (/UPOZ|⚠️|halucinacij|pala|nije obrađen/i.test(t)) return { cls: "log-warning", badge: "UPZ" };
    if (/✅|uspješno|završen.*GEMINI|završen.*GROQ|završen.*MISTRAL|završen.*CEREBRAS|završen.*SAMBANOVA/i.test(t)) return { cls: "log-success", badge: "OK" };
    if (/score\s*=\s*([89](\.\d+)?|10)/i.test(t)) return { cls: "log-score-good", badge: "SCR" };
    if (/score\s*=\s*[67](\.\d+)?/i.test(t))      return { cls: "log-score-mid",  badge: "SCR" };
    if (/score\s*=\s*[0-5](\.\d+)?/i.test(t))     return { cls: "log-score-bad",  badge: "SCR" };
    if (/^\s*(SYS|📄|📖|🔍|🚀|📁)/m.test(t))    return { cls: "log-system",  badge: "SYS" };
    if (/^\s*(NET|📦|🔀|🌐|Parallel|Blok\s\d)/m.test(t)) return { cls: "log-tech", badge: "NET" };
    return { cls: "log-info", badge: "INF" };
}

function _parseAuditTime(div) {
    // Izvlači timestamp ako postoji (format HH:MM:SS)
    const m = div.match(/^(\d{2}:\d{2}:\d{2})/);
    return m ? m[1] : "";
}

function updateAuditLog(html) {
    const log = document.getElementById("audit-log");
    if (!log) return;

    // Parsiramo svaki <div ...> kao log entry
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const entries = doc.body.querySelectorAll("div");

    if (entries.length === 0) {
        log.innerHTML = html;
        if (_auditAutoScroll) log.scrollTop = log.scrollHeight;
        return;
    }

    let output = "";
    entries.forEach(el => {
        const raw = el.innerHTML || "";
        const text = el.textContent || "";
        const { cls, badge } = _auditClass(text);
        const time = _parseAuditTime(text.trim());
        // Ukloni timestamp i kategorijski prefiks iz poruke
        const _prefixes = ["GREŠKA", "UPOZ", "SYS", "NET", "INF", "ERR", "UPZ", "OK", "SCR"];
        let msgHtml = time ? raw.replace(time, "") : raw;
        // Ukloni poznate tekstualne prefikse na početku
        msgHtml = msgHtml.replace(
            /^\s*(GREŠKA|UPOZ|SYS|NET|GREŠKAGREŠKA|UPOZUPOZ|SYSSYS|NETNET)\s*/,
            ""
        ).trim();
        output += `<div class='log-entry ${cls}'>` +
            `<span class='log-time'>${time}</span>` +
            `<span class='log-badge'>${badge}</span>` +
            `<span class='log-msg'>${msgHtml}</span>` +
            `</div>`;
    });

    log.innerHTML = output;
    if (_auditAutoScroll) log.scrollTop = log.scrollHeight;
}

function extractPreview(html) {
    // FIX 1.1 — vise paterna, fallback, nikad ne skriva ako ima sadrzaja
    const block = document.getElementById("live-preview-block");
    const enEl = document.getElementById("preview-en");
    const hrEl = document.getElementById("preview-hr");
    if (!block || !enEl || !hrEl) return;

    // Skini HTML tagove, normaliziraj whitespace
    const flat = html
        .replace(/<[^>]+>/g, " ")
        .replace(/\s+/g, " ")
        .trim();

    let mEn = null,
        mHr = null;

    // Patern A — EN: ... HR:/BS: ...
    const pA = flat.match(/EN:\s*(.{5,220}?)(?=(?:HR|BS|BHS):|$)/i);
    const pB = flat.match(/(?:HR|BS|BHS):\s*(.{5,220}?)(?=EN:|\[|$)/i);
    if (pA) mEn = pA[1].trim().slice(0, 200);
    if (pB) mHr = pB[1].trim().slice(0, 200);

    // Patern B — [ORIGINAL] / [PRIJEVOD]
    if (!mEn || !mHr) {
        const pC = flat.match(/\[ORIGINAL\]\s*(.{5,220}?)(?=\[|$)/i);
        const pD = flat.match(/\[PRIJEVOD\]\s*(.{5,220}?)(?=\[|$)/i);
        if (pC) mEn = pC[1].trim().slice(0, 200);
        if (pD) mHr = pD[1].trim().slice(0, 200);
    }

    // Patern C — strelica →  (samo prijevod bez originala)
    if (!mHr) {
        const pE = flat.match(
            /\u2192\s*([A-Z\u0160\u0110\u010c\u0106\u017d\"\'][^\u2192]{10,200})/
        );
        if (pE) mHr = pE[1].trim().slice(0, 200);
    }

    // Patern D — zadnji log entry koji ima vise od 20 slova BHS abecede
    if (!mHr) {
        const pF = flat.match(
            /([A-Z\u0160\u0110\u010c\u0106\u017da-z\u0161\u0111\u010d\u0107\u017e ,.!?]{20,200})\s*$/
        );
        if (pF) mHr = pF[1].trim().slice(0, 200);
    }

    if (mEn) enEl.textContent = mEn;
    if (mHr) hrEl.textContent = mHr;

    // Prikazi blok ako ima BILO STA korisnog
    block.style.display = mEn || mHr ? "grid" : "none";

    // Sakrij EN box ako nema originala; pokaži ga i prilagodi grid ako ima
    const enBox = document.getElementById("preview-en-box");
    if (enBox) {
        enBox.style.display = mEn ? "" : "none";
        block.style.gridTemplateColumns = mEn ? "1fr 1fr" : "1fr";
    }
}

function fmtTime(s) {
    if (!s || s < 0) return "--:--:--";
    const h = Math.floor(s / 3600),
        m = Math.floor((s % 3600) / 60),
        ss = Math.floor(s % 60);
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

function updatePipeline(status, pct) {
    const steps = [
        "pipe-analiza",
        "pipe-prevod",
        "pipe-lektor",
        "pipe-korektor",
        "pipe-gotovo"
    ];
    steps.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove("active", "done");
    });
    if (pct >= 100) {
        steps.forEach(id => document.getElementById(id)?.classList.add("done"));
        return;
    }
    if (status.includes("ANALIZ")) {
        document.getElementById("pipe-analiza")?.classList.add("active");
    } else if (pct < 30) {
        document.getElementById("pipe-analiza")?.classList.add("done");
        document.getElementById("pipe-prevod")?.classList.add("active");
    } else if (pct < 60) {
        ["pipe-analiza", "pipe-prevod"].forEach(id =>
            document.getElementById(id)?.classList.add("done")
        );
        document.getElementById("pipe-lektor")?.classList.add("active");
    } else if (pct < 85) {
        ["pipe-analiza", "pipe-prevod", "pipe-lektor"].forEach(id =>
            document.getElementById(id)?.classList.add("done")
        );
        document.getElementById("pipe-korektor")?.classList.add("active");
    } else {
        ["pipe-analiza", "pipe-prevod", "pipe-lektor", "pipe-korektor"].forEach(
            id => document.getElementById(id)?.classList.add("done")
        );
        document.getElementById("pipe-gotovo")?.classList.add("active");
    }
}

// ═══════════════ SAVE APP STATE ═══════════════════════
function saveAppState() {
    try {
        const s = {
            book: document.getElementById("book-select")?.value || "",
            model: document.getElementById("model-select")?.value || "",
            mode:
                document.querySelector('input[name="mode"]:checked')?.value ||
                "FUSION",
            step2: !(
                document
                    .getElementById("wizard-page-2")
                    ?.classList.contains("hidden") ?? true
            ),
            dashboard: !(
                document
                    .getElementById("dashboard-panel")
                    ?.classList.contains("hidden") ?? true
            ),
            theme: document.body.classList.contains("light") ? "light" : "dark"
        };
        localStorage.setItem("bf_state", JSON.stringify(s));
    } catch (_) {}
}

function restoreAppState() {
    try {
        const raw = localStorage.getItem("bf_state");
        if (!raw) return;
        const s = JSON.parse(raw);
        if (s.theme === "light") document.body.classList.add("light");
        const check = setInterval(function () {
            const bs = document.getElementById("book-select");
            const ms = document.getElementById("model-select");
            if (bs && bs.options.length > 1 && ms && ms.options.length > 0) {
                if (
                    s.book &&
                    Array.from(bs.options).some(o => o.value === s.book)
                )
                    bs.value = s.book;
                if (
                    s.model &&
                    Array.from(ms.options).some(o => o.value === s.model)
                )
                    ms.value = s.model;
                if (s.mode) {
                    const r = document.querySelector(
                        `input[name="mode"][value="${s.mode}"]`
                    );
                    if (r) r.checked = true;
                }
                if (s.step2) {
                    setWizardStep(2);
                }
                clearInterval(check);
            }
        }, 200);
        setTimeout(() => clearInterval(check), 10000);
    } catch (_) {}
}

// ═══════════════ FLEET ═════════════════════════════════
const PROV_ICONS = {
    GEMINI: "♊",
    GROQ: "⚡",
    CEREBRAS: "🔬",
    SAMBANOVA: "🧠",
    MISTRAL: "💫",
    COHERE: "🌐",
    OPENROUTER: "🔀",
    GITHUB: "🐙",
    TOGETHER: "🤝",
    FIREWORKS: "🎆",
    CHUTES: "🪣",
    HUGGINGFACE: "🤗",
    KLUSTER: "🔗",
    GEMMA: "🔷"
};

function updateExpertFleetHealthBadge(totalActive, totalKeys) {
    const badge = document.getElementById("expert-fleet-health-badge");
    if (!badge) return;

    if (!totalKeys) {
        badge.classList.remove("has-data");
        const ring = badge.querySelector(".ql-ring");
        const mainEl = badge.querySelector(".ql-score-main");
        const subEl = badge.querySelector(".ql-score-sub");
        if (ring) {
            ring.style.setProperty("--ql-pct", "0%");
            ring.style.background =
                "conic-gradient(var(--accent-2) 0% 0%, var(--bg-3) 0%)";
            ring.setAttribute("data-val", "—");
        }
        if (mainEl) mainEl.textContent = "—";
        if (subEl) subEl.textContent = "zdravlje flote";
        return;
    }

    const pct = Math.round((totalActive / totalKeys) * 100);
    const color =
        pct >= 80
            ? "var(--emerald)"
            : pct >= 60
              ? "var(--accent-2)"
              : pct >= 35
                ? "var(--amber)"
                : "var(--rose)";
    const ring = badge.querySelector(".ql-ring");
    const mainEl = badge.querySelector(".ql-score-main");
    const subEl = badge.querySelector(".ql-score-sub");
    if (ring) {
        ring.style.setProperty("--ql-pct", `${pct}%`);
        ring.style.background = `conic-gradient(${color} 0% ${pct}%, var(--bg-3) 0%)`;
        ring.setAttribute("data-val", String(pct));
    }
    if (mainEl) mainEl.textContent = `${pct}%`;
    if (subEl) subEl.textContent = `${totalActive}/${totalKeys} aktivno`;
    badge.classList.add("has-data");
}

function renderFleet(data) {
    const c = document.getElementById("fleet-cards-container");
    const simpleOk = document.getElementById("fleet-ok-count");
    const simpleCol = document.getElementById("fleet-cooling-count");
    const simpleErr = document.getElementById("fleet-err-count");
    if (!c) return;
    const entries = Object.entries(data || {});
    if (entries.length === 0) {
        updateExpertFleetHealthBadge(0, 0);
        c.innerHTML =
            '<div style="text-align:center;padding:24px;color:var(--tx-3);font-size:0.75rem">Nema provajdera u floti.</div>';
        return;
    }
    let totalActive = 0,
        totalKeys = 0,
        totalCooling = 0,
        totalErr = 0;
    let html = "";
    for (const [prov, info] of entries) {
        const active = info.active || 0,
            total = info.total || 0,
            keys = info.keys || [];
        totalActive += active;
        totalKeys += total;
        keys.forEach(k => {
            if (!k.available && !k.disabled && k.cooldown_remaining > 0)
                totalCooling++;
        });
        keys.forEach(k => {
            if (k.errors && k.errors > 0 && !k.available) totalErr++;
        });
        const pct = total > 0 ? Math.round((active / total) * 100) : 0;
        const barCls = pct >= 60 ? "good" : pct >= 30 ? "warn" : "low";
        const icon = PROV_ICONS[prov.toUpperCase()] || "🔑";
        html += `<div class="fleet-provider">
            <div class="fleet-provider-header">
                <span>${icon}</span>
                <span style="flex:1;font-weight:600">${prov}</span>
                <div class="fleet-health-bar"><div class="fleet-health-fill ${barCls}" style="width:${pct}%"></div></div>
                <span style="font-family:var(--font-mono);font-size:0.7rem;margin-left:6px">${active}/${total}</span>
            </div>
        </div>`;
    }
    c.innerHTML = html;
    if (simpleOk) simpleOk.textContent = totalActive;
    if (simpleCol) simpleCol.textContent = totalCooling;
    if (simpleErr) simpleErr.textContent = totalErr;
    document.getElementById("fleet-total-count").textContent = totalActive;
    updateExpertFleetHealthBadge(totalActive, totalKeys);

    // Render detailed fleet view in expert tab
    const expertC = document.getElementById("expert-fleet-container");
    if (expertC) {
        if (entries.length === 0) {
            expertC.innerHTML = '<div style="text-align:center;padding:20px;color:var(--tx-3)">Nema provajdera u floti.</div>';
        } else {
            let expertHtml = "";
            for (const [prov, info] of entries) {
                const keys = info.keys || [];
                const active = info.active || 0;
                const total = info.total || 0;
                const pct = total > 0 ? Math.round((active / total) * 100) : 0;
                const barCls = pct >= 60 ? "good" : pct >= 30 ? "warn" : "low";
                const icon = PROV_ICONS[prov.toUpperCase()] || "🔑";
                const keyPills = keys.map(k => {
                    const available = k.available && !k.disabled;
                    const cooling = !k.available && !k.disabled && k.cooldown_remaining > 0;
                    const disabled = k.disabled;
                    let cls = "ok", label = `✓ ${k.masked}`, extra = "";
                    if (disabled) { cls = "off"; label = `○ ${k.masked}`; }
                    else if (cooling) { cls = "warn"; label = `⏳ ${k.masked}`; extra = `<span style="font-size:0.65rem;opacity:0.7">${Math.ceil(k.cooldown_remaining)}s</span>`; }
                    else if (!available) { cls = "err"; label = `✕ ${k.masked}`; }
                    const healthStr = k.health != null ? `<span style="font-size:0.65rem;opacity:0.6">${k.health}%</span>` : "";
                    return `<span class="key-pill ${cls}" data-prov="${prov}" data-key="${k.masked}">${label}${healthStr}${extra}</span>`;
                }).join("");
                expertHtml += `<div class="fleet-provider" style="margin-bottom:6px;border-radius:var(--r-md);overflow:hidden;border:1px solid var(--bd)">
                    <div class="fleet-provider-header">
                        <span>${icon}</span>
                        <span style="flex:1;font-weight:600">${prov}</span>
                        <div class="fleet-health-bar"><div class="fleet-health-fill ${barCls}" style="width:${pct}%"></div></div>
                        <span style="font-family:var(--font-mono);font-size:0.7rem;margin-left:6px">${active}/${total}</span>
                    </div>
                    ${keys.length > 0 ? `<div class="fleet-keys-grid">${keyPills}</div>` : ""}
                </div>`;
            }
            expertC.innerHTML = expertHtml;
            expertC.querySelectorAll(".key-pill[data-prov]").forEach(pill => {
                pill.addEventListener("click", () => {
                    toggleKey(pill.dataset.prov, pill.dataset.key);
                });
            });
        }
    }
}

async function toggleKey(provider, key) {
    try {
        const r = await fetch("/api/fleet/toggle", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider, key })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast(
            `${provider}: ${d.disabled ? "🔴 onemogućen" : "🟢 aktiviran"}`,
            d.disabled ? "warning" : "success"
        );
        pollFleet();
    } catch (e) {
        showToast("Toggle greška: " + e.message, "error");
    }
}

async function loadKeys() {
    const container = document.getElementById("keys-list-container");
    if (!container) return;
    try {
        const r = await fetch("/api/keys");
        const data = await r.json();
        const entries = Object.entries(data || {});
        if (entries.length === 0) {
            container.innerHTML =
                '<div style="color:var(--tx-3)">Nema unesenih API ključeva.</div>';
            return;
        }
        let html = "";
        entries.forEach(([prov, keys]) => {
            (keys || []).forEach((masked, idx) => {
                html += `<div class="key-row">
                    <span class="key-prov-badge">${PROV_ICONS[prov.toUpperCase()] || "🔑"} ${prov}</span>
                    <span class="key-masked">${masked}</span>
                    <button class="key-ping-btn" data-provider="${prov}" data-index="${idx}" title="Testiraj ključ">🔍</button>
                    <button class="key-del-btn" data-provider="${prov}" data-index="${idx}" title="Obriši">✕</button>
                </div>`;
            });
        });
        container.innerHTML = html;
        // Dugme za brisanje
        container.querySelectorAll(".key-del-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                deleteKey(btn.dataset.provider, btn.dataset.index);
            });
        });
        // Dugme za ping/provjeru
        container.querySelectorAll(".key-ping-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                pingKey(btn.dataset.provider, btn.dataset.index, btn);
            });
        });
    } catch (e) {
        container.innerHTML = `<div style="color:var(--rose)">❌ ${e.message}</div>`;
    }
}

async function addKey() {
    const provSelect = document.getElementById("key-provider-select");
    const keyInput = document.getElementById("key-value-input");
    const prov = provSelect?.value;
    const key = keyInput?.value?.trim();
    if (!prov || !key || key.length < 8) {
        showToast("Provjeri provajdera i ključ!", "warning");
        return;
    }
    const btn = document.getElementById("btn-add-key");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "⏳";
    }
    try {
        const r = await fetch(`/api/keys/${encodeURIComponent(prov)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key })
        });
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast(`Ključ za ${prov} dodan!`, "success");
        keyInput.value = "";
        await loadKeys();
        pollFleet();
    } catch (e) {
        showToast("Greška: " + e.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "➕ Dodaj";
        }
    }
}

async function deleteKey(provider, index) {
    if (!confirm(`Obrisati ključ #${index} za ${provider}?`)) return;
    try {
        const r = await fetch(
            `/api/keys/${encodeURIComponent(provider)}/${index}`,
            {
                method: "DELETE"
            }
        );
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        showToast("Ključ obrisan.", "info");
        await loadKeys();
        pollFleet();
    } catch (e) {
        showToast("Greška: " + e.message, "error");
    }
}

async function pingKey(provider, index, btn) {
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "⏳";
    try {
        const r = await fetch(
            `/api/keys/${encodeURIComponent(provider)}/${index}/ping`,
            { method: "POST" }
        );
        const d = await r.json();
        // Server-side greška (400/404/500) — HTTP status nije OK i nema ping rezultata
        if (!r.ok) {
            showToast(`${provider}: ❌ ${d.error || "Greška servera"}`, "error");
            btn.textContent = "✕";
            setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 3000);
            return;
        }
        if (d.ok) {
            showToast(`${provider} ✅ OK — ${d.latency_ms}ms`, "success");
            btn.textContent = "✅";
        } else {
            const msg = d.error || `HTTP ${d.status_code}`;
            showToast(`${provider} ⚠️ ${msg} (${d.latency_ms}ms)`, "warning");
            btn.textContent = "⚠️";
        }
        setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 4000);
    } catch (e) {
        showToast(`Ping greška: ${e.message}`, "error");
        btn.textContent = origText;
        btn.disabled = false;
    }
}

// ═══════════════ TABS ═══════════════════════════════
function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.toggle("active", b.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-panel").forEach(p => {
        p.classList.toggle("active", p.id === tabId);
    });
    if (tabId === "tab-fleet") pollFleet();
    if (tabId === "tab-expert") {
        pollFleet();
        loadKeys();
    }
    if (tabId === "tab-quality") loadQualityScores();
    if (tabId === "tab-history") renderHistory();
    if (tabId === "tab-epub") loadEpubPreview();
}

// ═══════════════ QUALITY SCORES ═════════════════════

// [v2.0.3] Live quality indikator u headeru
async function updateLiveQuality() {
    const badge = document.getElementById("quality-live-badge");
    if (!badge) return;
    try {
        const r = await fetch("/api/quality_scores");
        const data = await r.json();
        if (
            !data.has_data ||
            !data.scores ||
            Object.keys(data.scores).length === 0
        ) {
            badge.classList.remove("has-data");
            return;
        }
        const vals = Object.values(data.scores).filter(
            v => typeof v === "number"
        );
        if (vals.length === 0) {
            badge.classList.remove("has-data");
            return;
        }

        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        const ringPct = Math.round((avg / 10) * 100);
        const avgRounded = avg.toFixed(1);

        const color =
            avg >= 8.5
                ? "var(--emerald)"
                : avg >= 6.5
                  ? "var(--accent-2)"
                  : avg >= 4.0
                    ? "var(--amber)"
                    : "var(--rose)";

        const poor = vals.filter(v => v >= 4.0 && v < 6.5).length;
        const critical = vals.filter(v => v < 4.0).length;
        const bad = poor + critical;
        const subText = bad > 0 ? `${bad} treba retro` : `${vals.length} blk ✓`;

        const ring = badge.querySelector(".ql-ring");
        if (ring) {
            ring.style.setProperty("--ql-pct", ringPct + "%");
            ring.style.background = `conic-gradient(${color} 0% ${ringPct}%, var(--bg-3) 0%)`;
            ring.setAttribute("data-val", avgRounded);
        }
        const mainEl = badge.querySelector(".ql-score-main");
        const subEl = badge.querySelector(".ql-score-sub");
        if (mainEl) mainEl.textContent = avgRounded + "/10";
        if (subEl) subEl.textContent = subText;

        badge.classList.add("has-data");

        // Ažuriraj i badge na tabu kvaliteta
        const qualBadge = document.getElementById("quality-badge");
        if (qualBadge) {
            if (bad > 0) {
                qualBadge.textContent = bad;
                qualBadge.classList.remove("hidden");
            } else {
                qualBadge.classList.add("hidden");
            }
        }
    } catch (_) {
        badge.classList.remove("has-data");
    }
}

function _getQualityGrade(avg) {
    if (avg >= 8.5)
        return {
            cls: "excellent",
            emoji: "🌟",
            text: "Odlično — prijevod je spreman za štampu"
        };
    if (avg >= 6.5)
        return {
            cls: "good",
            emoji: "✅",
            text: "Dobro — sitne korekcije nisu neophodne"
        };
    if (avg >= 4.0)
        return {
            cls: "poor",
            emoji: "⚠",
            text: "Treba doradu — preporučuje se re-lektura"
        };
    return { cls: "critical", emoji: "🔴", text: "Potrebna ponovna obrada" };
}

async function loadQualityScores() {
    const loadingEl = document.getElementById("quality-loading");
    const contentEl = document.getElementById("quality-content");
    try {
        const r = await fetch("/api/quality_scores");
        const d = await r.json();
        const scores = d.scores || {};
        const overrides = getOverrides();
        for (const [stem, ostatus] of Object.entries(overrides)) {
            if (ostatus === "deleted") delete scores[stem];
            else if (ostatus === "fixed" && scores[stem] !== undefined)
                scores[stem] = 10.0;
        }
        const vals = Object.values(scores);
        if (!vals.length) {
            if (loadingEl) loadingEl.textContent = "Nema podataka.";
            loadingEl?.classList.remove("hidden");
            contentEl?.classList.add("hidden");
            return;
        }
        STATE.qualityLoaded = true;
        const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
        const excellent = vals.filter(v => v >= 8.5).length;
        const good = vals.filter(v => v >= 6.5 && v < 8.5).length;
        const poor = vals.filter(v => v >= 4.0 && v < 6.5).length;
        const critical = vals.filter(v => v < 4.0).length;
        const printReadyPct = Math.round((excellent / vals.length) * 100);

        const gi = _getQualityGrade(avg);
        const gradeEl = document.getElementById("qs-grade-display");
        if (gradeEl) {
            gradeEl.className = "qs-grade " + gi.cls;
            gradeEl.innerHTML = `<span>${gi.emoji}</span><span>${gi.text}</span><span style="margin-left:auto;font-family:var(--font-mono);font-size:0.78rem;opacity:0.7">${avg.toFixed(1)}/10</span>`;
        }

        setVal("qs-avg-big", avg.toFixed(2) + "/10");
        setVal("qs-total-label", `${vals.length} blokova ocijenjeno`);
        setVal("qs-excellent", excellent);
        setVal("qs-good", good);
        setVal("qs-poor", poor);
        setVal("qs-critical", critical);
        setVal("qs-print-ready-pct", printReadyPct + "%");
        const bar = document.getElementById("qs-print-ready-bar");
        if (bar) bar.style.width = printReadyPct + "%";
        const ring = document.getElementById("qs-avg-ring");
        if (ring) {
            const ringPct = Math.round((avg / 10) * 100);
            const color =
                avg >= 8.5
                    ? "var(--emerald)"
                    : avg >= 6.5
                      ? "var(--accent-2)"
                      : avg >= 4
                        ? "var(--amber)"
                        : "var(--rose)";
            ring.style.setProperty("--ring-pct", ringPct + "%");
            ring.style.background = `conic-gradient(${color} 0% ${ringPct}%, var(--bg-3) 0%)`;
            ring.setAttribute("data-val", avg.toFixed(1));
        }

        const byFile = {};
        for (const [stem, score] of Object.entries(scores)) {
            const fn = stem.split("_blok_")[0] || stem;
            if (!byFile[fn]) byFile[fn] = { blocks: [], total: 0, count: 0 };
            byFile[fn].blocks.push({ stem, score });
            byFile[fn].total += score;
            byFile[fn].count++;
        }
        const filesHtml = Object.entries(byFile)
            .map(([fn, info]) => {
                const fileAvg = info.total / info.count;
                const gi2 = _getQualityGrade(fileAvg);
                const blocksHtml = info.blocks
                    .map(b => {
                        const cls =
                            b.score >= 8.5
                                ? "excellent"
                                : b.score >= 6.5
                                  ? "good"
                                  : b.score >= 4
                                    ? "poor"
                                    : "critical";
                        const blokNum = b.stem.split("_blok_")[1] || "?";
                        return `<span class="qs-block-pill ${cls}" data-stem="${b.stem}" title="${b.stem}: ${b.score}/10 — klikni za reviziju">B${parseInt(blokNum) || blokNum} ${b.score.toFixed(1)}</span>`;
                    })
                    .join("");
                return `<div class="qs-file-item">
                    <div class="qs-file-header">
                        <span class="qs-file-name">${fn}</span>
                        <span class="qs-file-avg" style="color:var(--${gi2.cls === "excellent" ? "emerald" : gi2.cls === "good" ? "accent-2" : gi2.cls === "poor" ? "amber" : "rose"})">${fileAvg.toFixed(1)}/10</span>
                        <span style="font-size:0.7rem;color:var(--tx-3)">${info.count} blk</span>
                        <span style="color:var(--tx-3)">▾</span>
                    </div>
                    <div class="qs-blocks-grid hidden">${blocksHtml}</div>
                </div>`;
            })
            .join("");
        const fc = document.getElementById("qs-files-container");
        if (fc)
            fc.innerHTML =
                filesHtml ||
                '<div style="color:var(--tx-3);padding:12px">Nema podataka.</div>';

        loadingEl?.classList.add("hidden");
        contentEl?.classList.remove("hidden");

        const qualBadge = document.getElementById("quality-badge");
        if (qualBadge) {
            if (poor + critical > 0) {
                qualBadge.textContent = poor + critical;
                qualBadge.classList.remove("hidden");
            } else qualBadge.classList.add("hidden");
        }

        // Dodaj event listenere za qs-block-pill
        document.querySelectorAll(".qs-block-pill[data-stem]").forEach(pill => {
            pill.addEventListener("click", () => {
                const stem = pill.dataset.stem;
                if (_markedForReview.has(stem)) {
                    _markedForReview.delete(stem);
                    pill.style.outline = "";
                } else {
                    _markedForReview.add(stem);
                    pill.style.outline = "2px solid var(--amber)";
                }
                _updateRefixBar();
            });
        });

        // Takođe dodaj toggle za file headers
        document.querySelectorAll(".qs-file-header").forEach(header => {
            header.addEventListener("click", function () {
                const grid =
                    this.parentElement.querySelector(".qs-blocks-grid");
                grid?.classList.toggle("hidden");
            });
        });

        // Osvježi live quality badge u headeru
        updateLiveQuality();
    } catch (e) {
        if (loadingEl) loadingEl.textContent = "Greška: " + e.message;
    }
}

const _markedForReview = new Set();

function _updateRefixBar() {
    const bar = document.getElementById("qs-refix-bar");
    const info = document.getElementById("qs-refix-info");
    const btn = document.getElementById("btn-send-marked");
    const n = _markedForReview.size;
    if (n > 0) {
        if (bar) bar.style.display = "flex";
        if (info)
            info.textContent =
                n + " blok" + (n === 1 ? "" : "a") + " oznaceno za relekturu";
        if (btn) btn.classList.remove("hidden");
    } else {
        if (bar) bar.style.display = "none";
        if (btn) btn.classList.add("hidden");
    }
    const qualBadge = document.getElementById("quality-badge");
    if (qualBadge) {
        if (n > 0) {
            qualBadge.textContent = n;
            qualBadge.classList.remove("hidden");
        } else {
            qualBadge.classList.add("hidden");
        }
    }
}

function selectBadBlocks(tip) {
    const pills = document.querySelectorAll(".qs-block-pill[data-stem]");
    pills.forEach(function (pill) {
        const m = pill.textContent.match(/[\d.]+$/);
        const score = m ? parseFloat(m[0]) : 10;
        let treba = false;
        if (tip === "poor") treba = score >= 4.0 && score < 6.5;
        if (tip === "critical") treba = score < 4.0;
        if (tip === "all") treba = score < 6.5;
        if (treba) {
            _markedForReview.add(pill.dataset.stem);
            pill.style.outline = "2px solid var(--amber)";
        }
    });
    const poorBox = document.getElementById("qs-box-poor");
    const critBox = document.getElementById("qs-box-critical");
    if (poorBox)
        poorBox.classList.toggle(
            "qs-selected",
            tip === "poor" || tip === "all"
        );
    if (critBox)
        critBox.classList.toggle(
            "qs-selected",
            tip === "critical" || tip === "all"
        );
    document.querySelectorAll(".qs-blocks-grid.hidden").forEach(function (g) {
        g.classList.remove("hidden");
    });
    _updateRefixBar();
}

function clearMarkedBlocks() {
    _markedForReview.clear();
    document
        .querySelectorAll(".qs-block-pill[data-stem]")
        .forEach(function (el) {
            el.style.outline = "";
        });
    const poorBox = document.getElementById("qs-box-poor");
    const critBox = document.getElementById("qs-box-critical");
    if (poorBox) poorBox.classList.remove("qs-selected");
    if (critBox) critBox.classList.remove("qs-selected");
    _updateRefixBar();
}

async function sendMarkedForRefix() {
    if (_markedForReview.size === 0) {
        showToast("Nisi označio nijedan blok.", "warning");
        return;
    }
    const book = STATE.book || document.getElementById("book-select")?.value;
    const model =
        STATE.model ||
        document.getElementById("model-select")?.value ||
        "V10_TURBO";
    const stems = Array.from(_markedForReview);
    if (!book) {
        showToast("Nema aktivne knjige.", "warning");
        return;
    }
    try {
        const r1 = await fetch("/api/review/mark", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ book, stems })
        });
        const d1 = await r1.json();
        if (d1.error) throw new Error(d1.error);
        const r2 = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ book, model, tool: "REFIX" })
        });
        const d2 = await r2.json();
        if (d2.error) throw new Error(d2.error);
        showToast(
            `🔧 Re-lektura pokrenuta za ${stems.length} blokova!`,
            "success"
        );
        _markedForReview.clear();
        document
            .querySelectorAll(".qs-block-pill[data-stem]")
            .forEach(el => (el.style.outline = ""));
        document.getElementById("qs-box-poor")?.classList.remove("qs-selected");
        document
            .getElementById("qs-box-critical")
            ?.classList.remove("qs-selected");
        _updateRefixBar();
        showDashboard();
    } catch (e) {
        showToast("Greška: " + e.message, "error");
    }
}

// ═══════════════════════════════════════════════════════════
// refreshQualityBlock — FIX 1.3 + 1.4
// Briše ili ažurira pill u Score tabu nakon akcije u Review tabu.
// ═══════════════════════════════════════════════════════════
function refreshQualityBlock(stem, action) {
    // FIX FAZA2 refreshQualityBlock — potpuni DOM sync
    const pill = document.querySelector(
        `.qs-block-pill[data-stem="${CSS.escape(stem)}"]`
    );

    if (action === "deleted") {
        if (pill) {
            const fileItem = pill.closest(".qs-file-item");
            pill.remove();
            if (fileItem) {
                const remaining = fileItem.querySelectorAll(".qs-block-pill");
                if (remaining.length === 0) {
                    fileItem.remove();
                } else {
                    _recalcFileAvg(fileItem);
                }
            }
        }
    } else if (action === "fixed") {
        if (pill) {
            const blokNum = stem.split("_blok_")[1] || "?";
            pill.className = "qs-block-pill excellent";
            pill.style.outline = "2px solid var(--emerald)";
            pill.title = `${stem}: 10.0/10 — ručno sačuvano`;
            pill.innerHTML = `B${parseInt(blokNum) || blokNum} 10.0`;
            const fileItem = pill.closest(".qs-file-item");
            if (fileItem) _recalcFileAvg(fileItem);
        }
    }

    // Ažuriraj quality-badge na tabu
    const badPills = document.querySelectorAll(
        ".qs-block-pill.poor, .qs-block-pill.critical"
    );
    const badge = document.getElementById("quality-badge");
    if (badge) {
        if (badPills.length > 0) {
            badge.textContent = badPills.length;
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }

    // Osvježi live quality indikator u headeru
    updateLiveQuality();
}

function _recalcFileAvg(fileItem) {
    // Preračunaj prosječnu ocjenu fajla iz trenutnih pill-ova
    const pills = fileItem.querySelectorAll(".qs-block-pill");
    if (!pills.length) return;
    let total = 0,
        count = 0;
    pills.forEach(p => {
        // Izvuci broj iz teksta "B3 7.0"
        const m = p.textContent.match(/([\d.]+)\s*$/);
        if (m) {
            total += parseFloat(m[1]);
            count++;
        }
    });
    if (!count) return;
    const avg = (total / count).toFixed(1);
    const avgEl = fileItem.querySelector(".qs-file-avg");
    if (avgEl) {
        avgEl.textContent = avg + "/10";
        const color =
            avg >= 8.5
                ? "var(--emerald)"
                : avg >= 6.5
                  ? "var(--accent-2)"
                  : avg >= 4.0
                    ? "var(--amber)"
                    : "var(--rose)";
        avgEl.style.color = color;
    }
}

// ═══════════════ EPUB PREGLED ═══════════════════
// [LIVE EPUB] Učitava djelimični EPUB tokom obrade
async function loadEpubPreview() {
    const wrap = document.getElementById("epub-reader-wrap");
    const noContent = document.getElementById("epub-no-content");
    const content = document.getElementById("epub-content");

    if (noContent) {
        noContent.innerHTML =
            '<div style="color:var(--tx-3);text-align:center;padding:32px;font-size:0.8rem">⏳ Učitavam pregled...</div>';
        noContent.classList.remove("hidden");
    }
    if (wrap) wrap.classList.add("hidden");

    try {
        const r = await fetch("/api/epub_preview");
        // Uvijek čitamo kao tekst — nema JSON parsiranja
        const text = await r.text();

        if (!text || text.trim().length === 0) {
            if (noContent)
                noContent.innerHTML = `<div style="color:var(--tx-3);text-align:center;padding:32px">
                    <div style="font-size:1.8rem;margin-bottom:8px">📭</div>
                    <div style="font-size:0.82rem">Nema obrađenog teksta za prikaz.</div>
                    <button onclick="loadEpubPreview()" class="btn btn-sm" style="margin-top:12px">↻ Pokušaj ponovo</button>
                 </div>`;
            return;
        }

        // Prikaži čist tekst — svaki paragraf u <p> tagu
        if (content) {
            content.innerHTML = text
                .split(/\n\n+/)
                .filter(p => p.trim().length > 0)
                .map(
                    p =>
                        `<p style="margin:0 0 0.9em 0;line-height:1.7">${p.trim().replace(/\n/g, "<br>")}</p>`
                )
                .join("");
        }

        if (wrap) wrap.classList.remove("hidden");
        if (noContent) noContent.classList.add("hidden");

        // Ažuriraj label
        const label = document.getElementById("epub-chapter-label");
        if (label) label.textContent = "Pregled obrađenog teksta";
    } catch (e) {
        if (noContent)
            noContent.innerHTML = `<div style="color:var(--rose);text-align:center;padding:32px">
                <div style="font-size:0.82rem">Greška: ${e.message}</div>
                <button onclick="loadEpubPreview()" class="btn btn-sm" style="margin-top:12px">↻ Pokušaj ponovo</button>
             </div>`;
        if (wrap) wrap.classList.add("hidden");
        if (noContent) noContent.classList.remove("hidden");
    }
}

function showEpubChapter(idx) {
    const ch = STATE.epubChapters[idx];
    if (!ch) return;
    const content = document.getElementById("epub-content");
    const label = document.getElementById("epub-chapter-label");

    let chapterHtml = ch.html || "<p>" + (ch.text || "—") + "</p>";

    if (ch.partial) {
        chapterHtml =
            '<div class="epub-chapter-partial">' + chapterHtml + "</div>";
        if (label)
            label.textContent =
                "⚡ " +
                (idx + 1) +
                "/" +
                STATE.epubChapters.length +
                ": " +
                (ch.title || "") +
                " (u obradi...)";
    } else {
        if (label)
            label.textContent =
                "Poglavlje " +
                (idx + 1) +
                "/" +
                STATE.epubChapters.length +
                ": " +
                (ch.title || "");
    }

    if (content) content.innerHTML = chapterHtml;
}

function prevEpubChapter() {
    if (STATE.epubChapterIdx > 0) {
        STATE.epubChapterIdx--;
        showEpubChapter(STATE.epubChapterIdx);
    }
}
function nextEpubChapter() {
    if (STATE.epubChapterIdx < STATE.epubChapters.length - 1) {
        STATE.epubChapterIdx++;
        showEpubChapter(STATE.epubChapterIdx);
    }
}

// ═══════════════ INIT ═══════════════════════════
document.addEventListener("DOMContentLoaded", async function () {
    // [v2.0.1] Pokrećemo load knjiga i modela paralelno
    await Promise.allSettled([loadBooks(), loadModels()]);
    renderHistory();
    restoreAppState();

    let showedDashboard = false;
    try {
        const r = await fetch("/api/status");
        const d = await r.json();
        updateStatus(d);
        const st = (d.status || "IDLE").toUpperCase();
        if (
            st.includes("TOKU") ||
            st.includes("POKRETANJE") ||
            st.includes("FIX")
        ) {
            showDashboard();
            STATE.processing = true;
            if (!STATE.startTime)
                STATE.startTime = Date.now() - ((d.pct || 0) / 100) * 60000;
            showedDashboard = true;
        }
        if (!showedDashboard) {
            const sess = loadSession();
            if (sess && sess.book) {
                if (st !== "IDLE" && st !== "ZAUSTAVLJENO") {
                    STATE.book = sess.book;
                    STATE.model = sess.model || STATE.model;
                    showDashboard();
                    showedDashboard = true;
                    showToast(`Sesija obnovljena: ${sess.book}`, "info");
                } else {
                    clearSession();
                }
            }
        }
    } catch (_) {}

    startDashboardPolling();
    setInterval(pollFleet, 20000);

    // Audit scroll
    const log = document.getElementById("audit-log");
    if (log) {
        log.addEventListener("scroll", () => {
            _auditAutoScroll =
                log.scrollHeight - log.scrollTop - log.clientHeight < 40;
            const ind = document.getElementById("audit-scroll-indicator");
            if (ind) ind.style.display = _auditAutoScroll ? "none" : "flex";
        });
    }

    // ══════ EVENT LISTENERI ══════

    // Header / Setup dugmad
    document
        .getElementById("theme-btn")
        ?.addEventListener("click", toggleTheme);
    document
        .getElementById("btn-show-setup")
        ?.addEventListener("click", showSetup);
    document
        .getElementById("btn-show-setup-dashboard")
        ?.addEventListener("click", showSetup);

    // Wizard dugmad
    document
        .getElementById("btn-wizard-next")
        ?.addEventListener("click", wizardNext);
    document
        .getElementById("btn-wizard-back")
        ?.addEventListener("click", wizardBack);
    document
        .getElementById("btn-start")
        ?.addEventListener("click", startProcessing);

    // Kontrolna dugmad (dashboard)
    document
        .getElementById("btn-pause")
        ?.addEventListener("click", () => sendControl("pause"));
    document
        .getElementById("btn-resume")
        ?.addEventListener("click", () => sendControl("resume"));
    document
        .getElementById("btn-reset")
        ?.addEventListener("click", () => sendControl("reset"));
    document
        .getElementById("btn-stop")
        ?.addEventListener("click", () => sendControl("stop"));

    // Download dugmad
    document
async function requestLiveDownload() {
    try {
        const r = await fetch("/api/download_live");
        if (!r.ok) { showToast("Live download nije dostupan.", "warning"); return; }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "live_preview.epub";
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        showToast("Greška pri downloadu: " + e.message, "error");
    }
}

        document.getElementById("btn-download-live")
        ?.addEventListener("click", requestLiveDownload);
    document
        .getElementById("btn-download-final")
        ?.addEventListener("click", () => {
            window.location.href = "/api/download";
        });

    // Download modal dugmad
    document
function closeDownloadModal() {
    const m = document.getElementById("download-modal");
    if (m) m.classList.remove("open");
}

async function confirmDownloadLive() {
    closeDownloadModal();
    try {
        const r = await fetch("/api/download_live");
        if (!r.ok) { showToast("Live download nije dostupan.", "warning"); return; }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "live_preview.epub";
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        showToast("Greška: " + e.message, "error");
    }
}

        document.getElementById("btn-close-download-modal")
        ?.addEventListener("click", closeDownloadModal);
    document
        .getElementById("btn-confirm-download-live")
        ?.addEventListener("click", confirmDownloadLive);

    // Quality / dugmad
    document
        .getElementById("btn-refresh-quality")
        ?.addEventListener("click", loadQualityScores);
    document
        .getElementById("btn-send-marked")
        ?.addEventListener("click", sendMarkedForRefix);



    // TTS dugmad
    document
        .getElementById("btn-select-tts")
        ?.addEventListener("click", selectTTSMode);
    document
        .getElementById("btn-cancel-tts")
        ?.addEventListener("click", cancelTTSMode);

    // Upload zona klik
    document
        .getElementById("upload-zone")
        ?.addEventListener("click", triggerUpload);

    // Tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            switchTab(btn.dataset.tab);
        });
    });

    // Tier pills
    document.querySelectorAll(".tier-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            filterTier(pill.dataset.tier);
        });
    });

    // Guide banner "Dalje" dugme
    document
        .querySelector(".guide-action")
        ?.addEventListener("click", wizardNext);

    // Book select change
    document
        .getElementById("book-select")
        ?.addEventListener("change", function () {
            onBookChange(this.value);
        });
});

// ── FIX 2.3: Custom tooltip popover ──────────────────────────────────────────
(function initTooltip() {
    let tip = null;
    let hideTimer = null;

    function _getOrCreate() {
        if (!tip) {
            tip = document.createElement("div");
            tip.id = "bf-tooltip";
            tip.className = "bf-tooltip";
            document.body.appendChild(tip);
        }
        return tip;
    }

    function _showTip(el, text) {
        if (!text) return;
        clearTimeout(hideTimer);
        const t = _getOrCreate();
        t.textContent = text;
        t.style.display = "block";
        t.style.opacity = "0";

        const rect = el.getBoundingClientRect();
        const scrollY = window.scrollY || 0;
        const scrollX = window.scrollX || 0;

        // Pozicioniraj iznad elementa
        let top = rect.top + scrollY - t.offsetHeight - 8;
        let left = rect.left + scrollX + rect.width / 2 - t.offsetWidth / 2;

        // Korekcija za rub ekrana
        if (left < 8) left = 8;
        if (left + t.offsetWidth > window.innerWidth - 8)
            left = window.innerWidth - t.offsetWidth - 8;
        if (top < scrollY + 8) top = rect.bottom + scrollY + 8; // ispod ako nema mjesta

        t.style.top = top + "px";
        t.style.left = left + "px";
        t.style.opacity = "1";
    }

    function _hideTip() {
        hideTimer = setTimeout(() => {
            if (tip) {
                tip.style.opacity = "0";
                setTimeout(() => {
                    if (tip) tip.style.display = "none";
                }, 180);
            }
        }, 120);
    }

    // Delegirani event listener na document
    document.addEventListener("mouseover", e => {
        const el = e.target.closest("[data-tip]");
        if (el) _showTip(el, el.dataset.tip);
    });
    document.addEventListener("mouseout", e => {
        if (e.target.closest("[data-tip]")) _hideTip();
    });
    // Touch (mobilni)
    document.addEventListener(
        "touchstart",
        e => {
            const el = e.target.closest("[data-tip]");
            if (el) {
                e.preventDefault();
                _showTip(el, el.dataset.tip);
                setTimeout(_hideTip, 2800);
            }
        },
        { passive: false }
    );
})();

// ═══════════════ Neon naslov animacija ═══════════════
(function neonTitle() {
    const el = document.getElementById("brand-title");
    if (!el) return;
    const palette = [
        "#6366f1",
        "#06b6d4",
        "#10b981",
        "#f59e0b",
        "#f43f5e",
        "#a78bfa"
    ];
    let idx = 0;
    function flash() {
        const c = palette[idx++ % palette.length];
        el.style.textShadow = `0 0 8px ${c}60, 0 0 24px ${c}40`;
        setTimeout(
            () => {
                el.style.textShadow = "";
            },
            180 + Math.random() * 220
        );
        setTimeout(flash, 600 + Math.random() * 1200);
    }
    setTimeout(flash, 800);
})();

// ═══════════════════════════════════════════════════════════════════
// HIGHLIGHT EDITOR za Review tab — v3.0
// Backdrop + textarea overlay: textarea ostaje editable,
// backdrop prikazuje HTML highlight spanove u realnom vremenu.
// ═══════════════════════════════════════════════════════════════════

(function initHighlightEditor() {
    // ── Interne reference ──────────────────────────────────────────
    let _ta = null; // textarea#review-text
    let _backdrop = null; // div#hl-highlights
    let _statsBar = null; // div#hl-stats-bar
    let _rafPending = false;

    // ── Inicijalizacija (poziva se kad se učita tab ili blok) ──────
    function _init() {
        _ta = document.getElementById("review-text");
        _backdrop = document.getElementById("hl-highlights");
        _statsBar = document.getElementById("hl-stats-bar");
        if (!_ta || !_backdrop) return false;

        // H1c FIX: Sync scroll — textarea scroll povlači backdrop scroll
        _ta.addEventListener("scroll", _syncScroll, { passive: true });
        // Live update na svaki input
        _ta.addEventListener("input", _scheduleUpdate, { passive: true });

        // Osiguraj identičan font/padding između textarea i highlights diva
        // (mora biti identično da se span-ovi podudaraju s riječima)
        _syncFont();

        // Prati promjene dimenzija
        if (window.ResizeObserver) {
            new ResizeObserver(_syncFont).observe(_ta);
        }

        return true;
    }

    function _syncFont() {
        if (!_ta || !_backdrop) return;
        const cs = window.getComputedStyle(_ta);
        const props = [
            "fontFamily",
            "fontSize",
            "fontWeight",
            "lineHeight",
            "letterSpacing",
            "wordSpacing",
            "paddingTop",
            "paddingRight",
            "paddingBottom",
            "paddingLeft",
            "borderTopWidth",
            "borderRightWidth",
            "borderBottomWidth",
            "borderLeftWidth",
            "boxSizing",
            "tabSize"
        ];
        props.forEach(prop => {
            _backdrop.style[prop] = cs[prop];
        });
        // Visina backdrop = visina textarea sadržaja
        _backdrop.parentElement.style.height = _ta.offsetHeight + "px";
    }

    function _syncScroll() {
        // H1 FIX: pomjeri highlights div s translateY umjesto scroll
        // Backdrop je position:absolute i ne scrolluje sam — moramo ručno
        // pomaknuti highlights div za isti iznos kao što textarea scrolluje
        if (_backdrop) {
            _backdrop.scrollTop = _ta.scrollTop;
        }
    }

    function _scheduleUpdate() {
        if (_rafPending) return;
        _rafPending = true;
        requestAnimationFrame(() => {
            _rafPending = false;
            _update();
        });
    }

    // ── Ručno pokretanje highlight-a s tekstom ────────────────────
    function _applyText(text) {
        if (!_ta) _init();
        if (!_ta) return;
        _ta.value = text;
        _update();
    }

    // ── Glavni update: scan → render → stats ─────────────────────
    function _update() {
        if (!_ta || !_backdrop) return;
        const rawText = _ta.value;
        if (!rawText.trim()) {
            _backdrop.innerHTML = "";
            if (_statsBar) _statsBar.style.display = "none";
            return;
        }

        // Koristi postojeći _heuristicScan iz main.js
        const highlights =
            typeof _heuristicScan === "function" ? _heuristicScan(rawText) : [];

        // Render backdrop HTML
        _backdrop.innerHTML = _buildBackdropHTML(rawText, highlights);

        // Render stats bar
        _renderStatsBar(highlights, rawText);
    }

    // ── Gradi backdrop HTML s highlight span-ovima ─────────────────
    function _buildBackdropHTML(text, highlights) {
        if (!highlights.length) {
            // Nema grešaka — samo escapeuj tekst (mora biti isti layout)
            return _escHl(text);
        }

        const CLASS_MAP = {
            en_word: "hl-en",
            anglicizam: "hl-kalk",
            gramatika: "hl-gram",
            word_order: "hl-gram"
        };

        let html = "",
            cursor = 0;
        for (const h of highlights) {
            if (h.start > cursor) {
                html += _escHl(text.slice(cursor, h.start));
            }
            const cls = CLASS_MAP[h.type] || "hl-en";
            const tip = _escAttr(h.reason || "");
            html += `<span class="${cls}" title="${tip}">${_escHl(text.slice(h.start, h.end))}</span>`;
            cursor = h.end;
        }
        if (cursor < text.length) html += _escHl(text.slice(cursor));
        return html;
    }

    // ── Stats bar ─────────────────────────────────────────────────
    function _renderStatsBar(highlights, text) {
        if (!_statsBar) return;
        if (!highlights.length) {
            _statsBar.innerHTML = `<span class="hl-stats-clean">✓ Nema grešaka</span>`;
            _statsBar.style.display = "flex";
            return;
        }

        const enCount = highlights.filter(h => h.type === "en_word").length;
        const kalkCount = highlights.filter(
            h => h.type === "anglicizam"
        ).length;
        const gramCount = highlights.filter(
            h => h.type === "gramatika" || h.type === "word_order"
        ).length;
        const total = highlights.length;

        let chips = "";
        if (enCount)
            chips += `<span class="hl-stat-chip en">🇬🇧 ${enCount} EN</span>`;
        if (kalkCount)
            chips += `<span class="hl-stat-chip kalk">⚠ ${kalkCount} kalk</span>`;
        if (gramCount)
            chips += `<span class="hl-stat-chip gram">~ ${gramCount} gram.</span>`;

        _statsBar.innerHTML =
            chips +
            `<span style="margin-left:auto;color:var(--tx-3)">${total} ukupno · hover za detalj</span>`;
        _statsBar.style.display = "flex";
    }

    // ── Escape helpers ────────────────────────────────────────────
    function _escHl(s) {
        // Moramo sačuvati razmake i newlineove za identičan layout
        return s
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\n/g, "<br>")
            .replace(/ /g, "&nbsp;");
    }
    function _escAttr(s) {
        return s.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    // ── Javno API ─────────────────────────────────────────────────
    window._hlEditor = {
        init: _init,
        applyText: _applyText,
        update: _update,
        clear: function () {
            if (_ta) _ta.value = "";
            if (_backdrop) _backdrop.innerHTML = "";
            if (_statsBar) _statsBar.style.display = "none";
        }
    };

    // Auto-init kad DOM bude spreman
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", _init);
    } else {
        _init();
    }
})();

// ═══════════════════════════════════════════════════════════════════
// REVIEW TAB — inline editor s highlight podrškom + multiselect
// ═══════════════════════════════════════════════════════════════════

const _reviewMultiSelected = new Set();

function _updateReviewMultiBar() {
    const n = _reviewMultiSelected.size;
    const el1 = document.getElementById("review-multi-count");
    const el2 = document.getElementById("review-multi-count2");
    if (el1) el1.textContent = n + " označeno";
    if (el2) el2.textContent = n;
}

function _clearTabEditor() {
    if (window._hlEditor) window._hlEditor.clear();
    const fn = document.getElementById("review-filename");
    if (fn) fn.textContent = "—";
    const emptyBanner = document.getElementById("review-empty-banner");
    if (emptyBanner) emptyBanner.style.display = "none";
    const legend = document.getElementById("review-legend");
    if (legend) legend.style.display = "none";
    const preview = document.getElementById("review-preview-panel");
    if (preview) preview.style.display = "none";
    const hint = document.getElementById("review-hint-count");
    if (hint) hint.textContent = "";
}


function applyHighlights(container, patterns) {
    // D FIX: inline underline span umjesto backdrop div
    // container = DOM element s tekstom (contenteditable ili div)
    if (!container) return;

    // Reset — ukloni stare highlight span-ove
    container.querySelectorAll(".hl-match").forEach(el => {
        el.replaceWith(document.createTextNode(el.textContent));
    });
    container.normalize();

    if (!patterns || patterns.length === 0) return;

    // Iteriraj text nodove i wrap matches u <span class="hl-match hl-COLOR">
    function walkAndHighlight(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.textContent;
            let result = null;
            let matchIdx = -1;
            let matchLen = 0;
            let matchClass = "hl-amber";

            for (const pat of patterns) {
                const rx =
                    pat.regex instanceof RegExp
                        ? pat.regex
                        : new RegExp(pat.pattern || pat, "gi");
                const m = rx.exec(text);
                if (m && (matchIdx === -1 || m.index < matchIdx)) {
                    matchIdx = m.index;
                    matchLen = m[0].length;
                    matchClass = pat.color || pat.cls || "hl-amber";
                    result = m;
                }
            }

            if (result === null || matchIdx === -1) return;

            const before = document.createTextNode(text.slice(0, matchIdx));
            const span = document.createElement("span");
            span.className = `hl-match ${matchClass}`;
            span.textContent = text.slice(matchIdx, matchIdx + matchLen);
            const after = document.createTextNode(
                text.slice(matchIdx + matchLen)
            );

            const parent = node.parentNode;
            parent.replaceChild(after, node);
            parent.insertBefore(span, after);
            parent.insertBefore(before, span);

            // Nastavi od "after" node-a
            walkAndHighlight(after);
        } else if (
            node.nodeType === Node.ELEMENT_NODE &&
            !node.classList.contains("hl-match")
        ) {
            Array.from(node.childNodes).forEach(walkAndHighlight);
        }
    }

    walkAndHighlight(container);
}
