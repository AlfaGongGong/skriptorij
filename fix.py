#!/usr/bin/env python3
"""
fix_rod_patterne.py — Ispravlja ROD_PATTERNE u rod_retro_scan.py

Problemi:
1. Pattern "on je + ženski GPR" hvata "Darlington je podigla" jer
   re.IGNORECASE + lookahead ne provjerava je li "on" stvarno zamjenica
2. Pattern "bila je + muški GPR" hvata priloge i imenice (tamno, oko, itd.)
3. Pattern "bila je + pridjev -an/-en" hvata vlastita imena i imenice

Rješenje:
- Patterne mijenjamo da zahtijevaju da zamjenica bude IZOLOVANA (word boundary
  + ne prethodi joj veliko slovo ili vlastito ime)
- Whitelistu dodajemo sve preostale false-positive riječi
- Dodajemo post-filter koji odbacuje match ako GPR nije glagolskog porijekla
"""

from pathlib import Path
# import re
import sys

FAJL = Path("rod_retro_scan.py")

if not FAJL.exists():
    print("GREŠKA: rod_retro_scan.py nije pronađen u trenutnom direktoriju")
    sys.exit(1)

t = FAJL.read_text(encoding="utf-8")
originalni = t

# ─────────────────────────────────────────────────────────────────────────────
# FIX 1: Pattern "on je + ženski GPR"
# Problem: hvata "Darlington je podigla" jer IGNORECASE + "on" matchuje kraj
# imenice (DarlINGTON je...)
# Rješenje: dodaj negative lookbehind — ne smije biti slovo ispred "on"
# ─────────────────────────────────────────────────────────────────────────────
staro_on = (
    r'r"(on\s+je\s+|on\s+(?:nije|nije\s+bio)\s+)(\w+(?:ala|ila|ela|[^i]la))\b",'
    "\n            re.IGNORECASE"
)
novo_on = (
    r'r"(?<![A-Za-zČčŠšŽžĐđĆćÄäÖöÜü])(?<!\w)(on\s+je\s+|on\s+(?:nije|nije\s+bio)\s+)(\w+(?:ala|ila|ela|[^i]la))\b",'
    "\n            re.IGNORECASE"
)

if staro_on in t:
    t = t.replace(staro_on, novo_on)
    print("✓ Fix 1: Pattern 'on je + ženski GPR' — dodan negative lookbehind")
else:
    print("⚠ Fix 1: Marker nije pronađen, preskačem")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 2: Pattern "ona je + muški GPR"
# Isto — "ona" može biti kraj imenice
# ─────────────────────────────────────────────────────────────────────────────
staro_ona = (
    r'r"(ona\s+je\s+|ona\s+(?:nije|nije\s+bila)\s+)(\w+(?:ao|io|eo|[^al]o))\b",'
    "\n            re.IGNORECASE"
)
novo_ona = (
    r'r"(?<![A-Za-zČčŠšŽžĐđĆćÄäÖöÜü])(?<!\w)(ona\s+je\s+|ona\s+(?:nije|nije\s+bila)\s+)(\w+(?:ao|io|eo|[^al]o))\b",'
    "\n            re.IGNORECASE"
)

if staro_ona in t:
    t = t.replace(staro_ona, novo_ona)
    print("✓ Fix 2: Pattern 'ona je + muški GPR' — dodan negative lookbehind")
else:
    print("⚠ Fix 2: Marker nije pronađen, preskačem")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 3: Pattern "bila je + muški GPR"
# Problem: hvata "bila je tamno", "bila je oko", "bila je savršeno"
# Rješenje: zahtijevaj da GPR završava na glagolski sufiks (-ao, -io, -eo)
# a NE na -no, -ko, -to, -ro, -lo (to su tipično prilozi/pridjevi sr. roda)
# ─────────────────────────────────────────────────────────────────────────────
staro_bila = (
    r'r"(bila\s+je\s+)(\w+(?:ao|io|eo|[^al]o))\b",'
    "\n            re.IGNORECASE"
)
novo_bila = (
    r'r"(bila\s+je\s+)(\w+(?:ao|io|[^aeio]eo))\b",'
    "\n            re.IGNORECASE"
)

if staro_bila in t:
    t = t.replace(staro_bila, novo_bila)
    print("✓ Fix 3: Pattern 'bila je + muški GPR' — precizniji sufiks")
else:
    print("⚠ Fix 3: Marker nije pronađen, preskačem")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 4: Dodaj post-filter u skeniraj_tekst koji odbacuje match
# ako GPR nije glagolskog porijekla (tj. ako je u whitelisti ili
# ako mu prethodi vlastito ime u rečenici)
# ─────────────────────────────────────────────────────────────────────────────

staro_filter = (
    "            if any(_je_whitelisted(r) for r in rijeci):\n                continue"
)
novo_filter = """\
            if any(_je_whitelisted(r) for r in rijeci):
                continue
            # Odbaci ako je subjekat zapravo vlastito ime (veliko slovo ispred match-a)
            poz = m.start()
            prethodni = tekst[max(0, poz-40):poz]
            zadnja_rijec = re.search(r'(\\S+)\\s*$', prethodni)
            if zadnja_rijec:
                zr = zadnja_rijec.group(1).rstrip('.,;:!?—–-\\"\\')
                # Ako zadnja riječ ispred "on/ona/bio/bila" počinje velikim slovom
                # i nije na whitelisti zamjenica — preskači (vlastito ime kao subj)
                ZAMJENICE = {"on", "ona", "bio", "bila", "nije", "je"}
                if (len(zr) > 2 and zr[0].isupper()
                        and zr.lower() not in ZAMJENICE
                        and not zr[0].isdigit()):
                    continue"""

broj_zamjena = t.count(staro_filter)
if broj_zamjena > 0:
    t = t.replace(staro_filter, novo_filter)
    print(f"✓ Fix 4: Post-filter za vlastita imena dodan ({broj_zamjena}x)")
else:
    print("⚠ Fix 4: Filter marker nije pronađen, preskačem")

# ─────────────────────────────────────────────────────────────────────────────
# FIX 5: Proširi whitelist — preostale false-positive riječi
# ─────────────────────────────────────────────────────────────────────────────
whitelist_dodatak = """\
    # Preostali false-positivi — imenice i prilozi na -o
    "oko", "uho", "pero", "kolo", "čelo", "tlo", "zlo", "dobro",
    "tamno", "bijelo", "crno", "crveno", "zeleno", "plavo", "žuto",
    "pješčano", "savršeno", "čvrsto", "meko", "tvrdo", "glatko",
    "duboko", "plitko", "visoko", "nisko", "široko", "usko",
    "daleko", "blisko", "skoro", "skupo", "jeftino",
    "toplo", "hladno", "mokro", "suho", "puno", "prazno",
    "teško", "lagano", "ravno", "krivo", "točno", "ispravno",
    "slobodno", "mirno", "tiho", "glasno", "jasno", "mutno",
    "čisto", "prljavo", "uredno", "lijepo", "ružno",
    "sigurno", "opasno", "korisno", "vrijedno", "moguće",
    "nemoguće", "potrebno", "nužno", "zanimljivo", "dosadno",
    "čudno", "normalno", "važno", "poznato", "vidljivo",
    "isključivo", "gotovo", "jednako", "netko", "nitko",
    "nešto", "ništa", "svašta", "mnogo", "dosta", "dovoljno",
    "previše", "toliko", "koliko", "otprilike", "zbilja",
    "stvarno", "doduše", "možda", "valjda", "vjerovatno",
    "vjerojatno", "naravno", "zapravo", "zaista", "doista",
    "naročito", "posebno", "osobito", "iznimno", "izuzetno",
    "napokon", "konačno", "ujedno", "zajedno", "odjednom",
    "pogotovo", "međutim", "podjednako", "ravnomjerno",
    "plijen", "rješenje", "mišljenje", "viđenje", "osjećanje",
    "saznanje", "otkriće", "iskustvo", "znanje", "more",
    "polje", "brdo", "selo", "mjesto", "središte", "dno",
    "ogledalo", "staklo", "zlato", "srebro", "tijelo", "srce",
    "pedala",  # imenica (dio bicikla), ne glagol
"""

# Ubaci prije zatvarajuće } od WHITELIST
marker_wl = "}\n\ndef _je_whitelisted"
if marker_wl in t and "pedala" not in t:
    t = t.replace(marker_wl, whitelist_dodatak + "}\n\ndef _je_whitelisted")
    print("✓ Fix 5: Whitelist proširen")
else:
    print("⚠ Fix 5: Whitelist marker nije pronađen ili već patchiran")

# ─────────────────────────────────────────────────────────────────────────────
# Zapiši i provjeri
# ─────────────────────────────────────────────────────────────────────────────
if t != originalni:
    # Backup
    backup = FAJL.with_suffix(".py.bak_rod_fix")
    backup.write_text(originalni, encoding="utf-8")
    print(f"✓ Backup: {backup}")

    FAJL.write_text(t, encoding="utf-8")
    print(f"✓ Zapisano: {FAJL}")
else:
    print("⚠ Nema promjena — provjeri markere ručno")
    sys.exit(1)

print("\nPokreni provjeru:")
print(
    "  python rod_retro_scan.py --scan --prag 11 --verbose 2>&1 | grep -E 'Original|⚠|Skenirano'"
)
