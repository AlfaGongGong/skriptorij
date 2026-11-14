from core.chk_cilj import cilj_za_upis, sa_zaglavljem


def test_lektura_i_prevod_idu_na_osnovni(tmp_path):
    assert cilj_za_upis(tmp_path / "ch1.html_blok_3.lektura.chk") == tmp_path / "ch1.html_blok_3.chk"
    assert cilj_za_upis(tmp_path / "ch1.html_blok_3.prevod.chk") == tmp_path / "ch1.html_blok_3.chk"


def test_osnovni_ostaje(tmp_path):
    p = tmp_path / "index_split_001.html_blok_0.chk"
    assert cilj_za_upis(p) == p


def test_zaglavlje_se_cuva(tmp_path):
    src = tmp_path / "a_blok_0.lektura.chk"
    src.write_text("<!-- chunk_sha:v2:GEMINI::abc123 -->\nstari tekst", encoding="utf-8")
    assert sa_zaglavljem(src, "novi tekst") == "<!-- chunk_sha:v2:GEMINI::abc123 -->\nnovi tekst"


def test_zaglavlje_se_ne_dupla(tmp_path):
    src = tmp_path / "a_blok_0.lektura.chk"
    src.write_text("<!-- chunk_sha:x -->\nstari", encoding="utf-8")
    t = "<!-- chunk_sha:y -->\nnovi"
    assert sa_zaglavljem(src, t) == t


def test_bez_zaglavlja_i_bez_fajla(tmp_path):
    assert sa_zaglavljem(tmp_path / "nema.chk", "novi") == "novi"
