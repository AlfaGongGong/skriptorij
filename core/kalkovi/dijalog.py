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

# 2026-11-04: tipografija (navodnici, crtice, trotočje) živi u core/tipografija.py.
# DIJALOG_TIPOGRAFIJA uklonjen — bio je izvor kontradikcije ASCII vs „”.


# ── Poštapalice i srbizmi u dijalogu ─────────────────────────────────────

DIJALOG_KALKOVI = [
    # "Dobro" kao srbistički filler na početku odgovora u dijalogu
    # Samo kad je izolirano ili na početku replike, ne u frazama
    (
        r'(?m)^(—\s*|"\s*)Dobro,\s+(?=(?:ali|međutim|dakle|tako))',
        r"\1",
    ),  # "Dobro, ali → ali
    # Uobičajene srpske uzrečice koje AI ubacuje
    # F0.0 (2026-11-04): ZAMRZNUTO — "važi" je običan glagol u HR/BS
    # ("pravilo važi za sve"). Zamjena kvari smisao.
    # (r"\bvaži\b", "dogovoreno"),
    # (r"\bvaži\s*,", "dogovoreno,"),
    # (r"\bVaži\b", "Dogovoreno"),
    # F1.4 (2026-11-04): ZAMRZNUTO — "kako god" je normalan HR izraz
    # ("kako god hoćeš"). Zamjena kvari smisao.
    # (r"\bkako\s+god\b", "kako mu drago"),
    # (r"\bkako\s+god\s+ti\b", "kako ti"),
    # Srpska forma odricanja u dijalogu
    # "Šta" umjesto "što" — dosljedan ekavizam/srbizam u dijalogu
    (r"\bŠta\b", "Što"),
    (r"\bšta\b", "što"),
    (r"\bŠta\s+to\b", "Što to"),
    (r"\bšta\s+to\b", "što to"),
    # "Ko" umjesto "tko" (srbizam u dijalogu)
    (r"(?<![a-zčćšžđ])ko\s+je\b", "tko je"),
    (r"(?<![a-zčćšžđ])Ko\s+je\b", "Tko je"),
    (r"(?<![a-zčćšžđ])ko\s+to\b", "tko to"),
    (r"(?<![a-zčćšžđ])Ko\s+to\b", "Tko to"),
    (r"(?<![a-zčćšžđ])ko\s+si\b", "tko si"),
    (r"(?<![a-zčćšžđ])Ko\s+si\b", "Tko si"),
    (r"(?<![a-zčćšžđ])ko\s+zna\b", "tko zna"),
    (r"(?<![a-zčćšžđ])Ko\s+zna\b", "Tko zna"),
    (r"(?<![a-zčćšžđ])ko\s+god\b", "tko god"),
    (r"(?<![a-zčćšžđ])Ko\s+god\b", "Tko god"),
    # "Kad" → "kada" (stilska preferencija u književnom tekstu)
    # ISKLJUČENO — "kad" je prihvatljivo u BS, ne patch-amo
    # (r'\bkad\b', 'kada'),
    # Anglizam "OK" u dijalogu → lokalna forma
    # F1.4 (2026-11-04): ZAMRZNUTO — "OK" je normalan u dijalogu, mijenja registar.
    # (r"\bOK\b", "U redu"),
    # (r"\bOk\b(?!\w)", "U redu"),
    # Srpska forma "izvini" → "ispričaj se" / "oprosti"
    # F1.4 (2026-11-04): ZAMRZNUTO — "izvini" i "oprosti" su oba ispravna HR.
    # (r"\bIzvini\b", "Oprosti"),
    # (r"\bizvini\b", "oprosti"),
    # (r"\bIzvinite\b", "Oprostite"),
    # (r"\bizvinite\b", "oprostite"),
    # (r"\bIzvinjavaj\b", "Ispričavaj"),
    # (r"\bizvinjavaj\b", "ispričavaj"),
    # Srpska forma "molim" bez "te/vas" → dodaj (kontekstualno sigurno)
    # ISKLJUČENO — "molim" je ok u BS kao pozdrav/uljudnost
    # "servisi" → "usluge" u dijalogu
    # F0.0 (2026-11-04): ZAMRZNUTO — "servis" u HR/BS znači servis vozila,
    # servis posuđa, teniski servis. Lookahead izuzeci pokrivaju samo
    # nekoliko fraza, sve ostalo se kvari.
    # (r"\bservise\b", "usluge"),
    # (r"\bservisima\b", "uslugama"),
    # (r"\bservis\b(?!\s+(?:vozila|automobila|auta|kola|motora|bicikla))", "usluga"),
]

# Objedinjena lista za __init__.py
DIJALOG = DIJALOG_KALKOVI
