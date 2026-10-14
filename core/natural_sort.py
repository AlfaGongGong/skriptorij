# core/natural_sort.py
# FIX 30.08.2026: html_files liste (run.py, retro.py, tts.py,
# api/routes/processing.py) su se sortirale leksikografski
# (key=lambda x: x.name), pa je "chapter10.xhtml" < "chapter2.xhtml"
# alfabetski — poglavlja su zavrsavala u pogresnom redoslijedu u
# toc_entries -> NCX navMap -> "Chapters" lista u citacu (Moon Reader
# i slicni EPUB2 citaci grade tu listu iz NCX-a, ne iz OPF spine-a).
# Ovaj helper razdvaja ime fajla na tekst/broj segmente i poredi
# brojeve numericki umjesto kao stringove.

import re

_NUM_RE = re.compile(r"(\d+)")


def natural_sort_key(path):
    """Prirodni sort key za Path objekte.

    'chapter2.xhtml' < 'chapter10.xhtml' (numericki), ne
    'chapter10.xhtml' < 'chapter2.xhtml' (leksikografski).
    """
    name = path.name if hasattr(path, "name") else str(path)
    parts = _NUM_RE.split(name)
    return tuple(int(p) if p.isdigit() else p.lower() for p in parts)
