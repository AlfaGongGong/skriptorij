#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_audit_v3.py — lektorski audit strojno prevedenog EPUB-a (EN → HR/BS/SR)

Arhitektura: MOTOR (pravila koja vrijede za svaku knjigu) + PROFIL (sve što je
naučeno na jednoj knjizi: imena, pragovi, isključena pravila, preskočene datoteke).

Upotreba:
    python3 epub_audit_v3.py knjiga_hr.epub
    python3 epub_audit_v3.py knjiga_hr.epub --profile profiles/first_law.json
    python3 epub_audit_v3.py knjiga_hr.epub --source knjiga_en.epub --learn-names
    python3 epub_audit_v3.py knjiga_hr.epub --disable zamjenice,truncated
    python3 epub_audit_v3.py --list-rules --profile profiles/first_law.json

Svojstva:
  * deterministički: isti ulaz + isti profil → bajt-identični izlazi (idempotentno)
  * auditabilno: *_audit_run.json bilježi SHA-256 ulaza/profila/izlaza i efektivnu konfiguraciju
  * samo standardna biblioteka (radi u Termuxu bez pip-a)
"""
from __future__ import annotations

import argparse
import copy
import csv
import difflib
import hashlib
import html as html_mod
import io
import json
import math
import os
import posixpath
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import unquote

VERSION = "3.0"

# ═══════════════════════════════════════════════════════════════
# KONSTANTE (motor — ne ovise o knjizi)
# ═══════════════════════════════════════════════════════════════

SEV_ORDER = {"info": 1, "upozorenje": 2, "greška": 3}
SEV_LABEL = {"greška": "GREŠKA", "upozorenje": "UPOZ", "info": "INFO"}
DC_NS = "{http://purl.org/dc/elements/1.1/}"
WORD_RE = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])[\"“”»]?\s+(?=[A-ZČĆĐŠŽ„“\"»(])")
TERM_CHARS = set('.!?…:;)]}»«"„“”’\'*—–')

# Varijante ciljnog jezika: koja se skupina pravila primjenjuje.
LANGS = {
    "hr": {"codes": ("hr", "hrv"), "ekav": True, "dijalekt": True},
    "bs": {"codes": ("bs", "bos"), "ekav": True, "dijalekt": False},
    "sr": {"codes": ("sr", "srp"), "ekav": False, "dijalekt": False},
}

# Zadani profil. Profil iz datoteke PREPISUJE ključeve (liste se zamjenjuju, ne spajaju);
# "thresholds" se spaja ključ po ključ.
DEFAULT_THRESHOLDS = {
    "sentence_words_floor": 60,     # donja granica: rečenica kraća od ovoga nikad se ne prijavljuje
    "paragraph_chars_floor": 2000,  # isto za pasus (znakovi)
    "percentile": 99.0,             # granica = max(floor, percentil_knjige * factor)
    "percentile_factor": 1.5,
    "pron_per_par": 3,              # rečenica koje počinju zamjenicom + glagolom u jednom pasusu
    "min_style_samples": 20,        # min. uzoraka da bi se proglasio "dominantni stil"
    "minority_ratio": 0.2,          # stil s udjelom manjim od ovoga je "manjinski"
    "learn_names_min_count": 1,     # min. pojavljivanja imena u izvorniku
    "learn_names_lower_ratio": 0.1, # dopušten udio malih slova (May/may → nije ime)
}

DEFAULT_PROFILE = {
    "name": "default",
    "language": "hr",
    "names": {},              # {en: hr} — ime_en
    "proper_names": [],       # riječi koje nisu greška kad su velikim slovom usred rečenice
    "foreign_ok": ["lady", "lord", "sir", "madam", "mister", "sherry", "whisky"],
    #   "x*" = prefiks (obuhvaća padeže), "x" = točno taj oblik
    "skip_files": [],         # regex na putanju: datoteka se uopće ne čita kao poglavlje
    "structure_skip_files": [r"content\.opf", r"(?:nav|toc)\.xhtml"],  # bez provjere h1/praznih <p>
    "chapter_number_regex": r"(?:POGLAVLJE|Poglavlje)\s+(\d+)",
    "lang_accept": None,      # None → prema varijanti jezika
    "quote_style": "auto",    # auto | hr | off
    "learn_names": None,      # None → uključeno ako je zadan --source
    "skip_fantasy": False,
    "disabled_rules": [],
    "thresholds": {},
    "extra_rules": [],        # [{pattern, code, severity, message, suggestion, ignore_case}]
}

PLACES_EN_HR = {
    "Germany": "Njemačka", "France": "Francuska", "England": "Engleska",
    "Spain": "Španjolska", "Italy": "Italija", "Switzerland": "Švicarska",
    "Netherlands": "Nizozemska", "Holland": "Nizozemska", "Russia": "Rusija",
    "Hungary": "Mađarska", "Poland": "Poljska", "Sweden": "Švedska",
    "Denmark": "Danska", "Greece": "Grčka", "Turkey": "Turska",
    "Egypt": "Egipat", "Scotland": "Škotska", "Ireland": "Irska",
    "Vienna": "Beč", "Prague": "Prag", "Rome": "Rim", "Venice": "Venecija",
    "Munich": "München", "Cologne": "Köln", "Moscow": "Moskva",
    "Warsaw": "Varšava", "Athens": "Atena", "Brussels": "Bruxelles",
    "Copenhagen": "Kopenhagen", "Lisbon": "Lisabon", "Belgrade": "Beograd",
    "Florence": "Firenca", "Naples": "Napulj", "Geneva": "Ženeva",
    "Mediterranean": "Sredozemno more", "Atlantic": "Atlantik",
    "Pacific": "Pacifik", "Baltic": "Baltik",
}

EN_STOP = {
    "the", "an", "this", "that", "these", "those",
    "you", "she", "it", "we", "they",
    "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "yours", "hers", "ours", "theirs",
    "myself", "yourself", "himself", "herself", "itself",
    "ourselves", "themselves",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "does", "did", "doing", "done",
    "will", "would", "shall", "should", "can", "could",
    "may", "might", "must",
    "don't", "didn't", "doesn't", "won't", "wouldn't",
    "can't", "couldn't", "shouldn't", "isn't", "aren't",
    "wasn't", "weren't", "haven't", "hasn't", "hadn't",
    "of", "in", "at", "by", "for", "with", "without",
    "from", "into", "onto", "upon", "about", "above",
    "below", "over", "under", "between", "through", "during",
    "before", "after", "since", "until", "till", "while",
    "and", "or", "but", "nor", "yet", "because",
    "if", "unless", "though", "although", "whereas",
    "than", "then", "as",
    "not", "yes", "very", "too", "also", "only", "just",
    "still", "already", "again", "ever", "never", "always",
    "sometimes", "often", "rarely", "seldom", "usually",
    "here", "there", "where", "when", "why", "how",
    "now", "soon", "later",
    "some", "any", "every", "each", "all", "both", "either", "neither",
    "few", "little", "many", "much", "less", "least",
    "several", "enough",
    "well", "okay", "yeah", "yep", "nope",
    "i'm", "i've", "i'll", "i'd",
    "you're", "you've", "you'll", "you'd",
    "he's", "she's", "it's", "we're", "they're",
    "we've", "they've", "we'll", "they'll",
    "that's", "what's", "who's", "there's", "here's",
}

EN_STRUCT = {
    "chapter", "prologue", "epilogue", "contents", "introduction",
    "acknowledgements", "acknowledgments", "foreword", "preface",
    "afterword", "dedication", "appendix", "glossary", "index",
}

ABBR_HR = {
    "npr", "tj", "itd", "itsl", "dr", "sv", "g", "gđa", "gđica", "str",
    "usp", "god", "br", "tzv", "prof", "mr", "ing", "ul", "tel", "kn",
    "čl", "sl", "vl", "ur", "pr", "isp", "ok", "ibid", "bl", "kat", "pl",
    "gosp", "fra", "don", "sr", "hr", "dipl", "inž", "mag", "doc",
    "k", "o", "r", "t", "v", "ž", "b", "p", "s", "u", "z",
}

SKIP_BACK = set(" \u00a0„“”\"»«‘’'()[]–—-")

CODE_LABEL = {
    "neprevedeno_dio": "Nepreveden / djelomično engleski odlomak",
    "engleska_riječ": "Engleska riječ u hrvatskom tekstu",
    "ekavica": "Ekavski oblik",
    "dijalekt": "Srbizam/bosnizam (odstupanje od hr. standarda)",
    "purizam": "Anglicizam/internacionalizam (purizam)",
    "kalk": "Kalk / doslovni prijevod",
    "ime_en": "Englesko ime nije prilagođeno",
    "mjesto_en": "Engleski egzonim umjesto hrvatskog",
    "ime_strano_pismo": "Ime sa stranim slovima/grafemima",
    "ime_nedosljedno": "Nedosljedno pisanje imena",
    "strano_slovo_riječ": "Riječ sa stranim slovima/grafemima",
    "navodnici": "Navodnici (stil, parnost)",
    "navodnici_stil": "Navodnici: odstupanje od dominantnog stila knjige",
    "neparni_navodnik": "Neparni navodnik (bez para)",
    "crtica": "Crtice / spojnice",
    "crtica_stil": "Dijaloška crtica: odstupanje od dominantnog stila knjige",
    "interpunkcija": "Interpunkcija i razmaci",
    "veliko_malo": "Veliko/malo slovo",
    "tropuntkice": "Nedosljedne/nepravilne tri točkice",
    "ponovljena_riječ": "Ponovljena riječ",
    "rečenica_duga": "Predugačka rečenica (relativno prema knjizi)",
    "zamjenice": "Nagomilane zamjenice u subjektu",
    "prazan_pasus": "Prazan <p> bez slike",
    "predug_pasus": "Predug pasus (relativno prema knjizi)",
    "truncated": "Pasus bez završne interpunkcije",
    "udvostručen_odlomak": "Udvostručen odlomak",
    "prekinut_odlomak": "Prekinut odlomak (nastavlja se u sljedećem)",
    "odlomak_malo_slovo": "Odlomak počinje malim slovom nakon završene rečenice",
    "h1_nedostaje": "Poglavlje bez <h1>",
    "h1_višestruk": "Poglavlje sa više <h1>",
    "numeracija_rupa": "Rupa u numeraciji poglavlja",
    "struktura_poglavlja": "Neispravna struktura poglavlja",
    "ai_artefakt": "Ostaci AI-ja / markdowna / predloška",
    "prompt_echo": "AI vratio svoj prompt umjesto prijevoda",
    "kodiranje": "Kodiranje / nevidljivi znakovi",
    "pismo": "Tuđe pismo (ćirilica, grčki, homoglifi)",
    "dvostruko_escapano": "Dvostruko escapiran HTML entitet",
    "metapodaci": "Metapodaci / jezik / TOC",
    "izvornik_identičan": "Identično izvorniku (neprevedeno)",
    "izvornik_brojevi": "Brojevi se ne podudaraju s izvornikom",
    "izvornik_duljina": "Neobičan omjer duljine prema izvorniku",
    "izvornik_odlomci": "Različit broj poglavlja od izvornika",
    "izvornik_nedostaje": "Odlomak postoji u izvorniku, ne u prijevodu",
    "izvornik_višak": "Odlomak postoji u prijevodu, ne u izvorniku",
    "nepoznata_riječ": "Riječ nije u rječniku",
}

EKAV_PATTERNS = [
    (r"\bvreme\b", "vrijeme"),
    (r"\bdete(?:ta|tu|tom|ti)?\b", "dijete / djeteta"),
    (r"\bdec(?:a|e|i|u|om|ama)\b", "djeca"),
    (r"\blep(?:o|a|e|i|u|og|om|im|ih|oj)\b", "lijep…"),
    (r"\bmlek(?:o|a|u|om)\b", "mlijeko"),
    (r"\bpesm(?:a|e|u|om|i|ama)\b", "pjesma"),
    (r"\bdevojk(?:a|e|u|om|i|ama)\b", "djevojka"),
    (r"\breč(?:i|ju|ima|nik)?\b", "riječ / rječnik"),
    (r"\bsneg(?:a|u|om|ovi|ova)?\b", "snijeg"),
    (r"\bcve(?:t|ta|tu|tom|tovi|će|ća)\b", "cvijet / cvijeće"),
    (r"\bmest(?:o|a|u|om|ima)\b", "mjesto"),
    (r"\bce(?:o|la|lo|li|le|log|loj|lom|lim)\b", "cijel… / cio"),
    (r"\bbe(?:o|la|lo|li|le|log|loj|lom|lim)\b", "bijel…"),
    (r"\bmesec(?:a|u|om|i|ima)?\b", "mjesec"),
    (r"\brek(?:a|e|u|om|ama)\b", "rijeka"),
    (r"\bpre\b", "prije"),
    (r"\bposle\b", "poslije"),
    (r"\bgde\b", "gdje"),
    (r"\bovde\b", "ovdje"),
    (r"\bnigde\b", "nigdje"),
    (r"\bnegde\b", "negdje"),
    (r"\buvek\b", "uvijek"),
    (r"\brazume(?:ti|m|š|o|la|li|lo|ju)\b", "razumjeti / razumijem"),
    (r"\bhte(?:o|la|lo|li|le)\b", "htio / htjela"),
    (r"\bvide(?:la|li|lo|le)\b", "vidjela / vidjeli"),
    (r"\bživ(?:eo|ela|eli|elo)\b", "živio / živjela"),
    (r"\bvole(?:o|la|li|lo)\b", "volio / voljela"),
    (r"\bžele(?:o|la|li|lo)\b", "želio / željela"),
    (r"\bsledeć(?:i|a|e|u|im|eg|em)\b", "sljedeći"),
    (r"\bsećanj(?:e|a|u|em|ima)\b", "sjećanje"),
    (r"\bumetnost(?:i|ima)?\b", "umjetnost"),
    (r"\btel(?:o|a|u|om)\b", "tijelo"),
    (r"\bsme(?:h|ha|hu|hom|hovi)\b", "smijeh"),
    (r"\bposet(?:a|e|u|om|i|io|ila)\b", "posjet / posjetio"),
    (r"\bveče\b", "večer"),
]

DIJALEKT_PATTERNS = [
    (r"\bšta\b", "što"),
    (r"\bda\s+li\b", "je li / -li"),
    (r"\bhiljad(?:a|e|u|i|ama)\b", "tisuća"),
    (r"\bsedmic(?:a|e|u|i|om|ama)\b", "tjedan"),
    (r"\bhl(?:je|e)b(?:a|u|om|ovi)?\b", "kruh"),
    (r"\bvoz(?:a|u|om|ovi|ova|ovima)?\b", "vlak"),
    (r"\bvazduh(?:a|u|om)?\b", "zrak"),
    (r"\bmuzik(?:a|e|u|om)\b", "glazba"),
    (r"\bistorij(?:a|e|u|om|ski|ska|sko)\b", "povijest / povijesni"),
    (r"\bopštin(?:a|e|u|om|ama)\b", "općina"),
    (r"\bpozorišt(?:e|a|u|em|ima)\b", "kazalište"),
    (r"\bkaf(?:a|u|e|i|om|ama)\b", "kava"),
    (r"\btač(?:ka|ke|ku|kom|no|an|na)\b", "točka / točno"),
    (r"\blekar(?:a|u|em|i|ima)?\b", "liječnik"),
    (r"\bporodic(?:a|e|u|om|ama)\b", "obitelj"),
    (r"\bćerk(?:a|e|u|om|ama)\b", "kći"),
    (r"\bkomšij(?:a|e|u|om|ama|ski)\b", "susjed"),
    (r"\bizvin(?:i|ite|javam)\b", "oprosti / ispričavam se"),
    (r"\bjuče\b", "jučer"),
    (r"\buniverzitet(?:a|u|om|i|ima)?\b", "sveučilište"),
    (r"\bnauk(?:a|e|u|om|ama)\b", "znanost"),
    (r"\bbezbed(?:an|na|no|nost|nosti|niji|nija)\b", "siguran / sigurnost"),
    (r"\bmilion(?:a|u|om|i|ima)?\b", "milijun"),
    (r"\bizuzet(?:ak|ka|ku|kom|cima|no|an|na|nije)\b", "iznimka / iznimno"),
    (r"\bsistem(?:a|u|om|i|ima|ski)?\b", "sustav"),
    (r"\bevrop(?:a|e|u|om|ski|ska|sko)\b", "Europa / europski"),
    (r"\boficir(?:a|u|em|i|ima)?\b", "časnik"),
]

DA_DA_PATTERN = re.compile(
    r"\b(?:mogu|možeš|može|možemo|možete|moram|moraš|mora|moramo|morate|moraju|"
    r"počinje|počeo|počela|počeli|počelo|"
    r"pokušava|pokušao|pokušala|pokušali|pokušalo|"
    r"treba|trebam|trebaš|trebamo|trebate|trebaju|"
    r"želi|želio|željela|žele|želimo|želite|"
    r"morao|morala|morali|moralo)\s+da\b"
)
NE_GLAGOL_PATTERN = re.compile(
    r"\b[Nn]e(?:mogu|može|možeš|možemo|možete|"
    r"znam|znaš|zna|znamo|znate|znaju|"
    r"želim|želiš|želi|želimo|želite|žele|"
    r"volim|voliš|voli|volimo|volite|vole|"
    r"vidim|vidiš|vidi|vidimo|vidite|vide|"
    r"moram|moraš|mora|moramo|morate|moraju)\b"
)

PURIZAM_PATTERNS = [
    (r"\bokej\b|\bokay\b|\bok\b", "u redu"),
    (r"\bkul\b", "sjajno / zgodno"),
    (r"\bmenadžer(?:a|u|em|i|ima)?\b|\bmanager(?:a|u|em|i|ima)?\b", "voditelj / upravitelj"),
    (r"\be-?mail(?:a|u|om|ovi|ova|ovima)?\b|\bimejl(?:a|u|om|ovi|ova|ovima)?\b", "e-pošta"),
    (r"\bšoping(?:a|u|om)?\b|\bshopping\b", "kupnja / kupovanje"),
    (r"\bbiznis(?:a|u|om|i|ima)?\b|\bbusiness\b", "posao / poslovanje"),
    (r"\bdeadline\b|\bdedlajn(?:a|u|om|i|ima)?\b", "rok"),
    (r"\bkompjut(?:er|ora|eru|erom|eri|erima)\b|\bcomputer\b", "računalo"),
    (r"\bsoftver(?:a|u|om|i|ima)?\b|\bsoftware\b", "programska potpora / programi"),
    (r"\bhardver(?:a|u|om|i|ima)?\b", "sklopovlje"),
    (r"\bfajl(?:a|u|om|ovi|ova|ovima)?\b", "datoteka"),
    (r"\bfan(?:ovi|ova|ovima|ove|u|a|om)?\b", "obožavatelj / poklonik"),
    (r"\blider(?:a|u|om|i|ima)?\b", "vođa"),
    (r"\bparty\b|\bžurk(?:a|e|u|om|ama)\b", "zabava / proslava"),
    (r"\bkontaktir(?:ati|am|aš|a|amo|ate|aju|ao|ala|ali)\b", "obratiti se / javiti se"),
    (r"\bfokusir(?:ati|am|aš|a|amo|ate|aju|ao|ala|ali)\b", "usredotočiti"),
    (r"\brealizir(?:ati|am|aš|a|amo|ate|aju|ao|ala|ali)\b", "ostvariti"),
    (r"\bprezentir(?:ati|am|aš|a|amo|ate|aju|ao|ala|ali)\b", "predstaviti"),
]

KALK_PATTERNS = [
    (r"\buze(?:o|la|li|lo|ti)\s+(?:je\s+)?mjest(?:o|a)\b", "take place → održati se / zbiti se"),
    (r"\bnapravi(?:o|la|li|lo|ti)\s+(?:je\s+)?smisl(?:a|o)\b", "make sense → imati smisla"),
    (r"\bgleda(?:o|la|li|lo|ti)\s+naprijed\s+(?:do|na|prema)\b", "look forward to → veseliti se"),
    (r"\bna\s+kraju\s+dana\b", "at the end of the day → naposljetku / u konačnici"),
    (r"\brazbi(?:o|la|li|lo|ti)\s+led\b", "break the ice → probiti led"),
    (r"\bpo\s+defaultu\b", "by default → zadano / po zadanim postavkama"),
    (r"\bdati\s+(?:mi\s+)?(?:šansu|priliku)\s+da\b", "give a chance → pružiti priliku"),
]

PROMPT_ECHO_MARKERS = [
    "The user wants me", "The user is asking", "The user has",
    "I need to apply", "I need to translate", "I need to professionally",
    "I need to provide", "I will now", "I'll now", "I'll keep it",
    "I'll write", "I'll translate",
    "Let me analyze", "Let me check", "Let me translate", "Let me compare",
    "Let me see", "Let me try",
    "Original:", "Raw:", "Issues:",
    "Here is the translation", "Here is the Croatian", "Here's the translation",
    "Sure, here", "As an AI", "As a language model",
    "Translation:", "Prijevod:", "Prevod:", "Evo prijevoda", "Evo prevoda",
]

AI_ARTIFACT_PATTERNS = [
    (r"^\s*(?:Naravno|Svakako|Evo|Izvolite|Dakle)\b[^.!?]{0,60}(?:prijevod|prevod|prevedeno|preveden)", "Uvodna rečenica AI-ja o prijevodu", re.I | re.M),
    (r"\bas an AI\b|\bkao (?:AI|jezični model|umjetna inteligencija)\b", "AI se oglasio u tekstu", re.I),
    (r"^\s*(?:Translation|Prijevod|Translated text|Prevod)\s*:", "Oznaka prijevoda ostala u tekstu", re.I | re.M),
    (r"```", "Ostatak markdown ograde koda", 0),
    (r"\*\*[^*\n]{1,80}\*\*", "Ostatak markdown podebljanja (**)", 0),
    (r"(?<!\w)__[^_\n]{1,80}__(?!\w)", "Ostatak markdown podebljanja (__)", 0),
    (r"^\s{0,3}#{1,6}\s", "Ostatak markdown naslova (#)", re.M),
    (r"</?think>|\[\[|\]\]|\{\{|\}\}", "Tehnički ostatak ([[ ]], {{ }}, <think>)", 0),
    (r"\\n|\\t|\\\"", "Neprevedeni escape znakovi", 0),
    (r"\b(?:null|undefined|NaN)\b", "Moguća tehnička vrijednost", 0),
    (r"\b(?:TODO|FIXME|XXX)\b", "Oznaka za doradu ostala u tekstu", 0),
    (r"\[(?:ime|name|NAME|TBD|ovdje|insert)[^\]]*\]", "Neispunjen predložak", 0),
    (r"\{\w*\}|%[sd]\b", "Neispunjeno mjesto za vrijednost ({0}, %s)", 0),
    (r"napomena\s+prevoditelj\w*", "Napomena prevoditelja – provjeri treba li ostati", re.I),
    (r"\b(?:lorem\s+ipsum|placeholder)\b", "Placeholder tekst ostao", re.I),
]

ENCODING_RULES = [
    (r"\ufffd", "greška", "Znak zamjene (oštećeno kodiranje)"),
    (r"[\u200b\u200c\u200d\u2060\ufeff]", "upozorenje", "Nevidljivi znak (zero-width/BOM)"),
    (r"[\u0300-\u036f]", "greška", "Razdvojeni dijakritik (NFD) – č/š/ž nisu jedan znak"),
    (r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "greška", "Kontrolni znak u tekstu"),
    (r"&(?!(?:amp|lt|gt|quot|apos|nbsp);)(?:[a-zA-Z]{2,8}|#\d+|#x[0-9a-fA-F]+);", "greška", "Ostatak HTML entiteta u tekstu"),
    (r"[ðÐśŚŝŹżŻċĊ]", "upozorenje", "Slovo izvan hrvatske abecede (pogrešan dijakritik?)"),
    (r"\u00ad", "info", "Meki spojnik u tekstu"),
]

SCRIPT_PATTERNS = {
    "cyrillic": re.compile(r"[\u0400-\u04FF]"),
    "greek": re.compile(r"[\u0370-\u03FF]"),
    "arabic": re.compile(r"[\u0600-\u06FF]"),
    "cjk": re.compile(r"[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]"),
    "hebrew": re.compile(r"[\u0590-\u05FF]"),
    "devanagari": re.compile(r"[\u0900-\u097F]"),
    "emoji": re.compile(r"[\U0001F300-\U0001F9FF]"),
}
SCRIPT_LABEL = {"cyrillic": "ćirilica", "greek": "grčki", "arabic": "arapski",
                "cjk": "CJK", "hebrew": "hebrejski", "devanagari": "devanagari",
                "emoji": "emoji"}
LATIN_LETTER = re.compile(r"[A-Za-zČĆĐŠŽčćđšž]")

# Početak navodnog izraza: početak pasusa ili nakon razmaka/zagrade/crtice, iza njega nije razmak.
QUOTE_OPEN_RX = re.compile(r'(?:^|(?<=[\s(\[—–-]))(["„“«»‘])(?=\S)')
QUOTE_STYLE_KEY = {'"': '"…"', "„": "„…“", "“": "“…”", "«": "«…»", "»": "»…«", "‘": "‘…’"}

# ═══════════════════════════════════════════════════════════════
# MODELI
# ═══════════════════════════════════════════════════════════════

@dataclass
class Seg:
    """Segment teksta: pasus, naslov, alt-tekst, TOC unos, metadata vrijednost."""
    file: str
    spine: int
    chapter: str
    par: int
    tag: str
    eid: str
    text: str
    kind: str = "tekst"  # tekst | toc | meta | naslov | attr:*
    # NFC normalizacija se radi u Auditor.audit_seg POSLIJE provjere kodiranja.


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    file: str
    spine: int
    chapter: str
    par: int
    tag: str
    eid: str
    offset: int
    match: str
    context: str
    suggestion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# PROFIL
# ═══════════════════════════════════════════════════════════════

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _bad_regex(label: str, pattern: str, groups: Optional[int] = None) -> None:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        sys.exit(f"[FAIL] profil: neispravan regex u '{label}': {pattern!r} ({e})")
    if groups is not None and rx.groups < groups:
        sys.exit(f"[FAIL] profil: '{label}' mora imati barem {groups} grupu za hvatanje")


def load_profile(path: Optional[str]) -> tuple[dict, dict]:
    """Vraća (profil, info). Nepoznati ključevi → upozorenje; neispravni regexi → prekid."""
    prof = copy.deepcopy(DEFAULT_PROFILE)
    prof["thresholds"] = dict(DEFAULT_THRESHOLDS)
    info = {"datoteka": None, "sha256": None}
    if path:
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            data = json.loads(raw.decode("utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            sys.exit(f"[FAIL] --profile: {e}")
        if not isinstance(data, dict):
            sys.exit("[FAIL] --profile: korijen mora biti JSON objekt")
        for k, v in data.items():
            if k.startswith("_"):
                continue  # komentari
            if k not in DEFAULT_PROFILE:
                sys.stderr.write(f"[WARN] profil: nepoznat ključ „{k}“ (ignoriran)\n")
                continue
            if k == "thresholds":
                for tk, tv in v.items():
                    if tk not in DEFAULT_THRESHOLDS:
                        sys.stderr.write(f"[WARN] profil: nepoznat prag „{tk}“\n")
                    else:
                        prof["thresholds"][tk] = tv
            else:
                prof[k] = v
        info = {"datoteka": os.path.basename(path), "sha256": sha256_bytes(raw)}
    if prof["language"] not in LANGS:
        sys.exit(f"[FAIL] profil: language mora biti jedan od {sorted(LANGS)}")
    if prof["quote_style"] not in ("auto", "hr", "off"):
        sys.exit("[FAIL] profil: quote_style mora biti auto | hr | off")
    for p in prof["skip_files"]:
        _bad_regex("skip_files", p)
    for p in prof["structure_skip_files"]:
        _bad_regex("structure_skip_files", p)
    _bad_regex("chapter_number_regex", prof["chapter_number_regex"], groups=1)
    for i, r in enumerate(prof["extra_rules"]):
        if "pattern" not in r:
            sys.exit(f"[FAIL] profil: extra_rules[{i}] nema 'pattern'")
        _bad_regex(f"extra_rules[{i}]", r["pattern"])
        if r.get("severity", "upozorenje") not in SEV_ORDER:
            sys.exit(f"[FAIL] profil: extra_rules[{i}].severity mora biti {list(SEV_ORDER)}")
    for c in prof["disabled_rules"]:
        if c not in CODE_LABEL:
            sys.stderr.write(f"[WARN] profil: nepoznato pravilo u disabled_rules: „{c}“\n")
    return prof, info


# ═══════════════════════════════════════════════════════════════
# HTML PARSER
# ═══════════════════════════════════════════════════════════════

class ChapterParser(HTMLParser):
    """Parsira XHTML poglavlje u listu pasusa/atributa/linkova."""
    BLOCK = {
        "p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote", "td", "th", "dt", "dd", "figcaption", "caption",
        "pre", "section", "article", "aside", "tr", "main", "header",
        "footer", "nav", "address",
    }
    ATTRS_TO_CHECK = ("alt", "title", "aria-label")
    MEDIA = {"img", "svg", "image", "video", "audio", "object", "canvas"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str]] = []
        self.buf: list[str] = []
        self.segs: list[tuple[int, str, str, str]] = []
        self.attrs: list[tuple[str, str, str]] = []
        self.links: list[str] = []
        self.par = 0
        self.first_id = ""
        self.lang: Optional[str] = None
        self.skip = 0
        self.in_head = False
        self.in_title = False
        self.doc_title = ""
        self.h1_count = 0
        self.p_count = 0
        self.empty_p_count = 0
        self._p_open = False
        self._p_content = False

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if text:
            self.par += 1
            tag, eid = self.stack[-1] if self.stack else ("body", "")
            self.segs.append((self.par, tag, eid or self.first_id, text))
        self.first_id = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang") or a.get("xml:lang")
        if tag == "head":
            self.in_head = True
        if tag == "title" and self.in_head:
            self.in_title = True
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in self.MEDIA and self._p_open:
            self._p_content = True
        for name in self.ATTRS_TO_CHECK:
            v = (a.get(name) or "").strip()
            if len(v) >= 2 and re.search(r"[^\W\d_]", v) and not self.in_head:
                self.attrs.append((tag, name, v))
        if tag in self.BLOCK:
            self.flush()
            self.stack.append((tag, a.get("id", "")))
            if tag == "p":
                self.p_count += 1
                self._p_open = True
                self._p_content = False
            elif tag == "h1":
                self.h1_count += 1
        else:
            if a.get("id") and not self.first_id:
                self.first_id = a["id"]
            if tag == "br":
                self.buf.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag == "head":
            self.in_head = False
        if tag == "title":
            self.in_title = False
        if tag == "p" and self._p_open:
            if not self._p_content:
                self.empty_p_count += 1
            self._p_open = False
        if tag in self.BLOCK:
            self.flush()
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.doc_title += data
        elif not self.in_head:
            self.buf.append(data)
            if self._p_open and data.strip():
                self._p_content = True


# ═══════════════════════════════════════════════════════════════
# BOOK
# ═══════════════════════════════════════════════════════════════

def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _is_external(href: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href))


@dataclass
class Book:
    path: str
    meta: list[Seg] = field(default_factory=list)
    toc: list[Seg] = field(default_factory=list)
    chapters: list[tuple[int, str, list[Seg]]] = field(default_factory=list)
    langs: dict[str, Optional[str]] = field(default_factory=dict)
    opf_langs: list[str] = field(default_factory=list)
    opf_path: str = ""
    manifest: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    spine: list[str] = field(default_factory=list)
    h1_count: dict[int, int] = field(default_factory=dict)
    p_count: dict[int, int] = field(default_factory=dict)
    empty_p_count: dict[int, int] = field(default_factory=dict)
    toc_links: list[tuple[str, str]] = field(default_factory=list)
    all_files: set = field(default_factory=set)
    chapter_numbers: dict[int, int] = field(default_factory=dict)
    skipped_files: list[str] = field(default_factory=list)

    @classmethod
    def read(cls, path: str, skip_files: Optional[list[str]] = None) -> "Book":
        skip_rx = [re.compile(p) for p in (skip_files or [])]
        book = cls(path=path)
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            book.all_files = names

            cont_path = "META-INF/container.xml"
            if cont_path not in names:
                raise ValueError(f"Neispravan EPUB: nema {cont_path}")
            cont = ET.fromstring(z.read(cont_path))
            rootfile = next(
                (e.get("full-path") for e in cont.iter() if local(e.tag) == "rootfile"),
                None,
            )
            if not rootfile:
                raise ValueError("Neispravan EPUB: nema rootfile")
            book.opf_path = rootfile
            base = posixpath.dirname(rootfile)

            def resolve(href: str, rel_base: str = base) -> str:
                return posixpath.normpath(posixpath.join(rel_base, unquote(href.split("#")[0])))

            opf = ET.fromstring(z.read(rootfile))
            for e in opf.iter():
                if not isinstance(e.tag, str):
                    continue
                ln = local(e.tag)
                if ln == "item":
                    book.manifest[e.get("id", "")] = (
                        resolve(e.get("href", "")),
                        e.get("media-type", ""),
                        e.get("properties", "") or "",
                    )
                elif ln == "itemref":
                    book.spine.append(e.get("idref", ""))
                elif e.tag.startswith(DC_NS) and (e.text or "").strip():
                    val = e.text.strip()
                    if ln == "language":
                        book.opf_langs.append(val)
                    book.meta.append(Seg(
                        file=rootfile, spine=0, chapter="metapodaci",
                        par=len(book.meta) + 1, tag=f"dc:{ln}", eid="",
                        text=val, kind="meta",
                    ))

            for idx, idref in enumerate(book.spine, 1):
                if idref not in book.manifest:
                    continue
                href, mt, props = book.manifest[idref]
                if href not in names or "nav" in props.split():
                    continue
                if any(rx.search(href) for rx in skip_rx):
                    book.skipped_files.append(href)
                    continue
                if mt not in ("application/xhtml+xml", "text/html"):
                    continue
                try:
                    p = ChapterParser()
                    p.feed(z.read(href).decode("utf-8-sig", errors="replace"))
                    p.close()
                    p.flush()
                except Exception as e:
                    sys.stderr.write(f"[WARN] {href}: {e}\n")
                    continue
                title = ""
                for _, tg, _, tx in p.segs:
                    if tg in ("h1", "h2", "h3"):
                        title = tx[:80]
                        break
                if not title:
                    title = posixpath.basename(href)
                segs: list[Seg] = []
                for par, tg, eid, tx in p.segs:
                    segs.append(Seg(href, idx, title, par, tg, eid, tx))
                for tg, nm, v in p.attrs:
                    segs.append(Seg(href, idx, title, 0, f"attr:{tg}", "", v, kind=f"attr:{nm}"))
                if p.doc_title.strip():
                    segs.append(Seg(href, idx, title, 0, "title", "", p.doc_title.strip(), kind="naslov"))
                book.langs[href] = p.lang
                book.h1_count[idx] = p.h1_count
                book.p_count[idx] = p.p_count
                book.empty_p_count[idx] = p.empty_p_count
                book.chapters.append((idx, href, segs))

            for _idref, (href, mt, props) in book.manifest.items():
                if href not in names:
                    continue
                nav_dir = posixpath.dirname(href)
                if "nav" in props.split():
                    try:
                        p = ChapterParser()
                        p.feed(z.read(href).decode("utf-8-sig", errors="replace"))
                        p.close()
                        p.flush()
                    except Exception:
                        continue
                    for par, tg, eid, tx in p.segs:
                        book.toc.append(Seg(href, 0, "sadržaj (nav)", par, tg, eid, tx, kind="toc"))
                    for h in p.links:
                        if h and not h.startswith("#") and not _is_external(h):
                            book.toc_links.append((href, resolve(h, nav_dir)))
                elif mt == "application/x-dtbncx+xml":
                    try:
                        root = ET.fromstring(z.read(href))
                    except ET.ParseError:
                        continue
                    k = 0
                    for el in root.iter():
                        if not isinstance(el.tag, str):
                            continue
                        ln = local(el.tag)
                        if ln == "navLabel":
                            tx = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
                            if tx:
                                k += 1
                                book.toc.append(Seg(href, 0, "sadržaj (ncx)", k, "navLabel", "", tx, kind="toc"))
                        elif ln == "content" and el.get("src"):
                            h = el.get("src")
                            if not h.startswith("#") and not _is_external(h):
                                book.toc_links.append((href, resolve(h, nav_dir)))
        return book


# ═══════════════════════════════════════════════════════════════
# POMOĆNE FUNKCIJE
# ═══════════════════════════════════════════════════════════════

def sentence_initial(t: str, i: int) -> bool:
    """Je li znak na poziciji i početak rečenice? Poštuje kratice."""
    j = i - 1
    while j >= 0 and t[j] in SKIP_BACK:
        j -= 1
    if j < 0:
        return True
    c = t[j]
    if c in ".!?…:":
        if c == ".":
            m = re.search(r"([^\W\d_]+)\.$", t[max(0, j - 15): j + 1])
            if m and (len(m.group(1)) == 1 or m.group(1).lower() in ABBR_HR):
                return False
        return True
    return False


def make_context(text: str, start: int, end: int, width: int = 45) -> str:
    a = max(0, start - width)
    b = min(len(text), end + width)
    pre = "…" if a else ""
    suf = "…" if b < len(text) else ""
    return f"{pre}{text[a:start]}⟦{text[start:end]}⟧{text[end:b]}{suf}"


def demoji(word: str) -> Optional[str]:
    """Pokušaj popraviti mojibake (UTF-8 → cp1252 → UTF-8)."""
    try:
        r = word.encode("cp1252").decode("utf-8")
        return r if r != word else None
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None


def adaptive_limit(values: list[int], floor: int, pct: float, factor: float) -> float:
    """Granica relativna prema knjizi: max(floor, percentil * faktor)."""
    if not values:
        return float(floor)
    vs = sorted(values)
    k = min(len(vs) - 1, max(0, int(math.ceil(pct / 100.0 * len(vs))) - 1))
    return max(float(floor), vs[k] * factor)


def learn_proper_names(src: Book, min_count: int, lower_ratio: float) -> set[str]:
    """Imena iz izvornika: velikim slovom usred rečenice, a (gotovo) nikad malim slovom.
    Time se 'May'/'Death' (obične riječi) ne uče kao imena."""
    cap: Counter = Counter()
    low: Counter = Counter()
    for _i, _h, segs in src.chapters:
        for s in segs:
            if s.kind != "tekst":
                continue
            t = unicodedata.normalize("NFC", s.text)
            for m in WORD_RE.finditer(t):
                w = re.sub(r"['’]s$", "", m.group())
                if len(w) > 1 and w[0].isupper() and not w.isupper():
                    if sentence_initial(t, m.start()):
                        low[w.lower()] += 1
                    else:
                        cap[w] += 1
                else:
                    low[w.lower()] += 1
    return {w for w, c in cap.items()
            if c >= min_count and len(w) >= 3 and low[w.lower()] <= lower_ratio * c}


# ═══════════════════════════════════════════════════════════════
# AUDITOR
# ═══════════════════════════════════════════════════════════════

class Auditor:
    def __init__(self, cfg: dict, wordlist: Optional[set[str]]):
        self.cfg = cfg
        self.th = cfg["thresholds"]
        self.disabled = frozenset(cfg["disabled"])
        self.lang = LANGS[cfg["language"]]
        self.names_map: dict[str, str] = cfg["names"]
        self.names_sorted = sorted(self.names_map, key=len, reverse=True)
        self.name_rx = self._build_name_rx()
        self.place_rx = re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, PLACES_EN_HR)))
        self.wordlist = wordlist
        self.proper: set[str] = set(cfg["proper_names"]) | set(self.names_map) | set(PLACES_EN_HR)
        self.learned: set[str] = set()
        self.learned_prefix: tuple[str, ...] = ()

        fo = [x.lower() for x in cfg["foreign_ok"]]
        self.foreign_exact = {x for x in fo if not x.endswith("*")}
        self.foreign_prefix = tuple(x[:-1] for x in fo if x.endswith("*") and len(x) > 1)

        self.ekav_rx = [(re.compile(p, re.I), s) for p, s in EKAV_PATTERNS] if self.lang["ekav"] else []
        self.dijalekt_rx = [(re.compile(p, re.I), s) for p, s in DIJALEKT_PATTERNS] if self.lang["dijalekt"] else []
        self.use_da_da = self.lang["dijalekt"]
        self.purizam_rx = [(re.compile(p, re.I), s) for p, s in PURIZAM_PATTERNS]
        self.kalk_rx = [(re.compile(p, re.I), s) for p, s in KALK_PATTERNS]
        self.ai_rx = [(re.compile(p, f), m) for p, m, f in AI_ARTIFACT_PATTERNS]
        self.encoding_rx = [(re.compile(p), s, m) for p, s, m in ENCODING_RULES]
        self.custom_rx = [
            (re.compile(r["pattern"], re.I if r.get("ignore_case", True) else 0),
             r.get("code", "korisnicko"), r.get("severity", "upozorenje"),
             r.get("message", "Custom pravilo"), r.get("suggestion", ""))
            for r in cfg["extra_rules"]
        ]
        self.napr_rx = re.compile(r"\bnapravi\w*", re.I)
        self.chnum_rx = re.compile(cfg["chapter_number_regex"])

        self.findings: list[Finding] = []
        self.name_cnt: Counter = Counter()
        self.name_first: dict[str, tuple[Seg, int, int]] = {}
        self.chap_words: Counter = Counter()
        self.chap_title: dict[int, str] = {}
        self.sentences = 0
        self.pron_sent = 0
        self.napr = 0
        self.total_words = 0
        self.unknown_words: Counter = Counter()
        self.unknown_first: dict[str, tuple[Seg, int, int]] = {}
        self.ellipsis: defaultdict[str, list[tuple[Seg, int, int]]] = defaultdict(list)
        self.quote_open: defaultdict[str, list[tuple[Seg, int, int]]] = defaultdict(list)
        self.dash_start: defaultdict[str, list[tuple[Seg, int, int]]] = defaultdict(list)
        self.sent_lengths: list[int] = []
        self.sent_cand: list[tuple[Seg, int, int, int]] = []
        self.par_lengths: list[int] = []
        self.par_cand: list[tuple[Seg, int]] = []
        self.chapter_numbers: dict[int, int] = {}
        self.computed: dict = {}

    # ── pomoćno ─────────────────────────────────────────
    def on(self, code: str) -> bool:
        return code not in self.disabled

    def set_learned(self, names: set[str]) -> None:
        self.learned = set(names)
        self.learned_prefix = tuple(sorted(n for n in names if len(n) >= 4))

    def known_name(self, w: str) -> bool:
        return (w in self.proper or w in self.learned
                or (bool(self.learned_prefix) and w.startswith(self.learned_prefix)))

    def foreign_ok(self, lw: str) -> bool:
        if lw in self.foreign_exact or (self.foreign_prefix and lw.startswith(self.foreign_prefix)):
            return True
        if self.learned_prefix:
            return any(lw.startswith(n.lower()) for n in self.learned_prefix) or \
                   any(lw == n.lower() for n in self.learned)
        return False

    def _build_name_rx(self) -> Optional[re.Pattern]:
        if not self.names_map:
            return None
        dec = [re.escape(n) for n in self.names_sorted]
        return re.compile(
            r"\b(?:%s)(?:ov(?:a|o|u|om|e|i|ih|im|ima|oj)?|a|u|om|e|i)?\b" % "|".join(dec),
            re.UNICODE,
        )

    def add(self, seg: Seg, sev: str, code: str, msg: str,
            start: int, end: int, sug: str = "") -> None:
        if code in self.disabled:       # središnja vrata: --disable / disabled_rules
            return
        t = seg.text
        self.findings.append(Finding(
            severity=sev, code=code, message=msg,
            file=seg.file, spine=seg.spine, chapter=seg.chapter,
            par=seg.par, tag=seg.tag, eid=seg.eid,
            offset=start, match=t[start:end][:200],
            context=make_context(t, start, min(end, start + 200)),
            suggestion=sug,
        ))

    # ── prolaz ──────────────────────────────────────────
    def audit_chapter(self, spine: int, segs: list[Seg]) -> None:
        for s in segs:
            if s.spine and s.chapter:
                self.chap_title.setdefault(s.spine, s.chapter)
            self.audit_seg(s)
        body = [s for s in segs if s.kind == "tekst"]
        for i, s in enumerate(body):
            prev = body[i - 1] if i > 0 else None
            nxt = body[i + 1] if i + 1 < len(body) else None
            self.check_structure(s, prev, nxt)

    def audit_seg(self, seg: Seg) -> None:
        self.check_encoding(seg)               # prije NFC normalizacije
        seg.text = unicodedata.normalize("NFC", seg.text)
        full = seg.kind in ("tekst", "toc")

        toks = list(WORD_RE.finditer(seg.text))
        if full:
            self.chap_words[seg.spine] += len(toks)
            self.total_words += len(toks)

        self.check_scripts(seg)
        self.check_tokens(seg, toks, full)

        if not full:
            return

        for rx, sug in self.ekav_rx:
            for m in rx.finditer(seg.text):
                self.add(seg, "greška", "ekavica", f"Ekavski oblik „{m.group()}“", m.start(), m.end(), sug)
        for rx, sug in self.dijalekt_rx:
            for m in rx.finditer(seg.text):
                self.add(seg, "upozorenje", "dijalekt", f"Srbizam/bosnizam „{m.group()}“", m.start(), m.end(), sug)
        if self.use_da_da:
            for m in DA_DA_PATTERN.finditer(seg.text):
                self.add(seg, "upozorenje", "dijalekt", "„da + prezent“ umjesto infinitiva", m.start(), m.end(), "infinitiv")
        for m in NE_GLAGOL_PATTERN.finditer(seg.text):
            self.add(seg, "upozorenje", "dijalekt", "„ne“ uz glagol piše se odvojeno", m.start(), m.end(),
                     m.group()[:2] + " " + m.group()[2:])
        for rx, sug in self.purizam_rx:
            for m in rx.finditer(seg.text):
                self.add(seg, "info", "purizam", f"Anglicizam „{m.group()}“", m.start(), m.end(), sug)
        for rx, sug in self.kalk_rx:
            for m in rx.finditer(seg.text):
                self.add(seg, "upozorenje", "kalk", f"Mogući kalk „{m.group()}“", m.start(), m.end(), sug)
        for rx, msg in self.ai_rx:
            for m in rx.finditer(seg.text):
                if m.end() > m.start():
                    self.add(seg, "greška", "ai_artefakt", msg, m.start(), m.end())
        for marker in PROMPT_ECHO_MARKERS:
            idx = seg.text.find(marker)
            if idx >= 0:
                self.add(seg, "greška", "prompt_echo",
                         f"Marker „{marker}“ – AI vratio prompt umjesto prijevoda",
                         idx, idx + len(marker))
        for rx, code, sev, msg, sug in self.custom_rx:
            for m in rx.finditer(seg.text):
                if m.end() > m.start():
                    self.add(seg, sev, code, msg, m.start(), m.end(), sug)

        self.check_names(seg)
        self.check_typography(seg)
        self.check_style(seg)
        self.check_numbering(seg)

    # ── kodiranje ───────────────────────────────────────
    def check_encoding(self, seg: Seg) -> None:
        t = seg.text
        for rx, sev, msg in self.encoding_rx:
            for m in rx.finditer(t):
                self.add(seg, sev, "kodiranje", msg, m.start(), m.end())
        for m in re.finditer(r"\S*[ÃÄÅÂ]\S*|\S*â€\S*", t):
            fixed = demoji(m.group())
            if fixed:
                self.add(seg, "greška", "kodiranje", "Mojibake (dvostruko kodiran UTF-8)",
                         m.start(), m.end(), fixed)
        for m in re.finditer(r"&(?:amp|lt|gt|quot|apos|nbsp);", t):
            self.add(seg, "greška", "dvostruko_escapano",
                     f"HTML entitet u tekstu: {m.group()}", m.start(), m.end())

    # ── pismo ───────────────────────────────────────────
    def check_scripts(self, seg: Seg) -> None:
        t = seg.text
        for name, rx in SCRIPT_PATTERNS.items():
            for m in rx.finditer(t):
                ws = m.start()
                while ws > 0 and (t[ws - 1].isalnum() or t[ws - 1] == "-"):
                    ws -= 1
                we = m.end()
                while we < len(t) and (t[we].isalnum() or t[we] == "-"):
                    we += 1
                word = t[ws:we]
                has_latin = bool(LATIN_LETTER.search(word))
                sev = "greška" if has_latin else "upozorenje"
                label = SCRIPT_LABEL.get(name, name)
                msg = (f"Homoglif: latinica + {label} u istoj riječi" if has_latin
                       else f"{label.capitalize()} znak u latiničnom tekstu")
                self.add(seg, sev, "pismo", msg, m.start(), m.end())

    # ── tokeni ──────────────────────────────────────────
    def check_tokens(self, seg: Seg, toks: list[re.Match], full: bool) -> None:
        t = seg.text
        if seg.kind in ("meta", "naslov") or seg.tag == "title":
            return
        en_hits: list[re.Match] = []
        for m in toks:
            w = m.group()
            lw = w.lower().replace("’", "'")
            if lw in EN_STOP or lw in EN_STRUCT:
                en_hits.append(m)
                continue
            if not full:
                continue
            if w[0].isupper() and len(w) > 1 and not w.isupper():
                if sentence_initial(t, m.start()):
                    continue
                if self.known_name(w):
                    continue
                self.name_cnt[w] += 1
                self.name_first.setdefault(w, (seg, m.start(), m.end()))
                if not self.cfg["skip_fantasy"]:
                    if re.search(r"(?i)[wqxy]|th|sh|ck|ph|gh|ee|oo", w) and w not in PLACES_EN_HR:
                        self.add(seg, "upozorenje", "ime_strano_pismo",
                                 f"Ime/pojam sa stranim grafemima „{w}“ – prilagodi hrvatskom pismu",
                                 m.start(), m.end())
            else:
                if re.search(r"[wqxy]", lw) and not self.foreign_ok(lw):
                    self.add(seg, "info", "strano_slovo_riječ",
                             f"Riječ sa stranim grafemima „{w}“ – moguća neprevedena engleska riječ",
                             m.start(), m.end())
                if (self.wordlist is not None and len(w) >= 3
                        and "-" not in w and "'" not in w and lw not in self.wordlist
                        and not self.known_name(w)):
                    self.unknown_words[lw] += 1
                    self.unknown_first.setdefault(lw, (seg, m.start(), m.end()))

        n = len(toks)
        if not en_hits or n < 5:
            return
        ratio = len(en_hits) / max(n, 1)
        if n >= 5 and (len(en_hits) >= 3 or (len(en_hits) >= 2 and ratio >= 0.15)):
            self.add(seg, "greška", "neprevedeno_dio",
                     f"Odlomak je neprevedeno/djelomično engleski ({len(en_hits)} EN funkcijskih od {n})",
                     0, min(len(t), 160))
        else:
            for m in en_hits:
                self.add(seg, "greška", "engleska_riječ",
                         f"Engleska riječ „{m.group()}“ u hrvatskom tekstu",
                         m.start(), m.end())

    # ── imena ───────────────────────────────────────────
    def check_names(self, seg: Seg) -> None:
        if seg.kind in ("toc", "meta", "naslov"):
            return
        t = seg.text
        if self.name_rx and self.on("ime_en"):
            for m in self.name_rx.finditer(t):
                w = m.group()
                base = next((n for n in self.names_sorted if w.startswith(n)), None)
                if base and w != self.names_map[base] and not w.startswith(self.names_map[base]):
                    self.add(seg, "upozorenje", "ime_en",
                             f"Englesko ime „{w}“ – hrvatski oblik: {self.names_map[base]}",
                             m.start(), m.end(), self.names_map[base])
        if self.on("mjesto_en"):
            for m in self.place_rx.finditer(t):
                self.add(seg, "upozorenje", "mjesto_en",
                         f"Engleski egzonim „{m.group()}“", m.start(), m.end(), PLACES_EN_HR[m.group()])

    # ── tipografija ─────────────────────────────────────
    def check_typography(self, seg: Seg) -> None:
        t = seg.text
        qs = self.cfg["quote_style"]
        if qs == "hr":
            n_ascii = t.count('"')
            n_hr = t.count("„") + t.count("“") + t.count("”")
            if n_ascii > 0 and n_hr > 0 and n_ascii % 2 == 1:
                self.add(seg, "upozorenje", "navodnici", "Mješani ravni i hrvatski navodnici u pasusu", 0, 0, "„…“")
            for m in re.finditer(r"(?:^|(?<=[\s(\[]))“(?=\S)", t):
                self.add(seg, "upozorenje", "navodnici", "Engleski otvarajući navodnik", m.start(), m.end(), "„")
        elif qs == "auto":
            for m in QUOTE_OPEN_RX.finditer(t):
                self.quote_open[QUOTE_STYLE_KEY[m.group(1)]].append((seg, m.start(1), m.end(1)))
        if self.on("neparni_navodnik"):
            self.check_unpaired_quotes(seg)

        if seg.kind == "tekst" and len(t) > 1 and t[0] in "—–-":
            self.dash_start[t[0]].append((seg, 0, 1))

        for m in re.finditer(r"(?<=\s)-(?=\s)", t):
            self.add(seg, "upozorenje", "crtica", "Spojnica umjesto polupauze", m.start(), m.end(), "–")
        for m in re.finditer(r"(?<!-)--(?!-)", t):
            self.add(seg, "upozorenje", "crtica", "Dvije spojnice", m.start(), m.end(), "–")
        for m in re.finditer(r"(?<=\w)—|—(?=\w)", t):
            self.add(seg, "upozorenje", "crtica", "Crtica bez razmaka", m.start(), m.end(), " – ")

        for m in re.finditer(r"(?<=[\w»“”\"\)])[ \u00a0]+[,;:.!?](?![.\d])", t):
            self.add(seg, "greška", "interpunkcija", "Razmak prije interpunkcije", m.start(), m.end())
        for m in re.finditer(r"(?<=[a-zčćđšž])[,;:!?](?=[A-Za-zČĆĐŠŽčćđšž])", t):
            self.add(seg, "greška", "interpunkcija", "Nedostaje razmak iza interpunkcije", m.start(), m.end())
        for m in re.finditer(r"(?<=[a-zčćđšž]{2})\.(?=[A-ZČĆĐŠŽ])", t):
            self.add(seg, "greška", "interpunkcija", "Nedostaje razmak iza točke", m.start(), m.end())
        for m in re.finditer(r",,|;;|::|,\.|(?<!\.)\.\.(?!\.)", t):
            self.add(seg, "greška", "interpunkcija", "Udvostručena interpunkcija", m.start(), m.end())

        for m in re.finditer(r"(?<!\.)\.{3}(?!\.)|…", t):
            self.ellipsis[m.group()].append((seg, m.start(), m.end()))
        for m in re.finditer(r"\.{4,}|…\.+|\.+…|……", t):
            self.add(seg, "upozorenje", "tropuntkice", "Nepravilan broj točkica", m.start(), m.end(), "… ili ...")

    def check_unpaired_quotes(self, seg: Seg) -> None:
        """Neparni navodnici. Dijalog kroz više pasusa je legitiman, pa je tolerancija 1."""
        t = seg.text
        if t.lstrip()[:1] in ("—", "–", "-"):
            positions = [m.start() for m in re.finditer(r'"', t)]
            if len(positions) % 2 == 1:
                pos = positions[-1]
                self.add(seg, "upozorenje", "neparni_navodnik",
                         "Neparni \" u dijalogu (vjerojatno treba obrisati)", pos, pos + 1, "obriši")
        opens = [m.start() for m in re.finditer("„", t)]
        closes = [m.start() for m in re.finditer("[“”]", t)]
        if abs(len(opens) - len(closes)) > 1:
            pos = (opens or closes)[-1]
            self.add(seg, "upozorenje", "neparni_navodnik",
                     f"Neparni „“ navodnici (otvarajućih {len(opens)}, zatvarajućih {len(closes)})",
                     pos, pos + 1)

    # ── stil ────────────────────────────────────────────
    def check_style(self, seg: Seg) -> None:
        t = seg.text
        skip_dup = {"da", "ne", "ha", "he", "hi", "ho", "bla", "ah", "oh", "voljela",
                    "ajde", "la", "tra", "ta", "ni", "pa", "ma", "je", "i", "u", "a",
                    "na", "se", "od", "do", "za", "s", "k", "su", "bi", "smo", "ste"}
        for m in re.finditer(r"(?<![\w-])([^\W\d_]{2,})(\s+)\1(?![\w-])", t, re.I):
            if m.group(1).lower() in skip_dup:
                continue
            self.add(seg, "upozorenje", "ponovljena_riječ",
                     f"Uzastopno ponovljena riječ „{m.group(1)}“", m.start(), m.end())

        for m in re.finditer(
            r"\b(?:Siječanj|Veljača|Ožujak|Travanj|Svibanj|Lipanj|Srpanj|Kolovoz|Rujan|"
            r"Listopad|Studeni|Prosinac|Ponedjeljak|Utorak|Srijeda|Četvrtak|Petak|Subota|Nedjelja)\b",
            t,
        ):
            if not sentence_initial(t, m.start()):
                self.add(seg, "upozorenje", "veliko_malo",
                         "Mjesec/dan piše se malim slovom", m.start(), m.end(), m.group().lower())

        pron_starts = []
        for m in re.finditer(r"\b(?:On|Ona|Ono|Oni|One|Ja|Ti|Mi|Vi)\s+(?:je|su|sam|si|smo|ste|bi|će|ću|ćeš|ćemo|ćete|neće|nije|nisu|nisam)\b", t):
            if sentence_initial(t, m.start()):
                pron_starts.append(m)
        self.pron_sent += len(pron_starts)
        k = self.th["pron_per_par"]
        if len(pron_starts) >= k:
            m = pron_starts[k - 1]
            self.add(seg, "info", "zamjenice",
                     f"{len(pron_starts)} rečenica u pasusu počinje zamjenicom + glagolom",
                     m.start(), m.end())

        self.napr += len(self.napr_rx.findall(t))

        bounds = [0] + [m.end() for m in SENT_SPLIT_RE.finditer(t)] + [len(t)]
        self.sentences += len(bounds) - 1
        if self.on("rečenica_duga") and seg.kind == "tekst":
            floor = self.th["sentence_words_floor"]
            for a, b in zip(bounds, bounds[1:]):
                nw = len(WORD_RE.findall(t[a:b]))
                self.sent_lengths.append(nw)
                if nw >= floor:
                    self.sent_cand.append((seg, a, b, nw))

    # ── struktura pasusa ────────────────────────────────
    def check_structure(self, seg: Seg, prev: Optional[Seg], nxt: Optional[Seg]) -> None:
        t = seg.text
        if not t:
            self.add(seg, "upozorenje", "prazan_pasus", "Prazan odlomak", 0, 0)
            return
        if prev and prev.text == t and len(t) >= 40:
            self.add(seg, "greška", "udvostručen_odlomak", "Odlomak identičan prethodnom",
                     0, min(len(t), 120))
        if self.on("predug_pasus"):
            self.par_lengths.append(len(t))
            if len(t) >= self.th["paragraph_chars_floor"]:
                self.par_cand.append((seg, len(t)))
        ends = t.rstrip().endswith(tuple(TERM_CHARS))
        is_head = seg.tag.startswith("h")
        continues = bool(nxt and nxt.text[:1].islower())
        if (self.on("truncated") and not ends and not is_head and len(t) >= 80
                and not continues):
            self.add(seg, "upozorenje", "truncated",
                     "Pasus završava bez interpunkcije", max(0, len(t) - 40), len(t))
        if len(t) >= 60 and nxt and nxt.tag == seg.tag and not ends and nxt.text[:1].islower():
            self.add(seg, "greška", "prekinut_odlomak",
                     "Odlomak prekinut usred rečenice (sljedeći počinje malim slovom)",
                     max(0, len(t) - 60), len(t))
        if (self.on("odlomak_malo_slovo") and not is_head and t[:1].islower()
                and prev and prev.text.rstrip().endswith(tuple(".!?…"))):
            self.add(seg, "upozorenje", "odlomak_malo_slovo",
                     "Odlomak počinje malim slovom nakon završene rečenice", 0, 1)

    def check_numbering(self, seg: Seg) -> None:
        for m in self.chnum_rx.finditer(seg.text):
            self.chapter_numbers[seg.spine] = int(m.group(1))


# ═══════════════════════════════════════════════════════════════
# USPOREDBA S IZVORNIKOM — DP alignment (Gale-Church-lite)
# ═══════════════════════════════════════════════════════════════

class SourceComparator:
    """Poravnava pasuse prijevoda i izvornika dinamičkim programiranjem po
    duljini (+ podudaranju brojeva). Radi i kad se broj pasusa razlikuje."""

    GAP = 1.5

    def __init__(self, aud: Auditor, src: Book):
        self.aud = aud
        self.src = src
        self.src_list = [segs for _i, _h, segs in src.chapters]
        self.src_by_idx = {i: segs for i, _h, segs in src.chapters}

    def compare(self, tgt: Book) -> None:
        if len(tgt.chapters) != len(self.src.chapters):
            seg = Seg("(knjiga)", 0, "usporedba", 0, "", "", "", kind="meta")
            self.aud.add(seg, "upozorenje", "izvornik_odlomci",
                         f"Različit broj poglavlja: prijevod {len(tgt.chapters)}, izvornik {len(self.src.chapters)}",
                         0, 0)
        same = len(tgt.chapters) == len(self.src.chapters)
        for k, (idx, _href, tsegs) in enumerate(tgt.chapters):
            ssegs = self.src_list[k] if same else self.src_by_idx.get(idx, [])
            T = [s for s in tsegs if s.kind == "tekst"]
            S = [s for s in ssegs if s.kind == "tekst"]
            if not T or not S:
                continue
            for ti, si in self._align(T, S):
                if ti is None:
                    self.aud.add(S[si], "upozorenje", "izvornik_nedostaje",
                                 "Odlomak postoji u izvorniku, ne u prijevodu (lokacija je u izvorniku)",
                                 0, min(len(S[si].text), 160))
                elif si is None:
                    self.aud.add(T[ti], "upozorenje", "izvornik_višak",
                                 "Odlomak postoji u prijevodu, ne u izvorniku",
                                 0, min(len(T[ti].text), 160))
                else:
                    self._compare_para(T[ti], S[si])

    def _align(self, T: list[Seg], S: list[Seg]) -> list[tuple[Optional[int], Optional[int]]]:
        nT, nS = len(T), len(S)
        lt = [len(s.text) for s in T]
        ls = [len(s.text) for s in S]
        mu = math.log((sum(lt) + 1) / (sum(ls) + 1))
        band = max(25, int(0.25 * max(nT, nS)))
        dT = [set(re.findall(r"\d+", s.text)) for s in T]
        dS = [set(re.findall(r"\d+", s.text)) for s in S]

        def mcost(i: int, j: int) -> float:
            c = abs(math.log((lt[i] + 1) / (ls[j] + 1)) - mu)
            if dT[i] or dS[j]:
                c -= 0.6 * len(dT[i] & dS[j]) / len(dT[i] | dS[j])
            return max(c, 0.0)

        cost: list[dict[int, float]] = [{} for _ in range(nT + 1)]
        back: list[dict[int, tuple[int, int]]] = [{} for _ in range(nT + 1)]
        cost[0][0] = 0.0
        for i in range(nT + 1):
            center = i * nS / nT
            lo = max(0, int(center) - band)
            hi = min(nS, int(center) + band)
            for j in range(lo, hi + 1):
                if i == 0 and j == 0:
                    continue
                best: Optional[float] = None
                bp: Optional[tuple[int, int]] = None
                if i > 0 and j > 0:
                    p = cost[i - 1].get(j - 1)
                    if p is not None:
                        best, bp = p + mcost(i - 1, j - 1), (i - 1, j - 1)
                if i > 0:
                    p = cost[i - 1].get(j)
                    if p is not None and (best is None or p + self.GAP < best):
                        best, bp = p + self.GAP, (i - 1, j)
                if j > 0:
                    p = cost[i].get(j - 1)
                    if p is not None and (best is None or p + self.GAP < best):
                        best, bp = p + self.GAP, (i, j - 1)
                if best is not None and bp is not None:
                    cost[i][j] = best
                    back[i][j] = bp

        if nS not in back[nT]:  # rezerva: 1:1 po poziciji
            pairs: list[tuple[Optional[int], Optional[int]]] = [(i, i) for i in range(min(nT, nS))]
            pairs += [(i, None) for i in range(nS, nT)]
            pairs += [(None, j) for j in range(nT, nS)]
            return pairs

        pairs = []
        i, j = nT, nS
        while (i, j) != (0, 0):
            pi, pj = back[i][j]
            if pi == i - 1 and pj == j - 1:
                pairs.append((i - 1, j - 1))
            elif pi == i - 1:
                pairs.append((i - 1, None))
            else:
                pairs.append((None, j - 1))
            i, j = pi, pj
        pairs.reverse()
        return pairs

    def _compare_para(self, t_seg: Seg, s_seg: Seg) -> None:
        tt, ss = t_seg.text, s_seg.text
        norm = lambda x: re.sub(r"\W+", " ", x).strip().lower()

        if len(ss) >= 25 and norm(tt) == norm(ss) and re.search(r"[^\W\d_]{3}", ss):
            self.aud.add(t_seg, "greška", "izvornik_identičan",
                         "Odlomak je identičan izvorniku (neprevedeno)", 0, min(len(tt), 160))
            return

        num_rx = re.compile(r"\d+(?:[.,]\d+)*")
        cn = lambda x: Counter(re.sub(r"[.,]", "", n) for n in num_rx.findall(x))
        ct, cs = cn(tt), cn(ss)
        if ct != cs:
            missing = list((cs - ct).elements())
            extra = list((ct - cs).elements())
            if missing or extra:
                self.aud.add(t_seg, "upozorenje", "izvornik_brojevi",
                             f"Brojevi se razlikuju – u izvorniku: {missing or '—'}, u prijevodu: {extra or '—'}",
                             0, min(len(tt), 160))

        if len(ss) >= 80:
            r = len(tt) / len(ss)
            if r < 0.45:
                self.aud.add(t_seg, "greška", "izvornik_duljina",
                             f"Prijevod je {r:.0%} duljine izvornika – moguće ispuštanje",
                             0, min(len(tt), 160))
            elif r < 0.6:
                self.aud.add(t_seg, "upozorenje", "izvornik_duljina",
                             f"Prijevod je {r:.0%} duljine izvornika", 0, min(len(tt), 160))
            elif r > 1.9:
                self.aud.add(t_seg, "upozorenje", "izvornik_duljina",
                             f"Prijevod je {r:.0%} duljine izvornika – moguće dodavanje",
                             0, min(len(tt), 160))


# ═══════════════════════════════════════════════════════════════
# ZAVRŠNI PROLAZI
# ═══════════════════════════════════════════════════════════════

def minority_report(aud: Auditor, store: dict[str, list], code: str, what: str) -> dict:
    """Prijavi pojave stila čiji je udio manji od minority_ratio (kad je dominantni stil jasan)."""
    counts = {k: len(v) for k, v in sorted(store.items())}
    total = sum(counts.values())
    if total < aud.th["min_style_samples"] or len(counts) < 2:
        return counts
    major = max(counts, key=lambda k: (counts[k], k))
    for k in sorted(store):
        if k == major or counts[k] / total >= aud.th["minority_ratio"]:
            continue
        for seg, s, e in store[k]:
            aud.add(seg, "upozorenje", code,
                    f"{what}: većina knjige koristi {major} ({counts[major]}×), ovdje {k}",
                    s, e, major)
    return counts


def finish(aud: Auditor) -> None:
    # tri točkice — manjinski zapis
    if len(aud.ellipsis) > 1 and aud.on("tropuntkice"):
        minority = min(aud.ellipsis, key=lambda k: len(aud.ellipsis[k]))
        major = max(aud.ellipsis, key=lambda k: len(aud.ellipsis[k]))
        for seg, s, e in aud.ellipsis[minority]:
            aud.add(seg, "info", "tropuntkice",
                    f"Nedosljedno: većina knjige koristi „{major}“", s, e, major)

    # dominantni stil navodnika i dijaloške crtice
    if aud.cfg["quote_style"] == "auto" and aud.on("navodnici_stil"):
        aud.computed["navodnici_po_stilu"] = minority_report(
            aud, aud.quote_open, "navodnici_stil", "Nedosljedan stil navodnika")
    if aud.on("crtica_stil"):
        aud.computed["dijalog_crtica_po_stilu"] = minority_report(
            aud, aud.dash_start, "crtica_stil", "Nedosljedna dijaloška crtica")

    # granice relativne prema knjizi
    th = aud.th
    if aud.on("rečenica_duga"):
        lim = adaptive_limit(aud.sent_lengths, th["sentence_words_floor"],
                             th["percentile"], th["percentile_factor"])
        aud.computed["granica_rečenice_riječi"] = round(lim, 1)
        for seg, a, b, nw in aud.sent_cand:
            if nw > lim:
                aud.add(seg, "info", "rečenica_duga",
                        f"Rečenica ima {nw} riječi (granica za ovu knjigu: {lim:.0f})", a, min(b, a + 160))
    if aud.on("predug_pasus"):
        lim = adaptive_limit(aud.par_lengths, th["paragraph_chars_floor"],
                             th["percentile"], th["percentile_factor"])
        aud.computed["granica_pasusa_znakova"] = round(lim, 1)
        for seg, n in aud.par_cand:
            if n > lim:
                aud.add(seg, "upozorenje", "predug_pasus",
                        f"Pasus ima {n} znakova (granica za ovu knjigu: {lim:.0f}) – spojeni blokovi?",
                        0, min(n, 160))

    # nedosljednost imena
    if aud.on("ime_nedosljedno"):
        top = [w for w, _ in aud.name_cnt.most_common(1500) if len(w) >= 4]
        seen: set[tuple[str, str]] = set()
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                if a[0] != b[0] or abs(len(a) - len(b)) > 2 or (a, b) in seen:
                    continue
                if a.startswith(b) or b.startswith(a):
                    continue
                if a[:-2] == b[:-2] and a[-2:] != b[-2:]:   # razlika samo u padežnom nastavku
                    continue
                mn = min(len(a), len(b))
                if mn >= 4 and a[:mn - 1].lower() == b[:mn - 1].lower():
                    continue
                if difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.86:
                    seen.add((a, b))
                    rare = b if aud.name_cnt[b] <= aud.name_cnt[a] else a
                    other = a if rare == b else b
                    seg, s, e = aud.name_first[rare]
                    aud.add(seg, "upozorenje", "ime_nedosljedno",
                            f"Moguće nedosljedno pisanje imena: „{rare}“ ({aud.name_cnt[rare]}×) "
                            f"↔ „{other}“ ({aud.name_cnt[other]}×)", s, e, other)

    # nepoznate riječi
    for w, c in aud.unknown_words.items():
        seg, s, e = aud.unknown_first[w]
        aud.add(seg, "info", "nepoznata_riječ", f"Riječ nije u rječniku ({c}× u knjizi)", s, e)


def check_chapter_structure(aud: Auditor, book: Book) -> None:
    skip_rx = [re.compile(p) for p in aud.cfg["structure_skip_files"]]
    for idx, href, segs in book.chapters:
        if any(rx.search(href) for rx in skip_rx):
            continue
        body = [s for s in segs if s.kind == "tekst"]
        chap = body[0].chapter if body else ""
        if not body:
            aud.add(Seg(href, idx, "", 0, "", "", "", kind="meta"),
                    "upozorenje", "struktura_poglavlja", "Poglavlje bez teksta", 0, 0)
            continue
        h1 = book.h1_count.get(idx, 0)
        if h1 == 0:
            aud.add(Seg(href, idx, chap, 0, "", "", "", kind="meta"),
                    "upozorenje", "h1_nedostaje", "Poglavlje nema <h1>", 0, 0)
        elif h1 > 1:
            aud.add(Seg(href, idx, chap, 0, "", "", "", kind="meta"),
                    "upozorenje", "h1_višestruk", f"Poglavlje ima {h1} <h1> (treba 1)", 0, 0)
        empty = book.empty_p_count.get(idx, 0)
        if empty >= 3:
            aud.add(Seg(href, idx, chap, 0, "", "", "", kind="meta"),
                    "upozorenje", "prazan_pasus", f"Poglavlje ima {empty} praznih <p>", 0, 0)

    items = sorted(book.chapter_numbers.items(), key=lambda kv: kv[1])
    for (_sp0, n0), (sp1, n1) in zip(items, items[1:]):
        if n1 - n0 > 1:
            aud.add(Seg("(knjiga)", sp1, "numeracija", 0, "", "", "", kind="meta"),
                    "upozorenje", "numeracija_rupa", f"Rupa u numeraciji: {n0} → {n1}", 0, 0)

    codes = aud.lang["codes"]
    accept = tuple(x.lower() for x in (aud.cfg["lang_accept"] or codes))
    target = codes[0]
    for lg in book.opf_langs or ["(nema)"]:
        if not lg.lower().startswith(accept):
            aud.add(Seg("content.opf", 0, "metapodaci", 0, "dc:language", "", lg, kind="meta"),
                    "greška", "metapodaci", f"dc:language je „{lg}“, a treba biti „{target}“", 0, len(lg), target)
    for href, lang in book.langs.items():
        if lang is not None and not lang.lower().startswith(accept):
            aud.add(Seg(href, 0, "", 0, "html", "", lang, kind="meta"),
                    "upozorenje", "metapodaci", f"Atribut lang/xml:lang je „{lang}“", 0, len(lang), target)
        elif lang is None:
            aud.add(Seg(href, 0, "", 0, "html", "", "(bez lang)", kind="meta"),
                    "info", "metapodaci", "Datoteka nema lang atribut", 0, 0, f'lang="{target}"')

    for src_file, target_f in book.toc_links:
        if target_f not in book.all_files:
            aud.add(Seg(src_file, 0, "sadržaj", 0, "a", "", target_f, kind="toc"),
                    "upozorenje", "metapodaci",
                    f"TOC link pokazuje na nepostojeću datoteku: {target_f}", 0, len(target_f))


# ═══════════════════════════════════════════════════════════════
# IZVJEŠTAJI (deterministički; zapis samo ako se sadržaj promijenio)
# ═══════════════════════════════════════════════════════════════

FIELDS = [
    ("id", "id"), ("severity", "ozbiljnost"), ("code", "vrsta"),
    ("message", "opis"), ("file", "datoteka"), ("spine", "poredak_u_spineu"),
    ("chapter", "poglavlje"), ("par", "odlomak"), ("tag", "element"),
    ("eid", "id_elementa"), ("offset", "znak"), ("match", "pronađeno"),
    ("context", "kontekst"), ("suggestion", "prijedlog"),
]


def location(d: dict) -> str:
    el = ""
    if d["tag"]:
        eid = ("#" + d["eid"]) if d["eid"] else ""
        el = "<" + d["tag"] + eid + ">"
    return f"{d['file']} · „{d['chapter']}“ · odl. {d['par']} {el} · znak {d['offset']}"


def write_if_changed(path: str, content: str, bom: bool = False) -> tuple[str, bool]:
    """Atomski zapis. Vraća (sha256 sadržaja, je_li_zapisano)."""
    raw = (("\ufeff" if bom else "") + content).encode("utf-8")
    digest = sha256_bytes(raw)
    try:
        if os.path.exists(path) and sha256_file(path) == digest:
            return digest, False
    except OSError:
        pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(raw)
    os.replace(tmp, path)
    return digest, True


def render_csv(data: list[dict]) -> str:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_MINIMAL)
    w.writerow([h for _, h in FIELDS])
    for d in data:
        w.writerow([d.get(k, "") for k, _ in FIELDS])
    return buf.getvalue()


def render_json(data: list[dict]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


def render_jsonl(data: list[dict]) -> str:
    return "\n".join(json.dumps(d, ensure_ascii=False, sort_keys=True) for d in data) + "\n"


def render_md(data: list[dict], base: str, aud: Auditor, by_sev: Counter, prof_name: str) -> str:
    L: list[str] = [f"# Lektorski audit: {os.path.basename(base)}.epub", ""]
    L += [f"Profil: **{prof_name}** · jezik: **{aud.cfg['language']}** · alat: epub_audit v{VERSION}", ""]
    if aud.disabled:
        L += ["Isključena pravila: " + ", ".join(sorted(aud.disabled)), ""]
    L += [f"Riječi (približno): **{aud.total_words}** · nalaza: **{len(data)}** "
          f"(greške {by_sev['greška']}, upozorenja {by_sev['upozorenje']}, info {by_sev['info']})", ""]
    by_code: defaultdict[str, Counter] = defaultdict(Counter)
    for d in data:
        by_code[d["code"]][d["severity"]] += 1
    L += ["## Po vrstama", "", "| vrsta | opis | greške | upoz. | info | ukupno |", "|---|---|--:|--:|--:|--:|"]
    for code, c in sorted(by_code.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        L.append(f"| {code} | {CODE_LABEL.get(code, '')} | {c['greška']} | {c['upozorenje']} | {c['info']} | {sum(c.values())} |")
    chap: defaultdict[int, Counter] = defaultdict(Counter)
    for d in data:
        if d["severity"] != "info":
            chap[d["spine"]][d["severity"]] += 1
    L += ["", "## Poglavlja po gustoći (greške+upozorenja na 1000 riječi)", "",
          "| # | poglavlje | riječi | greške | upoz. | /1000 |", "|--:|---|--:|--:|--:|--:|"]
    dens = []
    for sp, c in chap.items():
        wc = max(aud.chap_words.get(sp, 1), 1)
        dens.append(((c["greška"] + c["upozorenje"]) * 1000 / wc, sp, wc, c))
    for dn, sp, wc, c in sorted(dens, key=lambda x: (-x[0], x[1]))[:30]:
        title = aud.chap_title.get(sp, "")
        L.append(f"| {sp} | {title[:50]} | {wc} | {c['greška']} | {c['upozorenje']} | {dn:.1f} |")
    L += ["", "## Imena i velika slova usred rečenice", "",
          ", ".join(f"{w} ({c})" for w, c in aud.name_cnt.most_common(60))]
    L += ["", "## Pokazatelji stila", "",
          f"- Rečenica: {aud.sentences}; rečenica koje počinju „On/Ona/Ja… je“: {aud.pron_sent}",
          f"- Oblici „napravi…“: {aud.napr} ({aud.napr * 1000 / max(aud.total_words, 1):.1f} na 1000 riječi)"]
    for k, v in sorted(aud.computed.items()):
        L.append(f"- {k}: {json.dumps(v, ensure_ascii=False, sort_keys=True)}")
    if aud.unknown_words:
        L += ["", "## Najčešće nepoznate riječi", "",
              ", ".join(f"{w} ({c})" for w, c in aud.unknown_words.most_common(60))]
    L += ["", "## Primjeri po vrsti", ""]
    ex: defaultdict[str, list[dict]] = defaultdict(list)
    for d in data:
        if len(ex[d["code"]]) < 12:
            ex[d["code"]].append(d)
    for code in sorted(ex):
        L += [f"### {code} – {CODE_LABEL.get(code, '')}", ""]
        for d in ex[code]:
            sug = f" → *{d['suggestion']}*" if d["suggestion"] else ""
            L.append(f"- [{d['severity']}] {d['message']}{sug}  \n  `{d['lokacija']}`  \n  {d['context']}")
        L.append("")
    return "\n".join(L)


HTML_CSS = """
body { font-family: system-ui, sans-serif; margin: 1em; background: #f8f9fa; }
h1 { font-size: 1.3em; }
.summary { display: flex; gap: 1em; margin: 1em 0; flex-wrap: wrap; }
.stat { padding: 0.5em 1em; background: white; border-radius: 6px; border-left: 4px solid #ccc; }
.stat.greska { border-color: #dc3545; } .stat.upozorenje { border-color: #ffc107; } .stat.info { border-color: #6c757d; }
.stat b { font-size: 1.5em; display: block; }
.controls { margin: 1em 0; display: flex; gap: 0.5em; flex-wrap: wrap; }
.controls input, .controls select { padding: 0.4em; border: 1px solid #ccc; border-radius: 4px; }
table { width: 100%; border-collapse: collapse; background: white; }
th { background: #e9ecef; padding: 0.5em; text-align: left; font-size: 0.85em; cursor: pointer; position: sticky; top: 0; }
td { padding: 0.35em 0.5em; border-bottom: 1px solid #dee2e6; font-size: 0.85em; vertical-align: top; }
tr:hover { background: #f1f3f5; }
.badge { padding: 0.1em 0.4em; border-radius: 3px; color: white; font-size: 0.75em; font-weight: bold; }
.badge-greska { background: #dc3545; } .badge-upozorenje { background: #ffc107; color: #000; } .badge-info { background: #6c757d; }
.code { font-family: monospace; color: #0d6efd; }
.file { font-family: monospace; font-size: 0.8em; color: #6c757d; }
.ctx { font-family: monospace; font-size: 0.8em; max-width: 400px; overflow-wrap: break-word; }
.sug { color: #198754; }
"""

HTML_JS = """
const tbody = document.querySelector('#table tbody');
const search = document.getElementById('search');
const codeSel = document.getElementById('code');
const sevSel = document.getElementById('sev');
function applyFilter() {
  const q = search.value.toLowerCase(), code = codeSel.value, sev = sevSel.value;
  for (const tr of tbody.children) {
    const ok = (!code || tr.dataset.code === code) && (!sev || tr.dataset.sev === sev)
               && (!q || tr.textContent.toLowerCase().includes(q));
    tr.style.display = ok ? '' : 'none';
  }
}
search.addEventListener('input', applyFilter);
codeSel.addEventListener('change', applyFilter);
sevSel.addEventListener('change', applyFilter);
const COLS = {id:0, sev:1, code:2, message:3, chapter:4, file:5, par:6};
document.querySelectorAll('th[data-sort]').forEach(th => {
  let asc = true;
  th.addEventListener('click', () => {
    const c = COLS[th.dataset.sort], numeric = (th.dataset.sort === 'id' || th.dataset.sort === 'par');
    const rows = [...tbody.children];
    rows.sort((a, b) => {
      let av = a.children[c].textContent, bv = b.children[c].textContent;
      if (numeric) { av = +av; bv = +bv; }
      return (av > bv ? 1 : av < bv ? -1 : 0) * (asc ? 1 : -1);
    });
    rows.forEach(r => tbody.appendChild(r));
    asc = !asc;
  });
});
"""


def render_html(data: list[dict], base: str, aud: Auditor) -> str:
    esc = html_mod.escape
    by_code: defaultdict[str, Counter] = defaultdict(Counter)
    for d in data:
        by_code[d["code"]][d["severity"]] += 1
    cls = lambda s: {"greška": "greska"}.get(s, s)
    rows = []
    for d in data:
        rows.append(
            f'<tr data-sev="{esc(d["severity"])}" data-code="{esc(d["code"])}">'
            f'<td>{d["id"]}</td>'
            f'<td><span class="badge badge-{cls(d["severity"])}">{SEV_LABEL[d["severity"]]}</span></td>'
            f'<td class="code">{esc(d["code"])}</td>'
            f'<td>{esc(d["message"])}</td>'
            f'<td>{esc(d["chapter"][:40])}</td>'
            f'<td class="file">{esc(d["file"])}</td>'
            f'<td>{d["par"]}</td>'
            f'<td class="ctx">{esc(d["context"])}</td>'
            f'<td class="sug">{esc(d["suggestion"] or "")}</td>'
            f'</tr>'
        )
    code_options = "\n".join(
        f'<option value="{esc(c)}">{esc(c)} ({sum(v.values())})</option>'
        for c, v in sorted(by_code.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    )
    n_err = sum(1 for d in data if d["severity"] == "greška")
    n_warn = sum(1 for d in data if d["severity"] == "upozorenje")
    n_info = sum(1 for d in data if d["severity"] == "info")
    title = esc(os.path.basename(base))
    parts = [
        '<!DOCTYPE html>\n<html lang="hr"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Audit: {title}</title><style>{HTML_CSS}</style></head><body>",
        f"<h1>Audit: {title}.epub</h1>",
        '<div class="summary">',
        f'<div class="stat greska"><b>{n_err}</b>greške</div>',
        f'<div class="stat upozorenje"><b>{n_warn}</b>upozorenja</div>',
        f'<div class="stat info"><b>{n_info}</b>info</div>',
        f'<div class="stat"><b>{aud.total_words}</b>riječi</div>',
        f'<div class="stat"><b>{len(data)}</b>ukupno nalaza</div></div>',
        '<div class="controls">',
        '<input type="search" id="search" placeholder="Pretraži…" style="flex:1;min-width:200px;">',
        f'<select id="code"><option value="">— sve vrste —</option>{code_options}</select>',
        '<select id="sev"><option value="">— sve ozbiljnosti —</option>'
        '<option value="greška">greške</option><option value="upozorenje">upozorenja</option>'
        '<option value="info">info</option></select></div>',
        '<div style="overflow-x:auto"><table id="table"><thead><tr>',
        '<th data-sort="id">#</th><th data-sort="sev">Ozb.</th><th data-sort="code">Vrsta</th>',
        '<th data-sort="message">Opis</th><th data-sort="chapter">Pogl.</th>',
        '<th data-sort="file">Datoteka</th><th data-sort="par">Odl.</th>',
        '<th>Kontekst</th><th>Prijedlog</th></tr></thead><tbody>',
        "".join(rows),
        f"</tbody></table></div><script>{HTML_JS}</script></body></html>",
    ]
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def _csv_arg(s: Optional[str]) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(
        description=f"Lektorski audit strojno prevedenog EPUB-a — v{VERSION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("epub", nargs="?", help="prevedeni EPUB")
    ap.add_argument("--source", help="izvorni EPUB (en) za usporedbu")
    ap.add_argument("--profile", help="JSON profil knjige (imena, pragovi, isključena pravila…)")
    ap.add_argument("-o", "--out", default=".", help="mapa za izlaz")
    ap.add_argument("--wordlist", help="datoteka s riječima ciljnog jezika")
    ap.add_argument("--names", help="JSON s dodatnim imenima {en: hr}")
    ap.add_argument("--lexicon", help="JSON s dodatnim regex pravilima")
    ap.add_argument("--exclude", help="JSON {files:[regex], patterns:[regex]} ili lista regexa")
    ap.add_argument("--skip-files", help="dodatni regexi (zarez) za datoteke koje se ne čitaju")
    ap.add_argument("--disable", help="kodovi pravila za isključiti (zarez)")
    ap.add_argument("--enable", help="kodovi pravila za uključiti (nadjačava profil)")
    ap.add_argument("--list-rules", action="store_true", help="ispiši pravila i njihovo stanje")
    ap.add_argument("--learn-names", action=argparse.BooleanOptionalAction, default=None,
                    help="nauči vlastita imena iz --source (nadjačava profil)")
    ap.add_argument("--min-severity", default="info", choices=list(SEV_ORDER))
    ap.add_argument("--max-words", type=int, help="donja granica duljine rečenice (riječi)")
    ap.add_argument("--max-paragraph", type=int, help="donja granica duljine pasusa (znakovi)")
    ap.add_argument("--format", default="csv,json,md,html", help="csv,json,jsonl,md,html")
    ap.add_argument("--skip-fantasy", action="store_true",
                    help="ne prijavljuj ime_strano_pismo")
    ap.add_argument("--version", action="version", version=f"epub_audit {VERSION}")
    args = ap.parse_args(argv)

    prof, prof_info = load_profile(args.profile)

    disabled = set(prof["disabled_rules"]) | set(_csv_arg(args.disable))
    disabled -= set(_csv_arg(args.enable))
    for c in sorted(set(_csv_arg(args.disable)) | set(_csv_arg(args.enable))):
        if c not in CODE_LABEL:
            sys.stderr.write(f"[WARN] nepoznato pravilo: „{c}“\n")

    if args.list_rules:
        print(f"[profil] {prof['name']} · jezik {prof['language']}")
        for code in sorted(CODE_LABEL):
            state = "ISKLJUČENO" if code in disabled else "uključeno "
            print(f"  {state}  {code:<22} {CODE_LABEL[code]}")
        return
    if not args.epub:
        ap.error("potreban je EPUB (ili --list-rules)")

    th = dict(prof["thresholds"])
    if args.max_words is not None:
        th["sentence_words_floor"] = args.max_words
    if args.max_paragraph is not None:
        th["paragraph_chars_floor"] = args.max_paragraph

    names = dict(prof["names"])
    if args.names:
        try:
            with open(args.names, encoding="utf-8") as fh:
                names.update(json.load(fh))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"[FAIL] --names: {e}")

    extra_rules = list(prof["extra_rules"])
    if args.lexicon:
        try:
            with open(args.lexicon, encoding="utf-8") as fh:
                extra_rules += json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"[FAIL] --lexicon: {e}")

    exclude: list[str] = []
    if args.exclude:
        try:
            with open(args.exclude, encoding="utf-8") as fh:
                ex = json.load(fh)
            exclude = list(ex) if isinstance(ex, list) else list(ex.get("files", [])) + list(ex.get("patterns", []))
        except (OSError, json.JSONDecodeError) as e:
            sys.exit(f"[FAIL] --exclude: {e}")

    wordlist: Optional[set[str]] = None
    if args.wordlist:
        try:
            with open(args.wordlist, encoding="utf-8") as fh:
                wordlist = {ln.strip().lower() for ln in fh if ln.strip()}
        except OSError as e:
            sys.exit(f"[FAIL] --wordlist: {e}")

    skip_files = list(prof["skip_files"]) + _csv_arg(args.skip_files)
    for p in skip_files:
        _bad_regex("--skip-files", p)

    learn = args.learn_names if args.learn_names is not None else prof["learn_names"]
    if learn is None:
        learn = bool(args.source)

    cfg = {
        "language": prof["language"], "names": names,
        "proper_names": set(prof["proper_names"]), "foreign_ok": list(prof["foreign_ok"]),
        "thresholds": th, "quote_style": prof["quote_style"], "disabled": sorted(disabled),
        "skip_fantasy": bool(args.skip_fantasy or prof["skip_fantasy"]),
        "chapter_number_regex": prof["chapter_number_regex"],
        "structure_skip_files": list(prof["structure_skip_files"]),
        "lang_accept": prof["lang_accept"], "extra_rules": extra_rules,
    }

    print(f"[audit] {args.epub}  (profil: {prof['name']}, jezik: {prof['language']})")
    try:
        book = Book.read(args.epub, skip_files)
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        sys.exit(f"[FAIL] {args.epub}: {e}")
    print(f"[audit] poglavlja: {len(book.chapters)}  (preskočeno datoteka: {len(book.skipped_files)})")

    src_book: Optional[Book] = None
    if args.source:
        try:
            src_book = Book.read(args.source, skip_files)
            print(f"[audit] izvornik: {len(src_book.chapters)} poglavlja")
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError, KeyError) as e:
            sys.stderr.write(f"[WARN] --source: {e}\n")

    aud = Auditor(cfg, wordlist)

    learned: set[str] = set()
    if learn:
        if src_book is None:
            sys.stderr.write("[WARN] učenje imena traži valjan --source; preskočeno\n")
        else:
            learned = learn_proper_names(src_book, int(th["learn_names_min_count"]),
                                         float(th["learn_names_lower_ratio"]))
            aud.set_learned(learned)
            print(f"[audit] naučeno vlastitih imena iz izvornika: {len(learned)}")

    def skipped(seg: Seg) -> bool:
        return any(re.search(p, seg.file) or re.search(p, seg.chapter) for p in exclude)

    for seg in book.meta:
        if not skipped(seg):
            aud.audit_seg(seg)
    for seg in book.toc:
        if not skipped(seg):
            aud.audit_seg(seg)
    for idx, href, segs in book.chapters:
        if any(re.search(p, href) for p in exclude):
            continue
        aud.audit_chapter(idx, segs)

    book.chapter_numbers = dict(aud.chapter_numbers)
    check_chapter_structure(aud, book)

    if src_book:
        SourceComparator(aud, src_book).compare(book)

    finish(aud)

    findings = [f for f in aud.findings if SEV_ORDER[f.severity] >= SEV_ORDER[args.min_severity]]
    findings.sort(key=lambda f: (f.spine, f.par, f.offset, f.code))
    data: list[dict] = []
    for i, f in enumerate(findings, 1):
        d = f.to_dict()
        d["id"] = i
        d["lokacija"] = location(d)
        data.append(d)

    base = os.path.splitext(os.path.basename(args.epub))[0]
    os.makedirs(args.out, exist_ok=True)
    base_path = os.path.join(args.out, base)
    by_sev = Counter(d["severity"] for d in data)
    by_code = Counter(d["code"] for d in data)

    print(f"\n[audit] ukupno nalaza: {len(data)}")
    print(f"  GREŠKA:       {by_sev.get('greška', 0)}")
    print(f"  UPOZORENJE:   {by_sev.get('upozorenje', 0)}")
    print(f"  INFO:         {by_sev.get('info', 0)}")
    print("\n[audit] po vrsti (top 15):")
    for code, n in sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
        print(f"  {code:<22} {n:>6}   {CODE_LABEL.get(code, '')[:60]}")

    formats = {f.strip().lower() for f in args.format.split(",") if f.strip()}
    outputs: dict[str, str] = {}
    status: list[tuple[str, bool]] = []

    def emit(name: str, content: str, bom: bool = False) -> None:
        path = base_path + name
        digest, wrote = write_if_changed(path, content, bom)
        outputs[os.path.basename(path)] = digest
        status.append((path, wrote))

    if "csv" in formats:
        emit("_audit.csv", render_csv(data), bom=True)
    if "json" in formats:
        emit("_audit.json", render_json(data))
    if "jsonl" in formats:
        emit("_audit.jsonl", render_jsonl(data))
    if "md" in formats:
        emit("_audit.md", render_md(data, base, aud, by_sev, prof["name"]))
    if "html" in formats:
        emit("_audit.html", render_html(data, base, aud))

    manifest = {
        "alat": {"naziv": "epub_audit", "verzija": VERSION},
        "ulaz": {"datoteka": os.path.basename(args.epub), "sha256": sha256_file(args.epub),
                 "bajtova": os.path.getsize(args.epub)},
        "izvornik": ({"datoteka": os.path.basename(args.source), "sha256": sha256_file(args.source)}
                     if src_book else None),
        "profil": {"naziv": prof["name"], **prof_info},
        "konfiguracija": {
            "jezik": prof["language"], "quote_style": prof["quote_style"],
            "isključena_pravila": sorted(disabled), "pragovi": th,
            "skip_files": skip_files, "učenje_imena": bool(learn and src_book),
            "min_severity": args.min_severity,
            "wordlist_sha256": sha256_file(args.wordlist) if args.wordlist else None,
        },
        "izračunato": {**aud.computed, "naučena_imena": len(learned),
                       "preskočene_datoteke": sorted(book.skipped_files), "riječi": aud.total_words},
        "nalazi": {"ukupno": len(data), "po_ozbiljnosti": dict(sorted(by_sev.items())),
                   "po_vrsti": dict(sorted(by_code.items()))},
        "izlazi_sha256": dict(sorted(outputs.items())),
    }
    mpath = base_path + "_audit_run.json"
    _, wrote = write_if_changed(mpath, json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True))
    status.append((mpath, wrote))

    print("\n[audit] izlaz:")
    for p, wrote in status:
        print(f"  {p}  [{'zapisano' if wrote else 'nepromijenjeno'}]")


if __name__ == "__main__":
    main()
