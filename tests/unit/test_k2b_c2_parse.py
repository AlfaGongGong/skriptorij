class _L:
    def __init__(self):
        self.w = []
        self.d = []
    def warning(self, *a, **k):
        self.w.append(a)
    def debug(self, *a, **k):
        self.d.append(a)
    def __getattr__(self, n):
        return lambda *a, **k: None


def test_obican_tekst_bez_upozorenja(monkeypatch):
    import core.text_utils as T
    L = _L()
    monkeypatch.setattr(T, "logger", L)
    T._smart_extract("Ovo je obican prijevod bez JSON-a.")
    assert not [a for a in L.w if "C2_parse" in str(a)]


def test_pokvaren_json_upozorenje(monkeypatch):
    import core.text_utils as T
    L = _L()
    monkeypatch.setattr(T, "logger", L)
    T._smart_extract('{"korektura": "abc')
    assert [a for a in L.w if "C2_parse" in str(a)]
