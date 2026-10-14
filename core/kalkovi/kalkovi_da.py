"""
core/kalkovi/da.py
Kategorija: Suvišno "da" uz glagole (srbizmi / balkanski sintaktički kalk)

U standardnom hrvatskom književnom jeziku infinitiv se koristi
direktno uz modalne i fazne glagole. Konstrukcija "modal + da + prezent"
je srbizam koji AI modeli (posebno Groq/Cerebras/SambaNova) uvode jer su
pretežno trenirani na srpskom korpusu.

ISPRAVNO:   "morao je otići"
POGREŠNO:   "morao je da ode"

ISPRAVNO:   "počela je plakati"
POGREŠNO:   "počela je da plače"

Napomena o patternima:
- \b osigurava granicu riječi
- Glagoli u zamjeni su infinitivi BHS oblika
- Redosljed u listi je bitan — specifičniji patrni idu prije općenitijih
- Prezentski oblici (ode, plače...) se ne mogu uvijek auto-ispraviti
  jer zahtijevaju kontekst → te ostavljamo za AI lektor prolaz
- Pokrivamo: moći, morati, smjeti, htjeti, željeti, početi, nastaviti,
  prestati, trebati, uspjeti, znati, voljeti, nastojati, pokušati,
  namjeravati, planirati, odlučiti, zaboraviti, sjetiti se, navikavati,
  učiti, početi, završiti, izbjeći, odbiti, pristati, obećati,
  primorati, tjerati, pustiti, dati (dopuštanje), pomoći, učiti (koga)
"""

# ─────────────────────────────────────────────────────────────────────────────
# POMOĆNI BUILDER — generira sve lične oblike za dati glagol
# ─────────────────────────────────────────────────────────────────────────────


def _m(modal_oblici, infinitiv):
    """
    Vraća listu kalkova za sve oblike modalnog glagola + da + prezent.
    modal_oblici: lista regex stringova za oblike modalnog glagola
    infinitiv: ispravni infinitiv koji se ubacuje u zamjenu
    """
    rezultat = []
    for oblik in modal_oblici:
        # modal + da + jednočlani prezent (najčešći slučaj)
        rezultat.append(
            (
                rf"\b{oblik}\s+da\s+(\w+)",
                lambda m, inf=infinitiv: f"{m.group(0).split('da')[0].rstrip()} {inf}"
                if False
                else r"\g<0>",  # placeholder — koristimo dolje
            )
        )
    return rezultat


# ─────────────────────────────────────────────────────────────────────────────
# LISTA KALKOVA
# Format: (pattern, zamjena) — re.IGNORECASE se primjenjuje automatski
# ─────────────────────────────────────────────────────────────────────────────

KALKOVI = [
    # ══════════════════════════════════════════════════════════════════════
    # 1. MOĆI (mogu, možeš, može, možemo, možete, mogu)
    # ══════════════════════════════════════════════════════════════════════
    # Nisu mogli da → nisu mogli
    # Perfekt
    # Kondicional
    # ══════════════════════════════════════════════════════════════════════
    # 2. MORATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 3. SMJETI / SMETI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 4. HTJETI / HTETI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 5. ŽELJETI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 6. POČETI / POČINJATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 7. NASTAVITI / NASTAVLJATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 8. PRESTATI / PRESTAJATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 9. TREBATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 10. USPJETI / USPIJEVATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 11. ZNATI (u smislu "umjeti")
    # ══════════════════════════════════════════════════════════════════════
    (
    ),
    (
    ),
    # ══════════════════════════════════════════════════════════════════════
    # 12. VOLJETI / VOLITI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 13. POKUŠATI / POKUŠAVATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 14. NAMJERAVATI / PLANIRATI / ODLUČITI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 15. ZABORAVITI / SJETITI SE / PAMTITI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 16. NASTOJATI / TRUDITI SE
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 17. ODBITI / PRISTATI / OBEĆATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 18. PRISILITI / TJERATI / NATJERATI / PUSTITI / DATI (dopuštanje)
    # ══════════════════════════════════════════════════════════════════════
    (
        r"\bprisili\s+(?:ga|je|ih|me|te|nas|vas)\s+da\s+(\w+)",
        lambda m: m.group(0).replace(" da ", " ").rstrip(),
    ),  # ostavi strukturu
    (
        r"\btjera\s+(?:ga|je|ih|me|te|nas|vas)\s+da\s+(\w+)",
        lambda m: m.group(0).replace(" da ", " "),
    ),
    (
        r"\bnatjera\s+(?:ga|je|ih|me|te|nas|vas)\s+da\s+(\w+)",
        lambda m: m.group(0).replace(" da ", " "),
    ),
    # "pusti me da idem" → "pusti me ići" — kontekstualno, ostavljamo
    # "dao mi je da" → kontekstualno
    # ══════════════════════════════════════════════════════════════════════
    # 19. NAUČITI / NAVIKNUTI / NAVIKAVATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 20. IZBJEĆI / IZBJEGAVATI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 21. POMOĆI / DOPUSTITI / DOZVOLITI
    # ══════════════════════════════════════════════════════════════════════
    (
        r"\bpomoći\s+(?:mu|joj|im|mi|ti|nam|vam)\s+da\s+(\w+)",
        lambda m: m.group(0).replace(" da ", " "),
    ),
    (
        r"\bpomogao\s+(?:mu|joj|im|mi|ti)\s+da\s+(\w+)",
        lambda m: m.group(0).replace(" da ", " "),
    ),
    # ══════════════════════════════════════════════════════════════════════
    # 22. OSTATI / ZADRŽATI SE
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 23. ZAVRŠITI / DOVRŠITI
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 24. USUDITI SE / SMJELITI SE / ODVAŽITI SE
    # ══════════════════════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════════════════════
    # 25. ČEKATI / JEDVA ČEKATI
    # ══════════════════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════════════
    # FRAZNI KALKOVI — dodani 2026-09-25
    # Ovi patterni su BEZ capture grupe (bez \1) — sigurni.
    # Zamjenjuju ustaljene frazne kalkove engleskog u HR.
    # ═══════════════════════════════════════════════════════════════════
    (r"\bbio je u stanju da\b", r"mogao je"),
    (r"\bbila je u stanju da\b", r"mogla je"),
    (r"\bbili su u stanju da\b", r"mogli su"),
    (r"\bbile su u stanju da\b", r"mogle su"),
    (r"\bbio sam u stanju da\b", r"mogao sam"),
    (r"\bbila sam u stanju da\b", r"mogla sam"),
    (r"\bnije bio u mogu[ćc]nosti da\b", r"nije mogao"),
    (r"\bnije bila u mogu[ćc]nosti da\b", r"nije mogla"),
    (r"\bnije u mogu[ćc]nosti da\b", r"ne može"),
    (r"\bnije u stanju da\b", r"ne može"),
    (r"\buspio je da\b", r"uspio je"),
    (r"\buspjela je da\b", r"uspjela je"),
    (r"\buspio sam da\b", r"uspio sam"),
    (r"\bpoku[šs]ao je da\b", r"pokušao je"),
    (r"\bpoku[šs]ala je da\b", r"pokušala je"),
    (r"\bu cilju da\b", r"da bi"),
    (r"\bs ciljem da\b", r"da bi"),
    (r"\bsa svrhom da\b", r"da bi"),
    (r"\bu svrhu da\b", r"da bi"),
    (r"\bpo pitanju\s+", r"o "),
    (r"\bu pogledu\s+", r"što se tiče "),
    (r"\bu vezi sa\s+", r"o "),
    (r"\bu vezi s\s+", r"o "),
    (r"\bu odnosu na to\b", r"prema tome"),
    (r"\bu odnosu na\b", r"prema"),
    (r"\bs obzirom na to\b", r"s obzirom na to"),
    (r"\bimati u vidu\b", r"imati na umu"),
    (r"\bimaju[ćc]i u vidu\b", r"s obzirom na"),
    (r"\bimaju[ćc]i u vidu to\b", r"s obzirom na to"),
    (r"\buzeti u obzir to da\b", r"uzeti u obzir da"),
    (r"\bna osnovu toga\b", r"iz toga"),
    (r"\bna temelju toga\b", r"na osnovu toga"),
    (r"\biz razloga [šs]to\b", r"jer"),
    (r"\biz razloga [šs]to je\b", r"jer je"),
    (r"\bu svjetlu toga\b", r"s obzirom na to"),
    (r"\bu svijetlu toga\b", r"s obzirom na to"),
    (r"\bu stvari\b", r"zapravo"),
    (r"\bnaravno da\b", r"naravno"),
    (r"\bpored toga\b", r"osim toga"),
    (r"\bs druge strane\b", r"nasuprot tome"),
    (r"\b[čc]ini se da\b", r"izgleda da"),
    (r"\bka[žz]e se da\b", r"tvrdi se da"),
    (r"\bna neki na[čc]in\b", r"nekako"),
    (r"\bna kraju dana\b", r"naposljetku"),
    (r"\bkao [šs]to je poznato\b", r"poznato je da"),
    (r"\bu najmanju ruku\b", r"barem"),
    (r"\bbez obzira na to\b", r"bez obzira na to"),
    (r"\bs vremena na vrijeme\b", r"povremeno"),
    (r"\bu to vrijeme\b", r"tada"),
    (r"\bu me[đd]uvremenu\b", r"u međuvremenu"),
    (r"\bmalo po malo\b", r"postepeno"),
    (r"\bjedan po jedan\b", r"jedan po jedan"),
    (r"\biznad svega\b", r"povrh svega"),
    (r"\bu prvom redu\b", r"prvenstveno"),
    (r"\bposljednje ali ne najmanje va[žz]no\b", r"naposljetku, ali ne manje važno"),
    (r"\bu krajnjoj liniji\b", r"naposljetku"),
    (r"\bu svakom slu[čc]aju\b", r"u svakom slučaju"),
    (r"\bizme[đd]u ostalog\b", r"između ostalog"),
    (r"\bs jedne strane\b", r"s jedne strane"),
    (r"\bu pogledu na to\b", r"glede toga"),
    (r"\bsve u svemu\b", r"sve u svemu"),
    (r"\bkao rezultat toga\b", r"zbog toga"),
    (r"\bkao rezultat\s+", r"zbog "),
    (r"\bbez sumnje\b", r"nesumnjivo"),
    (r"\bu svrhu toga\b", r"u tu svrhu"),
    (r"\bs obzirom da\b", r"budući da"),
    (r"\bu slu[čc]aju da\b", r"ako"),
    (r"\bpod uslovom da\b", r"ako"),
    (r"\bprije svega\b", r"prije svega"),
    (r"\biz tog razloga\b", r"zato"),
    (r"\bkao takav\b", r"kao takav"),
    (r"\bu zavisnosti od\b", r"zavisno od"),
    (r"\bna kraju krajeva\b", r"naposljetku"),
    (r"\bna taj na[čc]in\b", r"tako"),
    (r"\biz tog ugla\b", r"iz te perspektive"),
    (r"\bu tom pogledu\b", r"u tom smislu"),
    (r"\bu potpunosti\b", r"potpuno"),
    (r"\bu cjelosti\b", r"u cijelosti"),
    (r"\bu cijelosti\b", r"u cijelosti"),
    (r"\bna vrijeme\b", r"na vrijeme"),
    (r"\bs toga\b", r"stoga"),
    (r"\buprkos tome\b", r"unatoč tome"),
    (r"\bi pored toga\b", r"i unatoč tome"),
    (r"\bkao i obi[čc]no\b", r"kao obično"),
    (r"\bs pravom\b", r"opravdano"),
    (r"\bbez ikakve sumnje\b", r"nesumnjivo"),
    (r"\bna sve na[čc]ine\b", r"svim sredstvima"),

]
