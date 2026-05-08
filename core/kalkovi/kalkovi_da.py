"""
core/kalkovi/da.py
Kategorija: Suvišno "da" uz glagole (srbizmi / balkanski sintaktički kalk)

U standardnom bosanskom/hrvatskom književnom jeziku infinitiv se koristi
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

import re

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
    (r"\bmogu\s+da\s+(\w+im|\w+em|\w+am)\b", r"mogu \1"),  # 1. l. jd
    (r"\bmožeš\s+da\s+(\w+iš|\w+eš|\w+aš)\b", r"možeš \1"),
    (r"\bmože\s+da\s+(\w+i|\w+e|\w+a)\b", r"može \1"),
    (r"\bmožemo\s+da\s+(\w+imo|\w+emo|\w+amo)\b", r"možemo \1"),
    (r"\bmožete\s+da\s+(\w+ite|\w+ete|\w+ate)\b", r"možete \1"),
    # Nisu mogli da → nisu mogli
    (r"\bnijesu\s+mogli\s+da\s+(\w+)", r"nisu mogli \1"),
    (r"\bnijesu\s+mogle\s+da\s+(\w+)", r"nisu mogle \1"),
    (r"\bnisu\s+mogli\s+da\s+(\w+)", r"nisu mogli \1"),
    (r"\bnisu\s+mogle\s+da\s+(\w+)", r"nisu mogle \1"),
    (r"\bnisam\s+mogao\s+da\s+(\w+)", r"nisam mogao \1"),
    (r"\bnisam\s+mogla\s+da\s+(\w+)", r"nisam mogla \1"),
    (r"\bnisi\s+mogao\s+da\s+(\w+)", r"nisi mogao \1"),
    (r"\bnisi\s+mogla\s+da\s+(\w+)", r"nisi mogla \1"),
    (r"\bnije\s+mogao\s+da\s+(\w+)", r"nije mogao \1"),
    (r"\bnije\s+mogla\s+da\s+(\w+)", r"nije mogla \1"),
    (r"\bnismo\s+mogli\s+da\s+(\w+)", r"nismo mogli \1"),
    (r"\bniste\s+mogli\s+da\s+(\w+)", r"niste mogli \1"),
    # Perfekt
    (r"\bmogao\s+je\s+da\s+(\w+)", r"mogao je \1"),
    (r"\bmogla\s+je\s+da\s+(\w+)", r"mogla je \1"),
    (r"\bmogli\s+su\s+da\s+(\w+)", r"mogli su \1"),
    (r"\bmogle\s+su\s+da\s+(\w+)", r"mogle su \1"),
    (r"\bmogao\s+sam\s+da\s+(\w+)", r"mogao sam \1"),
    (r"\bmogla\s+sam\s+da\s+(\w+)", r"mogla sam \1"),
    (r"\bmogao\s+si\s+da\s+(\w+)", r"mogao si \1"),
    (r"\bmogla\s+si\s+da\s+(\w+)", r"mogla si \1"),
    (r"\bmogli\s+smo\s+da\s+(\w+)", r"mogli smo \1"),
    (r"\bmogle\s+smo\s+da\s+(\w+)", r"mogle smo \1"),
    (r"\bmogli\s+ste\s+da\s+(\w+)", r"mogli ste \1"),
    # Kondicional
    (r"\bbih\s+mogao\s+da\s+(\w+)", r"bih mogao \1"),
    (r"\bbih\s+mogla\s+da\s+(\w+)", r"bih mogla \1"),
    (r"\bbi\s+mogao\s+da\s+(\w+)", r"bi mogao \1"),
    (r"\bbi\s+mogla\s+da\s+(\w+)", r"bi mogla \1"),
    (r"\bbi\s+mogli\s+da\s+(\w+)", r"bi mogli \1"),
    (r"\bbismo\s+mogli\s+da\s+(\w+)", r"bismo mogli \1"),
    (r"\bbiste\s+mogli\s+da\s+(\w+)", r"biste mogli \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 2. MORATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bmoram\s+da\s+(\w+)", r"moram \1"),
    (r"\bmoraš\s+da\s+(\w+)", r"moraš \1"),
    (r"\bmora\s+da\s+(\w+)", r"mora \1"),
    (r"\bmoramo\s+da\s+(\w+)", r"moramo \1"),
    (r"\bmorati\s+da\s+(\w+)", r"morati \1"),
    (r"\bmorao\s+je\s+da\s+(\w+)", r"morao je \1"),
    (r"\bmorala\s+je\s+da\s+(\w+)", r"morala je \1"),
    (r"\bmorali\s+su\s+da\s+(\w+)", r"morali su \1"),
    (r"\bmorale\s+su\s+da\s+(\w+)", r"morale su \1"),
    (r"\bmorao\s+sam\s+da\s+(\w+)", r"morao sam \1"),
    (r"\bmorala\s+sam\s+da\s+(\w+)", r"morala sam \1"),
    (r"\bmorao\s+si\s+da\s+(\w+)", r"morao si \1"),
    (r"\bmorala\s+si\s+da\s+(\w+)", r"morala si \1"),
    (r"\bmorali\s+smo\s+da\s+(\w+)", r"morali smo \1"),
    (r"\bmorali\s+ste\s+da\s+(\w+)", r"morali ste \1"),
    (r"\bnije\s+morao\s+da\s+(\w+)", r"nije morao \1"),
    (r"\bnisam\s+morao\s+da\s+(\w+)", r"nisam morao \1"),
    (r"\bnisam\s+morala\s+da\s+(\w+)", r"nisam morala \1"),
    (r"\bnisi\s+morao\s+da\s+(\w+)", r"nisi morao \1"),
    (r"\bnismo\s+morali\s+da\s+(\w+)", r"nismo morali \1"),
    (r"\bmorao\s+bih\s+da\s+(\w+)", r"morao bih \1"),
    (r"\bmorala\s+bih\s+da\s+(\w+)", r"morala bih \1"),
    (r"\bmorao\s+bi\s+da\s+(\w+)", r"morao bi \1"),
    (r"\bmorala\s+bi\s+da\s+(\w+)", r"morala bi \1"),
    (r"\bmorali\s+bi\s+da\s+(\w+)", r"morali bi \1"),
    (r"\bmorali\s+bismo\s+da\s+(\w+)", r"morali bismo \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 3. SMJETI / SMETI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bsmijem\s+da\s+(\w+)", r"smijem \1"),
    (r"\bsmiješ\s+da\s+(\w+)", r"smiješ \1"),
    (r"\bsmije\s+da\s+(\w+)", r"smije \1"),
    (r"\bsmijemo\s+da\s+(\w+)", r"smijemo \1"),
    (r"\bsmijete\s+da\s+(\w+)", r"smijete \1"),
    (r"\bsmem\s+da\s+(\w+)", r"smijem \1"),
    (r"\bsmeš\s+da\s+(\w+)", r"smiješ \1"),
    (r"\bsme\s+da\s+(\w+)", r"smije \1"),
    (r"\bsmemo\s+da\s+(\w+)", r"smijemo \1"),
    (r"\bsmete\s+da\s+(\w+)", r"smijete \1"),
    (r"\bnie\s+smio\s+da\s+(\w+)", r"nije smio \1"),
    (r"\bnije\s+smio\s+da\s+(\w+)", r"nije smio \1"),
    (r"\bnije\s+smjela\s+da\s+(\w+)", r"nije smjela \1"),
    (r"\bnisam\s+smio\s+da\s+(\w+)", r"nisam smio \1"),
    (r"\bnisam\s+smjela\s+da\s+(\w+)", r"nisam smjela \1"),
    (r"\bsmio\s+je\s+da\s+(\w+)", r"smio je \1"),
    (r"\bsmjela\s+je\s+da\s+(\w+)", r"smjela je \1"),
    (r"\bsmjeli\s+su\s+da\s+(\w+)", r"smjeli su \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 4. HTJETI / HTETI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bhoću\s+da\s+(\w+)", r"hoću \1"),
    (r"\bhoćeš\s+da\s+(\w+)", r"hoćeš \1"),
    (r"\bhoće\s+da\s+(\w+)", r"hoće \1"),
    (r"\bhoćemo\s+da\s+(\w+)", r"hoćemo \1"),
    (r"\bhoćete\s+da\s+(\w+)", r"hoćete \1"),
    (r"\bneću\s+da\s+(\w+)", r"neću \1"),
    (r"\bnećeš\s+da\s+(\w+)", r"nećeš \1"),
    (r"\bneće\s+da\s+(\w+)", r"neće \1"),
    (r"\bnećemo\s+da\s+(\w+)", r"nećemo \1"),
    (r"\bnećete\s+da\s+(\w+)", r"nećete \1"),
    (r"\bhtio\s+je\s+da\s+(\w+)", r"htio je \1"),
    (r"\bhtjela\s+je\s+da\s+(\w+)", r"htjela je \1"),
    (r"\bhtjeli\s+su\s+da\s+(\w+)", r"htjeli su \1"),
    (r"\bhtjele\s+su\s+da\s+(\w+)", r"htjele su \1"),
    (r"\bhtio\s+sam\s+da\s+(\w+)", r"htio sam \1"),
    (r"\bhtjela\s+sam\s+da\s+(\w+)", r"htjela sam \1"),
    (r"\bhtio\s+si\s+da\s+(\w+)", r"htio si \1"),
    (r"\bhtjeli\s+smo\s+da\s+(\w+)", r"htjeli smo \1"),
    (r"\bhtjeli\s+ste\s+da\s+(\w+)", r"htjeli ste \1"),
    (r"\bnisam\s+htio\s+da\s+(\w+)", r"nisam htio \1"),
    (r"\bnisam\s+htjela\s+da\s+(\w+)", r"nisam htjela \1"),
    (r"\bnije\s+htio\s+da\s+(\w+)", r"nije htio \1"),
    (r"\bnije\s+htjela\s+da\s+(\w+)", r"nije htjela \1"),
    (r"\bnisu\s+htjeli\s+da\s+(\w+)", r"nisu htjeli \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 5. ŽELJETI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bželim\s+da\s+(\w+)", r"želim \1"),
    (r"\bželiš\s+da\s+(\w+)", r"želiš \1"),
    (r"\bželi\s+da\s+(\w+)", r"želi \1"),
    (r"\bželimo\s+da\s+(\w+)", r"želimo \1"),
    (r"\bželite\s+da\s+(\w+)", r"želite \1"),
    (r"\bžele\s+da\s+(\w+)", r"žele \1"),
    (r"\bželio\s+je\s+da\s+(\w+)", r"želio je \1"),
    (r"\bželjela\s+je\s+da\s+(\w+)", r"željela je \1"),
    (r"\bželjeli\s+su\s+da\s+(\w+)", r"željeli su \1"),
    (r"\bželio\s+sam\s+da\s+(\w+)", r"želio sam \1"),
    (r"\bželjela\s+sam\s+da\s+(\w+)", r"željela sam \1"),
    (r"\bželio\s+si\s+da\s+(\w+)", r"želio si \1"),
    (r"\bželjeli\s+smo\s+da\s+(\w+)", r"željeli smo \1"),
    (r"\bnisam\s+želio\s+da\s+(\w+)", r"nisam želio \1"),
    (r"\bnisam\s+željela\s+da\s+(\w+)", r"nisam željela \1"),
    (r"\bnije\s+želio\s+da\s+(\w+)", r"nije želio \1"),
    (r"\bnije\s+željela\s+da\s+(\w+)", r"nije željela \1"),
    (r"\bnisu\s+željeli\s+da\s+(\w+)", r"nisu željeli \1"),
    (r"\bželio\s+bih\s+da\s+(\w+)", r"želio bih \1"),
    (r"\bželjela\s+bih\s+da\s+(\w+)", r"željela bih \1"),
    (r"\bželi\s+bi\s+da\s+(\w+)", r"želi bi \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 6. POČETI / POČINJATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bpočinjem\s+da\s+(\w+)", r"počinjem \1"),
    (r"\bpočinješ\s+da\s+(\w+)", r"počinješ \1"),
    (r"\bpočinje\s+da\s+(\w+)", r"počinje \1"),
    (r"\bpočinjemo\s+da\s+(\w+)", r"počinjemo \1"),
    (r"\bpočinjete\s+da\s+(\w+)", r"počinjete \1"),
    (r"\bpočeo\s+je\s+da\s+(\w+)", r"počeo je \1"),
    (r"\bpočela\s+je\s+da\s+(\w+)", r"počela je \1"),
    (r"\bpočeli\s+su\s+da\s+(\w+)", r"počeli su \1"),
    (r"\bpočele\s+su\s+da\s+(\w+)", r"počele su \1"),
    (r"\bpočeo\s+sam\s+da\s+(\w+)", r"počeo sam \1"),
    (r"\bpočela\s+sam\s+da\s+(\w+)", r"počela sam \1"),
    (r"\bpočeo\s+si\s+da\s+(\w+)", r"počeo si \1"),
    (r"\bpočeli\s+smo\s+da\s+(\w+)", r"počeli smo \1"),
    (r"\bpočeli\s+ste\s+da\s+(\w+)", r"počeli ste \1"),
    (r"\bnijesam\s+počeo\s+da\s+(\w+)", r"nisam počeo \1"),
    (r"\bnisam\s+počeo\s+da\s+(\w+)", r"nisam počeo \1"),
    (r"\bnisam\s+počela\s+da\s+(\w+)", r"nisam počela \1"),
    (r"\bnije\s+počeo\s+da\s+(\w+)", r"nije počeo \1"),
    (r"\bnije\s+počela\s+da\s+(\w+)", r"nije počela \1"),
    (r"\bnisu\s+počeli\s+da\s+(\w+)", r"nisu počeli \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 7. NASTAVITI / NASTAVLJATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bnastavljam\s+da\s+(\w+)", r"nastavljam \1"),
    (r"\bnastaviš\s+da\s+(\w+)", r"nastaviš \1"),
    (r"\bnastavlja\s+da\s+(\w+)", r"nastavlja \1"),
    (r"\bnastavljamo\s+da\s+(\w+)", r"nastavljamo \1"),
    (r"\bnastavljate\s+da\s+(\w+)", r"nastavljate \1"),
    (r"\bnastavlja\s+se\s+da\s+(\w+)", r"nastavlja se \1"),
    (r"\bnastavio\s+je\s+da\s+(\w+)", r"nastavio je \1"),
    (r"\bnastavila\s+je\s+da\s+(\w+)", r"nastavila je \1"),
    (r"\bnastavili\s+su\s+da\s+(\w+)", r"nastavili su \1"),
    (r"\bnastavio\s+sam\s+da\s+(\w+)", r"nastavio sam \1"),
    (r"\bnastavila\s+sam\s+da\s+(\w+)", r"nastavila sam \1"),
    (r"\bnastavili\s+smo\s+da\s+(\w+)", r"nastavili smo \1"),
    (r"\bnije\s+nastavio\s+da\s+(\w+)", r"nije nastavio \1"),
    (r"\bnije\s+nastavila\s+da\s+(\w+)", r"nije nastavila \1"),
    (r"\bnisu\s+nastavili\s+da\s+(\w+)", r"nisu nastavili \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 8. PRESTATI / PRESTAJATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bprestajem\s+da\s+(\w+)", r"prestajem \1"),
    (r"\bprestaješ\s+da\s+(\w+)", r"prestaješ \1"),
    (r"\bprestaje\s+da\s+(\w+)", r"prestaje \1"),
    (r"\bprestajemo\s+da\s+(\w+)", r"prestajemo \1"),
    (r"\bprestajete\s+da\s+(\w+)", r"prestajete \1"),
    (r"\bprestao\s+je\s+da\s+(\w+)", r"prestao je \1"),
    (r"\bprestala\s+je\s+da\s+(\w+)", r"prestala je \1"),
    (r"\bprestali\s+su\s+da\s+(\w+)", r"prestali su \1"),
    (r"\bprestale\s+su\s+da\s+(\w+)", r"prestale su \1"),
    (r"\bprestao\s+sam\s+da\s+(\w+)", r"prestao sam \1"),
    (r"\bprestala\s+sam\s+da\s+(\w+)", r"prestala sam \1"),
    (r"\bprestali\s+smo\s+da\s+(\w+)", r"prestali smo \1"),
    (r"\bnije\s+prestao\s+da\s+(\w+)", r"nije prestao \1"),
    (r"\bnije\s+prestala\s+da\s+(\w+)", r"nije prestala \1"),
    (r"\bnisu\s+prestali\s+da\s+(\w+)", r"nisu prestali \1"),
    (r"\bnisam\s+prestao\s+da\s+(\w+)", r"nisam prestao \1"),
    (r"\bnisam\s+prestala\s+da\s+(\w+)", r"nisam prestala \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 9. TREBATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\btrebam\s+da\s+(\w+)", r"trebam \1"),
    (r"\btrebaš\s+da\s+(\w+)", r"trebaš \1"),
    (r"\btreba\s+da\s+(\w+)", r"treba \1"),
    (r"\btrebamo\s+da\s+(\w+)", r"trebamo \1"),
    (r"\btrebate\s+da\s+(\w+)", r"trebate \1"),
    (r"\btrebaju\s+da\s+(\w+)", r"trebaju \1"),
    (r"\btrebao\s+je\s+da\s+(\w+)", r"trebao je \1"),
    (r"\btrebala\s+je\s+da\s+(\w+)", r"trebala je \1"),
    (r"\btrebali\s+su\s+da\s+(\w+)", r"trebali su \1"),
    (r"\btrebao\s+sam\s+da\s+(\w+)", r"trebao sam \1"),
    (r"\btrebala\s+sam\s+da\s+(\w+)", r"trebala sam \1"),
    (r"\btrebali\s+smo\s+da\s+(\w+)", r"trebali smo \1"),
    (r"\bnijetrebao\s+da\s+(\w+)", r"nije trebao \1"),  # typo zaštita
    (r"\bnije\s+trebao\s+da\s+(\w+)", r"nije trebao \1"),
    (r"\bnije\s+trebala\s+da\s+(\w+)", r"nije trebala \1"),
    (r"\bnisu\s+trebali\s+da\s+(\w+)", r"nisu trebali \1"),
    (r"\bnisam\s+trebao\s+da\s+(\w+)", r"nisam trebao \1"),
    (r"\bnisam\s+trebala\s+da\s+(\w+)", r"nisam trebala \1"),
    (r"\bnisi\s+trebao\s+da\s+(\w+)", r"nisi trebao \1"),
    (r"\btrebao\s+bi\s+da\s+(\w+)", r"trebao bi \1"),
    (r"\btrebala\s+bi\s+da\s+(\w+)", r"trebala bi \1"),
    (r"\btrebali\s+bi\s+da\s+(\w+)", r"trebali bi \1"),
    (r"\btrebao\s+bih\s+da\s+(\w+)", r"trebao bih \1"),
    (r"\btrebala\s+bih\s+da\s+(\w+)", r"trebala bih \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 10. USPJETI / USPIJEVATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\buspijevam\s+da\s+(\w+)", r"uspijevam \1"),
    (r"\buspijevaš\s+da\s+(\w+)", r"uspijevaš \1"),
    (r"\buspijeva\s+da\s+(\w+)", r"uspijeva \1"),
    (r"\buspijevamo\s+da\s+(\w+)", r"uspijevamo \1"),
    (r"\buspijevate\s+da\s+(\w+)", r"uspijevate \1"),
    (r"\buspijevaju\s+da\s+(\w+)", r"uspijevaju \1"),
    (r"\buspio\s+je\s+da\s+(\w+)", r"uspio je \1"),
    (r"\buspjela\s+je\s+da\s+(\w+)", r"uspjela je \1"),
    (r"\buspjeli\s+su\s+da\s+(\w+)", r"uspjeli su \1"),
    (r"\buspio\s+sam\s+da\s+(\w+)", r"uspio sam \1"),
    (r"\buspjela\s+sam\s+da\s+(\w+)", r"uspjela sam \1"),
    (r"\buspjeli\s+smo\s+da\s+(\w+)", r"uspjeli smo \1"),
    (r"\bnije\s+uspio\s+da\s+(\w+)", r"nije uspio \1"),
    (r"\bnije\s+uspjela\s+da\s+(\w+)", r"nije uspjela \1"),
    (r"\bnisu\s+uspjeli\s+da\s+(\w+)", r"nisu uspjeli \1"),
    (r"\bnisam\s+uspio\s+da\s+(\w+)", r"nisam uspio \1"),
    (r"\bnisam\s+uspjela\s+da\s+(\w+)", r"nisam uspjela \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 11. ZNATI (u smislu "umjeti")
    # ══════════════════════════════════════════════════════════════════════
    (
        r"\bznam\s+da\s+(plivam|vozim|čitam|pišem|kuvam|kuhám|sviram|pjevam|plešem|trčim)\b",
        r"znam \1",
    ),
    (r"\bznaš\s+da\s+(pliva[šs]|vozi[šs]|čita[šs]|piše[šs])\b", r"znaš \1"),
    (
        r"\bzna\s+da\s+(pliva|vozi|čita|piše|kuva|kuha|svira|pjeva|pleše|trči)\b",
        r"zna \1",
    ),
    (r"\bznao\s+je\s+da\s+(\w+)", r"znao je \1"),
    (r"\bznala\s+je\s+da\s+(\w+)", r"znala je \1"),
    (r"\bznali\s+su\s+da\s+(\w+)", r"znali su \1"),
    (r"\bznao\s+sam\s+da\s+(\w+)", r"znao sam \1"),
    (r"\bznala\s+sam\s+da\s+(\w+)", r"znala sam \1"),
    (r"\bnije\s+znao\s+da\s+(\w+)", r"nije znao \1"),
    (r"\bnije\s+znala\s+da\s+(\w+)", r"nije znala \1"),
    (r"\bnisu\s+znali\s+da\s+(\w+)", r"nisu znali \1"),
    (r"\bnisam\s+znao\s+da\s+(\w+)", r"nisam znao \1"),
    (r"\bnisam\s+znala\s+da\s+(\w+)", r"nisam znala \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 12. VOLJETI / VOLITI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bvolim\s+da\s+(\w+)", r"volim \1"),
    (r"\bvoliš\s+da\s+(\w+)", r"voliš \1"),
    (r"\bvoli\s+da\s+(\w+)", r"voli \1"),
    (r"\bvolimo\s+da\s+(\w+)", r"volimo \1"),
    (r"\bvolite\s+da\s+(\w+)", r"volite \1"),
    (r"\bvole\s+da\s+(\w+)", r"vole \1"),
    (r"\bvolio\s+je\s+da\s+(\w+)", r"volio je \1"),
    (r"\bvoljela\s+je\s+da\s+(\w+)", r"voljela je \1"),
    (r"\bvoljeli\s+su\s+da\s+(\w+)", r"voljeli su \1"),
    (r"\bvolio\s+sam\s+da\s+(\w+)", r"volio sam \1"),
    (r"\bvoljela\s+sam\s+da\s+(\w+)", r"voljela sam \1"),
    (r"\bnije\s+volio\s+da\s+(\w+)", r"nije volio \1"),
    (r"\bnije\s+voljela\s+da\s+(\w+)", r"nije voljela \1"),
    (r"\bnisu\s+voljeli\s+da\s+(\w+)", r"nisu voljeli \1"),
    (r"\bnisam\s+volio\s+da\s+(\w+)", r"nisam volio \1"),
    (r"\bnisam\s+voljela\s+da\s+(\w+)", r"nisam voljela \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 13. POKUŠATI / POKUŠAVATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bpokušavam\s+da\s+(\w+)", r"pokušavam \1"),
    (r"\bpokušavaš\s+da\s+(\w+)", r"pokušavaš \1"),
    (r"\bpokušava\s+da\s+(\w+)", r"pokušava \1"),
    (r"\bpokušavamo\s+da\s+(\w+)", r"pokušavamo \1"),
    (r"\bpokušavate\s+da\s+(\w+)", r"pokušavate \1"),
    (r"\bpokušavaju\s+da\s+(\w+)", r"pokušavaju \1"),
    (r"\bpokušao\s+je\s+da\s+(\w+)", r"pokušao je \1"),
    (r"\bpokušala\s+je\s+da\s+(\w+)", r"pokušala je \1"),
    (r"\bpokušali\s+su\s+da\s+(\w+)", r"pokušali su \1"),
    (r"\bpokušao\s+sam\s+da\s+(\w+)", r"pokušao sam \1"),
    (r"\bpokušala\s+sam\s+da\s+(\w+)", r"pokušala sam \1"),
    (r"\bpokušali\s+smo\s+da\s+(\w+)", r"pokušali smo \1"),
    (r"\bnije\s+pokušao\s+da\s+(\w+)", r"nije pokušao \1"),
    (r"\bnije\s+pokušala\s+da\s+(\w+)", r"nije pokušala \1"),
    (r"\bnisu\s+pokušali\s+da\s+(\w+)", r"nisu pokušali \1"),
    (r"\bnisam\s+pokušao\s+da\s+(\w+)", r"nisam pokušao \1"),
    (r"\bnisam\s+pokušala\s+da\s+(\w+)", r"nisam pokušala \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 14. NAMJERAVATI / PLANIRATI / ODLUČITI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bnamjeravam\s+da\s+(\w+)", r"namjeravam \1"),
    (r"\bnamjerava\s+da\s+(\w+)", r"namjerava \1"),
    (r"\bnamjeravao\s+je\s+da\s+(\w+)", r"namjeravao je \1"),
    (r"\bnamjeravala\s+je\s+da\s+(\w+)", r"namjeravala je \1"),
    (r"\bnamjeravao\s+sam\s+da\s+(\w+)", r"namjeravao sam \1"),
    (r"\bplaniram\s+da\s+(\w+)", r"planiram \1"),
    (r"\bplanira\s+da\s+(\w+)", r"planira \1"),
    (r"\bplanirao\s+je\s+da\s+(\w+)", r"planirao je \1"),
    (r"\bplanirala\s+je\s+da\s+(\w+)", r"planirala je \1"),
    (r"\bplanirali\s+su\s+da\s+(\w+)", r"planirali su \1"),
    (r"\bplanirao\s+sam\s+da\s+(\w+)", r"planirao sam \1"),
    (r"\bodlučim\s+da\s+(\w+)", r"odlučim \1"),
    (r"\bodluči\s+da\s+(\w+)", r"odluči \1"),
    (r"\bodlučio\s+je\s+da\s+(\w+)", r"odlučio je \1"),
    (r"\bodlučila\s+je\s+da\s+(\w+)", r"odlučila je \1"),
    (r"\bodlučili\s+su\s+da\s+(\w+)", r"odlučili su \1"),
    (r"\bodlučio\s+sam\s+da\s+(\w+)", r"odlučio sam \1"),
    (r"\bodlučila\s+sam\s+da\s+(\w+)", r"odlučila sam \1"),
    (r"\bodlučili\s+smo\s+da\s+(\w+)", r"odlučili smo \1"),
    (r"\bnije\s+odlučio\s+da\s+(\w+)", r"nije odlučio \1"),
    (r"\bnije\s+odlučila\s+da\s+(\w+)", r"nije odlučila \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 15. ZABORAVITI / SJETITI SE / PAMTITI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bzaboravim\s+da\s+(\w+)", r"zaboravim \1"),
    (r"\bzaboravi\s+da\s+(\w+)", r"zaboravi \1"),
    (r"\bzaboravio\s+je\s+da\s+(\w+)", r"zaboravio je \1"),
    (r"\bzaboravila\s+je\s+da\s+(\w+)", r"zaboravila je \1"),
    (r"\bzaboravili\s+su\s+da\s+(\w+)", r"zaboravili su \1"),
    (r"\bzaboravio\s+sam\s+da\s+(\w+)", r"zaboravio sam \1"),
    (r"\bzaboravila\s+sam\s+da\s+(\w+)", r"zaboravila sam \1"),
    (r"\bnijesam\s+zaboravio\s+da\s+(\w+)", r"nisam zaboravio \1"),
    (r"\bnisam\s+zaboravio\s+da\s+(\w+)", r"nisam zaboravio \1"),
    (r"\bsjetim\s+se\s+da\s+(\w+)", r"sjetim se \1"),
    (r"\bsjeti\s+se\s+da\s+(\w+)", r"sjeti se \1"),
    (r"\bsjetio\s+se\s+da\s+(\w+)", r"sjetio se \1"),
    (r"\bsjetila\s+se\s+da\s+(\w+)", r"sjetila se \1"),
    (r"\bsjetili\s+su\s+se\s+da\s+(\w+)", r"sjetili su se \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 16. NASTOJATI / TRUDITI SE
    # ══════════════════════════════════════════════════════════════════════
    (r"\bnastojim\s+da\s+(\w+)", r"nastojim \1"),
    (r"\bnastoji\s+da\s+(\w+)", r"nastoji \1"),
    (r"\bnastojao\s+je\s+da\s+(\w+)", r"nastojao je \1"),
    (r"\bnastojala\s+je\s+da\s+(\w+)", r"nastojala je \1"),
    (r"\bnastojali\s+su\s+da\s+(\w+)", r"nastojali su \1"),
    (r"\btrudim\s+se\s+da\s+(\w+)", r"trudim se \1"),
    (r"\btrudi\s+se\s+da\s+(\w+)", r"trudi se \1"),
    (r"\btrudimo\s+se\s+da\s+(\w+)", r"trudimo se \1"),
    (r"\btrudio\s+se\s+da\s+(\w+)", r"trudio se \1"),
    (r"\btrudila\s+se\s+da\s+(\w+)", r"trudila se \1"),
    (r"\btrudili\s+su\s+se\s+da\s+(\w+)", r"trudili su se \1"),
    (r"\btrudio\s+sam\s+se\s+da\s+(\w+)", r"trudio sam se \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 17. ODBITI / PRISTATI / OBEĆATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bodbijem\s+da\s+(\w+)", r"odbijem \1"),
    (r"\bodbi[jy]e\s+da\s+(\w+)", r"odbije \1"),
    (r"\bodbijem\s+da\s+(\w+)", r"odbijem \1"),
    (r"\bodbi[jy]o\s+je\s+da\s+(\w+)", r"odbio je \1"),
    (r"\bodbi[jy]la\s+je\s+da\s+(\w+)", r"odbila je \1"),
    (r"\bodb[ij]li\s+su\s+da\s+(\w+)", r"odbili su \1"),
    (r"\bodbi[jy]o\s+sam\s+da\s+(\w+)", r"odbio sam \1"),
    (r"\bpristanem\s+da\s+(\w+)", r"pristanem \1"),
    (r"\bpristane\s+da\s+(\w+)", r"pristane \1"),
    (r"\bpristao\s+je\s+da\s+(\w+)", r"pristao je \1"),
    (r"\bpristala\s+je\s+da\s+(\w+)", r"pristala je \1"),
    (r"\bpristali\s+su\s+da\s+(\w+)", r"pristali su \1"),
    (r"\bobećam\s+da\s+(\w+)", r"obećam \1"),
    (r"\bobeća\s+da\s+(\w+)", r"obeća \1"),
    (r"\bobećao\s+je\s+da\s+(\w+)", r"obećao je \1"),
    (r"\bobećala\s+je\s+da\s+(\w+)", r"obećala je \1"),
    (r"\bobećali\s+su\s+da\s+(\w+)", r"obećali su \1"),
    (r"\bobećao\s+sam\s+da\s+(\w+)", r"obećao sam \1"),
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
    (r"\bnaučim\s+da\s+(\w+)", r"naučim \1"),
    (r"\bnauči\s+da\s+(\w+)", r"nauči \1"),
    (r"\bnaučio\s+je\s+da\s+(\w+)", r"naučio je \1"),
    (r"\bnaučila\s+je\s+da\s+(\w+)", r"naučila je \1"),
    (r"\bnaučili\s+su\s+da\s+(\w+)", r"naučili su \1"),
    (r"\bnaučio\s+sam\s+da\s+(\w+)", r"naučio sam \1"),
    (r"\bnaučila\s+sam\s+da\s+(\w+)", r"naučila sam \1"),
    (r"\bnaviknem\s+da\s+(\w+)", r"naviknem \1"),
    (r"\bnavikne\s+da\s+(\w+)", r"navikne \1"),
    (r"\bnavikao\s+je\s+da\s+(\w+)", r"navikao je \1"),
    (r"\bnavikla\s+je\s+da\s+(\w+)", r"navikla je \1"),
    (r"\bnavikli\s+su\s+da\s+(\w+)", r"navikli su \1"),
    (r"\bnavikao\s+sam\s+da\s+(\w+)", r"navikao sam \1"),
    (r"\bnavikla\s+sam\s+da\s+(\w+)", r"navikla sam \1"),
    (r"\bnavikavam\s+se\s+da\s+(\w+)", r"navikavam se \1"),
    (r"\bnavikava\s+se\s+da\s+(\w+)", r"navikava se \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 20. IZBJEĆI / IZBJEGAVATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bizbj[ée]gavam\s+da\s+(\w+)", r"izbjegavam \1"),
    (r"\bizbj[ée]gava\s+da\s+(\w+)", r"izbjegava \1"),
    (r"\bizbj[ée]gavam\s+da\s+(\w+)", r"izbjegavam \1"),
    (r"\bizbj[ée]gao\s+je\s+da\s+(\w+)", r"izbjegao je \1"),
    (r"\bizbj[ée]gla\s+je\s+da\s+(\w+)", r"izbjegla je \1"),
    (r"\bizbj[ée]gli\s+su\s+da\s+(\w+)", r"izbjegli su \1"),
    (r"\bizbj[ée]gao\s+sam\s+da\s+(\w+)", r"izbjegao sam \1"),
    (r"\bnijesam\s+izbjegao\s+da\s+(\w+)", r"nisam izbjegao \1"),
    (r"\bnisam\s+izbjegao\s+da\s+(\w+)", r"nisam izbjegao \1"),
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
    (r"\bdopustim\s+da\s+(\w+)", r"dopustim \1"),
    (r"\bdopusti\s+da\s+(\w+)", r"dopusti \1"),
    (r"\bdopustio\s+je\s+da\s+(\w+)", r"dopustio je \1"),
    (r"\bdopustila\s+je\s+da\s+(\w+)", r"dopustila je \1"),
    (r"\bdozvolim\s+da\s+(\w+)", r"dozvolim \1"),
    (r"\bdozvoli\s+da\s+(\w+)", r"dozvoli \1"),
    (r"\bdozvolio\s+je\s+da\s+(\w+)", r"dozvolio je \1"),
    (r"\bdozvolila\s+je\s+da\s+(\w+)", r"dozvolila je \1"),
    (r"\bdozvolili\s+su\s+da\s+(\w+)", r"dozvolili su \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 22. OSTATI / ZADRŽATI SE
    # ══════════════════════════════════════════════════════════════════════
    (r"\bostajem\s+da\s+(\w+)", r"ostajem \1"),
    (r"\bostaje\s+da\s+(\w+)", r"ostaje \1"),
    (r"\bostao\s+je\s+da\s+(\w+)", r"ostao je \1"),
    (r"\bostala\s+je\s+da\s+(\w+)", r"ostala je \1"),
    (r"\bostali\s+su\s+da\s+(\w+)", r"ostali su \1"),
    (r"\bostao\s+sam\s+da\s+(\w+)", r"ostao sam \1"),
    (r"\bostala\s+sam\s+da\s+(\w+)", r"ostala sam \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 23. ZAVRŠITI / DOVRŠITI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bzavršim\s+da\s+(\w+)", r"završim \1"),
    (r"\bzavrši\s+da\s+(\w+)", r"završi \1"),
    (r"\bzavršio\s+je\s+da\s+(\w+)", r"završio je \1"),
    (r"\bzavršila\s+je\s+da\s+(\w+)", r"završila je \1"),
    (r"\bzavršili\s+su\s+da\s+(\w+)", r"završili su \1"),
    (r"\bzavršio\s+sam\s+da\s+(\w+)", r"završio sam \1"),
    (r"\bzavršila\s+sam\s+da\s+(\w+)", r"završila sam \1"),
    (r"\bdovršim\s+da\s+(\w+)", r"dovršim \1"),
    (r"\bdovrši\s+da\s+(\w+)", r"dovrši \1"),
    (r"\bdovršio\s+je\s+da\s+(\w+)", r"dovršio je \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 24. USUDITI SE / SMJELITI SE / ODVAŽITI SE
    # ══════════════════════════════════════════════════════════════════════
    (r"\busuđujem\s+se\s+da\s+(\w+)", r"usuđujem se \1"),
    (r"\busuđuje\s+se\s+da\s+(\w+)", r"usuđuje se \1"),
    (r"\busudio\s+se\s+da\s+(\w+)", r"usudio se \1"),
    (r"\busudila\s+se\s+da\s+(\w+)", r"usudila se \1"),
    (r"\busudili\s+su\s+se\s+da\s+(\w+)", r"usudili su se \1"),
    (r"\busudio\s+sam\s+se\s+da\s+(\w+)", r"usudio sam se \1"),
    (r"\bodvažim\s+se\s+da\s+(\w+)", r"odvažim se \1"),
    (r"\bodvaži\s+se\s+da\s+(\w+)", r"odvaži se \1"),
    (r"\bodvažio\s+se\s+da\s+(\w+)", r"odvažio se \1"),
    (r"\bodvažila\s+se\s+da\s+(\w+)", r"odvažila se \1"),
    # ══════════════════════════════════════════════════════════════════════
    # 25. ČEKATI / JEDVA ČEKATI
    # ══════════════════════════════════════════════════════════════════════
    (r"\bčekam\s+da\s+(\w+)", r"čekam \1"),
    (r"\bčeka\s+da\s+(\w+)", r"čeka \1"),
    (r"\bjedva\s+čekam\s+da\s+(\w+)", r"jedva čekam \1"),
    (r"\bjedva\s+čeka\s+da\s+(\w+)", r"jedva čeka \1"),
    (r"\bčekao\s+je\s+da\s+(\w+)", r"čekao je \1"),
    (r"\bčekala\s+je\s+da\s+(\w+)", r"čekala je \1"),
    (r"\bčekali\s+su\s+da\s+(\w+)", r"čekali su \1"),
]