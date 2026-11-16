"""R2b: kompaktna gornja traka i pune oznake tabova; ugovor id-eva iz R2a/R1 ostaje."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "templates/index.html").read_text("utf-8")
CSS = (ROOT / "static/css/design.css").read_text("utf-8")
VJS = (ROOT / "static/js/ui/views.js").read_text("utf-8")

TABOVI_PRIJE = ['tab-quality', 'tab-epub', 'tab-review', 'tab-history', 'panel-stil', 'panel-tts-filter', 'tab-expert', 'tab-monitor']
IDS_PRIJE = ['app', 'audit-filter-bar', 'audit-log', 'audit-scroll-indicator', 'auto-mode-desc', 'auto-mode-display', 'auto-mode-icon', 'auto-mode-label', 'auto-stil', 'bottom-nav', 'brand-logo', 'brand-title', 'btn-add-key', 'btn-audit-resume', 'btn-cancel-tts', 'btn-close-download-modal', 'btn-confirm-download-live', 'btn-download-final', 'btn-history-delete-selected', 'btn-load-qa-flags', 'btn-next-chapter', 'btn-pause', 'btn-prev-chapter', 'btn-refresh-quality', 'btn-reload-epub', 'btn-reset', 'btn-resume', 'btn-select-tts', 'btn-send-marked', 'btn-show-setup', 'btn-show-setup-dashboard', 'btn-start', 'btn-stop', 'btn-wizard-back', 'btn-wizard-next', 'confirm-body', 'confirm-icon', 'confirm-modal', 'confirm-no', 'confirm-title', 'confirm-yes', 'dashboard-panel', 'download-modal', 'download-modal-title', 'download-strip', 'download-strip-meta', 'download-strip-progress', 'download-strip-subtitle', 'download-strip-title', 'epub-chapter-label', 'epub-content', 'epub-no-content', 'epub-reader-wrap', 'expert-fleet-container', 'expert-fleet-health-badge', 'file-input', 'guide-after-upload', 'history-controls', 'history-empty', 'history-list', 'history-select-all', 'history-selected-count', 'hl-highlights', 'hl-stats-bar', 'key-provider-select', 'key-value-input', 'keys-list-container', 'kk-fajl', 'kk-faza', 'kk-faza-detalj', 'kk-knjiga', 'live-preview-block', 'modal-body-text', 'modal-pct-fill', 'modal-pct-label', 'model-select', 'mon-auto', 'mon-body', 'mon-refresh', 'mon-reset', 'mon-utc', 'p26-revizija-fab', 'panel-stil', 'panel-tts-filter', 'preflight-blocks', 'preflight-body', 'preflight-book', 'preflight-calls', 'preflight-cancel', 'preflight-eta', 'preflight-files', 'preflight-keys', 'preflight-modal', 'preflight-modal-title', 'preflight-mode', 'preflight-start', 'preview-en', 'preview-en-box', 'preview-en-label', 'preview-hr', 'progress-bar', 'progress-eta', 'progress-pct-text', "qa-edit-' + f.blok + '", 'qa-flags-empty', 'qa-flags-list', 'qa-flags-section', 'qs-avg-big', 'qs-avg-ring', 'qs-box-critical', 'qs-box-poor', 'qs-critical', 'qs-excellent', 'qs-files-container', 'qs-good', 'qs-grade-display', 'qs-grade-emoji', 'qs-grade-score', 'qs-grade-text', 'qs-metric-ok', 'qs-metric-reject', 'qs-metric-review', 'qs-metric-truncated', 'qs-metrics-grid', 'qs-poor', 'qs-print-ready-bar', 'qs-print-ready-pct', 'qs-refix-bar', 'qs-refix-info', 'qs-relektura-avg', 'qs-relektura-banner', 'qs-relektura-count', 'qs-relektura-label', 'qs-relektura-status-icon', 'qs-select-bar', 'qs-total-label', 'quality-badge', 'quality-content', 'quality-live-badge', 'quality-loading', 'report-avg', 'report-blocks', 'report-body', 'report-book', 'report-close', 'report-critical', 'report-download', 'report-duration', 'report-excellent', 'report-good', 'report-modal', 'report-modal-title', 'report-ok', 'report-output-path', 'report-poor', 'report-reject', 'report-review', 'report-trunc', 'review-delete-btn', 'review-empty-banner', 'review-filename', 'review-hint-count', 'review-legend', 'review-multi-count', 'review-multi-count2', 'review-preview-panel', 'review-save-btn', 'review-score-badge', 'review-text', 'selected-book-info', 'selected-book-name', 'setup-panel', 'st-audit-log', 'st-btn-clear-log', 'st-btn-download-css', 'st-btn-download-epub', 'st-btn-style', 'st-file-input', 'st-log-card', 'st-opt-ai-toc', 'st-opt-dropcaps', 'st-opt-ornaments', 'st-opt-toc', 'st-result-card', 'st-selected-book', 'st-selected-row', 'st-stat-chapters', 'st-stat-dropcaps', 'st-stat-toc', 'st-status-dot', 'st-status-row', 'st-status-text', 'st-upload-status', 'st-upload-zone', 'stat-avg-quality', 'stat-engine', 'stat-file', 'stat-fleet-active', 'stat-ok', 'stat-skipped', 'status-dot', 'status-text', 'step-1', 'step-2', 'tab-btn-monitor', 'tab-btn-stil', 'tab-epub', 'tab-expert', 'tab-history', 'tab-monitor', 'tab-quality', 'tab-review', 'theme-btn', 'tier-pills', 'toast-container', 'tts-audit-log', 'tts-btn-apply-edited', 'tts-btn-apply-file', 'tts-btn-clear-log', 'tts-btn-close-preview', 'tts-btn-preview', 'tts-btn-scan', 'tts-file-input', 'tts-log-card', 'tts-pairs-count', 'tts-panel', 'tts-preview-card', 'tts-replacement-info', 'tts-replacement-status', 'tts-replacement-textarea', 'tts-results-card', 'tts-selected-book', 'tts-selected-row', 'tts-stat-applied', 'tts-stat-entities', 'tts-stat-found', 'tts-status-dot', 'tts-status-row', 'tts-status-text', 'tts-upload-status', 'tts-upload-zone', 'upload-status', 'upload-zone', 'wizard-page-1', 'wizard-page-2']


def test_idevi_ostaju_samo_view_title_novi():
    ids = set(re.findall(r'\bid="([^"]+)"', HTML))
    nedostaje = set(IDS_PRIJE) - ids
    assert not nedostaje, nedostaje
    assert ids - set(IDS_PRIJE) <= {"view-title"}


def test_data_tab_isti():
    assert re.findall(r'data-tab="([^"]+)"', HTML) == TABOVI_PRIJE


def test_pune_oznake_tabova():
    for t in ("Kvaliteta", "Pregled", "Revizija", "Povijest", "Stil", "TTS", "Stručnjak", "Monitor"):
        assert re.search(r'class="tab-btn[^"]*"[^>]*>[^<]*' + t, HTML), t
    assert 'id="quality-badge"' in HTML


def test_view_title_u_headeru():
    m = re.search(r'<header class="app-header">(.*?)</header>', HTML, re.S)
    assert m and 'id="view-title"' in m.group(1)


def test_css_app_bar():
    assert "R2b" in CSS and ".view-title" in CSS and "position: sticky" in CSS
    assert "min-height: 44px" in CSS


def test_views_js_naslov():
    assert "updateTitle" in VJS and "view-title" in VJS
