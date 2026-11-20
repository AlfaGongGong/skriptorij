# -*- coding: utf-8 -*-
"""core/popravak_kapija.py — G34: kapija za popravke koji prepisuju .chk (verifier-popravak, tockasti popravak).

Glavni put (pipeline) ne upisuje .chk bez strukturne kapije (G3), provjere prekinutog teksta i EN ostataka.
Popravci verifikatora su drugi put do istog .chk-a i do sada ga nisu imali. Ovdje je isti skup provjera,
deterministicki, bez AI. Popravak se prihvaca samo ako NIJE gori od starog .chk-a:
  - nema NEPREVEDENO markera, nije prekinut/odsjecen,
  - EN ostaci <= 0.10 (ili ne veci nego u starom),
  - G3 razlozi: bez razloga, ili ne vise nego u starom .chk-u.
Greska u samoj kapiji = odbij (ostaje stari .chk).
"""
from __future__ import annotations

import os
import re

_ZAGLAVLJE = re.compile(r"<!--\s*chunk_sha[^>]*-->\s*\n?")


def _bez_zaglavlja(t):
    return _ZAGLAVLJE.sub("", t or "")


def _g3(en_html, hr_html, rel_glosar):
    from core.strukturna_kapija import provjeri

    try:
        return list(provjeri(en_html, hr_html, rel_glosar))
    except Exception:
        # oblik glosara nije kompatibilan: provjeri bez glosara (stroze za imena, ali sigurno)
        return list(provjeri(en_html, hr_html, None))


def prihvatljiv(en_html, hr_novo, hr_staro=None, rel_glosar=None):
    """-> (True, []) ili (False, [razlozi]). Nikad ne baca."""
    razlozi = []
    try:
        novo = _bez_zaglavlja(hr_novo)
        staro = _bez_zaglavlja(hr_staro) if hr_staro is not None else None
        if not novo.strip():
            return False, ["prazan tekst"]
        if "NEPREVEDENO" in novo:
            razlozi.append("NEPREVEDENO marker")

        from processing.pipeline import _je_prekinut_tekst

        if _je_prekinut_tekst(en_html, novo):
            razlozi.append("prekinut/odsjecen tekst")

        from core.text_utils import _detektuj_en_ostatke

        en_n = _detektuj_en_ostatke(novo)
        if en_n > 0.10:
            en_s = _detektuj_en_ostatke(staro) if staro is not None else None
            if en_s is None or en_n > en_s:
                razlozi.append("engleski ostaci %.2f" % en_n)

        if os.environ.get("BOOKLYFI_G3", "1") != "0":
            from core.quality import _je_nonprose_blok

            if not _je_nonprose_blok(en_html):
                g_n = _g3(en_html, novo, rel_glosar)
                if g_n:
                    g_s = _g3(en_html, staro, rel_glosar) if staro is not None else None
                    if g_s is None or len(g_n) > len(g_s):
                        razlozi.append("G3: " + "; ".join(g_n[:3]))
    except Exception as e:
        return False, ["greska kapije: %s" % e]
    return (not razlozi), razlozi
