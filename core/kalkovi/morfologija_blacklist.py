"""
core/kalkovi/morfologija_blacklist.py
──────────────────────────────────────
Eksplicitna lista nepostojećih / haluciniranih glagolskih oblika
za BS/HR jezik. Injektira se u system prompt via prompt_injector.py.

Svrha: smanjiti morfološke halucinacije za 60-70% bez fine-tuninga,
dajući modelu konkretne negativne primjere (što NIKAD ne pisati).

Format kompatibilan s prompt_injector.py — koristi se kao:
    from core.kalkovi.morfologija_blacklist import (
        BLACKLIST_PROMPT_BLOK,
        HALUCIRANI_OBLICI,
        ISPRAVNI_OBLICI,
    )
"""

# ── 1. HALUCIRANI → ISPRAVNI (rječnik za post-processing / audit) ──────────
HALUCIRANI_OBLICI: dict[str, str] = {
    # Nepostojeći iterativni/imperfektivni oblici (najčešći tip halucinacije)
    "voljevao":     "volio",
    "voljevala":    "voljela",
    "voljevali":    "voljeli",
    "hodavao":      "hodao",
    "hodavala":     "hodala",
    "hodavali":     "hodali",
    "gledavao":     "gledao",
    "gledavala":    "gledala",
    "gledavali":    "gledali",
    "vidjevao":     "vidio",
    "vidjevala":    "vidjela",
    "vidjevali":    "vidjeli",
    "čujevao":      "čuo",
    "čujevala":     "čula",
    "čujevali":     "čuli",
    "spavivao":     "spavao",
    "spavivala":    "spavala",
    "spavivali":    "spavali",
    "trčavao":      "trčao",
    "trčavala":     "trčala",
    "trčavali":     "trčali",
    "pjevavao":     "pjevao",
    "pjevavala":    "pjevala",
    "pjevavali":    "pjevali",
    "govorivao":    "govorio",
    "govorivala":   "govorila",
    "govorivali":   "govorili",
    "mislivao":     "mislio",
    "mislivala":    "mislila",
    "mislivali":    "mislili",
    "nosivao":      "nosio",
    "nosivala":     "nosila",
    "nosivali":     "nosili",
    "pisivao":      "pisao",
    "čitavivao":    "čitao",
    "radivao":      "radio",
    "radivala":     "radila",
    "radivali":     "radili",
    "stavivao":     "stavljao",
    "stavivala":    "stavljala",
    "uzimivao":     "uzimao",
    "uzimivala":    "uzimala",
    "davivao":      "davao",
    "davivala":     "davala",
    "pravivao":     "pravio",
    "pravivala":    "pravila",
    "tražavao":     "tražio",
    "tražavala":    "tražila",

    # Nepostojeći oblici perfekta (glagoli na -jeti / -iti)
    "uzdisnuo":     "uzdahnuo",
    "popivajući":   "ispijajući",
    "popivao":      "pio",
    "izlazivao":    "izlazio",
    "ulazivao":     "ulazio",
    "prolazivao":   "prolazio",
    "ostajivao":    "ostajao",
    "sijedio":      "sjedio",

    # Nepostojeći glagolski pridjevi radni
    "donesavši":    "donijevši",
    "iznesavši":    "iznijevši",
    "odnesavši":    "odnijevši",
    "prinesavši":   "prinijevši",
    "zanesavši":    "zanijevši",

    # Specifično za SF/fantasy kontekst
    "memorativao":  "pamtio",
    "procesivao":   "obrađivao",
    "skeniravao":   "skenirao",
    "uploadavao":   "učitavao",
    "downloadavao": "preuzimao",
    "connectavao":  "spajao",
    "logavao":      "bilježio",
}

# ── 2. ISPRAVNI OBLICI ────────────────────────────────────────────────────
ISPRAVNI_OBLICI: list[str] = [
    "volio / voljela / voljeli",
    "vidio / vidjela / vidjeli",
    "čuo / čula / čuli",
    "hodao / hodala / hodali",
    "gledao / gledala / gledali",
    "mislio / mislila / mislili",
    "uzdahnuo / uzdahnula",
    "ispijajući (ne: popivajući)",
    "sjedio / sjedjela (ne: sijedio)",
    "trčao / trčala (ne: trčavao)",
    "pjevao / pjevala (ne: pjevavao)",
    "skenirao / skenirala (ne: skeniravao)",
]

# ── 3. PROMPT BLOK ────────────────────────────────────────────────────────
BLACKLIST_PROMPT_BLOK: str = """
## Morfološka pravila — APSOLUTNE ZABRANE

Nikada ne koristiš sljedeće oblike jer NE POSTOJE u bosanskom/hrvatskom:
- voljevao, gledavao, hodavao, vidjevao, čujevao, trčavao, pjevavao
- govorivao, nosivao, radivao, stavivao, uzimivao, pravivao, tražavao
- popivajući (→ ispijajući), uzdisnuo (→ uzdahnuo)
- skeniravao, uploadavao, downloadavao, connectavao (→ skenirao, učitavao, preuzimao, spajao)

Ispravni oblici koje UVIJEK koristiš:
- volio/voljela, vidio/vidjela, čuo/čula, hodao/hodala
- gledao/gledala, mislio/mislila, trčao/trčala, pjevao/pjevala
- sjedio/sjedjela (NE: sijedio — to je ekavizam)

Pravilo: glagoli u muškom rodu jednine perfekta završavaju na -ao ili -io,
NIKAD na -avao ili -ivao osim ako je to standardni oblik (npr. poznavao ✓, čitavao ✓ arhaično).
""".strip()

# ── 4. REGEX PATTERNE ─────────────────────────────────────────────────────
import re

HALUCINACIJA_REGEX: list[re.Pattern] = [
    re.compile(r'\b\w+[aei]vao\b', re.IGNORECASE),
    re.compile(r'\b\w+[aei]vala\b', re.IGNORECASE),
    re.compile(r'\b\w+ivao\b', re.IGNORECASE),
    re.compile(r'\bpopivajući\b', re.IGNORECASE),
    re.compile(r'\buzdisnuo\b', re.IGNORECASE),
    re.compile(r'\bsijedio\b', re.IGNORECASE),
    re.compile(r'\b\w+(avao|ivao|evao)\b', re.IGNORECASE),
]

HALUCINACIJA_WHITELIST: set[str] = {
    "poznavao", "poznavala", "poznavali",
    "ostavljao", "ostavljala", "ostavljali",
    "ostajao", "ostajala", "ostajali",
    "prepoznavao", "prepoznavala", "prepoznavali",
    "prikazivao", "prikazivala", "prikazivali",
    "nazivao", "nazivala", "nazivali",
    "zahtijevao", "zahtijevala", "zahtijevali",
    "primjećivao", "primjećivala", "primjećivali",
    "pokušavao", "pokušavala", "pokušavali",
    "osjećao", "osjećala", "osjećali",
    "nalazivao",
    "čitavao",
    "pisivao",
    "dolazivao",
    "odlazivao",
    "saznavao", "saznavala", "saznavali",
    "doživljavao", "doživljavala", "doživljavali",
    "razmišljao", "razmišljala", "razmišljali",
    "svladavao", "svladavala", "svladavali",
    "savladavao", "savladavala", "savladavali",
    "pokazivao", "pokazivala", "pokazivali",
    "smijao", "smijala", "smijali",
    "nasmijao", "nasmijala", "nasmijali",
    "bojao", "bojala", "bojali",
    "stajao", "stajala", "stajali",
    "sijao", "sijala", "sijali",
    "pazio", "pazila", "pazili",
}


def skeniraj_halucinacije(tekst: str) -> list[dict]:
    """
    Brzi pre-screening teksta za sumnjive morfološke oblike.
    Vraća listu diktova: [{"oblik": str, "pozicija": int, "kontekst": str}]
    """
    nalazi = []
    
    for pattern in HALUCINACIJA_REGEX:
        for match in pattern.finditer(tekst):
            oblik = match.group(0).lower()
            if oblik in HALUCINACIJA_WHITELIST:
                continue
            start = max(0, match.start() - 40)
            end = min(len(tekst), match.end() + 40)
            nalazi.append({
                "oblik": match.group(0),
                "pozicija": match.start(),
                "kontekst": tekst[start:end].replace('\n', ' '),
                "sumnja": "halucinacija_regex",
            })
    
    return nalazi


if __name__ == "__main__":
    test = (
        "Hodavao je ulicom dok je gledavao u nebo. "
        "Pokušavao je zaboraviti sve što se desilo. "
        "Uzdisnuo je i nastavio dalje popivajući kavu."
    )
    print("Test tekst:", test)
    print()
    nalazi = skeniraj_halucinacije(test)
    print(f"Pronađeno {len(nalazi)} sumnjivih oblika:")
    for n in nalazi:
        print(f"  '{n['oblik']}' @ {n['pozicija']}: ...{n['kontekst']}...")
    print()
    print("Whitelist check — 'pokušavao' treba biti whitelist:")
    test2 = "Pokušavao je otvoriti vrata."
    print(f"  Nalazi: {skeniraj_halucinacije(test2)}")
