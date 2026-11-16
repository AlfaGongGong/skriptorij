"""R4: dashboard: sklopivi live status i logovi, kontrast ok-text, ugovor id-eva ostaje."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "static/css/design.css").read_text("utf-8")
HTML = (ROOT / "templates/index.html").read_text("utf-8")
SW = (ROOT / "static/sw.js").read_text("utf-8")
DJS = ROOT / "static/js/ui/dashboard.js"
IDS_PRIJE = ['toast-container', 'download-modal', 'download-modal-title', 'modal-body-text', 'modal-pct-fill', 'modal-pct-label', 'btn-close-download-modal', 'btn-confirm-download-live', 'report-modal', 'report-modal-title', 'report-body', 'report-book', 'report-duration', 'report-blocks', 'report-avg', 'report-excellent', 'report-good', 'report-poor', 'report-critical', 'report-ok', 'report-review', 'report-reject', 'report-trunc', 'report-output-path', 'report-close', 'report-download', 'preflight-modal', 'preflight-modal-title', 'preflight-body', 'preflight-book', 'preflight-mode', 'preflight-files', 'preflight-blocks', 'preflight-calls', 'preflight-eta', 'preflight-keys', 'preflight-cancel', 'preflight-start', 'confirm-modal', 'confirm-icon', 'confirm-title', 'confirm-body', 'confirm-no', 'confirm-yes', 'app', 'brand-logo', 'brand-title', 'status-dot', 'status-text', 'quality-live-badge', 'theme-btn', 'btn-show-setup', 'view-title', 'setup-panel', 'step-1', 'step-2', 'wizard-page-1', 'upload-zone', 'file-input', 'upload-status', 'guide-after-upload', 'btn-wizard-next', 'wizard-page-2', 'selected-book-info', 'selected-book-name', 'btn-wizard-back', 'tier-pills', 'model-select', 'auto-mode-display', 'auto-mode-icon', 'auto-mode-label', 'auto-mode-desc', 'btn-select-tts', 'tts-panel', 'btn-cancel-tts', 'auto-stil', 'btn-start', 'dashboard-panel', 'download-strip', 'download-strip-title', 'download-strip-subtitle', 'download-strip-progress', 'progress-bar', 'download-strip-meta', 'progress-pct-text', 'progress-eta', 'btn-download-final', 'kk-knjiga', 'kk-fajl', 'kk-faza', 'kk-faza-detalj', 'stat-engine', 'stat-file', 'stat-ok', 'stat-skipped', 'stat-fleet-active', 'stat-avg-quality', 'live-preview-block', 'preview-en-box', 'preview-en-label', 'preview-en', 'preview-hr', 'btn-pause', 'btn-resume', 'btn-reset', 'btn-stop', 'btn-show-setup-dashboard', 'quality-badge', 'tab-btn-stil', 'tab-btn-monitor', 'tab-quality', 'quality-loading', 'quality-content', 'qs-relektura-banner', 'qs-relektura-status-icon', 'qs-relektura-label', 'qs-relektura-avg', 'qs-relektura-count', 'qs-grade-display', 'qs-grade-emoji', 'qs-grade-text', 'qs-grade-score', 'qs-avg-ring', 'qs-avg-big', 'qs-total-label', 'btn-refresh-quality', 'btn-send-marked', 'qs-excellent', 'qs-good', 'qs-box-poor', 'qs-poor', 'qs-box-critical', 'qs-critical', 'qs-select-bar', 'qs-metrics-grid', 'qs-metric-ok', 'qs-metric-review', 'qs-metric-reject', 'qs-metric-truncated', 'qs-refix-bar', 'qs-refix-info', 'qs-print-ready-pct', 'qs-print-ready-bar', 'qs-files-container', 'tab-history', 'history-controls', 'history-select-all', 'history-selected-count', 'btn-history-delete-selected', 'history-empty', 'qa-flags-section', 'btn-load-qa-flags', 'qa-flags-empty', 'qa-flags-list', 'history-list', 'tab-epub', 'epub-no-content', 'epub-reader-wrap', 'epub-chapter-label', 'btn-reload-epub', 'btn-prev-chapter', 'btn-next-chapter', 'epub-content', 'tab-review', 'review-empty-banner', 'review-legend', 'review-filename', 'review-hint-count', 'review-save-btn', 'review-delete-btn', 'review-score-badge', 'hl-highlights', 'review-text', 'hl-stats-bar', 'review-multi-count', 'review-multi-count2', 'review-preview-panel', 'tab-expert', 'expert-fleet-health-badge', 'expert-fleet-container', 'audit-filter-bar', 'audit-log', 'audit-scroll-indicator', 'btn-audit-resume', 'key-provider-select', 'key-value-input', 'btn-add-key', 'keys-list-container', 'panel-stil', 'st-upload-zone', 'st-file-input', 'st-upload-status', 'st-selected-row', 'st-selected-book', 'st-opt-dropcaps', 'st-opt-ornaments', 'st-opt-toc', 'st-opt-ai-toc', 'st-btn-style', 'st-status-row', 'st-status-dot', 'st-status-text', 'st-result-card', 'st-stat-chapters', 'st-stat-dropcaps', 'st-stat-toc', 'st-btn-download-epub', 'st-btn-download-css', 'st-log-card', 'st-btn-clear-log', 'st-audit-log', 'panel-tts-filter', 'tts-upload-zone', 'tts-file-input', 'tts-upload-status', 'tts-selected-row', 'tts-selected-book', 'tts-replacement-info', 'tts-replacement-status', 'tts-btn-preview', 'tts-btn-scan', 'tts-btn-apply-file', 'tts-status-row', 'tts-status-dot', 'tts-status-text', 'tts-results-card', 'tts-stat-entities', 'tts-stat-found', 'tts-stat-applied', 'tts-log-card', 'tts-btn-clear-log', 'tts-audit-log', 'tts-preview-card', 'tts-btn-apply-edited', 'tts-btn-close-preview', 'tts-replacement-textarea', 'tts-pairs-count', 'tab-monitor', 'mon-utc', 'mon-reset', 'mon-auto', 'mon-refresh', 'mon-body', "qa-edit-' + f.blok + '", 'bottom-nav', 'p26-revizija-fab']


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _cr(a, b):
    la, lb = _lum(a), _lum(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _tok(n, blok):
    m = re.search(re.escape(blok) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert m, blok
    mm = re.search(r"--" + n + r":\s*(#[0-9a-fA-F]{6})", m.group(1))
    assert mm, (n, blok)
    return mm.group(1)


def test_ok_text_kontrast_obje_teme():
    for blok in (":root", "body.light"):
        for bg in ("bg-1", "bg-2"):
            assert _cr(_tok("ok-text", blok), _tok(bg, blok)) >= 4.5, (blok, bg)


def test_idevi_nepromijenjeni():
    assert re.findall(r'\bid="([^"]+)"', HTML) == IDS_PRIJE


def test_logovi_u_details():
    for lid in ("st-audit-log", "tts-audit-log"):
        assert re.search(r'<details class="log-details"><summary>[^<]*</summary><div class="audit-log" id="' + lid + '">', HTML), lid


def test_dashboard_js_ukljucen_i_precache():
    assert DJS.exists()
    assert "/static/js/ui/dashboard.js" in HTML
    assert '"/static/js/ui/dashboard.js"' in SW


def test_css_r4():
    assert "R4:" in CSS and ".human-timeline.collapsed" in CSS and ".log-details" in CSS


@pytest.mark.skipif(shutil.which("node") is None, reason="node nije instaliran")
def test_dashboard_js_sintaksa():
    r = subprocess.run(["node", "--check", str(DJS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
