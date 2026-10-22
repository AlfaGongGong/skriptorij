/**
 * metrics.js — Panel determinističkih metrika kvaliteta (F3c-JS)
 *
 * Izvor: GET /api/quality_scores  (api/routes/qualities.py)
 *   -> { metrics: { "<stem>": {ekavizmi_per_1000, en_ostaci_per_1000, duplikati,
 *                              ratio_source_target, tipografija_greske,
 *                              reci_ukupno, quality_class} },
 *        metrics_summary: {OK, REVIEW, REJECT, TRUNCATED},
 *        has_data: bool }
 *
 * Montira se u #metrics-panel (vidi dashboard_panel.html). Ako elementa nema,
 * ne radi ništa. Bez zavisnosti; ne koristi funkcije iz drugih JS fajlova.
 *
 * Javni API: window.MetricsPanel = { init, refresh, stop }
 */
(function () {
    'use strict';

    const ENDPOINT   = '/api/quality_scores';
    const REFRESH_MS = 30000;
    const TIMEOUT_MS = 10000;
    const PAGE_SIZE  = 100;

    const CLASSES  = ['OK', 'REVIEW', 'REJECT', 'TRUNCATED'];
    const SEVERITY = { REJECT: 0, TRUNCATED: 1, REVIEW: 2, OK: 3 };

    const fmt2 = v => (typeof v === 'number' && isFinite(v)) ? v.toFixed(2) : '—';
    const fmtI = v => (typeof v === 'number' && isFinite(v)) ? String(Math.round(v)) : '—';

    const COLS = [
        { key: 'ekavizmi_per_1000',   label: 'Ekav/1k', title: 'Ekavizmi na 1000 riječi',       fmt: fmt2 },
        { key: 'en_ostaci_per_1000',  label: 'EN/1k',   title: 'Engleski ostaci na 1000 riječi', fmt: fmt2 },
        { key: 'duplikati',           label: 'Dupl.',   title: 'Duplirani pasusi',               fmt: fmtI },
        { key: 'ratio_source_target', label: 'Omjer',   title: 'Riječi izvor / prijevod',        fmt: fmt2 },
        { key: 'tipografija_greske',  label: 'Tipogr.', title: 'Tipografske greške',             fmt: fmtI },
        { key: 'reci_ukupno',         label: 'Riječi',  title: 'Ukupno riječi u bloku',          fmt: fmtI },
    ];

    const state = {
        data: null,
        error: null,
        filter: null,
        shown: PAGE_SIZE,
        loading: false,
        updatedAt: null,
        timer: null,
    };

    let root = null;

    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function clsKey(c) {
        return CLASSES.indexOf(c) >= 0 ? c.toLowerCase() : 'unknown';
    }

    function pill(c) {
        const label = CLASSES.indexOf(c) >= 0 ? c : '—';
        return `<span class="mx-pill mx-${clsKey(c)}">${esc(label)}</span>`;
    }

    function normalize(j) {
        if (!j || typeof j !== 'object') return null;
        const metrics = (j.metrics && typeof j.metrics === 'object' && !Array.isArray(j.metrics))
            ? j.metrics : {};
        const summary = { OK: 0, REVIEW: 0, REJECT: 0, TRUNCATED: 0 };
        const srv = (j.metrics_summary && typeof j.metrics_summary === 'object') ? j.metrics_summary : null;
        if (srv) {
            CLASSES.forEach(c => { summary[c] = Number(srv[c]) || 0; });
        } else {
            Object.values(metrics).forEach(m => {
                const c = m && m.quality_class;
                if (summary[c] !== undefined) summary[c]++;
            });
        }
        return {
            metrics,
            summary,
            hasData: j.has_data !== false,
            message: typeof j.message === 'string' ? j.message : '',
        };
    }

    async function load() {
        if (state.loading) return;
        state.loading = true;
        setBusy(true);
        const ctrl = new AbortController();
        const to = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
        try {
            const r = await fetch(ENDPOINT, {
                cache: 'no-store',
                signal: ctrl.signal,
                headers: { Accept: 'application/json' },
            });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const parsed = normalize(await r.json());
            if (!parsed) throw new Error('neispravan odgovor');
            state.data = parsed;
            state.error = null;
            state.updatedAt = new Date();
        } catch (e) {
            state.error = (e && e.name === 'AbortError') ? 'timeout' : ((e && e.message) || 'greška');
        } finally {
            clearTimeout(to);
            state.loading = false;
            setBusy(false);
            render();
        }
    }

    function setBusy(b) {
        const btn = root && root.querySelector('#mx-refresh');
        if (!btn) return;
        btn.disabled = b;
        btn.classList.toggle('mx-busy', b);
    }

    function sortedRows(metrics) {
        const rows = Object.entries(metrics).filter(([, m]) => m && typeof m === 'object');
        rows.sort((a, b) => {
            const sa = SEVERITY[a[1].quality_class] ?? 9;
            const sb = SEVERITY[b[1].quality_class] ?? 9;
            if (sa !== sb) return sa - sb;
            return a[0].localeCompare(b[0], undefined, { numeric: true });
        });
        return rows;
    }

    function stemLabel(stem) {
        const i = stem.lastIndexOf('_blok_');
        return i > 0 ? `${stem.slice(0, i)} · blok ${stem.slice(i + 6)}` : stem;
    }

    function renderSummary(summary) {
        return CLASSES.map(c => {
            const active = state.filter === c;
            return `<button type="button" class="mx-badge mx-${c.toLowerCase()}${active ? ' mx-active' : ''}"
                        data-cls="${c}" aria-pressed="${active}" title="Filtriraj: ${c}">
                        <strong>${summary[c]}</strong><span>${c}</span>
                    </button>`;
        }).join('');
    }

    function renderTable(metrics) {
        let rows = sortedRows(metrics);
        const total = rows.length;
        if (state.filter) rows = rows.filter(([, m]) => m.quality_class === state.filter);
        if (rows.length === 0) {
            return `<div class="mx-empty">Nema blokova${state.filter ? ' u klasi ' + esc(state.filter) : ''}.</div>`;
        }
        const visible = rows.slice(0, state.shown);
        const head = COLS.map(c => `<th title="${esc(c.title)}">${esc(c.label)}</th>`).join('');
        const body = visible.map(([stem, m]) => {
            const cells = COLS.map(c => `<td>${c.fmt(m[c.key])}</td>`).join('');
            return `<tr><td class="mx-stem" title="${esc(stem)}">${esc(stemLabel(stem))}</td>${cells}<td>${pill(m.quality_class)}</td></tr>`;
        }).join('');
        const more = rows.length > visible.length
            ? `<button type="button" class="btn btn-sm btn-outline mx-more" id="mx-more">Prikaži još (${rows.length - visible.length})</button>`
            : '';
        return `<table class="mx-table">
                    <thead><tr><th>Blok</th>${head}<th>Klasa</th></tr></thead>
                    <tbody>${body}</tbody>
                </table>
                <div class="mx-foot">${visible.length} / ${rows.length}${state.filter ? ' (filter) ' : ''} od ${total} blokova ${more}</div>`;
    }

    function render() {
        if (!root) return;
        const sumEl = root.querySelector('#mx-summary');
        const stEl  = root.querySelector('#mx-status');
        const tbEl  = root.querySelector('#mx-table-wrap');
        if (!sumEl || !stEl || !tbEl) return;

        const d = state.data;
        if (!d) {
            sumEl.innerHTML = '';
            tbEl.innerHTML = '';
            stEl.className = 'mx-status mx-status-err';
            stEl.textContent = state.error
                ? `⚠ Metrike nedostupne (${state.error}).`
                : 'Učitavam metrike…';
            return;
        }

        sumEl.innerHTML = renderSummary(d.summary);

        const n = Object.keys(d.metrics).length;
        if (!d.hasData || n === 0) {
            tbEl.innerHTML = '';
            stEl.className = 'mx-status';
            stEl.textContent = d.message || 'Nema metrika. Pokreni obradu — quality_metrics.json se piše tokom obrade.';
            return;
        }

        tbEl.innerHTML = renderTable(d.metrics);

        if (state.error) {
            stEl.className = 'mx-status mx-status-err';
            stEl.textContent = `⚠ Osvježavanje nije uspjelo (${state.error}) — prikazani zadnji podaci.`;
        } else {
            stEl.className = 'mx-status';
            stEl.textContent = state.updatedAt
                ? `Ažurirano ${state.updatedAt.toLocaleTimeString()} · auto ${REFRESH_MS / 1000}s`
                : '';
        }
    }

    function onClick(ev) {
        const t = ev.target.closest && ev.target.closest('button');
        if (!t || !root.contains(t)) return;
        if (t.id === 'mx-refresh') { load(); return; }
        if (t.id === 'mx-more')    { state.shown += PAGE_SIZE; render(); return; }
        if (t.dataset && t.dataset.cls) {
            state.filter = (state.filter === t.dataset.cls) ? null : t.dataset.cls;
            state.shown = PAGE_SIZE;
            render();
        }
    }

    function tick() {
        if (document.hidden) return;
        if (root && root.offsetParent === null) return;
        load();
    }

    function init() {
        root = document.getElementById('metrics-panel');
        if (!root) return;
        if (!root.dataset.mxBound) {
            root.addEventListener('click', onClick);
            document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
            root.dataset.mxBound = '1';
        }
        render();
        load();
        if (state.timer) clearInterval(state.timer);
        state.timer = setInterval(tick, REFRESH_MS);
    }

    function stop() {
        if (state.timer) clearInterval(state.timer);
        state.timer = null;
    }

    window.MetricsPanel = { init, refresh: load, stop };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
