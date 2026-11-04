# P0.3 — tag-aware zamjena imena (epub/name_replacer._word_boundary_replace)
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from epub.name_replacer import _word_boundary_replace as R  # noqa: E402

CASES = [
    ("obicno", "<p>Nail je došao.</p>", "Nail", "Klover", "<p>Klover je došao.</p>"),
    ("dropcap", '<p><span class="dropcap">N</span>ail je došao.</p>', "Nail", "Klover",
     '<p><span class="dropcap">K</span>lover je došao.</p>'),
    ("em_split", "<p><em>Nai</em>l spava.</p>", "Nail", "Klover", "<p><em>Klo</em>ver spava.</p>"),
    ("dropcap_Judge", '<p><span class="dropcap">J</span>udge reče.</p>', "Judge", "Sudac",
     '<p><span class="dropcap">S</span>udac reče.</p>'),
    ("vise_pojava", '<p><span class="dropcap">N</span>ail, <em>Nail</em> i Nail.</p>', "Nail", "Klin",
     '<p><span class="dropcap">K</span>lin, <em>Klin</em> i Klin.</p>'),
    ("ne_preko_bloka", "<p>Na</p><p>il</p>", "Nail", "Klover", "<p>Na</p><p>il</p>"),
    ("ne_podrijec", "<p>Nailed it.</p>", "Nail", "Klover", "<p>Nailed it.</p>"),
    ("ne_nastavak_iza_taga", "<p>Nail<em>ova</em> kuća</p>", "Nail", "Klover",
     "<p>Nail<em>ova</em> kuća</p>"),
    ("velika_slova", "<p>NAIL viče.</p>", "Nail", "Klover", "<p>KLOVER viče.</p>"),
    ("atribut_ostaje", '<p class="Nail">Nail</p>', "Nail", "Klover", '<p class="Nail">Klover</p>'),
    ("nema_pojave", "<p>Ništa ovdje.</p>", "Nail", "Klover", "<p>Ništa ovdje.</p>"),
    ("prazan_pattern", "<p>Nail</p>", "", "Klover", "<p>Nail</p>"),
]


def test_slucajevi():
    bad = []
    for ime, h, p, r, exp in CASES:
        got = R(h, p, r)
        if got != exp:
            bad.append("%s: dobijeno %r, očekivano %r" % (ime, got, exp))
    assert not bad, "\n".join(bad)


if __name__ == "__main__":
    ok = 0
    for ime, h, p, r, exp in CASES:
        got = R(h, p, r)
        if got == exp:
            ok += 1
        else:
            print("XX", ime, repr(got), "!=", repr(exp))
    print("%d/%d" % (ok, len(CASES)))
    sys.exit(0 if ok == len(CASES) else 1)
