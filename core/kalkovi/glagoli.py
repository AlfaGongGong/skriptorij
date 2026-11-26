"""
core/kalkovi/glagoli.py
Kategorija: Glagolski vid, rekcija, morfološke greške i
            nepostojeci glagolski oblici (~55 zamjena)
Autor: BooklyFi QA pipeline — V10.3+

PRIORITET: Ova lista hvata:
  1. Pogrešnu rekciju (čekati NA nekoga → čekati nekoga)
  2. Pogrešne povratne oblike (sjetiti → sjetiti se)
  3. Nepostojeće glagolske oblike koje AI halucinira
     (popivajući, uzdisnuo, osmijehnuo, voljevao...)
  4. Morfološki ispravne ali stilski loše oblike

UPOZORENJE: Glagolski oblici su osjetljivi na kontekst.
Svaki pattern je pažljivo ograničen lookahead/lookbehind
da ne dirne legitimne slučajeve.
"""

GLAGOLI = [
    # ══════════════════════════════════════════════════════════════
    # 1. HALUCIRANI GLAGOLSKI OBLICI (morfološke halucinacije)
    #    Nepostojeci oblici koje AI stvara po analogiji
    # ══════════════════════════════════════════════════════════════
    # "popivajući" → "ispijajući" (gerundiv od "popiti" ne postoji)
    (r"\bpopivajući\b", "ispijajući"),
    (r"\bpopivat\b", "ispijati"),
    # "uzdisnuo" → "uzdahnuo" (pravilni perfekt od "uzdahnuti")
    (r"\buzdisnuo\b", "uzdahnuo"),
    (r"\buzdisla\b", "uzdahnula"),
    (r"\buzdisli\b", "uzdahnuli"),
    (r"\buzdisnuti\b", "uzdahnuti"),
    # "osmijehnuo" → "nasmiješio" (smiješiti se, ne osmijehnuti)
    (r"\bosmijehnuo\b", "nasmiješio"),
    (r"\bosmijehnula\b", "nasmiješila"),
    (r"\bosmijehnuli\b", "nasmiješili"),
    (r"\bosmijehnuti\b", "nasmiješiti se"),
    # "voljevao" — halucinacija, ne postoji
    (r"\bvoljevao\b", "volio"),
    (r"\bvoljevala\b", "voljela"),
    (r"\bvoljevali\b", "voljeli"),
    # "hodavao" / "hodavala" — iterativni imperfekt ne postoji za "hodati"
    (r"\bhodavao\b", "hodao"),
    (r"\bhodavala\b", "hodala"),
    (r"\bhodavali\b", "hodali"),
    # "gledavao" — ne postoji
    (r"\bgledavao\b", "gledao"),
    (r"\bgledavala\b", "gledala"),
    (r"\bgledavali\b", "gledali"),
    # "vidjevao" — ne postoji (vid- je korijen, perfekt je vidio)
    (r"\bvidjevao\b", "vidio"),
    (r"\bvidjevala\b", "vidjela"),
    (r"\bvidjevali\b", "vidjeli"),
    # "čujevao" — ne postoji
    (r"\bčujevao\b", "čuo"),
    (r"\bčujevala\b", "čula"),
    (r"\bčujevali\b", "čuli"),
    # "pisavao" — halucinacija
    (r"\bpisavao\b", "pisao"),
    (r"\bpisavala\b", "pisala"),
    # "govorio je da" + infinitiv bez "da" (srpski uticaj)
    # Ostaviti za prompt_injector, previše kontekstualno za regex
    # ══════════════════════════════════════════════════════════════
    # 2. POGREŠNA REKCIJA
    # ══════════════════════════════════════════════════════════════
    # "čekati na nekoga" → "čekati nekoga" (HR/BS norma)
    # Točniji: samo "čekati NA + ličnu zamjenicu" je pogrešno
    # "pitati za" nešto → "pitati za" je OK, ali "pitati NA pitanje" nije
    # ══════════════════════════════════════════════════════════════
    # 3. POGREŠNI POVRATNI OBLICI
    # ══════════════════════════════════════════════════════════════
    # "sjetiti" bez "se" (refleksivni glagol uvijek traži "se")
    # Oprezno: samo kad nije već "sjetiti se"
    # "dosjetiti" bez "se"
    # "smijati" bez "se" (u značenju laughing)
    # Previše opasno za regex — preskačemo, handled u prompt_injector
    # ══════════════════════════════════════════════════════════════
    # 4. STILSKI LOŠI ALI GRAMATIČKI OK OBLICI
    # ══════════════════════════════════════════════════════════════
    # "reče sam" → "rekoh" (arhaični narativni perfekt u dijalogu)
    # F1.4 ZAMRZNUTO: brise zamjenicu koja kaze ko govori
    # (r"\breče\s+ona\b", "reče"),  # "reče ona" → "reče" (redundantno)
    # F1.4 ZAMRZNUTO: brise zamjenicu koja kaze ko govori
    # (r"\breče\s+on\b", "reče"),
    # "govoreći" + direktni citat (anglizam)
    # Npr: "Govoreći: 'Idemo'" → "'Idemo'"
    # Previše kontekstualno — preskačemo
    # "biti u mogućnosti" → "moći"
    (r"\bbiti\s+u\s+mogućnosti\s+(?:da\s+)?(?=[a-zčćšžđ])", "moći "),
    (r"\bbio\s+u\s+mogućnosti\s+(?:da\s+)?(?=[a-zčćšžđ])", "mogao "),
    (r"\bbila\s+u\s+mogućnosti\s+(?:da\s+)?(?=[a-zčćšžđ])", "mogla "),
    # "izvršiti" → direktan glagol (nominalizacija)
    # [ovo je granično s kalkovima — dodajemo najsigurnije]
    (r"\bizvršiti\s+prijevod\b", "prevesti"),
    (r"\bizvršiti\s+provjeru\b", "provjeriti"),
    (r"\bizvršiti\s+analizu\b", "analizirati"),
    (r"\bizvršiti\s+procjenu\b", "procijeniti"),
    (r"\bizvršiti\s+plaćanje\b", "platiti"),
    (r"\bizvršiti\s+napad\b", "napasti"),
    (r"\bizvršiti\s+bijeg\b", "pobjeći"),
    # "vršiti pritisak" → "pritiskati"
    (r"\bvršiti\s+pritisak\b", "pritiskati"),
    (r"\bvrši\s+pritisak\b", "pritišće"),
    (r"\bvršio\s+pritisak\b", "pritiskao"),
]
