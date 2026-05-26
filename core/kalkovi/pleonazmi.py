"""
core/kalkovi/pleonazmi.py
Kategorija: Pleonazmi i suvišne konstrukcije (~45 zamjena)
Autor: BooklyFi QA pipeline — V10.3+

Filozofija: Pleonazam je suvišan element koji ne dodaje značenje.
Uklanjamo ga bez gubitka smisla. Redosljed: specifičnije ispred
općenitijeg da nema false-positive kolizija.
"""

PLEONAZMI = [

    # ── 1. Suvišni priložni dodaci uz glagole kretanja/stanja ──────────────
    (r'\bspustiti\s+(?:se\s+)?(?:prema\s+)?dolje\b',     'spustiti se'),
    (r'\bspusti\s+(?:se\s+)?(?:prema\s+)?dolje\b',       'spusti se'),
    (r'\bspustio\s+(?:se\s+)?(?:prema\s+)?dolje\b',      'spustio se'),
    (r'\bspustila\s+(?:se\s+)?(?:prema\s+)?dolje\b',     'spustila se'),
    (r'\bspustili\s+(?:se\s+)?(?:prema\s+)?dolje\b',     'spustili se'),
    (r'\bpopeti\s+se\s+gore\b',                           'popeti se'),
    (r'\bpopeo\s+se\s+gore\b',                            'popeo se'),
    (r'\bpopela\s+se\s+gore\b',                           'popela se'),
    (r'\bnastaviti\s+(?:i\s+)?dalje\b',                   'nastaviti'),
    (r'\bnastavlja\s+(?:i\s+)?dalje\b',                   'nastavlja'),
    (r'\bnastavlja\s+dalje\s+s\b',                        'nastavlja s'),
    (r'\bkrenuti\s+naprijed\b',                           'krenuti'),
    (r'\bkrenuo\s+naprijed\b',                            'krenuo'),
    (r'\bkrenula\s+naprijed\b',                           'krenula'),
    (r'\bvratiti\s+se\s+natrag\b',                        'vratiti se'),
    (r'\bvratio\s+se\s+natrag\b',                         'vratio se'),
    (r'\bvratila\s+se\s+natrag\b',                        'vratila se'),
    (r'\bvratili\s+se\s+natrag\b',                        'vratili se'),
    (r'\buspe?ti\s+se\s+gore\b',                          'uspeti se'),

    # ── 2. Suvišna pojačavanja pridjeva ─────────────────────────────────────
    (r'\bpotpuno\s+uništen(?:a|o|i|e)?\b',               'uništen'),
    (r'\bpotpuno\s+mrtav\b',                              'mrtav'),
    (r'\bpotpuno\s+mrtva\b',                              'mrtva'),
    (r'\bpotpuno\s+mrtvo\b',                              'mrtvo'),
    (r'\bpotpuno\s+prazn(?:a|o|i|e)?\b',                 'prazno'),
    (r'\bapsoluto\s+sigurn(?:a|o|i|e)?\b',               'sigurno'),
    (r'\bsasvim\s+jednak(?:a|o|i|e)?\b',                 'jednak'),
    (r'\bidentično\s+ist(?:a|o|i|e)?\b',                 'isto'),

    # ── 3. Vremenski pleonazmi ───────────────────────────────────────────────
    (r'\bu\s+toku\s+dana\b',                              'danju'),
    (r'\bu\s+toku\s+noći\b',                              'noću'),
    (r'\bu\s+toku\s+vremena\b',                           's vremenom'),
    (r'\btokom\s+čitavog\s+dana\b',                       'cijeli dan'),
    (r'\btokom\s+cijelog\s+dana\b',                       'cijeli dan'),
    (r'\bna\s+kraju\s+krajeva\b',                         'naposljetku'),
    (r'\bkonačno\s+i\s+definitivno\b',                    'konačno'),

    # ── 4. Osobne zamjenice uz "sam/lično" ───────────────────────────────────
    (r'\bsam\s+lično\b',                                  'osobno'),
    (r'\bsama\s+lično\b',                                 'osobno'),
    (r'\bja\s+osobno\s+sam\b',                            'osobno sam'),
    (r'\bti\s+osobno\s+si\b',                             'osobno si'),
    (r'\bon\s+osobno\s+je\b',                             'osobno je'),

    # ── 5. Glagolski pleonazmi ───────────────────────────────────────────────
    (r'\bvidjeti\s+(?:na\s+)?vlastite\s+oči\b',          'vidjeti'),
    (r'\bvidio\s+(?:na\s+)?vlastite\s+oči\b',            'vidio'),
    (r'\bčuti\s+(?:na\s+)?vlastite\s+uši\b',             'čuti'),
    (r'\bčuo\s+(?:na\s+)?vlastite\s+uši\b',              'čuo'),
    (r'\bponoviti\s+(?:još\s+)?jednom\s+(?:više|opet)\b','ponoviti'),
    (r'\bponovio\s+(?:još\s+)?jednom\s+(?:više|opet)\b', 'ponovio'),

    # ── 6. Opisni pleonazmi ──────────────────────────────────────────────────
    (r'\bcrna\s+tama\b',                                  'tama'),
    (r'\bbijela\s+snijeg\b',                              'snijeg'),  # "bijeli snijeg"
    (r'\bbijeli\s+snijeg\b',                              'snijeg'),
    (r'\bstara\s+ruševina\b',                             'ruševina'),
    (r'\bstare\s+ruševine\b',                             'ruševine'),
    (r'\bmladi\s+podmladak\b',                            'podmladak'),

]
