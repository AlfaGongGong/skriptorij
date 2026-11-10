import os
import re
import sys

KOR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, KOR)


def _c(p):
    return open(os.path.join(KOR, p), encoding="utf-8").read()


def test_tabovi_aria():
    h = _c("templates/index.html")
    assert 'role="tablist"' in h
    tabs = re.findall(r'<button class="tab-btn[^"]*" role="tab" aria-controls="([^"]+)" aria-selected="(true|false)"', h)
    assert len(tabs) == 8
    assert sum(1 for _, s in tabs if s == "true") == 1
    for cil, _ in tabs:
        assert 'role="tabpanel" class="tab-panel' in h and 'id="%s"' % cil in h


def test_nema_dup_id():
    ids = re.findall(r'\bid="([^"]+)"', _c("templates/index.html"))
    assert not {i for i in ids if ids.count(i) > 1}


def test_modali_labelledby_cilj_postoji():
    h = _c("templates/index.html")
    ciljevi = re.findall(r'aria-modal="true" aria-labelledby="([^"]+)"', h)
    assert len(ciljevi) == 4
    for c in ciljevi:
        assert 'id="%s"' % c in h, c


def test_switchtab_ažurira_aria():
    assert 'setAttribute("aria-selected"' in _c("static/js/main.js")


def test_stil_auto_print():
    p = _c("processing/pipeline.py")
    assert 'print(f"[stil-auto]' in p
