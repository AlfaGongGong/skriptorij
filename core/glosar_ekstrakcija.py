#!/usr/bin/env python3
"""core/glosar_ekstrakcija.py — Ekstrakcija, cistka i AI provjera glosara."""

import re
import json
from collections import Counter


STOP_RIJECI = set("""
The And But Or Of To In On At For With By From As Is Was Were Be Been Being
Have Has Had Do Does Did Will Would Could Should May Might Must Can This That
These Those It Its He She They We You I Me Him Her Them Us My Your His Their
Our No Not So If Then Than Too There Here Where When Why How What Which Who
Whom All Any Some One Two Three Now Just Only Very Well Even Still Yet Also
Back Down Up Out Off Over Under Through Yes Oh Ah Hey Please Thanks Thank
Sorry Hello Maybe Perhaps Indeed Like Get Got Don Didn Wasn Couldn Isn Are
Man Men Woman Women Boy Girl Child Father Mother Son Daughter Brother Sister
King Queen Lord Lady Sir Madam Mr Mrs Miss Colonel Captain Lieutenant
Sergeant Corporal General Marshal Duke Duchess Prince Princess Chief Priest
Priestess Prophet God Goddess Holy Saint Devil Hell Heaven Gods Damn Shit
Fuck Fucking Bloody Good Bad Best Worst Better Worse Big Small Little Old
New Young Long Short High Low Deep Shallow Wide Narrow Right Left Wrong
True False Real Fake First Last Next Same Other Another Every Each Both
None Many Much More Most Less Least Few Several Enough Nothing Everything
Something Anything Someone Anyone Everyone Nobody Anybody Everybody
Whatever Whichever Whoever Wherever Whenever However Because Though
Although While Until Unless Since After Before During Without Within
Between Among Against Toward Towards Upon Into Onto About Around Near Far
Away Anywhere Somewhere Everywhere Nowhere Always Never Sometimes Often
Usually Rarely Once Twice Again Already Quite Rather Fairly Pretty Really
Truly Actually Exactly Probably Possibly Certainly Surely Definitely
Absolutely Honestly Sadly Hopefully Luckily Unfortunately Naturally
Obviously Clearly Apparently Basically Essentially Especially Particularly
Specifically Generally Normally Typically Commonly Frequently Occasionally
Seldom Hardly Barely Scarcely Nearly Almost Completely Totally Entirely
Fully Partly Slightly Somewhat Extremely Incredibly Amazingly Surprisingly
Shockingly Strangely Oddly Curiously Interestingly Funny Weird Strange Odd
Unusual Normal Usual Common Typical Regular Ordinary Average Standard
Special Unique Different Similar Equal Identical Various Numerous Countless
Endless Infinite Order Company Battle War Peace Freedom Citadel Castle Fort
Fortress Tower Bridge Gate Wall Island Mountain River Forest Wood Field
Valley Hill Plain Desert Sea Ocean Lake Pond Stream Road Path Street Lane
Way Trail Track Circle World Time Morning Evening Night Day Summer Winter
Spring Autumn Fall Dawn Dusk Sun Moon Star Sky Cloud Rain Snow Wind Fire
Water Earth Air Light Dark Shadow Hope Fear Love Hate Joy Sorrow Pain
Pleasure Life Death Birth Age Youth Beauty Truth Lie Justice Mercy Vengeance
Honor Glory Shame Pride Courage Cowardice Wisdom Folly Strength Weakness
Power Wealth Poverty Health Sickness Food Drink Bread Meat Wine Beer House
Home Room Door Window Roof Floor Bed Chair Table Book Page Word Letter Pen
Sword Shield Armor Helmet Knife Axe Spear Bow Arrow Horse Dog Cat Bird Fish
Wolf Bear Lion Eagle Snake Dragon
Nije Ali Sto Možda Samo Ako Kako Kada Zato Tako Onda Sada Ovdje Tamo Gdje
Zašto Jer Ipak Naravno Svakako Dakle Nego Niti Ili Zatim Poslije Prije Osim
Prema Protiv Bez Kroz Iznad Ispod Unatoč Usprkos Nakon Tijekom Bilo Bila
Bio Bili Bile Bitno Bože Gospode Hvala Molim Izvoli Izvolite
""".split())


def mehanicka_cistka(imena, min_pojava=3):
    """Obrisi stop-rijec, titule, prekratke."""
    rezultat = {}
    for ime, broj in imena.items():
        if broj < min_pojava:
            continue
        if ime in STOP_RIJECI:
            continue
        if len(ime) < 4:
            continue
        if "'" in ime:
            continue
        rezultat[ime] = broj
    return rezultat


def detektuj_jezik(epub_path):
    """Vrati 'HR' ili 'EN' na osnovu prvih paragrafa."""
    import zipfile
    from bs4 import BeautifulSoup

    try:
        with zipfile.ZipFile(epub_path) as z:
            for n in z.namelist():
                if not n.endswith((".xhtml", ".html", ".htm")):
                    continue
                try:
                    html = z.read(n).decode("utf-8", errors="replace")
                except Exception:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                tekst = soup.get_text(" ", strip=True)[:5000].lower()
                if len(tekst) < 500:
                    continue

                hr_dijakritici = sum(tekst.count(c) for c in "čćžšđ")
                hr_rijeci = 0
                for w in [" je ", " se ", " da ", " na ", " za ", " koji ", " koja ", " koje ", " nije ", " kao "]:
                    hr_rijeci += tekst.count(w)
                en_rijeci = 0
                for w in [" the ", " and ", " of ", " is ", " to ", " a ", " in ", " that ", " was ", " he ", " she "]:
                    en_rijeci += tekst.count(w)

                hr_score = hr_dijakritici + hr_rijeci * 3
                en_score = en_rijeci * 3

                if hr_score > en_score * 1.5:
                    return "HR"
                elif en_score > hr_score * 1.5:
                    return "EN"
    except Exception:
        pass
    return "EN"


def posalji_ai_batch(jezik, batch, fleet):
    """Posalji batch AI-ju. Rotira SVE providere. Ako svi padnu — deterministicki fallback."""
    from network.http_client import api_call

    if jezik == "HR":
        SYSTEM = """Ti si urednik hrvatskog knjizevnog teksta.

Dobit ces listu termina iz HR knjige. Za SVAKI termin odluci:

  1. Je li to VLASTITO IME (lik, mjesto) ili SPECIFICAN TERMIN?
     - DA: lik, mjesto, termin
     - NE: obicna hrvatska rijec, veznik, glagol, pridjev

  2. Ako je DA:
     - kategorija: lik | mjesto | termin
     - hr: POTVRDI postojeci hrvatski oblik (ne mijenjaj ako je OK)
     - spoji_sa: ako je nadimak/varijanta, navedi glavni. Inace null.

  3. Ako je NE: vrati {"en": "...", "izbaci": true}

Vrati ISKLJUCIVO JSON:
{"rezultati": [{"en": "Sev", "kategorija": "lik", "hr": "Sev", "spoji_sa": "Sevedija"}]}
"""
    else:
        SYSTEM = """Ti si strucnjak za knjizevni prijevod s engleskog na hrvatski.

Dobit ces listu termina iz EN knjige. Za SVAKI termin odluci:

  1. Je li to VLASTITO IME (lik, mjesto) ili SPECIFICAN TERMIN?
  2. Ako je DA:
     - kategorija: lik | mjesto | termin
     - hr: hrvatski oblik (npr. Shev -> Sev)
     - spoji_sa: nadimak/varijanta glavnog.
  3. Ako je NE: vrati {"en": "...", "izbaci": true}

Vrati ISKLJUCIVO JSON. Budi STROG.
"""
    lista = "\n".join("- " + t for t in batch)
    user_prompt = "Termini:\n\n" + lista

    # Rotiraj kroz SVE moguce providere (redoslijed: brzi/stabilni prvi)
    PROVIDERI = ["GEMINI", "CLOUDFLARE", "GROQ", "MISTRAL", "NVIDIA", "OPENROUTER", "GEMMA"]

    for provider in PROVIDERI:
        try:
            key = fleet.get_best_key(provider)
            if not key:
                continue
            api_key = key.key if hasattr(key, "key") else str(key)
            model = fleet.get_active_model(provider)
            if not model:
                continue

            # GEMMA ne podrzava system role — merge u user
            if not getattr(fleet.get_profile(provider) if hasattr(fleet, "get_profile") else None, "supports_system_role", True):
                merged = SYSTEM + "\n\n" + user_prompt
                res = api_call(provider=provider, model=model, api_key=api_key,
                               system="", user=merged,
                               temperature=0.2, max_tokens=4000, timeout=120)
            else:
                res = api_call(provider=provider, model=model, api_key=api_key,
                               system=SYSTEM, user=user_prompt,
                               temperature=0.2, max_tokens=4000, timeout=120)
            if not res:
                continue

            clean = re.sub(r"```(?:json)?\s*", "", res).replace("```", "").strip()
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start < 0 or end <= start:
                continue
            data = json.loads(clean[start:end])

            rezultati = {}
            for r in data.get("rezultati", []):
                en = (r.get("en") or "").strip()
                if not en:
                    continue
                if r.get("izbaci"):
                    rezultati[en] = {"izbaci": True}
                else:
                    rezultati[en] = {
                        "kategorija": r.get("kategorija", "termin"),
                        "hr": r.get("hr", en),
                        "spoji_sa": r.get("spoji_sa") or "",
                    }
            if rezultati:
                return rezultati
        except Exception:
            continue

    # DETERMINISTICKI FALLBACK — svi AI provideri pali
    # Vlastita imena ostaju nepromijenjena, kategorija "lik"
    rezultati = {}
    for t in batch:
        if not t or not t.strip():
            continue
        # Heuristika: pocinje velikim slovom = vjerovatno vlastito ime
        if t[0].isupper():
            rezultati[t.strip()] = {
                "kategorija": "lik",
                "hr": t.strip(),
                "spoji_sa": "",
            }
    return rezultati
