from pathlib import Path

from core import odluke, zavrsi


def test_rebuild_dobiva_ime_knjige(monkeypatch, tmp_path):
    monkeypatch.setattr(odluke, "PUTANJA", tmp_path / "o.jsonl")
    monkeypatch.setattr(zavrsi, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(zavrsi, "STATUS_FILE", tmp_path / "logs" / "st.json")
    monkeypatch.setattr(zavrsi, "ISPRAVCI", tmp_path / "isp")
    monkeypatch.setattr(zavrsi, "STATUS", {"stanje": "nema"})
    monkeypatch.setattr(zavrsi, "_backup_styled", lambda *a, **k: None)
    pozivi = []

    def lazni(cmd, log, timeout=None):
        pozivi.append([str(c) for c in cmd])
        return 1, ""

    monkeypatch.setattr(zavrsi, "_cmd", lazni)
    ck = tmp_path / "ck"
    ck.mkdir()
    st = zavrsi.pokreni("Delacroix", Path("/x/Long Name -- Anna.epub"), ck)
    assert pozivi, "rebuild nije pozvan"
    assert pozivi[0][1:] == ["tools/rebuild_knjiga.py", "/x/Long Name -- Anna.epub", "Delacroix"]
    assert st["stanje"] == "pao"
