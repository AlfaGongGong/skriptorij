"""
core/kalkovi/dijalog.py
Kategorija: Dijalog-specifični kalkovi, srbizmi u govoru,
            i tipografska normalizacija navodnika (~45 zamjena)
Autor: BooklyFi QA pipeline — V10.3+

NAPOMENA o navodnicima:
  HR standard: "tekst" ili »tekst«
  Engleski standard koji AI koristi: "tekst" ili 'tekst'
  Srpski dijalog: „tekst"
  Ova lista normalizira na dvostruke navodnike ASCII stila (""),
  što je kompatibilno s većinom EPUB renderera (Moon+ Reader).
  Ako projekt zahtijeva »«, zamijeni zamjenski string ispod.

NAPOMENA o em-crtici:
  HR književni standard koristi crtu (—) ispred replike u dijalogu.
  AI često koristi kratku crtu (-) ili srednju (–).
"""

# ── Tipografija navodnika ─────────────────────────────────────────────────
# Pretvaramo sve varijante navodnika u konzistentni oblik.
# Red je bitan: specifičnije (trostruki, ugaoni) ispred jednostavnih.

DIJALOG_TIPOGRAFIJA = [
    # FIX 2026-09-27 v5: Patterni prihvaćaju SVE kombinacije
    # tipografskih + ASCII navodnika (AI često miješa).

    # Srpski otvarajući „ → zamijeni s ASCII " + sadržaj + zatvori s "
    # Prihvaća: „tekst"  „tekst"  „tekst"  „tekst"
    (r'\u201e([^"\u201c\u201d\u00bb\u00ab]*?)[\u201c\u201d"]', r'"\1"'),

    # Srpski otvarajući „ s ugaonim zatvaranjem (rijetko, ali moguće)
    (r'\u201e([^"\u201c\u201d\u00bb\u00ab]*?)\u00ab', r'"\1"'),

    # Ugaoni »tekst« → ASCII "tekst"
    (r'\u00bb([^"\u00bb\u00ab]*?)\u00ab', r'"\1"'),
    (r'\u203a([^\u2039\u203a]*?)\u2039', r'"\1"'),

    # Pametni ASCII → ASCII " (curly → straight)
    (r'\u201c([^"\u00bb\u00ab\u201c\u201d]*?)\u201d', r'"\1"'),

    # Jednostruki tipografski → ASCII '
    (r'\u2018([^\u2018\u2019]*?)\u2019', r"'\1'"),

    # Em-crtica ispred replike: - ili – na početku retka → —
    (r'(?m)^(\s*)-\s+(?=[A-ZČĆŠŽĐ"„»\u201c\u201e])', r'\1— '),
    (r'(?m)^(\s*)[\u2013\u2014]\s+(?=[A-ZČĆŠŽĐ"„»\u201c\u201e])', r'\1— '),

    # Višestruke točke → pravo trotočje
    (r'\.{3,4}', '\u2026'),
    (r'\.\s\.\s\.', '\u2026'),
]





# ── Poštapalice i srbizmi u dijalogu ─────────────────────────────────────

DIJALOG_KALKOVI = [

    # "Dobro" kao srbistički filler na početku odgovora u dijalogu
    # Samo kad je izolirano ili na početku replike, ne u frazama
    (r'(?m)^(—\s*|"\s*)Dobro,\s+(?=(?:ali|međutim|dakle|tako))',
                                               r'\1'),     # "Dobro, ali → ali

    # Uobičajene srpske uzrečice koje AI ubacuje
    (r'\bvaži\b',                              'dogovoreno'),
    (r'\bvaži\s*,',                            'dogovoreno,'),
    (r'\bVaži\b',                              'Dogovoreno'),
    (r'\bkako\s+god\b',                        'kako mu drago'),
    (r'\bkako\s+god\s+ti\b',                  'kako ti'),

    # Srpska forma odricanja u dijalogu
    (r'\bNije\s+valjda\b',                     'Valjda nije'),
    (r'\bnema\s+na\s+čemu\b',                  'nema na čemu'),   # OK u BS ali provjeriti

    # "Šta" umjesto "što" — dosljedan ekavizam/srbizam u dijalogu
    (r'\bŠta\b',                               'Što'),
    (r'\bšta\b',                               'što'),
    (r'\bŠta\s+to\b',                          'Što to'),
    (r'\bšta\s+to\b',                          'što to'),

    # "Ko" umjesto "tko" (srbizam u dijalogu)
    (r'(?<![a-zčćšžđ])ko\s+je\b',             'tko je'),
    (r'(?<![a-zčćšžđ])Ko\s+je\b',             'Tko je'),
    (r'(?<![a-zčćšžđ])ko\s+to\b',             'tko to'),
    (r'(?<![a-zčćšžđ])Ko\s+to\b',             'Tko to'),
    (r'(?<![a-zčćšžđ])ko\s+si\b',             'tko si'),
    (r'(?<![a-zčćšžđ])Ko\s+si\b',             'Tko si'),
    (r'(?<![a-zčćšžđ])ko\s+zna\b',            'tko zna'),
    (r'(?<![a-zčćšžđ])Ko\s+zna\b',            'Tko zna'),
    (r'(?<![a-zčćšžđ])ko\s+god\b',            'tko god'),
    (r'(?<![a-zčćšžđ])Ko\s+god\b',            'Tko god'),

    # "Kad" → "kada" (stilska preferencija u književnom tekstu)
    # ISKLJUČENO — "kad" je prihvatljivo u BS, ne patch-amo
    # (r'\bkad\b', 'kada'),

    # Anglizam "OK" u dijalogu → lokalna forma
    (r'\bOK\b',                                'U redu'),
    (r'\bOk\b(?!\w)',                          'U redu'),

    # Srpska forma "izvini" → "ispričaj se" / "oprosti"
    (r'\bIzvini\b',                            'Oprosti'),
    (r'\bizvini\b',                            'oprosti'),
    (r'\bIzvinite\b',                          'Oprostite'),
    (r'\bizvinite\b',                          'oprostite'),
    (r'\bIzvinjavaj\b',                        'Ispričavaj'),
    (r'\bizvinjavaj\b',                        'ispričavaj'),

    # Srpska forma "molim" bez "te/vas" → dodaj (kontekstualno sigurno)
    # ISKLJUČENO — "molim" je ok u BS kao pozdrav/uljudnost

    # "servisi" → "usluge" u dijalogu
    (r'\bservise\b',                           'usluge'),
    (r'\bservisima\b',                         'uslugama'),
    (r'\bservis\b(?!\s+(?:vozila|automobila|auta|kola|motora|bicikla))',
                                               'usluga'),

]

# Objedinjena lista za __init__.py
DIJALOG = DIJALOG_TIPOGRAFIJA + DIJALOG_KALKOVI
