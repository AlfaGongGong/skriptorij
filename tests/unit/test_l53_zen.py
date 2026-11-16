"""L53: ZEN MODE ne smije sakriti karticu s tabovima (audit-log je u tabu Strucnjak)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "static/js/main.js").read_text("utf-8")
HTML = (ROOT / "templates/index.html").read_text("utf-8")


def test_zen_skriva_audit_samo_u_dashboardu():
    assert "auditCard !== dashboard && dashboard.contains(auditCard)" in JS


def test_audit_log_je_u_kartici_s_tabovima_a_ne_u_dashboardu():
    i_audit = HTML.index('id="audit-log"')
    i_dash = HTML.index('id="dashboard-panel"')
    i_dash_kraj = HTML.index("</section>", i_dash)
    assert not (i_dash < i_audit < i_dash_kraj)
