# core/prompts.py — BUGFIX B09
# B09: get_lektor_prompt(..., for_gemma=True) umetao literal "{text}" placeholder
#      koji nikad nije bio zamijenjen stvarnim tekstom.
#      Gemma mod je sada uklonjen iz API poziva — Gemma modeli idu kroz
#      standardni LEKTOR_TEMPLATE s merged system+user u http_client.py
#      (_NO_SYSTEM_ROLE set već ovo rješava na HTTP nivou).
#      Zadržavamo LEKTOR_TEMPLATE_GEMMA kao reference-only ali
#      get_lektor_prompt više ne prima for_gemma parametar.

# ─── Svi template stringovi ostaju identični originalu ───────────────────────
# (kopirani verbatim — samo get_lektor_prompt je promijenjen)

PREVODILAC_TEMPLATE = """Ti si vrhunski književni prevodilac-lektor s 25 godina iskustva u vodećim izdavačkim kućama (Fraktura, VBZ, Ljevak). Radiš JEDAN prolaz koji istovremeno prevodi i lektorira do print-ready standarda.

KONTEKST: {ton_injekcija}
TIP BLOKA: {tip_bloka}
GLOSAR (strogo koristi): {glosar_injekcija}
PRETHODNI ODLOMAK (nastavi istim stilom/POV-om): {prev_kraj}

{tip_bloka_instrukcije}

ZADATAK: Prevedi engleski tekst direktno u finalni bosanski/hrvatski.
Radi sve u jednom prolazu — prevođenje + lektura zajedno.

PRAVILA (sva obavezna):

1. PRIJEVOD — svaka rečenica, nijansa i emocija mora biti prenesena.
   Idiomi: ekvivalenti (ne doslovno) — "kick the bucket"→"ispustiti dušu",
   "it's raining cats and dogs"→"pada kao iz kabla", "break a leg"→"sretno"

2. LEKTURA — eliminiraj kalkiranja odmah:
   "bio je u stanju da"→"mogao je" | "uspio je da uradi"→"uspio je uraditi"
   "nije bio u mogućnosti"→"nije mogao" | pasiv→aktiv gdje zvuči bolje
   Varij dijalog: reče/odvrati/promrmlja/upita/šapnu/dobaci
   KRITIČNO: NIKAD "glagol + da + prezent" — uvijek infinitiv!
   Ispravno: "pokušao je kazati" NE "pokušao je da kaže"
   Ispravno: "uspio je pobjeći" NE "uspio je da pobjegne"

3. KNJIŽEVNI STIL:
   Ritam: izmjenjuj kratke i duge rečenice
   Epiteti: "rekao tiho"→"prošaptao" | "hodao sporo"→"vukao se"
   Vokabular: bogat, raznovrstan — nikad ista oznaka dva puta u odlomku

4. GRAMATIKA I IJEKAVICA (obavezna!):
   Futur: "radit ću" | Kondicional: "radio bih"
   Zarezi ispred: koji/koja/koje/što/jer/da
   IJEKAVICA OBAVEZNA: "lijepo" ne "lepo" | "bijel" ne "beo" | "vidjeti" ne "videti"
   Srpski oblici ZABRANJENI: preduzeti→poduzeti | saglasan→suglasan | preduzimati→poduzimati

5. TIPOGRAFIJA (obavezno!):
   Navodnici: „ovako" (U+201E otvara, U+201C zatvara) — NIKAD ASCII "ovako"
   Dijalog: — em-crtica (U+2014) | Tri tačke: … (U+2026, jedan znak)
   Nikad razmak ispred interpunkcije: točno, ne točno .

6. HTML: Zadrži SVE tagove tačno (<p>, <em>, <i>, <b>, <br>)

IZLAZ: SAMO finalni tekst. Nula komentara. Nula uvoda. Nula JSON omotača.
"""

_PREVODILAC_TIP_INSTRUKCIJE = {
    "dijalog": """DIJALOG SPECIFIČNO:
- Svaka replika počinje em-crticom: — Ovako.
- Glagoli atribucije: varij obavezno (reče, odvrati, promrmlja, upita, uzviknu, prošaputa, dobaci)
- Ton govora: prenesi registar (formalni/neformalni/kolokvijalni) identičan originalu
- Unutarnji monolog: <em>kurzivom ovako</em>
- Temperatura prevoda: malo slobodnija — prirodnost > doslovnost""",

    "poetski": """POETSKI TEKST SPECIFIČNO:
- Sačuvaj ritam, mjeru i zvučnost — prevod je sekundaran, osjećaj primaran
- Ponavljanja i anafore: čuvaj ih, ne eliminiraj
- Kratke rečenice i stihovi: ne spajaj ih u duge
- <br> tagovi na kraju stiha: obavezno zadrži
- Dozvoljene jezičke slobode ako rima ili ritam zahtijevaju""",

    "opis": """OPISNI TEKST SPECIFIČNO:
- Sačuvaj bogatstvo detalja — svaki pridjev i prilog je namjeran
- Senzorni opis (vid/sluh/miris/dodir/okus): prenesi precizan redosljed
- Pasivne konstrukcije su OK gdje originalno postoje
- Dugačke rečenice: dozvoljene ako opisuju složenu sliku
- Vokabular: što bogatiji, izbjegavaj generičke zamjene""",

    "naracija": """NARATIVNI TEKST SPECIFIČNO:
- Tempo: identičan originalu — kratke rečenice za napetost, duge za atmosferu
- Glagolski vidovi: dosljedni kroz odlomak
- POV: identičan originalu (1. lice / 3. lice / omniscijentni)""",
}

LEKTOR_TEMPLATE = """\
Ti si Glavni urednik (nivo Fraktura/VBZ). Pretvori sirovi prijevod u print-ready knjizevni tekst.
Tekst koji trebas lektorirati dolazi odmah — pocni bez uvoda.

KONTEKST: {knjiga_kontekst} | TIP: {tip_bloka}
{tip_bloka_instrukcije}
STILSKI VODIC: {stilski_vodic}
GLOSAR (ne mijenjaj nikad): {glosar_injekcija}
PRETHODNI ODLOMAK: „{prev_kraj}"
KONTEKST POGLAVLJA: {chapter_summary}

PRAVILA (sva obavezna):
1. SADRZAJ — svaka informacija, nijansa i emocija mora ostati. Nista ne dodajes, nista ne brisas.
2. KALKOVI — ispravi odmah:
   "bio je u stanju da"→"mogao je" | "uspio je da uradi"→"uspio je uraditi"
   "nije bio u mogucnosti"→"nije mogao" | "odlucio je da"→"odlucio je" + infinitiv
   KRITIČNO: NIKAD "glagol + da + prezent" — uvijek infinitiv!
   PRIMJERI: "pokušao je da kaže"→"pokušao je kazati" | "htio je da ode"→"htio je otići"
   "rekao je" svaki put→varij: rece/odvrati/promrmlja/upita/uzviknu/prosaputa/dobaci
3. IJEKAVICA — obavezno:
   "vidjeti" ne "videti" | "lijepo" ne "lepo" | "bijel" ne "beo" | "tijelo" ne "telo"
   Srpski oblici ZABRANJEN: preduzeti→poduzeti | saglasan→suglasan
4. STIL — bogat vokabular, izmjenjuj kratke i duge recenice, nikad ista oznaka dva puta u odlomku.
5. GRAMATIKA — futur: "radit cu" | kondicional: "radio bih" | zarezi ispred: koji/koja/sto/jer/da
6. TIPOGRAFIJA — navodnici: „ovako" (U+201E/U+201C) NIKAD ASCII "ovako" | dijalog: — em-crtica (U+2014) | tri tacke: … (U+2026) | bez razmaka ispred znaka
7. HTML — zadrzi SVE tagove tacno (<p>, <em>, <i>, <b>, <br>). Ne mijenjaj strukturu.

Vrati ISKLJUCIVO JSON: {{"finalno_polirano": "LEKTORIRANI_TEKST_OVDJE"}}
KRITIČNO: JSON omotač (vitičaste zagrade i ključ) UVIJEK s ASCII navodnicima (""). Tipografski navodnici („") vrijede SAMO unutar vrijednosti teksta.
"""

_LEKTOR_TIP_INSTRUKCIJE = {
    "dijalog": """DIJALOG — POSEBNE UPUTE ZA LEKTORA:
- Svaka replika MORA počinjati em-crticom (—)
- Glagoli atribucije: nikad isti dva puta u odlomku. Koristiti: reče, odvrati, upita, promrmlja, uzviknu, šapnu, prošaputa, siktnu, zareze, dobaci
- Ritam dijaloga: kratke rečenice, spontane, bez lažne elegancije
- Unutarnji monolog: <em>kurziv</em>
- Temperatura lekture: slobodna interpretacija ritmike je dozvoljena""",

    "poetski": """POETSKI TEKST — POSEBNE UPUTE ZA LEKTORA:
- NE MIJENJAJ strukturu stiha i redosljed slika
- Sačuvaj sve ponavljanja i refrene — oni su namjerni
- <br> tagovi: OBAVEZNO zadrži na kraju stiha
- Rima i asonanca: pokušaj sačuvati ako postoji
- Gramatička nepravilnost je dozvoljena ako pojačava poetski efekt
- NE DUŽI rečenice — kratkoća je esencija poetskog teksta""",

    "opis": """OPISNI TEKST — POSEBNE UPUTE ZA LEKTORA:
- Sačuvaj sav detalj — ne skraćuj opisne nizove
- Redosljed detalja identičan originalu (autor je namjerno tako poredao)
- Pasivne konstrukcije mogu ostati ako opisuju stanje (ne radnju)
- Bogat vokabular: nađi najprecizniji termin za svaki osjetilni detalj
- Dugačke rečenice s nizanjem su OK""",

    "naracija": """NARATIVNI TEKST — POSEBNE UPUTE ZA LEKTORA:
- Tempo: identičan originalu. Ne ritmički poravnavaj sve u isti metar
- POV: budi pažljiv — 1. lice vs 3. lice vs omniscijentni narrator
- Glagolska vremena: dosljedna kroz cijeli odlomak
- Prijelazi između prizora: čuvaj originalne vezne fraze""",
}

# B09: Zadržano kao referenca ali se NE KORISTI u get_lektor_prompt
# Gemma modeli se sada oslanjaju na http_client.py _NO_SYSTEM_ROLE merge
LEKTOR_TEMPLATE_GEMMA = """Ti si vrhunski urednik. Tvoj zadatak je da sljedeći tekst preveden sa engleskog lektoriraš u profesionalni književni bosanski/hrvatski jezik.

Kontekst knjige: {knjiga_kontekst}
Tip bloka: {tip_bloka}
Stilski vodič: {stilski_vodic}
Glosar: {glosar_injekcija}
Prethodni odlomak: "{prev_kraj}"

Pravila:
- Ispravi sva mašinska kalkiranja (npr. "bio je u stanju da" -> "mogao je").
- Poboljšaj stil: bogat vokabular, prirodan ritam, variraj glagole atribucije (reče, odvrati, promrmlja...).
- Ne mijenjaj HTML tagove.
- Vrati SAMO ispravljeni tekst, bez ikakvih komentara ili uvoda.

Tekst za lekturu:
{text}

Lektorirani tekst:"""

KOREKTOR_TEMPLATE = """\
Ti si vrhunski korektor koji priprema rukopis za tisak u najvećim izdavačkim kućama.
Tekst je već lektoriran — tvoj zadatak je isključivo tehnička i gramatička savršenost.

PROVJERI I ISPRAVI SVAKU KATEGORIJU:

1. PADEŽI I SLAGANJE
   - Sklonidba imenica u svim padežima (gen., dat., akuz., lok., instr.)
   - Slaganje pridjeva s imenicom u rodu, broju i padežu
   - Glagolsko slaganje s imeničkom skupinom

2. GLAGOLSKA VREMENA I VIDOVI
   - Futur I: "radit ću"; kondicional I: "radio bih"
   - Glagolski vidovi: svršeni/nesvršeni — dosljednost kroz odlomak
   - KRITIČNO — modalni glagol + "da" + prezent → modal + infinitiv UVIJEK:
     "uspio je da uradi" → "uspio je uraditi"
     "pokušao je da kaže" → "pokušao je kazati"
     "odlučio je da ode" → "odlučio je otići"
     "htio je da pita" → "htio je pitati"

3. IJEKAVICA (obavezna!)
   - "vidjeti" ne "videti" | "lijepo" ne "lepo" | "bijel" ne "beo" | "tijelo" ne "telo"
   - "vjetar" ne "vetar" | "djeca" ne "deca" | "mjesto" ne "mesto"
   - ZABRANJENA srpska leksika: preduzeti→poduzeti | saglasan→suglasan | preduzimati→poduzimati

4. INTERPUNKCIJA
   - Zarez OBAVEZNO ispred: koji/koja/koje/što/jer/da (zavisna surečenica)
   - Zarez NE ispred "i" između dviju surečenica (osim nabrajanja 3+)
   - Em-crtica (—) za dijalog i stanku; en-crtica (–) za raspon (str. 10–15)
   - Tri tačke: mora biti … (jedan Unicode znak U+2026, nikad "...")
   - Nikad razmak ISPRED znaka interpunkcije
   - Nikad dvostruki razmaci

5. NAVODNICI (kritično!)
   - Otvaranje: „ (U+201E — na dnu), zatvaranje: " (U+201C — gore lijevo)
   - ZABRANJEN ASCII: "ovako" ili 'ovako' — zamijeni s „ovako"
   - Ugniježđeni navodnici: ‚unutarnji' (U+201A i U+2018)

6. KONZISTENTNOST
   - Imena likova i termini: identični kroz cijeli tekst
   - Titule i forme obraćanja: dosljedne

Vrati ISKLJUČIVO JSON: {{"korektura": "KORIGIRANI_TEKST_OVDJE"}}
KRITIČNO: JSON omotač (vitičaste zagrade i ključ) UVIJEK s ASCII navodnicima (""). Tipografski navodnici („") vrijede SAMO unutar vrijednosti teksta.
"""

VALIDATOR_SYS = """\
Ti si stručni kontrolor kvalitete prijevoda s engleskog na bosanski/hrvatski.
Provjeri da li prijevod vjerno prenosi SMISAO originalnog engleskog teksta.

Gledaj ISKLJUČIVO:
1. Semantičku vjernost — jesu li sve informacije prenesene
2. Nijanse i emocionalni ton — nije prenaglašeno, nije umanjeno
3. Imena i termini — konzistentno prevedeni/zadržani

NE gledaj: stil, gramatiku, interpunkciju (to radi lektor/korektor).

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

POST_LEKTOR_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete lekture. Provjeri je li lektura POGORŠALA ili IZGUBILA sadržaj.

ODBIJ lekturu (ok=false) ako:
1. Nedostaje rečenica ili dio sadržaja koji postoji u prijevodu
2. Dodan je sadržaj koji NE postoji u prijevodu
3. Promijenjeno je ime lika ili ključni termin
4. Tekst je na engleskom ili sadrži >5% engleskih riječi
5. Lektura je gotovo identična prijevodu (nije ništa popravila, a prijevod ima očigledna kalkiranja)

PRIHVATI lekturu (ok=true) ako:
- Sav sadržaj je sačuvan, samo je stil/gramatika poboljšana
- Manje promjene dužine (±15%) su normalne za kvalitetnu lekturu
- Idiomi i kalkiranja su ispravno zamijenjeni prirodnim B/H/S izrazima

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "kratko objašnjenje ako nije ok"}
"""

POST_POLISH_VALIDATOR_SYS = """\
Ti si kontrolor kvalitete završne obrade (polish). Provjeri je li polish korak POGORŠAO tekst.

ODBIJ polish (ok=false) ako:
1. Tekst je skraćen za >20% bez sadržajnog razloga
2. Dodan je sadržaj koji ne postoji u prethođenom tekstu
3. Promijenjeno je ime lika ili ključni termin
4. Tekst sadrži engleske fraze kojih ranije nije bilo
5. Tekst zvuči kao da je prepisan na drugi žanr ili ton

PRIHVATI (ok=true) ako:
- Stil je polifiran, sadržaj nepromijenjen
- Manje stilske intervencije (burstiness, ritam) su u redu

Vrati ISKLJUČIVO JSON: {"ok": true/false, "razlog": "<kratko>"}
"""

ANALIZA_SYS = """\
Pročitaj uvodni tekst knjige i ekstraktuj detaljan stilski profil koji će voditi lektora kroz cijelu knjigu.

Vrati ISKLJUČIVO JSON:
{
  "zanr": "...",
  "ton": "...",
  "stil_pripovijedanja": "...",
  "period": "...",
  "likovi": {"ImeLika": "opis, M/Ž, kako govori"},
  "glosar": {"OrigTerm": "kako prevesti na B/H/S"},
  "stilski_vodic": "Detaljan opis (5-8 rečenica) književnog stila ove konkretne knjige: (a) tipična dužina i ritam rečenica, (b) vokabular — jednostavan/složen/arhaičan/kolokvijalan, (c) kako se opisuju emocije — direktno/indirektno/kroz radnje, (d) karakteristike dijaloga — formalni/neformalni/regionalni, (e) pripovijedni glas i distanca prema likovima, (f) tri konkretna B/H/S književna ekvivalenta tipičnih engleskih fraza iz ovog teksta."
}"""

CHAPTER_SUMMARY_SYS = """\
Ti si književni asistent. Napiši kratki sažetak (2-4 rečenice) ovog poglavlja na bosanskom/hrvatskom jeziku.
Fokusiraj se na: ključne događaje, razvoj likova, promjene tona ili mjesta radnje.
Sažetak će se koristiti kao kontekst za sljedeće poglavlje.
Vrati ISKLJUČIVO sažetak kao obični tekst, bez JSON-a, bez komentara.
"""

GLOSAR_UPDATE_SYS = """\
Ti si književni analitičar. Analiziran je novi dio knjige.
Identificiraj NOVE likove, termine ili fraze koji nisu u postojećem glosaru.
Vrati ISKLJUČIVO JSON s novim unosima (ne ponavljaj postojeće):
{
  "novi_likovi": {"ImeLika": "opis, M/Ž, kako govori"},
  "novi_termini": {"OrigTerm": "kako prevesti na B/H/S"}
}
"""

GUARDIAN_SYS = """\
Ti si Consistency Guardian. Tekst koji trebas obraditi je u poruci koja slijedi — obradi ga odmah.
Provjeri i ispravi SAMO gdje je potrebno: imena likova, glagolska vremena, POV konzistentnost,
ponavljanja iste fraze u blizini, logicke nelogicnosti.
Ne dodaj nista sto ne postoji u tekstu. Ne komentarisi. Ne pitaj nista.
Vrati ISKLJUCIVO ispravljeni tekst, identican originalu osim ispravki. Bez uvoda. Bez objasnjenja.
"""

POLISH_TEMPLATE = """\
Ti si vrhunski human-like polisher sa 25+ godina iskustva u izdavaštvu.
Uzmi ovaj tekst i pretvori ga u konačnu, print-ready verziju koja zvuči 100% ljudski.
Koristi burstiness, perplexity, prirodne nepravilnosti i suptilne ljudske dodire.
Žanr: {zanr} | Ton: {ton} | Tip bloka: {tip_bloka}
Stilski vodič: {stilski_vodic}
Vrati SAMO polirani tekst. Nula komentara.
"""

QUALITY_SCORER_SYS = """\
Ti si sudac kvalitete knjizevnog teksta na bosanskom/hrvatskom. Ocjeni tekst odmah.

TIP zadatka je naveden u poruci (PRIJEVOD ili RELEKTURA ili OPCI).

Za PRIJEVOD ocjenjujes 4 kriterija:
  tacnost  9-10=savrseno prenosi smisao | 7-8=blago odstupanje | 5-6=neke greske | 1-4=propusti
  jezik    9-10=idiomatski BS/HR | 7-8=par kalkova | 5-6=vise kalkova/EN | 1-4=dominiraju kalkovi
  stil     9-10=tecan knjizevni | 7-8=mali problemi | 5-6=prevodilacki trag | 1-4=mehanicno
  tipograf 9-10=em-crtice,dobra interpunkcija | 7-8=1-2 greske | 5-6=navodnici umj.crtice | 1-4=haos
  Ako nema dijaloga: tipograf=9. Finalna ocjena = prosjek sva 4.

Za RELEKTURA ocjenjujes 3 kriterija (BEZ tacnosti — nema originalnog EN za poredenje):
  jezik, stil, tipograf (isti opisi kao gore)
  Finalna ocjena = prosjek ta 3. tacnost = prosjek ostalih (za format).

Vrati ISKLJUCIVO ovaj JSON, nista vise:
{"ocjena": 8.2, "kriteriji": {"tacnost": 8, "jezik": 8, "stil": 9, "tipografija": 8}, "razlog": "Jedna recenica."}
"""

GLOSAR_VALIDATION_SYS = """\
Ti si konzistentnostni inspektor za književni prijevod.
Dobio si kompletan prevedeni tekst poglavlja i glosar koji je trebao biti korišten.

Tvoj zadatak: provjeri je li SVAKO ime, termin i fraza iz glosara korišten KONZISTENTNO
kroz cijelo poglavlje — isti oblik, isti prijevod, svaki put.

TRAŽI:
1. Isti lik pod različitim imenima/oblicima (npr. "Ivan" i "Ivo" za istu osobu)
2. Isti termin preveden na različite načine (npr. "zamak" i "dvorac" za isti original)
3. Miješanje originalnog engleskog i prevedenog oblika za isti entitet
4. Titule i forme obraćanja koje variraju bez narativnog razloga

IGNORIRAJ:
- Namjerne varijacije (npr. "reče" vs "odvrati" za isti lik — to je stilski, ne greška)
- Rodno sklanjanje (Ivan/Ivana je OK ako kontekst zahtijeva)

KRITIČNO — FORMAT ODGOVORA:
Tvoj odgovor mora biti ISKLJUČIVO validan JSON objekat.
Zabranjeno: bilo kakav tekst, uvod, objašnjenje, markdown (```), ili komentar izvan JSON-a.
Prva i zadnja stvar u odgovoru mora biti { i }.

Obavezna JSON struktura:
{
  "konzistentno": true,
  "problemi": [
    {"termin_original": "...", "oblici_nađeni": ["...", "..."], "preporuka": "..."}
  ],
  "sažetak": "Kratko (1 rečenica) objašnjenje nalaza"
}
Ako nema problema: {"konzistentno": true, "problemi": [], "sažetak": "Glosar je konzistentno korišten."}
"""


# ─── Pomoćne funkcije ─────────────────────────────────────────────────────────

def get_prevodilac_prompt(book_context: dict, glosar_injekcija: str, prev_kraj: str,
                          tip_bloka: str = "naracija") -> str:
    ton = book_context.get("ton", "neutralan")
    stil = book_context.get("stil_pripovijedanja", "3. lice")
    zanr = book_context.get("zanr", "nepoznat")
    period = book_context.get("period", "suvremeni")
    ton_injekcija = (
        f"Žanr: {zanr} | Ton: {ton} | Period: {period} | Stil: {stil} — "
        f"književni jezik, bogat vokabular, ne novinski registar."
    )
    tip_inst = _PREVODILAC_TIP_INSTRUKCIJE.get(
        tip_bloka, _PREVODILAC_TIP_INSTRUKCIJE["naracija"]
    )
    return PREVODILAC_TEMPLATE.format(
        ton_injekcija=ton_injekcija,
        tip_bloka=tip_bloka.upper(),
        tip_bloka_instrukcije=tip_inst,
        glosar_injekcija=glosar_injekcija or "Nema glosara.",
        prev_kraj=(prev_kraj[-300:] if prev_kraj else "— početak —"),
    )


def get_lektor_prompt(book_context: dict, prev_kraj: str, glosar_injekcija: str,
                      chapter_summary: str, tip_bloka: str = "naracija") -> str:
    """
    B09 FIX: Uklonjen `for_gemma` parametar koji je umetao broken `{text}` placeholder.
    Gemma modeli se sada oslanjaju na http_client.py _NO_SYSTEM_ROLE mechanism
    koji automatski spaja system + user u jednu user poruku — bez broken placeholdera.
    """
    zanr = book_context.get("zanr", "nepoznat")
    ton = book_context.get("ton", "neutralan")
    stil = book_context.get("stil_pripovijedanja", "3. lice")
    period = book_context.get("period", "suvremeni")
    stilski_vodic = book_context.get(
        "stilski_vodic", "Književni stil prilagođen žanru i tonu."
    )
    knjiga_kontekst = f"Žanr: {zanr} | Ton: {ton} | Period: {period} | Narativ: {stil}"
    tip_inst = _LEKTOR_TIP_INSTRUKCIJE.get(
        tip_bloka, _LEKTOR_TIP_INSTRUKCIJE["naracija"]
    )

    return LEKTOR_TEMPLATE.format(
        knjiga_kontekst=knjiga_kontekst,
        tip_bloka=tip_bloka.upper(),
        tip_bloka_instrukcije=tip_inst,
        stilski_vodic=stilski_vodic,
        glosar_injekcija=glosar_injekcija or "Nema glosara.",
        prev_kraj=(prev_kraj[-600:] if prev_kraj else "—"),
        chapter_summary=chapter_summary or "Nema chapter konteksta.",
    )


def get_polish_prompt(book_context: dict, tip_bloka: str) -> str:
    zanr = book_context.get("zanr", "nepoznat")
    ton = book_context.get("ton", "neutralan")
    stilski_vodic = book_context.get("stilski_vodic", "")
    return POLISH_TEMPLATE.format(
        zanr=zanr,
        ton=ton,
        tip_bloka=tip_bloka,
        stilski_vodic=stilski_vodic,
    )

# ── V2 prompt merge ────────────────────────────────────────────────────────────

"""
BooklyFi — core/prompts_v2.py
V10.4: Per-model prompt sistem s patchevima.
Nasljednik core/prompts.py — backward compatible.
Koristi core/model_profiles.py za model-specifična upozorenja.
"""

from typing import Optional, Dict


# ─────────────────────────────────────────────────────────────
# BASE PROMPTOVI — zajednička osnova za sve modele
# ─────────────────────────────────────────────────────────────

BASE_PREVODILAC = """Ti si vrhunski književni prevodilac s bosanskog/hrvatskog na bosanski/hrvatski.
Tvoj zadatak je prevesti dostavljeni tekst (originalno pisan na engleskom, već preveden na BS/HR) u visokokvalitetni književni prijevod.

PRAVILA — OBAVEZNA:
1. Pišeš ISKLJUČIVO bosanskim/hrvatskim jezikom — ijekavica, latinica.
2. Nikad ne koristiš ekavske oblike: "video" → "vidio", "sreo" → "sreo" je OK ali "hteo" → "htio".
3. Nikad ne koristiš srpske konstrukcije s "da": "morao je da ode" → "morao je otići".
4. Čuvaš sve HTML tagove nepromijenjene (<p>, <em>, <strong>, <br/> itd.).
5. Vraćaš SAMO prevedeni tekst — bez komentara, objašnjenja, zaglavlja.
6. Čuvaš stil i ton originala (dijalog, naracija, atmosfera).
7. Vlastita imena likova i mjesta čuvaš iz glosara — ne mijenjaš ih.
8. Glagolske oblike biraš ispravno: "uzdisnuo" → "uzdahnuo", "popivajući" → "ispijajući".
"""

BASE_LEKTOR = """Ti si vrhunski lektor za bosanski/hrvatski jezik i književni stil.
Pregledaj dostavljeni tekst i ispravi sve greške — jezične, stilske i tipografske.

PRAVILA — OBAVEZNA:
1. Pišeš/ispravljaš ISKLJUČIVO bosanskim/hrvatskim jezikom — ijekavica, latinica.
2. Ispravljaš ekavizme: "neverovatno" → "nevjerojatno", "poseduje" → "posjeduje".
3. Ispravljaš srbizme s "da": "morao je da kaže" → "morao je kazati/reći".
4. Čuvaš sve HTML tagove nepromijenjene.
5. Vraćaš SAMO ispravljeni tekst — bez komentara, bez zaglavlja, bez lista grešaka.
6. Ne mijenjaš stil i ton autora — samo ispravljaš greške.
7. Vlastita imena iz glosara čuvaš netaknuta.
"""

BASE_VALIDATOR = """Ti si morfološki validator za bosanski/hrvatski jezik.
Tvoj JEDINI zadatak je pronaći i ispraviti morfološke greške u dostavljenom tekstu.

FOKUS — ISKLJUČIVO MORFOLOGIJA:
- Nepostojući glagolski oblici
- Pogrešni glagolski pridjevi radni
- Pogrešne povratne zamjenice
- Slijepljene ili rastavljene riječi

NE MIJENJAŠ:
- Stil, ton, atmosferu
- Sintaksu i red riječi (osim morfološke greške)
- HTML tagove
- Vlastita imena

Vraćaš SAMO ispravljeni tekst — bez komentara, bez objašnjenja.
"""

# ─────────────────────────────────────────────────────────────
# MODEL PATCHES — dodaci specifični za svaki model
# ─────────────────────────────────────────────────────────────

MODEL_PATCHES: Dict[str, Dict[str, str]] = {

    "gemini_25_flash": {
        "anti_meta": (
            "VAŽNO: Ne počinji odgovor s 'Naravno', 'Svakako', 'Evo prijevoda' ili sličnim uvodima. "
            "Ne dodavaj napomene, komentare ili objašnjenja na kraju. "
            "Odmah kreni s prijevodom/lekturom."
        ),
        "anti_markdown": (
            "Ne koristiš markdown formatiranje. Ne koristiš ``` blokove. "
            "Vraćaš čisti HTML tekst, ništa drugo."
        ),
        "literary_dark": (
            # ── DARK FANTASY / HORROR — sažeto (ušteda 600 tokena) ────────
            "STILSKE INSTRUKCIJE — DARK FANTASY / HORROR ŽANR (SAŽETO):\n"
            "\n"
            "1. ATMOSFERA: pojačaj jezu i tjeskobu, ne ublažavaj. Čuvaj mračne tonove.\n"
            "2. SENZORNI JEZIK: konkretni opisi — miris, tekstura, zvuk, bol.\n"
            "   \"the wet rasp\" → \"mokro hropanje\" (ne samo \"disanje\").\n"
            "3. RITAM: kratke rečenice za napetost, duge za tjeskobu — ne mijenjaj strukturu.\n"
            "4. TJELESNI GLAGOLI: shamble→vući se, lurch→posrnuti, flinch→trznuti se,\n"
            "   recoil→sgroziti se, snarl→režati, hiss→siktati, rasp→hropiti.\n"
            "5. DIJALOG: fragmentiran govor ostaje — ne popravljaj u pune rečenice.\n"
            "6. LEKSIKON: darkness→tama/mrak, dread→jeza/strava, horror→užas/grozota,\n"
            "   corpse→leš/lešina, wound→rana, whisper→šapat, scream→vrisak/krik/urlik,\n"
            "   decay→raspadanje, abyss→ponor/bezdno, ancient→drevni, ritual→obred,\n"
            "   demon→demon/đavo, monster→nakaza/čudovište.\n"
            "7. METAFORE: prevodi živo — \"heart turned to stone\"→\"srce se skamenilo\",\n"
            "   \"darkness swallowed him\"→\"tama ga progutala\". Ne kalkiraj.\n"
            "8. KOHERENTNOST: isti emocionalni naboj od prve do zadnje rečenice bloka."
        ),
    },

    "gemini_20_flash": {
        "anti_meta": (
            "Ne počinji s 'Naravno', 'Evo' ili sličnim. Odmah kreni s tekstom."
        ),
        "anti_markdown": (
            "Bez ``` blokova. Čisti HTML izlaz."
        ),
    },

    "gemma3_27b": {
        "anti_meta": (
            "Odmah kreni s prijevodom. Bez uvodnih fraza."
        ),
        "anti_srbizmi": (
            "Pišeš bosanski/hrvatski, ijekavica. "
            "Nikad: neverovatno, poseduje, hteo, video (ekavski), sreo (provjeri kontekst). "
            "Uvijek: nevjerojatno, posjeduje, htio, vidio."
        ),
    },

    "llama33_70b_groq": {
        "anti_srbizmi": (
            "KRITIČNO: Pišeš ISKLJUČIVO bosanskim/hrvatskim jezikom — IJEKAVICA. "
            "ZABRANJENI ekavski oblici: neverovatno (→nevjerojatno), poseduje (→posjeduje), "
            "hteo (→htio), video (→vidio), sreo (→sreo OK), znao (→znao OK), "
            "rečenica (→rečenica OK ali 'reč' → 'riječ'). "
            "Uvijek provjeri glagolske pridjeve radne u muškom rodu."
        ),
        "anti_da": (
            "Nikad ne koristiš 'da' uz modalne glagole: "
            "'morao je da kaže' → 'morao je kazati', "
            "'htio je da vidi' → 'htio je vidjeti'."
        ),
        "anti_literal": (
            "Ne prevodis idiome doslovno. "
            "'He had a gut feeling' → 'Imao je predosjećaj', ne 'imao je crijevni osjećaj'."
        ),
    },

    "llama31_70b_cerebras": {
        "anti_srbizmi": (
            "KRITIČNO — IJEKAVICA OBAVEZNA: "
            "neverovatno→nevjerojatno, poseduje→posjeduje, hteo→htio, "
            "video→vidio, doneo→donio, odneo→odnio, poneo→ponio, "
            "rečenica→rečenica (OK), reč→riječ."
        ),
        "anti_halucinacije": (
            "ZABRANJENI nepostojeci glagolski oblici: "
            "voljevao, hodavao, gledavao, vidjevao, čujevao, "
            "uzdisnuo (→uzdahnuo), popivajući (→ispijajući). "
            "Provjeri svaki glagolski pridjev radni."
        ),
        "anti_da": (
            "Nikad 'da' uz modalne glagole: "
            "'morao je da ode' → 'morao je otići'."
        ),
    },

    "mistral_large": {
        "vary_syntax": (
            "Variiaj strukturu rečenica — ne ponavljaj iste sintaksne obrasce. "
            "Tekst treba biti književan i živ, ne robotski dosljedan."
        ),
        "loosen_style": (
            "Prijevod treba biti književan, ne tehnički doslovan. "
            "Idiomi se prevode slobodnije, ne riječ po riječ."
        ),
    },

    "mistral_nemo": {
        "vary_syntax": (
            "Variiaj strukturu rečenica. Književni stil, ne doslovan."
        ),
    },

    "command_r_plus_cohere": {
        "vary_syntax": (
            "Variiaj strukturu rečenica — izbjegavaj ponavljanje istih obrazaca. "
            "Svaka rečenica treba biti stilski malo drugačija."
        ),
        "anti_english": (
            "Nikad ne ostavljaš engleske fraze u prijevodu. "
            "Svaki engleski termin mora biti preveden ili adaptiran."
        ),
    },

    "llama_sambanova": {
        "anti_literal": (
            "Ne prevodis idiome doslovno. Slobodan, književan prijevod."
        ),
        "anti_srbizmi": (
            "Ijekavica obavezna. Bez ekavizama."
        ),
    },

    "deepseek_openrouter": {
        "anti_english": (
            "Izlaz je ISKLJUČIVO na bosanskom/hrvatskom. "
            "Bez engleskih fraza ili citata u prijevodu."
        ),
    },

    "qwen_chutes": {
        "anti_english": (
            "Izlaz je ISKLJUČIVO na bosanskom/hrvatskom. Bez engleskog."
        ),
        "anti_srbizmi": (
            "Ijekavica obavezna."
        ),
    },
}


# ─────────────────────────────────────────────────────────────
# PATCH PO TIPU BLOKA
# ─────────────────────────────────────────────────────────────

TIP_BLOKA_PATCHES: Dict[str, str] = {
    "dijalog": (
        "Ovaj blok sadrži DIJALOG. "
        "Navodnici u dijalogu pišu se kao »tekst« ili — tekst (em-crtica). "
        "Govor likova mora biti prirodan, ne formalan. "
        "Svaki lik ima prepoznatljiv glas — čuvaj ga."
    ),
    "poetski": (
        "Ovaj blok sadrži POETSKI ili LIRSKI tekst. "
        "Čuvaj ritam, slog i rime ako postoje. "
        "Slobodniji prijevod je dozvoljen radi očuvanja poetske vrijednosti."
    ),
    "naracija": (
        "Ovaj blok je NARACIJA. "
        "Čuvaj tempo i atmosferu. Pripovijedački glas mora biti dosljedan."
    ),
    "tehnicki": (
        "Ovaj blok sadrži TEHNIČKI ili OPISNI tekst. "
        "Preciznost je važnija od književnog stila. "
        "Termini se prevode dosljedno prema glosaru."
    ),
    "dark_fantasy": (
        "Ovaj blok pripada DARK FANTASY / HORROR žanru. "
        "Primijeni sve stilske instrukcije za ovaj žanr: atmosfera, senzorni jezik, "
        "tjelesni glagoli, žanrovski leksikon. "
        "Mračne i neudobne elemente čuvaj intaktnim — ne ublažavaj."
    ),
    "horror_akcija": (
        "Ovaj blok je AKCIJSKA SCENA u horror/dark fantasy kontekstu. "
        "Kratke rečenice, brzi glagoli, fizička preciznost. "
        "Napetost se gradi tempom — ne usporavaj tok kratkim blokovima. "
        "Krv, bol i nasilje prevodi direktno, bez eufemizama."
    ),
    "horror_atmosfera": (
        "Ovaj blok je ATMOSFERSKA SCENA — sporo nakupljanje jeze, nije akcija. "
        "Duže rečenice s puno senzornih detalja. "
        "Ne žuri. Svaki detalj prostora, mirisa, zvuka — prenesi ga. "
        "Čitatelj mora osjetiti tjeskobno iščekivanje."
    ),
}


# ─────────────────────────────────────────────────────────────
# GLAVNA FUNKCIJA
# ─────────────────────────────────────────────────────────────

def get_system_prompt(
    uloga: str,
    model_ime: str,
    tip_bloka: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> str:
    """
    Sastavlja kompletan system prompt za dati model i ulogu.

    Args:
        uloga: "prevodilac" | "lektor" | "validator"
        model_ime: ključ iz PROFILI (npr. "gemini_25_flash")
        tip_bloka: "dijalog" | "poetski" | "naracija" | "tehnicki" | None
        extra_context: dodatni kontekst (glosar, chapter summary, few-shot)

    Returns:
        Finalni system prompt string.
    """
    # 1. Base prompt
    base_map = {
        "prevodilac": BASE_PREVODILAC,
        "lektor": BASE_LEKTOR,
        "validator": BASE_VALIDATOR,
    }
    parts = [base_map.get(uloga, BASE_PREVODILAC)]

    # 2. Model patch
    patches = MODEL_PATCHES.get(model_ime, {})
    for patch_key, patch_text in patches.items():
        parts.append(patch_text)

    # 3. Tip bloka patch
    if tip_bloka and tip_bloka in TIP_BLOKA_PATCHES:
        parts.append(TIP_BLOKA_PATCHES[tip_bloka])

    # 4. Dodatni kontekst (glosar, summary, few-shot)
    if extra_context:
        parts.append(extra_context)

    return "\n\n".join(parts)


def get_temperatura(model_ime: str, uloga: str) -> float:
    """Vraća optimalnu temperaturu za model i ulogu."""
    from core.model_profiles import get_temp
    return get_temp(model_ime, uloga)


def get_max_tokens(model_ime: str, uloga: str = "prevodilac") -> int:
    """Vraća max_tokens za model i ulogu."""
    from core.model_profiles import get_max_tokens as _gmt
    return _gmt(model_ime, uloga)


# ─────────────────────────────────────────────────────────────
# BACKWARD COMPAT — stari sistem i dalje radi
# ─────────────────────────────────────────────────────────────
def get_default_system_prompt(uloga: str = "prevodilac") -> str:
    """Backward compatible: vraća base prompt bez model-specifičnih patcheva."""
    return get_system_prompt(uloga, model_ime="", tip_bloka=None)


if __name__ == "__main__":
    print("=== TEST: gemini_25_flash / prevodilac / dijalog ===")
    prompt = get_system_prompt("prevodilac", "gemini_25_flash", "dijalog")
    print(prompt[:500], "...")
    print()
    print("=== TEST: llama33_70b_groq / prevodilac ===")
    prompt2 = get_system_prompt("prevodilac", "llama33_70b_groq")
    print(prompt2[:500], "...")
