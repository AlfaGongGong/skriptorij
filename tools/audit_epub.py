#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_epub.py — sveobuhvatni audit GOTOVOG (prevedenog + stiliziranog) EPUB-a.

CILJ: naći greške koje je pipeline mogao napraviti a da su prošle u finalni EPUB,
i za svaku grešku reći GDJE je (fajl + redni broj pasusa + isječak) i U KOJEM
dijelu koda je vjerovatno uzrok.

Samo ČITA EPUB. Piše isključivo u izlazni folder s izvještajem.

Upotreba (proot Ubuntu):
    python3 audit_epub.py KNJIGA.epub
    python3 audit_epub.py KNJIGA.epub --izvor ORIGINAL.epub --chk /put/do/_skr_folder
    python3 audit_epub.py KNJIGA.epub --brzo

Opcioni alati (koriste se samo ako postoje):
    apt install hunspell hunspell-hr            -> provjera pravopisa (JEZ-PRAVOPIS)
    apt install epubcheck default-jre-headless  -> službena validacija (STR-EPUBCHECK)
    pip install langdetect                      -> drugo mišljenje za engleske ostatke

Izlaz (u --out folderu):
    izvjestaj.md   — sažetak, tabela kategorija, najgora poglavlja, primjeri, "gdje u kodu"
    nalazi.csv     — svi nalazi (otvori u bilo kojem tabelarnom programu)
    nalazi.jsonl   — isto, mašinski čitljivo
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import hashlib
import json
import os
import posixpath
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import zipfile
import zlib
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

# ════════════════════════════════════════════════════════════════════
# Katalog kategorija: šifra -> (ozbiljnost, opis, gdje u kodu tražiti)
# ════════════════════════════════════════════════════════════════════
TEZINA = {"KRITICNO": 8.0, "VISOKO": 4.0, "SREDNJE": 2.0, "NISKO": 0.5, "INFO": 0.0}
REDOSLIJED = ["KRITICNO", "VISOKO", "SREDNJE", "NISKO", "INFO"]

KAT = {
    # ── struktura EPUB-a ──
    "STR-ZIP": ("KRITICNO", "ZIP/mimetype neispravan (mimetype mora biti prvi, nekompresovan)", "epub/styler.py::_write, epub/packager.py"),
    "STR-XML": ("KRITICNO", "XHTML nije well-formed XML (čitači mogu odbiti poglavlje)", "epub/styler.py (dodaj_*), epub/normalizer.py, core/prompts.py (HTML pravila)"),
    "STR-ENT": ("VISOKO", "imenovani HTML entitet (&nbsp; i sl.) — nije dozvoljen u XHTML-u", "epub/normalizer.py, post-polish zamjene"),
    "STR-OPF": ("KRITICNO", "OPF manifest pokazuje na fajl koji ne postoji / spine na nepoznat id", "epub/styler.py (OPF build), epub/packager.py"),
    "STR-ORPHAN": ("NISKO", "HTML fajl u EPUB-u nije u manifestu", "epub/styler.py (brisanje ne-poglavlja)"),
    "STR-NCX": ("VISOKO", "NCX/nav pokazuje na fajl ili sidro koje ne postoji", "engine.generate_ncx, epub/styler.py (TOC)"),
    "STR-LINK": ("SREDNJE", "interni link pokazuje na nepostojeći fajl/sidro", "epub/styler.py, epub/normalizer.py"),
    "STR-IMG": ("SREDNJE", "<img> pokazuje na nepostojeći fajl", "epub/styler.py (dropcap/ornament), epub/packager.py"),
    "STR-ID": ("NISKO", "duplikat id atributa u istom fajlu", "epub/styler.py"),
    "STR-EMPTY": ("VISOKO", "prazno ili gotovo prazno poglavlje", "processing/pipeline.py (.chk spajanje), epub/styler.py::_je_poglavlje"),
    "STR-DUPFILE": ("VISOKO", "dva poglavlja imaju identičan tekst", "processing/pipeline.py (resume/.chk spajanje)"),
    "STR-BROJ": ("SREDNJE", "numeracija poglavlja (POGLAVLJE N) ima rupu ili ponavljanje", "epub/styler.py (_dodaj_naslov), core/natural_sort.py"),
    "STR-EPUBCHECK": ("VISOKO", "epubcheck prijavio grešku/upozorenje", "vidi poruku (RSC/OPF/HTM kod)"),
    "STR-FAIL": ("INFO", "audit nije mogao obraditi fajl", "—"),
    # ── stilizacija ──
    "STIL-H1": ("SREDNJE", "poglavlje nema tačno jedan <h1> naslov", "epub/styler.py::_dodaj_naslov (postoje DVIJE definicije!)"),
    "STIL-DROPCAP-DUP": ("VISOKO", "više od jednog dropcapa u poglavlju", "epub/styler.py::_ukloni_sve / _dodaj_dropcap, stil_ai.py (dupli sistem)"),
    "STIL-VIJENAC-DUP": ("SREDNJE", "više od jednog ornamenta/vijenca u poglavlju", "epub/styler.py::_dodaj_vijenac"),
    "STIL-SIG": ("NISKO", "poglavlje ima drugačiji stilski potpis od većine knjige", "epub/styler.py (poglavlja koja preskače _je_poglavlje / dijalog-skip)"),
    "STIL-KLASA": ("NISKO", "zaostala izvorna CSS klasa (nije booklyfi-*)", "epub/normalizer.py::_strip_everything"),
    "STIL-STYLE": ("NISKO", "zaostali inline style= atributi izvan dropcapa", "epub/normalizer.py::_strip_everything"),
    "LEK-DROPCAP-DBL": ("VISOKO", "dupliran prvi znak pasusa (npr. 'AAutorska') — greška skrivenog slova", "epub/styler.py::_dodaj_dropcap / _ukloni_sve (skriveno slovo)"),
    # ── artefakti LLM-a ──
    "LEK-JSON": ("KRITICNO", "JSON omotač / ključ iz prompta procurio u tekst", "processing/pipeline.py::_chk_read, utils/checkpoint_cleaner.py::_ocisti_json_wrapper, network/http_client.py::_extract_gemini_native"),
    "LEK-FENCE": ("VISOKO", "markdown ``` ograda u tekstu", "network/http_client.py::_extract_*, utils/checkpoint_cleaner.py"),
    "LEK-META": ("KRITICNO", "model komentariše/odbija umjesto da prevodi (uvod, ispriku, refusal)", "core/prompts.py (IZLAZ), network/http_client.py (anti-refusal), nema validatora u processing/workers.py"),
    "LEK-TAG": ("VISOKO", "vidljivi HTML tag ili atribut u tekstu (escape-ovan)", "core/prompts.py (HTML u atributima), utils/checkpoint_cleaner.py"),
    "LEK-MARK": ("NISKO", "markdown oznake u tekstu (**, ##, `)", "core/prompts.py, core/text_utils.py"),
    "LEK-PLACE": ("VISOKO", "neizmijenjeni placeholder / marker iz prompta ({{..}}, [INSTRUKCIJE]...)", "network/http_client.py (_anti_refusal pre-prompt), core/prompt_injector.py"),
    "LEK-ESC": ("SREDNJE", "literalni escape (\\n, \\\", \\uXXXX) u tekstu", "utils/checkpoint_cleaner.py, JSON parsiranje u workers.py"),
    "LEK-MOJI": ("VISOKO", "mojibake / znak zamjene U+FFFD", "čitanje/pisanje fajlova bez utf-8, epub/packager.py"),
    "LEK-SKRIPTA": ("VISOKO", "znakovi iz stranog pisma (ćirilica, CJK, arapski, grčki, emoji)", "provider fallback (Qwen/Groq/GLM znaju procuriti kineski), core/validators"),
    "LEK-NULL": ("VISOKO", "pasus je 'None'/'null'/'undefined'", "processing/workers.py (prazan odgovor tretiran kao tekst)"),
    "LEK-CTRL": ("NISKO", "nevidljivi kontrolni znakovi (zero-width, soft hyphen)", "core/text_utils.py"),
    # ── jezik ──
    "JEZ-EN": ("VISOKO", "neprevedena engleska rečenica/pasus", "processing/workers.py (PREVODILAC preskočen/odbijen), provider_router fallback, PROHIBITED_CONTENT blokovi"),
    "JEZ-NEHR": ("SREDNJE", "pasus nije hrvatski ni engleski (drugi jezik?)", "provider fallback, core/validators"),
    "JEZ-EKAV": ("SREDNJE", "ekavizam/srbizam u ijekavskom tekstu", "core/kalkovi/ekavizmi.py, LEKTOR korak, core/validators/morfo_validator.py"),
    "JEZ-KALK": ("NISKO", "kalk iz liste (621 pravilo) preživio lekturu", "core/kalkovi/* (pravila), LEKTOR prompt, replacement faza"),
    "JEZ-DIAK": ("VISOKO", "poglavlju nedostaju dijakritici (č ć š ž đ)", "provider odgovor bez dijakritika, core/text_utils.py"),
    "JEZ-ROD": ("SREDNJE", "neslaganje roda (ona ... rekao / on ... rekla)", "core/kalkovi/rod_detektor.py, data/rod_registri"),
    "JEZ-DUPW": ("NISKO", "ponovljena riječ (je je, i i...)", "LEKTOR/POLISH korak"),
    "JEZ-PRAVOPIS": ("INFO", "riječ nepoznata hunspell rječniku (hr_HR)", "pregledaj top listu: izmišljene riječi, ekavizmi, tipfeleri"),
    # ── tipografija ──
    "TIP-NAVOD": ("SREDNJE", "neparni/pomiješani navodnici u pasusu", "core/kalkovi/dijalog.py, core/metrics.py::_navodnici_greske, chunk granice"),
    "TIP-STIL": ("SREDNJE", "poglavlje koristi drugi stil navodnika od ostatka knjige", "core/prompts.py (TIPOGRAFIJA), core/kalkovi/dijalog.py"),
    "TIP-CRTICA": ("NISKO", "dijalog počinje crticom '-' umjesto '—'", "core/kalkovi/dijalog.py"),
    "TIP-RAZMAK": ("NISKO", "razmak ispred interpunkcije / nedostaje iza nje", "core/metrics.py::_tipografija_pasus"),
    "TIP-ELIP": ("NISKO", "'...' umjesto '…' (miješanje)", "core/kalkovi/dijalog.py"),
    "TIP-ZAREZ": ("SREDNJE", "siroče zarez: ',,' ili ', .' (ostatak pokvarenih navodnika)", "core/kalkovi/dijalog.py, epub/styler.py::_dijalog"),
    # ── integritet sadržaja ──
    "INT-TRUNC": ("VISOKO", "poglavlje završava usred rečenice (odsječen zadnji blok)", "core/chunking.py, finish_reason=length retry u network/http_client.py"),
    "INT-SPLIT": ("VISOKO", "rečenica prekinuta između dva pasusa (granica bloka)", "core/chunking.py (max_words=250), inter-chapter context"),
    "INT-NEZAV": ("SREDNJE", "pasus završava veznikom/zarezom (vjerovatno odsječen)", "core/chunking.py, http_client.py (max_tokens)"),
    "INT-MALO": ("SREDNJE", "pasus počinje malim slovom usred poglavlja", "core/chunking.py (granice), processing/pipeline.py merge"),
    "INT-DUP": ("SREDNJE", "identičan dugi pasus se ponavlja", "processing/pipeline.py (retry/resume), spajanje .chk"),
    "INT-DUPS": ("VISOKO", "kraj jednog i početak sljedećeg pasusa se preklapaju (duplirana rečenica)", "core/chunking.py (preklapanje konteksta), pipeline merge"),
    "INT-LOOP": ("VISOKO", "petlja ponavljanja (model zapeo u ponavljanju)", "temperature/max_tokens u http_client.py, finish_reason"),
    "INT-DUGPASUS": ("SREDNJE", "ogroman pasus (spojeni blokovi / izgubljeni prijelomi)", "core/chunking.py, epub/normalizer.py::_normalize_html"),
    "INT-DUZINA": ("NISKO", "poglavlje je statistički odstupanje po dužini", "usporedi s izvorom (--izvor)"),
    "INT-RATIO": ("VISOKO", "odnos izvor/prijevod u poglavlju je izvan očekivanog (izostavljen ili napuhan tekst)", "processing/workers.py, core/quality.py (100-120% pravilo)"),
    "INT-IMENA-IZV": ("INFO", "ime iz izvornika se ne pojavljuje u prijevodu", "core/glosar_ekstrakcija.py, replacements"),
    "INT-GLOSAR": ("VISOKO", "izvorni oblik iz glosara je ostao u tekstu", "core/glosar_ekstrakcija.py, name_replacer, replacements"),
    # ── imena ──
    "IME-VAR": ("SREDNJE", "dva slična oblika imena (moguća nedosljednost prijevoda)", "core/glosar_ekstrakcija.py, analysis/book_context.py"),
    "IME-DIAK": ("SREDNJE", "isto ime s i bez dijakritika", "core/glosar_ekstrakcija.py, LEKTOR prompt"),
}

# ════════════════════════════════════════════════════════════════════
# Regexi i rječnici
# ════════════════════════════════════════════════════════════════════
RE_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)
RE_SENT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZČĆŠŽĐ„\"«“—–-])")

RE_JSON = re.compile(
    r'\{\s*"(?:finalno_polirano|finalno|prijevod|prevod|translation|polish\w*|tekst|text|output|result|html)"\s*:'
    r'|\bfinalno_polirano\b|\bchunk_sha\b|"(?:prevod|prijevod)"\s*:',
    re.I,
)
RE_FENCE = re.compile(r"```")
RE_META_HR = re.compile(
    r"\bevo (?:vašeg |tvog |traženog |lektoriranog |poliranog |tražen\w+ )?(?:prijevoda|prevoda|teksta)\b"
    r"|\bizvolite (?:prijevod|prevod|tekst)\b"
    r"|\bnaravno[,!] (?:evo|ovdje je|ispod)\b"
    r"|\b(?:lektorirani|prevedeni|poliran\w+) tekst:"
    r"|\bnapomena (?:prevodioca|prevoditelja|lektora)\b"
    r"|\bžao mi je[,.]? (?:ali )?(?:ne mogu|nisam u mogućnosti)"
    r"|\bne mogu (?:prevesti|obraditi|generirati|ispuniti|nastaviti s)\b"
    r"|\bkao (?:jezični model|umjetna inteligencija)\b",
    re.I,
)
RE_META_EN = re.compile(
    r"\bhere(?:'s| is) (?:the|your) (?:translat\w+|proofread\w*|text)\b"
    r"|\bas an ai\b|\bi(?:'m| am) sorry,? (?:but )?i\b"
    r"|\bi can(?:not|'t|’t) (?:translate|assist|comply|help with)\b"
    r"|\bprohibited_content\b|\bcontent (?:policy|violat\w+)\b"
    r"|^\s*(?:translation|prijevod|prevod|note|napomena)\s*:",
    re.I,
)
RE_TAGTXT = re.compile(r"</?(?:p|div|span|em|strong|br|h[1-6]|i|b|a|img)\b[^>]*>|\bclass\s*=|&(?:lt|gt|amp|quot|nbsp|#\d+);", re.I)
RE_MARK = re.compile(r"(?<!\w)\*\*[^*\n]+\*\*|^\s*#{1,6}\s+\S|`[^`\n]+`|\]\(https?://")
RE_ESC = re.compile(r"\\[nt\"'/]|\\u[0-9a-fA-F]{4}")
RE_PLACE = re.compile(
    r"\{\{[^}]{1,40}\}\}|\[\[[^\]]{1,40}\]\]|<<[^>]{1,40}>>|__[A-Z0-9_]{3,}__|⟦[^⟧]*⟧|§§\w+§§"
    r"|\bPLACEHOLDER\b|\bTODO\b|\bXXX+\b|%[sd]\b|\{(?:ime|name|glosar|tekst|text|blok|chunk)\w*\}"
    r"|\[(?:INSTRUKCIJE|TEKST ZA OBRADU|GLOSAR|KONTEKST|BLOK \d+)[^\]]*\]",
)
RE_MOJI = re.compile("Ã[\u0080-\u00bf]|Å[\u00a0-\u00bf]|Ä[\u0080-\u00bf]|â€|\ufffd")
RE_SKRIPTA = re.compile(
    "[\u0400-\u04ff\u0370-\u03ff\u0590-\u05ff\u0600-\u06ff\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af\U0001f300-\U0001faff]"
)
RE_CTRL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\u200b\u200c\u200d\u2060\ufeff\u00ad]")
NULL_SET = {"none", "null", "undefined", "nan", "n/a", "[]", "{}", '""', "''"}

RE_DBL_DROP = re.compile(r"^[„\"«“]?([A-ZČĆŠŽĐ])\1[a-zčćšžđ]{2,}")
RE_RAZ_PRIJE = re.compile(r"(?<=\w)\s+[,;:!?](?=\s|$)")
RE_RAZ_POSLIJE = re.compile(r"[,;:!?](?=[^\W\d_])|(?<=[a-zčćšžđ]{3})\.(?=[A-ZČĆŠŽĐ][a-zčćšžđ])")
RE_DUPW = re.compile(r"(?<![\w-])([^\W\d_]{3,})\s+\1(?![\w-])", re.I)
DUPW_OK = {"tako tako", "ili ili", "dobro dobro", "bila bila", "sada sada", "ha ha", "što što", "baš baš", "kako kako", "samo samo", "još još"}
RE_ROD_Z = re.compile(r"\b[Oo]na\s+je\s+(?:\w+\s+)?\w{2,}(?:ao|io|eo)\b")
RE_ROD_M = re.compile(r"\b[Oo]n\s+je\s+(?:\w+\s+)?\w{2,}la\b")
ROD_ISKLJUCI = {"jela", "sela", "bila", "pila", "dala", "zla", "prvila"}
RE_CAPWORD = re.compile(r"(?<![\w])([A-ZČĆŠŽĐ][a-zčćšžđ]{2,})(?![\w])")
RE_BROJ = re.compile(r"(\d+)")

TERM_END = set('.!?…"“”»)’\'—–:;*]')
NEZAV_RIJECI = {
    "i", "a", "ali", "te", "da", "u", "na", "sa", "s", "je", "su", "se", "će", "od", "do", "za", "kao", "što",
    "koji", "koja", "koje", "ni", "niti", "pa", "jer", "kad", "kada", "dok", "ako", "li", "bi", "bih", "ga", "mu",
    "joj", "im", "ih", "svoj", "svog", "svoje", "po", "iz", "o", "uz", "pod", "nad", "pred", "među", "kroz",
}
EN_STOP = {
    "the", "and", "of", "was", "he", "she", "his", "her", "with", "that", "had", "you", "for", "they", "this",
    "from", "have", "were", "said", "which", "been", "their", "would", "there", "what", "when", "will", "are",
    "but", "not", "him", "them", "then", "into", "than", "could", "who", "did", "its", "has", "only", "just",
    "like", "back", "down", "over", "out", "one", "all", "up", "i", "it", "in", "to", "of", "my", "me", "we",
}
EN_STOP_STRONG = EN_STOP - {"i", "it", "in", "to", "my", "me", "we", "one", "all", "up", "out"}
HR_STOP = {
    "je", "se", "i", "u", "na", "da", "ne", "su", "sa", "od", "za", "to", "koji", "što", "kao", "bio", "bila",
    "bilo", "ali", "mu", "ga", "joj", "ih", "nije", "će", "bi", "sam", "smo", "ste", "nisam", "kad", "ako",
    "samo", "još", "već", "ovo", "taj", "ta", "te", "mi", "ti", "on", "ona", "oni", "svoj", "pa", "li", "ni",
}
EKAV_FALLBACK = [
    r"\b(?:mleko|dete|deca|lepo|lepa|lepi|beo|bela|belo|vreme|vremena|reka|reke|pesma|ćerka|hteo|htela|"
    r"mesto|mesta|vetar|svetlo|sećanje|razumeti|videti|živeti|voleti|želeti|cvet|sneg|nedelja|pre\s+nego)\b"
]

NAV_RE = re.compile(r"^(?:nav|toc|cover|titlepage|booklyfi_\d+_|booklyfi_toc)", re.I)
BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "td", "th", "dd", "dt", "figcaption", "pre"}

ENT_RE = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)([A-Za-z][A-Za-z0-9]*);")


def alnum(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.lower())


def fold(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def snip(s: str, n: int = 140) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def levenshtein(a: str, b: str, cap: int = 2) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        lo = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            lo = min(lo, v)
        if lo > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# ════════════════════════════════════════════════════════════════════
# XHTML parser (stdlib)
# ════════════════════════════════════════════════════════════════════
class ChParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip = 0
        self.blocks: list[dict] = []
        self._cur = None
        self._loose: list[str] = []
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.srcs: list[str] = []
        self.classes = collections.Counter()
        self.style_attrs = 0
        self.hidden_spans = 0
        self.data_imgs = 0
        self.dropcaps = 0
        self.vijenac = 0
        self.h1 = 0
        self.naslov_h1 = 0

    def _flush_loose(self):
        t = " ".join("".join(self._loose).split())
        self._loose = []
        if t:
            self.blocks.append({"tag": "loose", "cls": "", "text": t})

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        cls = a.get("class", "").split()
        for c in cls:
            self.classes[c] += 1
        if "id" in a:
            self.ids.append(a["id"])
        if "style" in a:
            self.style_attrs += 1
            if "transparent" in a["style"]:
                self.hidden_spans += 1
        if tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        if tag in ("img", "image"):
            src = a.get("src") or a.get("xlink:href") or a.get("href") or ""
            self.srcs.append(src)
            if src.startswith("data:"):
                self.data_imgs += 1
            if "booklyfi-dropcap" in cls:
                self.dropcaps += 1
        if "booklyfi-vijenac" in cls:
            self.vijenac += 1
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "h1":
            self.h1 += 1
            if "booklyfi-naslov" in cls:
                self.naslov_h1 += 1
        if tag == "br" and self._cur is not None:
            self._cur["text"].append(" ")
        if tag in BLOCK and self._cur is None:
            self._flush_loose()
            self._cur = {"tag": tag, "cls": " ".join(cls), "text": []}

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in ("script", "style", "title") and tag not in BLOCK:
            return
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag == "title":
            self._in_title = False
            return
        if self._cur is not None and tag == self._cur["tag"]:
            t = " ".join("".join(self._cur["text"]).split())
            self._cur["text"] = t
            self.blocks.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        elif self._cur is not None:
            self._cur["text"].append(data)
        else:
            self._loose.append(data)

    def close(self):
        super().close()
        if self._cur is not None:
            self._cur["text"] = " ".join("".join(self._cur["text"]).split())
            self.blocks.append(self._cur)
            self._cur = None
        self._flush_loose()


def xml_provjera(raw: bytes):
    txt = raw.decode("utf-8", "replace")
    ents = sorted(set(ENT_RE.findall(txt)))
    safe = ENT_RE.sub("&#160;", txt)
    safe = re.sub(r"^\s*<\?xml[^>]*\?>", "", safe)
    err = None
    try:
        ET.fromstring(safe)
    except ET.ParseError as e:
        err = str(e)
    return ents, err


def lokalno(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ════════════════════════════════════════════════════════════════════
# Skupljač nalaza
# ════════════════════════════════════════════════════════════════════
class Nalazi:
    def __init__(self, max_po_fajlu=25, max_ukupno=150000):
        self.lista: list[dict] = []
        self.broj = collections.Counter()
        self.po_fajlu = collections.Counter()
        self.max_po_fajlu = max_po_fajlu
        self.max_ukupno = max_ukupno
        self.ch_score = collections.Counter()
        self.ch_kat = collections.defaultdict(collections.Counter)
        self.naslovi: dict[str, str] = {}

    def add(self, kat, fajl, par, tekst, detalj=""):
        sev = KAT[kat][0]
        self.broj[kat] += 1
        self.ch_score[fajl] += TEZINA[sev]
        self.ch_kat[fajl][kat] += 1
        k = (kat, fajl)
        self.po_fajlu[k] += 1
        if self.po_fajlu[k] > self.max_po_fajlu or len(self.lista) >= self.max_ukupno:
            return
        self.lista.append(
            {
                "kat": kat,
                "ozbiljnost": sev,
                "fajl": fajl,
                "poglavlje": self.naslovi.get(fajl, ""),
                "pasus": par,
                "isjecak": snip(tekst, 220),
                "detalj": detalj,
                "chk": "",
            }
        )


# ════════════════════════════════════════════════════════════════════
# Analiza jednog pasusa
# ════════════════════════════════════════════════════════════════════
class Kontekst:
    def __init__(self):
        self.langdetect = None
        try:
            import langdetect  # type: ignore

            langdetect.DetectorFactory.seed = 0
            self.langdetect = langdetect
        except Exception:
            pass
        self.imena = collections.Counter()
        self.imena_prvi: dict[str, tuple] = {}
        self.rijeci_mala = collections.Counter()
        self.rijeci_prva: dict[str, tuple] = {}
        self.pasusi_hash: dict[str, list] = collections.defaultdict(list)
        self.navodnik_stil = {}
        self.dijalog_start = {}
        self.sve_rijeci = collections.Counter()
        self.elip = collections.Counter()


def en_hr_udio(rijeci):
    low = [w.lower() for w in rijeci]
    n = max(1, len(low))
    en = sum(1 for w in low if w in EN_STOP_STRONG)
    en_all = sum(1 for w in low if w in EN_STOP)
    hr = sum(1 for w in low if w in HR_STOP)
    return en / n, en, hr / n, en_all / n


def _navod_nastavak(t, b, otv, zat):
    """Navod se nastavlja kroz susjedne pasuse (bez ponovnog otvaranja): nije greska."""
    def prvi(s):
        c = s.find("\u201d")
        o = s.find("\u201e")
        if c != -1 and (o == -1 or c < o):
            return "zat"
        return "otv" if o != -1 else ""
    prev = b.get("_prev") or ""
    nxt = b.get("_next") or ""
    if otv == zat + 1 and prvi(nxt) == "zat":
        return True
    if zat == otv + 1 and prvi(t) == "zat" and prev.count("\u201e") > prev.count("\u201d"):
        return True
    return False


def provjeri_pasus(N: Nalazi, K: Kontekst, fajl: str, i: int, b: dict):
    t = b["text"]
    tag = b["tag"]
    if not t:
        return
    naslov = tag in ("h1", "h2", "h3", "h4", "h5", "h6")
    low = t.lower()

    # ── LLM artefakti ──
    if RE_JSON.search(t):
        N.add("LEK-JSON", fajl, i, t)
    if RE_FENCE.search(t):
        N.add("LEK-FENCE", fajl, i, t)
    m = RE_META_HR.search(t) or RE_META_EN.search(t)
    if m:
        N.add("LEK-META", fajl, i, t, f"obrazac: {m.group(0)[:50]}")
    if RE_TAGTXT.search(t):
        N.add("LEK-TAG", fajl, i, t)
    if not naslov and RE_MARK.search(t):
        N.add("LEK-MARK", fajl, i, t)
    m = RE_PLACE.search(t)
    if m:
        N.add("LEK-PLACE", fajl, i, t, f"marker: {m.group(0)[:50]}")
    if RE_ESC.search(t):
        N.add("LEK-ESC", fajl, i, t)
    if RE_MOJI.search(t):
        N.add("LEK-MOJI", fajl, i, t)
    m = RE_SKRIPTA.findall(t)
    if m:
        N.add("LEK-SKRIPTA", fajl, i, t, f"{len(m)} znakova, npr. {''.join(m[:6])}")
    if low.strip() in NULL_SET:
        N.add("LEK-NULL", fajl, i, t)
    if RE_CTRL.search(t):
        N.add("LEK-CTRL", fajl, i, t)
    if RE_DBL_DROP.match(t):
        N.add("LEK-DROPCAP-DBL", fajl, i, t)

    if naslov:
        return

    rijeci = RE_WORD.findall(t)
    nw = len(rijeci)
    if nw == 0:
        return

    # ── ukupne riječi + imena ──
    for w in rijeci:
        K.sve_rijeci[w.lower()] += 1
        if w[0].islower() and len(w) >= 4 and "'" not in w and "’" not in w:
            K.rijeci_mala[w] += 1
            if w not in K.rijeci_prva:
                K.rijeci_prva[w] = (fajl, i)
    for m in RE_CAPWORD.finditer(t):
        pre = t[: m.start()].rstrip()
        if not pre or pre[-1] in ".!?…:—–-„“”\"«»(":
            continue
        ime = m.group(1)
        K.imena[ime] += 1
        K.imena_prvi.setdefault(ime, (fajl, i))

    # ── engleski / strani jezik ──
    if nw >= 6:
        sents = [s for s in RE_SENT.split(t) if s.strip()]
        flagged = 0
        for s in sents:
            sw = RE_WORD.findall(s)
            if len(sw) < 6:
                continue
            en_r, en_c, hr_r, en_all = en_hr_udio(sw)
            if en_r >= 0.22 and en_c >= 3 and hr_r < 0.2:
                flagged += 1
            elif 0.12 <= en_r < 0.22 and len(sw) >= 10 and K.langdetect is not None:
                try:
                    prob = {x.lang: x.prob for x in K.langdetect.detect_langs(s)}
                    if prob.get("en", 0) >= 0.9:
                        flagged += 1
                except Exception:
                    pass
        if flagged:
            cijeli = flagged >= max(1, len([s for s in sents if len(RE_WORD.findall(s)) >= 6]))
            N.add("JEZ-EN", fajl, i, t, ("cijeli pasus" if cijeli else f"{flagged} rečenica") + " neprevedeno")
        elif nw >= 10:
            en_r, en_c, hr_r, en_all = en_hr_udio(rijeci)
            velika = sum(1 for w in rijeci if w[0].isupper()) / nw
            if hr_r < 0.05 and en_r < 0.12 and velika < 0.5:
                N.add("JEZ-NEHR", fajl, i, t, f"hr udio {hr_r:.2f}")

    # ── rod ──
    m = RE_ROD_Z.search(t)
    if m and m.group(0).split()[-1].lower() not in ROD_ISKLJUCI:
        N.add("JEZ-ROD", fajl, i, t, m.group(0))
    m = RE_ROD_M.search(t)
    if m and m.group(0).split()[-1].lower() not in ROD_ISKLJUCI:
        N.add("JEZ-ROD", fajl, i, t, m.group(0))

    # ── duple riječi ──
    for m in RE_DUPW.finditer(t):
        if m.group(0).lower() not in DUPW_OK:
            N.add("JEZ-DUPW", fajl, i, t, m.group(0))
            break

    # ── siroče zarez ──
    mz = re.search(r",\s*,|,\s+\.", t)
    if mz:
        N.add("TIP-ZAREZ", fajl, i, t, f"„{mz.group(0)}“")

    # ── tipografija ──
    otv = t.count("„")
    zat = t.count("“") + t.count("”") + t.count('"')
    if otv:
        if otv != zat and not _navod_nastavak(t, b, otv, zat) and not (otv == zat + 1 and t.rstrip()[-1:] in ("…", "—", "–")):
            N.add("TIP-NAVOD", fajl, i, t, f"„={otv}, zatvarajućih={zat}")
    elif t.count('"') % 2 == 1:
        N.add("TIP-NAVOD", fajl, i, t, "neparan broj \"")
    if t.count("«") != t.count("»"):
        N.add("TIP-NAVOD", fajl, i, t, "« » neparni")
    st = K.navodnik_stil.setdefault(fajl, collections.Counter())
    st["hr"] += otv
    st["ascii"] += t.count('"') if not otv else 0
    st["en"] += len(re.findall(r"(?<![\w„])“(?=\w)", t))
    st["fr"] += t.count("«")

    prvi = t[0]
    ds = K.dijalog_start.setdefault(fajl, collections.Counter())
    if prvi == "—":
        ds["em"] += 1
    elif prvi == "–":
        ds["en"] += 1
    elif prvi == "-" and len(t) > 1 and (t[1] == " " or t[1].isalpha()):
        ds["hyph"] += 1
        N.add("TIP-CRTICA", fajl, i, t)
    elif prvi in "„\"«“":
        ds["quote"] += 1

    if RE_RAZ_PRIJE.search(t):
        N.add("TIP-RAZMAK", fajl, i, t, "razmak ispred interpunkcije")
    elif RE_RAZ_POSLIJE.search(t):
        N.add("TIP-RAZMAK", fajl, i, t, "nema razmaka iza interpunkcije")
    if "..." in t:
        K.elip["ascii"] += 1
    if "…" in t:
        K.elip["uni"] += 1

    # ── integritet ──
    if nw >= 600 or len(t) > 4500:
        N.add("INT-DUGPASUS", fajl, i, t, f"{nw} riječi")
    if len(t) > 300:
        ratio = len(zlib.compress(t.encode("utf-8"))) / max(1, len(t.encode("utf-8")))
        grams = collections.Counter(tuple(w.lower() for w in rijeci[j : j + 5]) for j in range(max(0, nw - 4)))
        top = grams.most_common(1)
        if ratio < 0.22 or (top and top[0][1] >= 4 and nw >= 25):
            N.add("INT-LOOP", fajl, i, t, f"zlib={ratio:.2f}, najčešći 5-gram x{top[0][1] if top else 0}")
    if nw >= 6:
        K.pasusi_hash[hashlib.md5(alnum(t).encode()).hexdigest()].append((fajl, i, nw, t))


def tekst_kraj_ok(t: str) -> bool:
    t = t.rstrip()
    return bool(t) and (t[-1] in TERM_END or t.endswith("..."))


# ════════════════════════════════════════════════════════════════════
# EPUB učitavanje
# ════════════════════════════════════════════════════════════════════
def ucitaj_epub(path: Path, N: Nalazi):
    z = zipfile.ZipFile(path)
    info = z.infolist()
    ok = bool(info) and info[0].filename == "mimetype" and info[0].compress_type == zipfile.ZIP_STORED
    try:
        ok = ok and z.read("mimetype").strip() == b"application/epub+zip"
    except KeyError:
        ok = False
    if not ok:
        N.add("STR-ZIP", "(zip)", 0, "mimetype", "mimetype nije prvi unos / nije STORED / pogrešan sadržaj")
    bad = z.testzip()
    if bad:
        N.add("STR-ZIP", "(zip)", 0, bad, "CRC greška u zip unosu")
    return z


def opf_parse(z: zipfile.ZipFile, N: Nalazi):
    cont = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = None
    for e in cont.iter():
        if lokalno(e.tag) == "rootfile":
            opf_path = e.get("full-path")
            break
    if not opf_path:
        raise RuntimeError("container.xml nema rootfile")
    opf = ET.fromstring(z.read(opf_path))
    base = posixpath.dirname(opf_path)
    manifest, spine, toc_id = {}, [], None
    for e in opf.iter():
        n = lokalno(e.tag)
        if n == "item":
            manifest[e.get("id")] = {
                "href": posixpath.normpath(posixpath.join(base, urllib.parse.unquote(e.get("href", "")))),
                "type": e.get("media-type", ""),
                "props": e.get("properties", ""),
            }
        elif n == "itemref":
            spine.append(e.get("idref"))
        elif n == "spine":
            toc_id = e.get("toc")
    return opf_path, manifest, spine, toc_id


# ════════════════════════════════════════════════════════════════════
# Glavni audit
# ════════════════════════════════════════════════════════════════════
def ucitaj_projekt(projekt: str | None, bez_kalkova: bool):
    ekav, kalk = [], []
    info = "projektni kalkovi: nisu učitani"
    if not projekt or not Path(projekt).is_dir() or bez_kalkova:
        return ekav, kalk, info
    sys.path.insert(0, projekt)
    try:
        import logging

        logging.disable(logging.CRITICAL)
        from core.kalkovi import SVE_LISTE, _EKAVIZMI  # type: ignore

        logging.disable(logging.NOTSET)
        ek_set = {str(e[0]) for e in _EKAVIZMI if isinstance(e, (tuple, list)) and e}

        def komp(lista):
            out = []
            for e in lista:
                if not isinstance(e, (tuple, list)) or not e:
                    continue
                try:
                    out.append((re.compile(str(e[0]), re.I), str(e[1]) if len(e) > 1 else "", str(e[0])))
                except re.error:
                    continue
            return out

        ekav = komp([e for e in SVE_LISTE if str(e[0]) in ek_set])
        kalk = komp([e for e in SVE_LISTE if str(e[0]) not in ek_set])
        info = f"projektni kalkovi: {len(ekav)} ekavizama + {len(kalk)} ostalih pravila"
    except Exception as e:  # noqa: BLE001
        info = f"projektni kalkovi: import nije uspio ({type(e).__name__}: {e})"
    return ekav, kalk, info


def traži_regexe(pravila, texts, maks_po_pravilu=6):
    """Vraća listu (pravilo_idx, pasus_idx, match, zamjena) — preko cijelog poglavlja odjednom."""
    joined = "\n".join(texts)
    offs, p = [], 0
    for t in texts:
        offs.append(p)
        p += len(t) + 1
    out = []
    for pi, (rx, zam, src) in enumerate(pravila):
        c = 0
        for m in rx.finditer(joined):
            idx = bisect.bisect_right(offs, m.start()) - 1
            out.append((pi, idx, m.group(0), zam))
            c += 1
            if c >= maks_po_pravilu:
                break
    return out


def audit(args) -> dict:
    t0 = time.time()
    N = Nalazi()
    K = Kontekst()
    path = Path(args.epub)
    ekav_pr, kalk_pr, info_proj = ucitaj_projekt(args.projekt, args.bez_kalkova or args.brzo)
    if not ekav_pr:
        ekav_pr = [(re.compile(EKAV_FALLBACK[0], re.I), "", "fallback")]
    print(f"[audit] {path.name}  |  {info_proj}", flush=True)

    z = ucitaj_epub(path, N)
    opf_path, manifest, spine, toc_id = opf_parse(z, N)
    names = set(z.namelist())

    # manifest / spine provjere
    for iid, it in manifest.items():
        if it["href"] not in names:
            N.add("STR-OPF", it["href"], 0, it["href"], f"manifest id={iid} pokazuje na nepostojeći fajl")
    for idref in spine:
        if idref not in manifest:
            N.add("STR-OPF", "(spine)", 0, str(idref), "spine idref nije u manifestu")
    man_hrefs = {it["href"] for it in manifest.values()}
    for n in sorted(names):
        if n.lower().endswith((".xhtml", ".html", ".htm")) and n not in man_hrefs:
            N.add("STR-ORPHAN", n, 0, n)

    docs = [manifest[i]["href"] for i in spine if i in manifest and manifest[i]["href"] in names]
    docs = [d for d in docs if d.lower().endswith((".xhtml", ".html", ".htm"))]
    print(f"[audit] spine: {len(docs)} dokumenata", flush=True)

    recs = {}
    sizes = []
    for k, d in enumerate(docs, 1):
        if k % 50 == 0:
            print(f"[audit] parsiranje {k}/{len(docs)}", flush=True)
        try:
            raw = z.read(d)
            sizes.append(len(raw))
            ents, err = xml_provjera(raw)
            if ents:
                N.add("STR-ENT", d, 0, ", ".join(ents[:8]), f"{len(ents)} različitih entiteta")
            if err:
                N.add("STR-XML", d, 0, err)
            p = ChParser()
            p.feed(raw.decode("utf-8", "replace"))
            p.close()
            recs[d] = p
            N.naslovi[d] = next((b["text"] for b in p.blocks if b["tag"] == "h1"), "") or p.title.strip()
        except Exception as e:  # noqa: BLE001
            N.add("STR-FAIL", d, 0, d, f"{type(e).__name__}: {e}")

    # ── strukturne provjere nad svakim dokumentom ──
    nav_hrefs = {it["href"] for it in manifest.values() if "nav" in it["props"].split()}
    ncx_hrefs = {it["href"] for it in manifest.values() if it["type"] == "application/x-dtbncx+xml"}
    ids_po_fajlu = {d: set(p.ids) for d, p in recs.items()}
    for d, p in recs.items():
        dup = [i for i, c in collections.Counter(p.ids).items() if c > 1]
        if dup:
            N.add("STR-ID", d, 0, ", ".join(dup[:6]), f"{len(dup)} duplih id-ova")
        for s in p.srcs:
            if s.startswith("data:") or not s or re.match(r"^[a-z]+:", s):
                continue
            tgt = posixpath.normpath(posixpath.join(posixpath.dirname(d), urllib.parse.unquote(s.split("#")[0])))
            if tgt not in names:
                N.add("STR-IMG", d, 0, s)
        for h in p.hrefs:
            if re.match(r"^[a-z]+:", h) or not h:
                continue
            fr = h.split("#", 1)
            tgt = d if not fr[0] else posixpath.normpath(posixpath.join(posixpath.dirname(d), urllib.parse.unquote(fr[0])))
            if tgt not in names:
                N.add("STR-LINK", d, 0, h, "fajl ne postoji")
            elif len(fr) > 1 and fr[1] and tgt in ids_po_fajlu and fr[1] not in ids_po_fajlu[tgt]:
                N.add("STR-LINK", d, 0, h, "sidro ne postoji")

    def provjeri_cilj(izvor, src):
        fr = src.split("#", 1)
        tgt = posixpath.normpath(posixpath.join(posixpath.dirname(izvor), urllib.parse.unquote(fr[0])))
        if tgt not in names:
            N.add("STR-NCX", izvor, 0, src, "cilj ne postoji")
        elif len(fr) > 1 and fr[1] and tgt in ids_po_fajlu and fr[1] not in ids_po_fajlu[tgt]:
            N.add("STR-NCX", izvor, 0, src, "sidro ne postoji")

    for ncx in ncx_hrefs & names:
        try:
            tree = ET.fromstring(z.read(ncx))
            for e in tree.iter():
                if lokalno(e.tag) == "content" and e.get("src"):
                    provjeri_cilj(ncx, e.get("src"))
        except Exception as e:  # noqa: BLE001
            N.add("STR-NCX", ncx, 0, ncx, f"NCX se ne parsira: {e}")
    for nav in nav_hrefs & names:
        try:
            p = ChParser()
            p.feed(z.read(nav).decode("utf-8", "replace"))
            p.close()
            for h in p.hrefs:
                if not re.match(r"^[a-z]+:", h):
                    provjeri_cilj(nav, h)
        except Exception as e:  # noqa: BLE001
            N.add("STR-NCX", nav, 0, nav, f"nav se ne parsira: {e}")

    # ── sadržajna poglavlja ──
    poglavlja = [d for d in docs if d in recs and not NAV_RE.match(posixpath.basename(d))]
    reci_po_pogl = {}
    pasusa_po_pogl = {}
    diak_po_pogl = {}
    tekst_po_pogl = {}
    hash_pogl = collections.defaultdict(list)
    sig = {}

    print(f"[audit] sadržajnih poglavlja: {len(poglavlja)}", flush=True)
    kalk_stat = collections.Counter()
    kalk_prvi = {}
    kalk_zam = {}
    kalk_gust = {}
    uzorak = max(1, args.kalkovi_uzorak)
    for k, d in enumerate(poglavlja, 1):
        if k % 10 == 0 or k == len(poglavlja):
            print(f"[audit] analiza {k}/{len(poglavlja)}  ({time.time() - t0:.0f}s)", flush=True)
        p = recs[d]
        bl = p.blocks
        tekstovi = [b["text"] for b in bl]
        body = [b for b in bl if b["tag"] not in ("h1", "h2", "h3", "h4", "h5", "h6")]
        cijeli = " ".join(tekstovi)
        nw = len(RE_WORD.findall(cijeli))
        reci_po_pogl[d] = nw
        pasusa_po_pogl[d] = len(body)
        tekst_po_pogl[d] = cijeli
        slova = [c for c in cijeli if c.isalpha()]
        diak_po_pogl[d] = (sum(1 for c in slova if c in "čćšžđČĆŠŽĐ") / len(slova)) if slova else 0.0

        if nw < 40:
            N.add("STR-EMPTY", d, 0, cijeli or "(prazno)", f"{nw} riječi")
        else:
            hash_pogl[hashlib.md5(alnum(cijeli).encode()).hexdigest()].append(d)

        for i, b in enumerate(bl):
            b["_prev"] = bl[i - 1]["text"] if i > 0 else ""
            b["_next"] = bl[i + 1]["text"] if i + 1 < len(bl) else ""
            provjeri_pasus(N, K, d, i, b)

        # struktura stila
        if p.h1 != 1:
            N.add("STIL-H1", d, 0, N.naslovi.get(d, ""), f"h1={p.h1}")
        if p.dropcaps > 1:
            N.add("STIL-DROPCAP-DUP", d, 0, N.naslovi.get(d, ""), f"{p.dropcaps} dropcapa")
        if p.vijenac > 1:
            N.add("STIL-VIJENAC-DUP", d, 0, N.naslovi.get(d, ""), f"{p.vijenac} vijenaca")
        sig[d] = (p.naslov_h1 >= 1, p.vijenac >= 1, p.dropcaps >= 1)
        ocekivano_style = p.dropcaps + p.hidden_spans
        if p.style_attrs - ocekivano_style > 0:
            N.add("STIL-STYLE", d, 0, N.naslovi.get(d, ""), f"{p.style_attrs - ocekivano_style} suvišnih style= atributa")

        # krajevi / prekidi rečenica
        if body:
            zadnji = body[-1]["text"]
            if len(RE_WORD.findall(zadnji)) >= 4 and not tekst_kraj_ok(zadnji):
                N.add("INT-TRUNC", d, len(bl) - 1, zadnji, "zadnji pasus poglavlja nema završnu interpunkciju")
        for j in range(len(bl) - 1):
            a, bb = bl[j], bl[j + 1]
            if a["tag"] not in ("p", "loose", "li", "blockquote") or bb["tag"] not in ("p", "loose", "li", "blockquote"):
                continue
            ta, tb = a["text"], bb["text"]
            wa = RE_WORD.findall(ta)
            if len(wa) >= 5 and not tekst_kraj_ok(ta):
                if tb and tb[0].islower():
                    N.add("INT-SPLIT", d, j, ta + " ‖ " + tb, "pasus bez završetka + sljedeći počinje malim slovom")
                elif ta.rstrip().endswith(",") or (wa and wa[-1].lower() in NEZAV_RIJECI):
                    N.add("INT-NEZAV", d, j, ta)
            elif tb and tb[0].islower() and len(RE_WORD.findall(tb)) >= 5 and tekst_kraj_ok(ta):
                N.add("INT-MALO", d, j + 1, tb)
            # preklapanje granice: početak sljedećeg se nalazi na kraju prethodnog
            if len(tb) > 40 and len(ta) > 40:
                kljuc = alnum(tb)[:45]
                if len(kljuc) >= 35 and kljuc in alnum(ta)[-400:]:
                    N.add("INT-DUPS", d, j, ta[-160:] + " ‖ " + tb[:120], "početak sljedećeg pasusa već je na kraju prethodnog")

        # ekavizmi + kalkovi (regex po cijelom poglavlju)
        texts_body = [b["text"] for b in bl]
        for pi, idx, mt, zam in traži_regexe(ekav_pr, texts_body, 8):
            N.add("JEZ-EKAV", d, idx, texts_body[idx], f"'{mt}'" + (f" → {zam}" if zam else ""))
        if kalk_pr and (k % uzorak == 0):
            hits = 0
            for pi, idx, mt, zam in traži_regexe(kalk_pr, texts_body, 4):
                hits += 1
                src = kalk_pr[pi][2]
                kalk_stat[src] += 1
                kalk_prvi.setdefault(src, (d, idx, mt))
                kalk_zam[src] = zam
                if kalk_stat[src] <= 3:
                    N.add("JEZ-KALK", d, idx, texts_body[idx], f"'{mt}' → {zam}")
                else:
                    N.broj["JEZ-KALK"] += 1
            kalk_gust[d] = hits / max(1, nw) * 1000

    # ── dupli poglavlja ──
    for h, lst in hash_pogl.items():
        if len(lst) > 1:
            N.add("STR-DUPFILE", lst[1], 0, N.naslovi.get(lst[1], ""), "identično kao: " + ", ".join(lst[:1]))

    # ── numeracija POGLAVLJE N ──
    brojevi = []
    for d in poglavlja:
        m = re.match(r"^\s*POGLAVLJE\s+(\d+)\s*$", N.naslovi.get(d, ""), re.I)
        if m:
            brojevi.append((int(m.group(1)), d))
    for (a, da), (b, db) in zip(brojevi, brojevi[1:]):
        if b == a:
            N.add("STR-BROJ", db, 0, N.naslovi.get(db, ""), f"ponovljen broj {b}")
        elif b != a + 1 and b != 1:
            N.add("STR-BROJ", db, 0, N.naslovi.get(db, ""), f"skok {a} → {b}")

    # ── odstupanja po dužini i dijakriticima ──
    vals = [v for v in reci_po_pogl.values() if v >= 40]
    if len(vals) >= 6:
        med = statistics.median(vals)
        for d, v in reci_po_pogl.items():
            if v >= 40 and v < 0.12 * med and v < 400:
                N.add("INT-DUZINA", d, 0, N.naslovi.get(d, ""), f"{v} riječi (medijan {med:.0f})")
            if pasusa_po_pogl.get(d, 0) == 1 and v > 500:
                N.add("INT-DUGPASUS", d, 0, N.naslovi.get(d, ""), f"cijelo poglavlje u 1 pasusu ({v} riječi)")
    dv = [v for d, v in diak_po_pogl.items() if reci_po_pogl[d] >= 500]
    if len(dv) >= 6:
        dmed = statistics.median(dv)
        for d, v in diak_po_pogl.items():
            if reci_po_pogl[d] >= 500 and dmed > 0.01 and v < 0.4 * dmed:
                N.add("JEZ-DIAK", d, 0, N.naslovi.get(d, ""), f"{v*100:.2f}% dijakritika (medijan {dmed*100:.2f}%)")

    # ── stilski potpis ──
    if sig:
        veci = collections.Counter(sig.values()).most_common(1)[0][0]
        for d, s in sig.items():
            if s != veci:
                N.add("STIL-SIG", d, 0, N.naslovi.get(d, ""), f"naslov/vijenac/dropcap={s}, većina={veci}")
    klase = collections.Counter()
    kl_prva = {}
    for d in poglavlja:
        for c, n in recs[d].classes.items():
            if not c.startswith("booklyfi"):
                klase[c] += n
                kl_prva.setdefault(c, d)
    for c, n in klase.most_common(40):
        N.add("STIL-KLASA", kl_prva[c], 0, c, f"{n} pojavljivanja u knjizi")

    # ── stil navodnika / dijaloga po poglavlju ──
    ukupno = collections.Counter()
    for st in K.navodnik_stil.values():
        ukupno.update(st)
    if sum(ukupno.values()) > 0:
        dom = ukupno.most_common(1)[0][0]
        for d, st in K.navodnik_stil.items():
            tot = sum(st.values())
            if tot >= 10 and st.most_common(1)[0][0] != dom:
                N.add("TIP-STIL", d, 0, N.naslovi.get(d, ""), f"poglavlje: {dict(st)}, knjiga dominantno '{dom}'")
    dtot = collections.Counter()
    for ds in K.dijalog_start.values():
        dtot.update(ds)
    if dtot:
        ddom = dtot.most_common(1)[0][0]
        for d, ds in K.dijalog_start.items():
            for tip, c in ds.items():
                if tip in ("en", "hyph") and ddom == "em" and c >= 3:
                    N.add("TIP-CRTICA", d, 0, N.naslovi.get(d, ""), f"{c} dijaloga počinje '{tip}' umjesto em-crtice")
    if K.elip["ascii"] and K.elip["uni"] and K.elip["ascii"] < K.elip["uni"]:
        N.add("TIP-ELIP", "(knjiga)", 0, "...", f"'...' {K.elip['ascii']}x vs '…' {K.elip['uni']}x")

    # ── duplikati pasusa ──
    for h, lst in K.pasusi_hash.items():
        if len(lst) < 2:
            continue
        for (f1, i1, w1, t1), (f2, i2, w2, t2) in zip(lst, lst[1:]):
            if w1 < 6:
                continue
            blizu = f1 == f2 and abs(i2 - i1) <= 3
            if blizu and w1 >= 8:
                N.add("INT-DUP", f2, i2, t2, f"ponavlja pasus {i1} u istom poglavlju ({w1} riječi)")
            elif w1 >= 15:
                N.add("INT-DUP", f2, i2, t2, f"identično kao {f1}#{i1} ({w1} riječi)")

    # ── imena ──
    zajednicka = [(n, c) for n, c in K.imena.items() if c >= 4]
    po_foldu = collections.defaultdict(list)
    for n, c in zajednicka:
        po_foldu[fold(n).lower()].append((n, c))
    for fk, lst in po_foldu.items():
        if len(lst) > 1 and len({x[0] for x in lst}) > 1:
            lst.sort(key=lambda x: -x[1])
            rj = lst[-1][0]
            f, i = K.imena_prvi[rj]
            N.add("IME-DIAK", f, i, rj, ", ".join(f"{n}({c})" for n, c in lst))
    kante = collections.defaultdict(list)
    for n, c in zajednicka:
        kante[(fold(n)[0].lower(), len(n))].append((n, c))
    prijavljeno = set()
    for (fc, ln), lst in kante.items():
        for dl in (0, 1):
            for a in lst:
                for b in kante.get((fc, ln + dl), []):
                    if a[0] >= b[0] and dl == 0:
                        continue
                    fa, fb = fold(a[0]).lower(), fold(b[0]).lower()
                    if fa == fb:
                        continue
                    zp = len(os.path.commonprefix([fa, fb]))
                    if zp >= max(3, min(len(fa), len(fb)) - 1):
                        continue
                    if levenshtein(fa, fb, 2) <= 2 and min(len(fa), len(fb)) >= 4:
                        kljuc = tuple(sorted((a[0], b[0])))
                        if kljuc in prijavljeno:
                            continue
                        prijavljeno.add(kljuc)
                        rj = a if a[1] < b[1] else b
                        f, i = K.imena_prvi[rj[0]]
                        N.add("IME-VAR", f, i, rj[0], f"{a[0]}({a[1]}) ~ {b[0]}({b[1]})")
                        if len(prijavljeno) > 120:
                            break

    # ── izvor (opciono) ──
    izvor_info = ""
    if args.izvor:
        izvor_info = usporedi_s_izvorom(args.izvor, N, K, poglavlja, reci_po_pogl, tekst_po_pogl)

    # ── glosar (opciono) ──
    if args.glosar:
        provjeri_glosar(args.glosar, N, K, tekst_po_pogl)

    # ── vanjski alati ──
    alati = []
    if not args.brzo and not args.bez_hunspell:
        alati.append(pokreni_hunspell(N, K))
    if not args.brzo and not args.bez_epubcheck:
        alati.append(pokreni_epubcheck(path, N))
    alati.append("langdetect: " + ("da" if K.langdetect else "ne"))

    # ── porijeklo u .chk (opciono) ──
    if args.chk:
        chk_porijeklo(args.chk, N)

    return {
        "N": N,
        "K": K,
        "vrijeme": time.time() - t0,
        "poglavlja": poglavlja,
        "reci": reci_po_pogl,
        "pasusa": pasusa_po_pogl,
        "info_proj": info_proj,
        "kalk_stat": kalk_stat,
        "kalk_prvi": kalk_prvi,
        "kalk_zam": kalk_zam,
        "kalk_gust": kalk_gust,
        "alati": alati,
        "izvor_info": izvor_info,
        "navodnici": ukupno,
        "dijalog": dtot,
        "docs": len(docs),
    }


# ════════════════════════════════════════════════════════════════════
# Opcione faze
# ════════════════════════════════════════════════════════════════════
def usporedi_s_izvorom(izvor, N, K, poglavlja, reci_po_pogl, tekst_po_pogl):
    try:
        z = zipfile.ZipFile(izvor)
        _, manifest, spine, _ = opf_parse(z, N)
        names = set(z.namelist())
        docs = [manifest[i]["href"] for i in spine if i in manifest and manifest[i]["href"] in names]
        sw, imena = [], collections.Counter()
        for d in docs:
            if not d.lower().endswith((".xhtml", ".html", ".htm")) or NAV_RE.match(posixpath.basename(d)):
                continue
            p = ChParser()
            p.feed(z.read(d).decode("utf-8", "replace"))
            p.close()
            txt = " ".join(b["text"] for b in p.blocks)
            n = len(RE_WORD.findall(txt))
            if n >= 150:
                sw.append((d, n))
            for b in p.blocks:
                t = b["text"]
                for m in RE_CAPWORD.finditer(t):
                    pre = t[: m.start()].rstrip()
                    if pre and pre[-1] not in ".!?…:—–-„“”\"«»(":
                        imena[m.group(1)] += 1
    except Exception as e:  # noqa: BLE001
        return f"izvor: nije učitan ({type(e).__name__}: {e})"
    ciljne = [(d, reci_po_pogl[d]) for d in poglavlja if reci_po_pogl[d] >= 150]
    ukupno_s, ukupno_c = sum(n for _, n in sw), sum(n for _, n in ciljne)
    info = f"izvor: {len(sw)} poglavlja / {ukupno_s} riječi; prijevod: {len(ciljne)} / {ukupno_c} riječi; omjer izvor/prijevod = {ukupno_s / max(1, ukupno_c):.3f}"
    if len(sw) == len(ciljne):
        for (ds, ns), (dc, nc) in zip(sw, ciljne):
            r = ns / max(1, nc)
            if r < 0.75 or r > 1.45:
                N.add("INT-RATIO", dc, 0, N.naslovi.get(dc, ""), f"izvor {ns} / prijevod {nc} riječi = {r:.2f} ({posixpath.basename(ds)})")
    else:
        info += "  (različit broj poglavlja — po-poglavlju poređenje preskočeno)"
    ciljni_prefiksi = {fold(w)[:5] for w in K.sve_rijeci}
    for ime, c in imena.most_common(400):
        if c < 5:
            break
        if fold(ime.lower())[:5] not in ciljni_prefiksi:
            N.add("INT-IMENA-IZV", "(knjiga)", 0, ime, f"{c}x u izvorniku, nema u prijevodu (preveden nadimak ili izostavljeno)")
    return info


def provjeri_glosar(putanja, N, K, tekst_po_pogl):
    try:
        data = json.load(open(putanja, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[glosar] nije učitan: {e}")
        return
    parovi = []

    def walk(o):
        if isinstance(o, dict):
            if o and all(isinstance(k, str) and isinstance(v, str) for k, v in o.items()):
                parovi.extend(o.items())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, str) for x in v):
                    parovi.append((v[0], v[1]))
                else:
                    walk(v)

    walk(data)
    cijeli_low = None
    for src, tgt in parovi[:5000]:
        if len(src) < 4 or len(src) > 60 or src.strip().lower() == tgt.strip().lower():
            continue
        if " " not in src:
            c = K.sve_rijeci.get(src.lower(), 0)
        else:
            if cijeli_low is None:
                cijeli_low = "\n".join(tekst_po_pogl.values()).lower()
            c = cijeli_low.count(src.lower())
        if c > 0:
            N.add("INT-GLOSAR", "(knjiga)", 0, src, f"'{src}' (→ '{tgt}') još se pojavljuje {c}x")


def pokreni_hunspell(N, K):
    exe = shutil.which("hunspell")
    if not exe:
        return "hunspell: nije instaliran (apt install hunspell hunspell-hr)"
    rijeci = [w for w, c in K.rijeci_mala.items() if "’" not in w]
    try:
        pr = subprocess.run([exe, "-d", "hr_HR", "-l"], input="\n".join(rijeci), capture_output=True, text=True, timeout=900)
    except Exception as e:  # noqa: BLE001
        return f"hunspell: greška ({e})"
    if pr.returncode != 0 or "Can't open" in pr.stderr:
        return "hunspell: rječnik hr_HR nije dostupan (apt install hunspell-hr)"
    nepoznate = [w for w in pr.stdout.split("\n") if w.strip()]
    nepoznate.sort(key=lambda w: -K.rijeci_mala.get(w, 0))
    for w in nepoznate[:400]:
        f, i = K.rijeci_prva.get(w, ("(knjiga)", 0))
        N.add("JEZ-PRAVOPIS", f, i, w, f"{K.rijeci_mala.get(w, 0)}x u knjizi")
    return f"hunspell: {len(nepoznate)} nepoznatih oblika od {len(rijeci)}"


def pokreni_epubcheck(path, N):
    exe = shutil.which("epubcheck")
    if not exe:
        return "epubcheck: nije instaliran (apt install epubcheck default-jre-headless)"
    try:
        pr = subprocess.run([exe, str(path)], capture_output=True, text=True, timeout=1800)
    except Exception as e:  # noqa: BLE001
        return f"epubcheck: greška ({e})"
    rx = re.compile(r"^(FATAL|ERROR|WARNING)\(([A-Z]+-\d+)\):\s*(.*?)\((\d+),(\d+)\):\s*(.*)$")
    n = 0
    for ln in (pr.stdout + "\n" + pr.stderr).splitlines():
        m = rx.match(ln.strip())
        if m:
            n += 1
            N.add("STR-EPUBCHECK", m.group(3) or "(epub)", int(m.group(4)), m.group(6), f"{m.group(1)} {m.group(2)}")
    return f"epubcheck: {n} poruka"


def chk_porijeklo(chk_dir, N):
    d = Path(chk_dir)
    fajlovi = sorted(d.glob("*.chk")) if d.is_dir() else []
    if not fajlovi:
        print(f"[chk] nema .chk fajlova u {chk_dir}")
        return
    baza = []
    for f in fajlovi:
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        meta = ""
        try:
            j = json.loads(raw)
            if isinstance(j, dict):
                meta = ", ".join(f"{k}={j[k]}" for k in ("provider", "prevodilac_provider", "model", "score", "uloga") if k in j)
        except Exception:
            pass
        baza.append((f.name, alnum(re.sub(r"<[^>]+>", " ", raw)), meta))
    cilj = [x for x in N.lista if TEZINA[x["ozbiljnost"]] >= 4 and x["isjecak"]][:400]
    for x in cilj:
        kljuc = alnum(x["isjecak"].split("‖")[0])[:40]
        if len(kljuc) < 25:
            continue
        for ime, txt, meta in baza:
            if kljuc in txt:
                x["chk"] = ime + (f" [{meta}]" if meta else "")
                break


# ════════════════════════════════════════════════════════════════════
# Izvještaj
# ════════════════════════════════════════════════════════════════════
def napisi_izvjestaj(rez, out: Path, epub: Path):
    N: Nalazi = rez["N"]
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "nalazi.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["kat", "ozbiljnost", "fajl", "poglavlje", "pasus", "isjecak", "detalj", "chk"])
        for x in N.lista:
            w.writerow([x["kat"], x["ozbiljnost"], x["fajl"], x["poglavlje"], x["pasus"], x["isjecak"], x["detalj"], x["chk"]])
    with open(out / "nalazi.jsonl", "w", encoding="utf-8") as f:
        for x in N.lista:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    L = []
    ukupno_reci = sum(rez["reci"].values())
    L.append(f"# Audit: {epub.name}\n")
    L.append(f"- Poglavlja: **{len(rez['poglavlja'])}** (dokumenata u spine: {rez['docs']}), riječi: **{ukupno_reci:,}**")
    L.append(f"- Trajanje: {rez['vrijeme']:.0f}s  |  {rez['info_proj']}")
    for a in rez["alati"]:
        L.append(f"- {a}")
    if rez["izvor_info"]:
        L.append(f"- {rez['izvor_info']}")
    L.append(f"- Navodnici (ukupno): {dict(rez['navodnici'])}  |  početci dijaloga: {dict(rez['dijalog'])}")
    L.append(f"- Ukupno nalaza: **{sum(N.broj.values()):,}** (sačuvano u CSV: {len(N.lista):,})\n")

    L.append("## 1. Kategorije (po ozbiljnosti)\n")
    L.append("| Šifra | Ozbiljnost | Broj | Poglavlja | Opis | Gdje u kodu |")
    L.append("|---|---|---:|---:|---|---|")
    redovi = []
    for kat, c in N.broj.items():
        sev, opis, kod = KAT[kat]
        pogl = len({f for f, cc in N.ch_kat.items() if cc.get(kat)})
        redovi.append((REDOSLIJED.index(sev), -c, kat, sev, c, pogl, opis, kod))
    for _, _, kat, sev, c, pogl, opis, kod in sorted(redovi):
        L.append(f"| {kat} | {sev} | {c:,} | {pogl} | {opis} | {kod} |")

    L.append("\n## 2. Najproblematičnija poglavlja\n")
    L.append("| # | Fajl | Naslov | Skor | Najčešće kategorije |")
    L.append("|---:|---|---|---:|---|")
    for k, (f, sc) in enumerate(N.ch_score.most_common(25), 1):
        top = ", ".join(f"{kk}×{cc}" for kk, cc in N.ch_kat[f].most_common(4))
        L.append(f"| {k} | {f} | {snip(N.naslovi.get(f, ''), 40)} | {sc:.0f} | {top} |")

    if rez["kalk_stat"]:
        L.append("\n## 3. Kalkovi koji su preživjeli lekturu (top 30 pravila)\n")
        L.append("| Pravilo | Broj | Prvi primjer | Zamjena |")
        L.append("|---|---:|---|---|")
        for src, c in rez["kalk_stat"].most_common(30):
            d, i, mt = rez["kalk_prvi"][src]
            L.append(f"| `{snip(src, 50)}` | {c} | {posixpath.basename(d)}#{i}: {snip(mt, 40)} | {snip(rez['kalk_zam'].get(src, ''), 40)} |")

    L.append("\n## 4. Primjeri po kategoriji (do 12 po kategoriji, najteže prvo)\n")
    po_kat = collections.defaultdict(list)
    for x in N.lista:
        po_kat[x["kat"]].append(x)
    for kat in sorted(po_kat, key=lambda k: (REDOSLIJED.index(KAT[k][0]), -N.broj[k])):
        sev, opis, kod = KAT[kat]
        L.append(f"\n### {kat} — {opis}  [{sev}, ukupno {N.broj[kat]:,}]")
        L.append(f"_Uzrok tražiti u:_ {kod}\n")
        for x in po_kat[kat][:12]:
            ch = f" — chk: {x['chk']}" if x["chk"] else ""
            det = f" ({x['detalj']})" if x["detalj"] else ""
            L.append(f"- `{posixpath.basename(x['fajl'])}` §{x['pasus']} _{snip(x['poglavlje'], 30)}_: {x['isjecak']}{det}{ch}")

    L.append("\n## 5. Preporučeni redoslijed ispravljanja\n")
    prio = sorted(
        ((TEZINA[KAT[k][0]] * min(c, 200), k, c) for k, c in N.broj.items() if KAT[k][0] in ("KRITICNO", "VISOKO")),
        reverse=True,
    )
    for k, (_, kat, c) in enumerate(prio[:10], 1):
        L.append(f"{k}. **{kat}** ({c:,}×) — {KAT[kat][1]} → {KAT[kat][2]}")
    (out / "izvjestaj.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Sveobuhvatni audit gotovog EPUB-a")
    ap.add_argument("epub")
    ap.add_argument("--izvor", help="izvorni (engleski) EPUB za poređenje")
    ap.add_argument("--glosar", help="JSON glosar (par izvor→prijevod)")
    ap.add_argument("--chk", help="folder s .chk fajlovima (_skr_...) za porijeklo nalaza")
    ap.add_argument("--projekt", default="/root/skriptorij", help="korijen projekta (za kalkove/ekavizme)")
    ap.add_argument("--out", help="izlazni folder")
    ap.add_argument("--brzo", action="store_true", help="bez kalkova, hunspella i epubchecka")
    ap.add_argument("--bez-kalkova", action="store_true")
    ap.add_argument("--bez-hunspell", action="store_true")
    ap.add_argument("--bez-epubcheck", action="store_true")
    ap.add_argument("--kalkovi-uzorak", type=int, default=1, help="kalkovi samo na svakom N-tom poglavlju (brže)")
    ap.add_argument("--gate", action="store_true", help="završna kapija: exit 1 ako postoje nalazi iz GATE_KAT")
    args = ap.parse_args()

    epub = Path(args.epub)
    if not epub.exists():
        print(f"EPUB ne postoji: {epub}")
        return 2
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = Path(args.out) if args.out else Path("/storage/emulated/0/Download/booklyfi_audit") / f"{epub.stem}_{stamp}"
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        out = Path.cwd() / f"audit_{epub.stem}_{stamp}"
        out.mkdir(parents=True, exist_ok=True)

    rez = audit(args)
    napisi_izvjestaj(rez, out, epub)
    N = rez["N"]
    print("\n════ SAŽETAK ════")
    for sev in REDOSLIJED:
        c = sum(n for k, n in N.broj.items() if KAT[k][0] == sev)
        print(f"{sev:9s} {c:>8,}")
    print(f"\nIzvještaj: {out / 'izvjestaj.md'}")
    print(f"CSV:       {out / 'nalazi.csv'}")
    if args.gate:
        GATE_KAT = ("TIP-NAVOD", "TIP-ZAREZ", "INT-DUP", "INT-DUPS", "JEZ-EN", "INT-GLOSAR", "INT-RATIO")
        pad = {k: N.broj[k] for k in GATE_KAT if N.broj.get(k)}
        print("\n════ KAPIJA ════")
        for k, n in pad.items():
            print(f"{k:12s} {n:>6,}")
        print("KAPIJA: " + ("PAO (exit 1)" if pad else "ČISTO (exit 0)"))
        return 1 if pad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
