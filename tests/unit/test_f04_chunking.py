import inspect

import pytest

from core import chunking
from core.chunking import ChunkingError, _otisak, chunk_html


def test_zadani_limit_je_500():
    assert inspect.signature(chunk_html).parameters["max_words"].default == 500


def test_span_oko_svake_rijeci():
    html = "<p>" + " ".join("<span>w%d</span>" % i for i in range(600)) + "</p>"
    ch = chunk_html(html, 500)
    assert len(ch) >= 2
    for c in ch:
        assert _otisak(c)[0] <= 500
    assert sum(_otisak(c)[0] for c in ch) == 600


def test_img_hr_i_sidro_na_pocetku_ostaju():
    html = '<a id="s1"></a><img src="a.png"/><hr/><p>Ona dolazi kući.</p>'
    ch = chunk_html(html, 500)
    r, n_img, n_hr, ids = _otisak("".join(ch))
    assert (n_img, n_hr, ids) == (1, 1, {"s1"})
    assert r == 3


def test_img_na_pocetku_prije_velikog_odlomka():
    veliki = "<p>" + " ".join(["riječ"] * 700) + "</p>"
    ch = chunk_html('<img src="x.png"/>' + veliki, 500)
    assert _otisak("".join(ch))[1] == 1
    assert "<img" in ch[0]


def test_zarez_rez_cuva_brojeve_i_dijeli_veliki_dio():
    s = "uno, " + " ".join(["w"] * 600) + ", dos 1,000 tres"
    dijelovi = chunking._split_long_sentence(s, 500)
    assert all(len(d.split()) <= 500 for d in dijelovi)
    assert sum(len(d.split()) for d in dijelovi) == len(s.split())
    assert "1,000" in " ".join(dijelovi)


def test_nema_razmaka_usred_rijeci_uz_inline_oznaku():
    html = "<p>" + "reč " * 520 + "stig<i>la</i> kući.</p>"
    ch = chunk_html(html, 500)
    assert "stig<i>la</i>" in "".join(ch)
    for c in ch:
        assert _otisak(c)[0] <= 500


def test_escape_i_komentar():
    html = "<p>a &lt; b &amp; c</p><!-- k --><p>drugo</p>"
    ch = chunk_html(html, 500)
    j = "".join(ch)
    assert "a &lt; b &amp; c" in j and "<!-- k -->" in j


def test_provjera_sacuvanosti_baca_gresku(monkeypatch):
    monkeypatch.setattr(chunking, "_grupisi_djecu", lambda ch, mw: [["<p>Samo ovo.</p>"]])
    with pytest.raises(ChunkingError):
        chunk_html('<p>Samo ovo.</p><img src="a.png"/><p>I još.</p>', 500)


def test_nema_bloka_bez_rijeci():
    html = "<p>" + " ".join(["riječ"] * 700) + "</p><img src='x.png'/>"
    ch = chunk_html(html, 500)
    assert all(_otisak(c)[0] > 0 for c in ch)
    assert _otisak("".join(ch))[1] == 1
    assert "<img" in ch[-1]
