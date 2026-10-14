"""
core/autor_analiza.py — Analiza autorovog stila pisanja.

Analizira prvih N rečenica iz knjige i vraća stilski profil:
- Dužina rečenica (kratke/detaljne)
- Omjer dijaloga i naracije
- Vrijeme (prošlo/sadašnje)
- Lice (1./3.)
- Prisutnost unutarnjeg monologa
- Tempo (brzi/spori)
- Ton (mračan/vedar/neutralan)

Profil se ubacuje u PREVODILAC prompt kao dinamička instrukcija.
"""
import re
import json
from collections import Counter
from pathlib import Path


def analiziraj_tekst(tekst: str) -> dict:
    """Analizira stil pisanja iz sirovog teksta."""
    if not tekst or len(tekst) < 500:
        return {}

    # ─── 1. Rečenice ───
    recenice = re.split(r'(?<=[.!?…])\s+', tekst)
    recenice = [r.strip() for r in recenice if len(r.strip()) > 10]

    if not recenice:
        return {}

    # Broj riječi po rečenici
    br_rijeci = [len(r.split()) for r in recenice]
    prosjek_rijeci = sum(br_rijeci) / len(br_rijeci)
    median_rijeci = sorted(br_rijeci)[len(br_rijeci) // 2]

    # Kratke rečenice (<10 riječi)
    kratke = sum(1 for b in br_rijeci if b < 10)
    # Duge rečenice (>25 riječi)
    duge = sum(1 for b in br_rijeci if b > 25)

    # ─── 2. Dijalozi ───
    dijalozi = 0
    for r in recenice:
        if r.startswith(('"', '„', '“', '—', '-', '–')):
            dijalozi += 1
    omjer_dijaloga = dijalozi / len(recenice)

    # ─── 3. Vrijeme ───
    # Prošlo: "rekao", "otišao", "bio"; Sadašnje: "kaže", "ide", "je"
    proslo = len(re.findall(r'\b\w+(ao|io|eo|la|lo|li|le)\b', tekst.lower()))
    sadasnje = len(re.findall(r'\b\w+(am|aš|a|amo|ate|aju|im|iš|i|imo|ite|e)\b', tekst.lower()))
    vrijeme = "prošlo" if proslo > sadasnje * 1.5 else ("sadašnje" if sadasnje > proslo * 1.5 else "miješano")

    # ─── 4. Lice ───
    prvo_lice = len(re.findall(r'\b(ja|mene|mi|nas|nama|moj|moja|moje)\b', tekst.lower()))
    trece_lice = len(re.findall(r'\b(on|ona|ono|njega|nje|njima|njihov|njegov|njezin)\b', tekst.lower()))
    lice = "prvo" if prvo_lice > trece_lice * 1.5 else ("treće" if trece_lice > prvo_lice * 1.5 else "miješano")

    # ─── 5. Unutarnji monolog ───
    # Česti markeri: "mislio", "pomislio", "osjećao", "znao"
    unutarnji = len(re.findall(
        r'\b(mislio|mislila|pomislio|pomislila|osjećao|osjećala|znao|znala|'
        r'želio|željela|nadala|nadao|bojao|bojala)\b', tekst.lower()
    ))
    ima_unutarnji = unutarnji > len(recenice) * 0.1

    # ─── 6. Tempo ───
    # Kratke rečenice + akcioni glagoli = brz tempo
    akcioni_glagoli = len(re.findall(
        r'\b(trčao|trčala|skočio|skočila|udario|udarila|ubio|ubila|'
        r'povukao|povukla|jurnuo|jurnula|poletio|poletjela)\b', tekst.lower()
    ))
    brz_tempo = (kratke > len(recenice) * 0.4) or (akcioni_glagoli > len(recenice) * 0.05)

    # ─── 7. Ton ───
    tamni_markeri = len(re.findall(
        r'\b(krv|smrt|ubio|ubila|mrtav|mrtva|rana|bol|tama|mrak|hladno|'
        r'strah|uzas|jeza|grozno|lešina|krvav)\b', tekst.lower()
    ))
    svijetli_markeri = len(re.findall(
        r'\b(smijeh|nasmijao|sretan|sreća|radost|ljubav|toplo|sunce|svjetlo|'
        r'lijepo|krasno|nježno|nada)\b', tekst.lower()
    ))
    if tamni_markeri > svijetli_markeri * 2:
        ton = "mračan"
    elif svijetli_markeri > tamni_markeri * 2:
        ton = "vedar"
    else:
        ton = "neutralan"

    # ─── 8. Stil rečenica ───
    if median_rijeci < 12:
        stil = "kratke, sjeckave rečenice"
    elif median_rijeci < 20:
        stil = "srednje duge, tečne rečenice"
    else:
        stil = "duge, opisne rečenice"

    return {
        "prosjek_rijeci": round(prosjek_rijeci, 1),
        "median_rijeci": median_rijeci,
        "kratke_pct": round(100 * kratke / len(recenice), 1),
        "duge_pct": round(100 * duge / len(recenice), 1),
        "omjer_dijaloga": round(omjer_dijaloga, 2),
        "vrijeme": vrijeme,
        "lice": lice,
        "ima_unutarnji": ima_unutarnji,
        "brz_tempo": brz_tempo,
        "ton": ton,
        "stil": stil,
        "ukupno_recenica": len(recenice),
    }


def napravi_prompt(profil: dict) -> str:
    """Pretvori profil u dinamički prompt za PREVODILAC."""
    if not profil:
        return ""

    upute = []
    upute.append(f"STIL AUTORA: {profil['stil']} (prosjek {profil['prosjek_rijeci']} riječi/rečenici).")

    if profil["omjer_dijaloga"] > 0.3:
        upute.append(
            f"DIJALOG DOMINIRA ({int(profil['omjer_dijaloga']*100)}% rečenica). "
            "Pazi na prirodnost govora, koristi crticu — za dijalog."
        )
    elif profil["omjer_dijaloga"] < 0.1:
        upute.append("NARACIJA DOMINIRA. Fokus na opisima i unutarnjem doživljaju.")

    if profil["vrijeme"] == "prošlo":
        upute.append("VRIJEME: prošlo (npr. 'rekao je', 'otišao je').")
    elif profil["vrijeme"] == "sadašnje":
        upute.append("VRIJEME: sadašnje (npr. 'kaže', 'ide'). Sačuvaj prezent.")

    if profil["lice"] == "prvo":
        upute.append("PRVO LICE (ja). Sačuvaj perspektivu.")
    elif profil["lice"] == "treće":
        upute.append("TREĆE LICE (on/ona). Sačuvaj perspektivu.")

    if profil["ima_unutarnji"]:
        upute.append("UNUTARNJI MONOLOG je prisutan. Sačuvaj introspekciju.")

    if profil["brz_tempo"]:
        upute.append("TEMPO: brz. Kratke rečenice, akcioni glagoli.")
    else:
        upute.append("TEMPO: sporiji. Dozvoli opisima da dišu.")

    if profil["ton"] == "mračan":
        upute.append("TON: mračan, brutalan. Ne ublažavaj.")
    elif profil["ton"] == "vedar":
        upute.append("TON: vedar, topao.")
    else:
        upute.append("TON: neutralan, književni.")

    return "\n".join(upute)


def analiziraj_knjigu(epub_path: str, max_znakova: int = 30000) -> dict:
    """
    Analizira stil iz EPUB-a.
    Uzima prvih max_znakova iz prvih 5 poglavlja.
    """
    import zipfile
    from bs4 import BeautifulSoup

    try:
        with zipfile.ZipFile(epub_path) as z:
            html_names = sorted(
                n for n in z.namelist()
                if n.lower().endswith(('.html', '.xhtml', '.htm'))
                and not any(s in Path(n).name.lower()
                            for s in ('toc', 'nav', 'cover', 'titlepage'))
            )
            tekst = ""
            for name in html_names:
                try:
                    html = z.read(name).decode('utf-8', errors='replace')
                except Exception:
                    continue
                soup = BeautifulSoup(html, 'html.parser')
                body = soup.find('body')
                if body:
                    tekst += body.get_text(' ', strip=True) + " "
                if len(tekst) > max_znakova:
                    break
    except Exception as e:
        return {"greska": str(e)}

    return analiziraj_tekst(tekst[:max_znakova])


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Koristenje: python3 -m core.autor_analiza <knjiga.epub>")
        sys.exit(1)
    profil = analiziraj_knjigu(sys.argv[1])
    print(json.dumps(profil, indent=2, ensure_ascii=False))
    print()
    print("=" * 60)
    print("DINAMIČKI PROMPT:")
    print("=" * 60)
    print(napravi_prompt(profil))
