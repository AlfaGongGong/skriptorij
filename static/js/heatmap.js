"use strict";

// ═══════════════════════════════════════════════════════════
// QUALITY HEATMAP RENDER
// Učitava se poslije main.js
// ═══════════════════════════════════════════════════════════

function renderiraj_heatmap(container, byFile, allScores) {
    if (!byFile || Object.keys(byFile).length === 0) {
        container.innerHTML = '<div style="color:var(--tx-3);padding:12px;text-align:center;">Nema podataka.</div>';
        return;
    }

    const fajlovi = Object.keys(byFile).sort(function(a, b) {
        const na = a.match(/\d+/g);
        const nb = b.match(/\d+/g);
        if (na && nb) {
            for (let i = 0; i < Math.min(na.length, nb.length); i++) {
                const d = parseInt(na[i]) - parseInt(nb[i]);
                if (d !== 0) return d;
            }
        }
        return a.localeCompare(b);
    });

    // Legenda
    let html = '<div class="qh-legend">';
    html += '<span style="color:var(--tx-2);font-weight:700;">LEGENDA:</span>';
    html += '<span class="qh-legend-item"><span class="qh-legend-dot excellent"></span> ≥ 8.5</span>';
    html += '<span class="qh-legend-item"><span class="qh-legend-dot good"></span> 6.5–8.5</span>';
    html += '<span class="qh-legend-item"><span class="qh-legend-dot poor"></span> 4.0–6.5</span>';
    html += '<span class="qh-legend-item"><span class="qh-legend-dot critical"></span> &lt; 4.0</span>';
    html += '<span style="margin-left:auto;color:var(--tx-3);">Klik na blok → detalj</span>';
    html += '</div>';

    // Grid
    html += '<div class="qh-container">';
    for (const fn of fajlovi) {
        const info = byFile[fn];
        const blocks = info.blocks || [];

        blocks.sort(function(a, b) {
            const ma = a.stem.match(/_blok_(\d+)/);
            const mb = b.stem.match(/_blok_(\d+)/);
            const na = ma ? parseInt(ma[1]) : 0;
            const nb = mb ? parseInt(mb[1]) : 0;
            return na - nb;
        });

        let cellsHtml = '';
        for (const b of blocks) {
            let cls = 'unknown';
            if (b.score >= 8.5) cls = 'excellent';
            else if (b.score >= 6.5) cls = 'good';
            else if (b.score >= 4.0) cls = 'poor';
            else cls = 'critical';

            const m = b.stem.match(/_blok_(\d+)/);
            const blokNum = m ? m[1] : '?';
            const scoreStr = b.score.toFixed(1);
            const title = fn + ' blok ' + blokNum + ': ' + scoreStr + '/10';

            cellsHtml += '<div class="qh-cell ' + cls + '"'
                + ' data-stem="' + b.stem + '"'
                + ' data-score="' + b.score + '"'
                + ' data-blok="' + blokNum + '"'
                + ' title="' + title + '"></div>';
        }

        let avg = info.avg || 0;
        // Fallback: ako avg je 0 ali ima blokova, izračunaj
        if (avg === 0 && blocks.length > 0) {
            const total = blocks.reduce(function(s, b) { return s + (b.score || 0); }, 0);
            avg = total / blocks.length;
        }
        let avgCls = 'good';
        if (avg >= 8.5) avgCls = 'excellent';
        else if (avg >= 6.5) avgCls = 'good';
        else if (avg >= 4.0) avgCls = 'poor';
        else avgCls = 'critical';

        const kratkoIme = fn.length > 20 ? fn.slice(0, 10) + '…' + fn.slice(-8) : fn;

        html += '<div class="qh-file">';
        html += '<div class="qh-file-name" title="' + fn + '">' + kratkoIme + '</div>';
        html += '<div class="qh-heatmap">' + cellsHtml + '</div>';
        html += '<div class="qh-file-stats">' + blocks.length + ' blk</div>';
        html += '<div class="qh-file-avg ' + avgCls + '">' + avg.toFixed(1) + '</div>';
        html += '</div>';
    }
    html += '</div>';

    container.innerHTML = html;

    // Klik na ćeliju
    container.querySelectorAll('.qh-cell').forEach(function(cell) {
        cell.addEventListener('click', function() {
            const stem = cell.dataset.stem;

            // Otvori Reviziju za taj blok
            if (typeof window.otvoriReviziju === 'function') {
                window.otvoriReviziju(stem);
            }

            // Toggle mark za relekturu
            if (typeof _markedForReview !== 'undefined') {
                if (_markedForReview.has(stem)) {
                    _markedForReview.delete(stem);
                    cell.style.outline = '';
                    cell.style.transform = '';
                } else {
                    _markedForReview.add(stem);
                    cell.style.outline = '2px solid var(--amber)';
                    cell.style.transform = 'scale(1.2)';
                }
                if (typeof _updateRefixBar === 'function') _updateRefixBar();
            }
        });

        cell.addEventListener('mouseenter', function() {
            let tip = document.getElementById('qh-tooltip');
            if (!tip) {
                tip = document.createElement('div');
                tip.id = 'qh-tooltip';
                tip.className = 'qh-tooltip';
                document.body.appendChild(tip);
            }
            tip.textContent = cell.title;
            tip.classList.add('visible');

            const rect = cell.getBoundingClientRect();
            tip.style.left = rect.left + 'px';
            tip.style.top = (rect.top - 30) + 'px';
        });

        cell.addEventListener('mouseleave', function() {
            const tip = document.getElementById('qh-tooltip');
            if (tip) tip.classList.remove('visible');
        });
    });
}

window.renderiraj_heatmap = renderiraj_heatmap;
