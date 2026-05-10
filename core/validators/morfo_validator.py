"""
core/validators/morfo_validator.py
────────────────────────────────────
AI morfološki validator — zaseban prolaz NAKON prijevoda, PRIJE .chk upisa.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from core.kalkovi.morfologija_blacklist import (
        BLACKLIST_PROMPT_BLOK,
        HALUCIRANI_OBLICI,
        skeniraj_halucinacije,
    )
    _BLACKLIST_DOSTUPAN = True
except ImportError:
    _BLACKLIST_DOSTUPAN = False
    BLACKLIST_PROMPT_BLOK = ""
    HALUCIRANI_OBLICI = {}
    def skeniraj_halucinacije(tekst): return []

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash"
MAX_CHUNK_ZNAKOVA = 4000
MIN_ZNAKOVA_ZA_AI = 50
AUDIT_LOG_PATH = Path("logs/morfo_audit.jsonl")
MAX_RETRIES = 2
RETRY_DELAY = 3.0


@dataclass
class ValidacijaRezultat:
    originalni_tekst: str
    validirani_tekst: str
    izmjene: list[dict] = field(default_factory=list)
    pre_screening_nalazi: list[dict] = field(default_factory=list)
    ai_korissten: bool = False
    greska: Optional[str] = None
    trajanje_ms: int = 0

    @property
    def promijenjen(self) -> bool:
        return self.originalni_tekst != self.validirani_tekst

    @property
    def broj_izmjena(self) -> int:
        return len(self.izmjene)


def _system_prompt() -> str:
    return f"""Ti si stručni lektor za bosanski/hrvatski jezik, specijaliziran isključivo za morfologiju glagola.

TVOJ JEDINI ZADATAK: Pronađi i ispravi nepostojeće / halucirane glagolske oblike u tekstu.

PRAVILA:
1. Ispravljaj SAMO morfološke greške glagola — NE mijenjaj stil, leksik, sintaksu, interpunkciju.
2. NE dodavaj, NE brišeš rečenice. Broj rečenica mora ostati isti.
3. NE "popravljaj" ispravne oblike samo zato što zvuče neobično.
4. Ako nisi 100% siguran da je oblik pogrešan — OSTAVI ga.
5. Čuvaj sve dijalektalne i stilski obilježene oblike koji su ISPRAVNI.

{BLACKLIST_PROMPT_BLOK}

FORMAT ODGOVORA — OBAVEZNO:
Vrati ISKLJUČIVO JSON, bez ikakvog teksta prije ili poslije:
{{
  "tekst": "<cijeli ispravljeni tekst>",
  "izmjene": [
    {{"original": "<pogrešan oblik>", "ispravak": "<ispravan oblik>", "objasnjenje": "<kratko>"}}
  ]
}}

Ako nema izmjena, vrati:
{{"tekst": "<originalni tekst nepromijenjen>", "izmjene": []}}"""


def _korisnik_prompt(tekst: str) -> str:
    return f"""Analiziraj sljedeći prevedeni tekst i ispravi morfološke greške glagola:

---
{tekst}
---

Vrati JSON s rezultatom."""


def _pozovi_gemini(
    tekst: str,
    api_key: str,
    timeout: int = 30,
) -> tuple[str, list[dict]]:
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai nije instaliran. "
            "Pokrenuti: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=_system_prompt(),
    )

    generation_config = genai.types.GenerationConfig(
        temperature=0.1,
        max_output_tokens=MAX_CHUNK_ZNAKOVA * 2,
        response_mime_type="application/json",
    )

    odgovor = model.generate_content(
        _korisnik_prompt(tekst),
        generation_config=generation_config,
    )

    raw = odgovor.text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    data = json.loads(raw)

    ispravljeni = data.get("tekst", tekst)
    izmjene = data.get("izmjene", [])

    if len(ispravljeni) < len(tekst) * 0.7:
        raise ValueError(
            f"AI vratio drastično kraći tekst ({len(ispravljeni)} vs {len(tekst)} znakova). "
            "Odbacivam — failsafe aktiviran."
        )

    return ispravljeni, izmjene


def _regex_zamjene(tekst: str) -> tuple[str, list[dict]]:
    izmjene = []
    rezultat = tekst

    for pogresno, ispravno in HALUCIRANI_OBLICI.items():
        pattern = re.compile(r'\b' + re.escape(pogresno) + r'\b', re.IGNORECASE)
        if pattern.search(rezultat):
            novi = rezultat
            for m in pattern.finditer(rezultat):
                original_case = m.group(0)
                if original_case[0].isupper():
                    zamjena = ispravno[0].upper() + ispravno[1:]
                else:
                    zamjena = ispravno
                novi = novi[:m.start()] + zamjena + novi[m.end():]
                izmjene.append({
                    "original": original_case,
                    "ispravak": zamjena,
                    "objasnjenje": "regex_blacklist",
                })
            rezultat = novi

    return rezultat, izmjene


def _audit_log(
    knjiga_id: str,
    chunk_id: int,
    rezultat: ValidacijaRezultat,
) -> None:
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        zapis = {
            "timestamp": datetime.utcnow().isoformat(),
            "knjiga_id": knjiga_id,
            "chunk_id": chunk_id,
            "promijenjen": rezultat.promijenjen,
            "broj_izmjena": rezultat.broj_izmjena,
            "ai_korissten": rezultat.ai_korissten,
            "greska": rezultat.greska,
            "trajanje_ms": rezultat.trajanje_ms,
            "izmjene": rezultat.izmjene,
            "pre_screening_nalazi": len(rezultat.pre_screening_nalazi),
        }
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(zapis, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Audit log greška (nebitno): {e}")


def validiraj_tekst(
    tekst: str,
    api_key: Optional[str] = None,
    knjiga_id: str = "unknown",
    chunk_id: int = 0,
    force_ai: bool = False,
    skip_ai: bool = False,
) -> str:
    """
    Javno sučelje — validira tekst i vraća ispravljenu verziju.
    FAIL-SAFE: Ako bilo što ne uspije, vraća originalni tekst nepromijenjen.
    """
    t_start = time.time()
    rezultat = ValidacijaRezultat(
        originalni_tekst=tekst,
        validirani_tekst=tekst,
    )

    try:
        if len(tekst.strip()) < MIN_ZNAKOVA_ZA_AI:
            return tekst

        # Korak 1: Regex zamjene (uvijek)
        tekst_nakon_regex, regex_izmjene = _regex_zamjene(tekst)
        rezultat.izmjene.extend(regex_izmjene)

        # Korak 2: Pre-screening
        pre_nalazi = skeniraj_halucinacije(tekst_nakon_regex)
        rezultat.pre_screening_nalazi = pre_nalazi

        # Korak 3: Odluka o AI prolazu
        trebamo_ai = (force_ai or len(pre_nalazi) > 0) and not skip_ai

        if trebamo_ai and api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")

        if trebamo_ai and api_key:
            logger.info(
                f"[morfo_validator] AI prolaz: knjiga={knjiga_id} chunk={chunk_id} "
                f"pre_screening={len(pre_nalazi)} oblika"
            )

            if len(tekst_nakon_regex) > MAX_CHUNK_ZNAKOVA:
                tekst_za_ai = tekst_nakon_regex[:MAX_CHUNK_ZNAKOVA]
                sufiks = tekst_nakon_regex[MAX_CHUNK_ZNAKOVA:]
                logger.warning(
                    f"[morfo_validator] Tekst predugačak ({len(tekst_nakon_regex)} znakova), "
                    f"validiramo samo prvih {MAX_CHUNK_ZNAKOVA}."
                )
            else:
                tekst_za_ai = tekst_nakon_regex
                sufiks = ""

            ai_tekst = None
            ai_izmjene = []
            zadnja_greska = None

            for pokusaj in range(MAX_RETRIES + 1):
                try:
                    ai_tekst, ai_izmjene = _pozovi_gemini(tekst_za_ai, api_key)
                    rezultat.ai_korissten = True
                    break
                except Exception as e:
                    zadnja_greska = str(e)
                    logger.warning(
                        f"[morfo_validator] AI pokušaj {pokusaj+1}/{MAX_RETRIES+1} neuspješan: {e}"
                    )
                    if pokusaj < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)

            if ai_tekst is not None:
                rezultat.validirani_tekst = ai_tekst + sufiks
                rezultat.izmjene.extend(ai_izmjene)
            else:
                logger.error(
                    f"[morfo_validator] AI prolaz neuspješan nakon {MAX_RETRIES+1} pokušaja. "
                    f"Zadnja greška: {zadnja_greska}. Koristim regex rezultat."
                )
                rezultat.greska = zadnja_greska
                rezultat.validirani_tekst = tekst_nakon_regex

        elif trebamo_ai and not api_key:
            logger.warning(
                "[morfo_validator] Pre-screening našao sumnjive oblike, "
                "ali API ključ nije dostupan. Koristim samo regex."
            )
            rezultat.validirani_tekst = tekst_nakon_regex
        else:
            rezultat.validirani_tekst = tekst_nakon_regex

    except Exception as e:
        logger.error(f"[morfo_validator] Kritična greška — vraćam original. Greška: {e}")
        rezultat.greska = str(e)
        rezultat.validirani_tekst = tekst

    finally:
        rezultat.trajanje_ms = int((time.time() - t_start) * 1000)
        _audit_log(knjiga_id, chunk_id, rezultat)

    return rezultat.validirani_tekst


class MorfoValidator:
    """
    Wrapper klasa za upotrebu u pipeline.py.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        skip_ai: bool = False,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.skip_ai = skip_ai
        self._statistika = {
            "ukupno": 0,
            "ai_koristen": 0,
            "izmjenjeno": 0,
            "gresaka": 0,
        }

    def validiraj(
        self,
        tekst: str,
        knjiga_id: str = "unknown",
        chunk_id: int = 0,
    ) -> str:
        self._statistika["ukupno"] += 1
        rezultat_tekst = validiraj_tekst(
            tekst=tekst,
            api_key=self.api_key,
            knjiga_id=knjiga_id,
            chunk_id=chunk_id,
            skip_ai=self.skip_ai,
        )
        if rezultat_tekst != tekst:
            self._statistika["izmjenjeno"] += 1
        return rezultat_tekst

    def statistika(self) -> dict:
        return dict(self._statistika)

    def __repr__(self) -> str:
        return (
            f"MorfoValidator(ai={'enabled' if self.api_key else 'disabled'}, "
            f"ukupno={self._statistika['ukupno']})"
        )


# ---------------------------------------------------------------------------
# Gotova instanca — importira se u workers_v2.py / pipeline.py
# ---------------------------------------------------------------------------

morfo_validator: MorfoValidator = MorfoValidator()


if __name__ == "__main__":
    import sys

    print("=== MorfoValidator — lokalni test (bez AI) ===\n")

    testovi = [
        "Hodavao je ulicom i gledavao kroz prozore.",
        "Uzdisnuo je duboko i popivajući kavu nastavio čitati.",
        "Pokušavao je razumjeti što se desilo te noći.",
        "Prepoznavao je njena lica iz snova.",
        "Govorivao im je o prošlim vremenima.",
        "Volio je grad, ali ga je i mrzio istovremeno.",
    ]

    for i, tekst in enumerate(testovi, 1):
        print(f"[{i}] ORIGINAL: {tekst}")
        rezultat = validiraj_tekst(tekst, skip_ai=True)
        if rezultat != tekst:
            print(f"    ISPRAVLJENO: {rezultat}")
        else:
            print(f"    OK — nema promjena")
        print()

    print(f"\nAudit log: {AUDIT_LOG_PATH}")
    print("Za AI test: postaviti GEMINI_API_KEY env var i ukloniti skip_ai=True")
