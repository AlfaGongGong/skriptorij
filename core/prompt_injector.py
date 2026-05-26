"""
core/prompt_injector.py
────────────────────────
Centralni modul za upravljanje i injektiranje konteksta u prompts.

Spaja sve izvore konteksta:
  1. morfologija_blacklist  → anti-pattern negative examples
  2. BookContext.glosar     → deklinacije likova
  3. BookContext.summary    → chapter summary
  4. BookContext.few_shot   → primjeri dobrog prijevoda
  5. model_profile          → per-model kalibracija (Korak 6)

Korištenje:
    from core.prompt_injector import PromptInjector
    injector = PromptInjector(book_context=ctx)
    system_prompt = injector.build_system_prompt(
        base_prompt="Prevedi na bosanski...",
        broj_poglavlja=3,
        model_name="gemini-2.5-flash",
    )
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Fail-safe importovi
try:
    from core.kalkovi.morfologija_blacklist import BLACKLIST_PROMPT_BLOK
    _BLACKLIST_OK = True
except ImportError:
    BLACKLIST_PROMPT_BLOK = ""
    _BLACKLIST_OK = False
    logger.warning("[prompt_injector] morfologija_blacklist nije dostupan")

try:
    from analysis.book_context import BookContext
    _BOOK_CONTEXT_OK = True
except ImportError:
    BookContext = None
    _BOOK_CONTEXT_OK = False
    logger.warning("[prompt_injector] book_context nije dostupan")


# ── Statički prompt blokovi ────────────────────────────────────────────────
BAZNI_JEZIK_BLOK = """
## Jezična pravila — bosanski/hrvatski standard
- Ijekavica dosljedno: bio/bila, vidio/vidjela, htio/htjela, sjedio/sjedjela
- Nikad ekavica: nevjerojatan (ne: neverovatno), posjeduje (ne: poseduje)
- Navodnici: » « za dijalog (ili " " — dosljedno kroz cijelu knjigu)
- Spojnica: – (en-dash) za dijalog, - (hyphen) samo za složenice
- Bez srbizama: treba (ne: mora da), hoće (ne: će da), može (ne: ume)
""".strip()

BAZNI_STIL_BLOK = """
## Stilska pravila
- Prirodan BS/HR tok rečenice — ne kalkirati englesku sintaksu
- Glagolski prilog sadašnji: hodajući, gledajući (ne: dok hoda, dok gleda — osim za naglasak)
- Vlastita imena: deklinirati prema BS/HR gramatici (v. glosar ispod)
- SF terminologija: zadržati ustaljene prijevode (stack, sleeve, kortikalni)
""".strip()


# ── Klasa injectora ────────────────────────────────────────────────────────
class PromptInjector:
    """
    Centralni injector — spaja sve izvore konteksta u jedan system prompt.
    """

    def __init__(
        self,
        book_context=None,
        ukljuci_blacklist: bool = True,
        ukljuci_glosar: bool = True,
        ukljuci_summary: bool = True,
        ukljuci_few_shot: bool = True,
        ukljuci_jezicna_pravila: bool = True,
        max_few_shot: int = 3,
        max_glosar_likova: int = 15,
        max_ukupno_znakova: int = 3000,
    ):
        self.ctx = book_context
        self.ukljuci_blacklist = ukljuci_blacklist and _BLACKLIST_OK
        self.ukljuci_glosar = ukljuci_glosar and _BOOK_CONTEXT_OK
        self.ukljuci_summary = ukljuci_summary and _BOOK_CONTEXT_OK
        self.ukljuci_few_shot = ukljuci_few_shot and _BOOK_CONTEXT_OK
        self.ukljuci_jezicna_pravila = ukljuci_jezicna_pravila
        self.max_few_shot = max_few_shot
        self.max_glosar_likova = max_glosar_likova
        self.max_ukupno_znakova = max_ukupno_znakova

    def _inject_blacklist(self) -> str:
        if not self.ukljuci_blacklist or not BLACKLIST_PROMPT_BLOK:
            return ""
        return BLACKLIST_PROMPT_BLOK

    def _inject_jezicna_pravila(self) -> str:
        if not self.ukljuci_jezicna_pravila:
            return ""
        return BAZNI_JEZIK_BLOK + "\n\n" + BAZNI_STIL_BLOK

    def _inject_glosar(self) -> str:
        if not self.ukljuci_glosar or not self.ctx:
            return ""
        try:
            return self.ctx.glosar_prompt_blok(max_likova=self.max_glosar_likova)
        except Exception as e:
            logger.warning(f"[prompt_injector] Glosar injection greška: {e}")
            return ""

    def _inject_chapter_summary(self, broj_poglavlja: Optional[int]) -> str:
        if not self.ukljuci_summary or not self.ctx or not broj_poglavlja:
            return ""
        try:
            return self.ctx.summary_prompt_blok(broj_poglavlja)
        except Exception as e:
            logger.warning(f"[prompt_injector] Summary injection greška: {e}")
            return ""

    def _inject_few_shot_primjeri(self) -> str:
        if not self.ukljuci_few_shot or not self.ctx:
            return ""
        try:
            return self.ctx.few_shot_prompt_blok(max_primjera=self.max_few_shot)
        except Exception as e:
            logger.warning(f"[prompt_injector] Few-shot injection greška: {e}")
            return ""

    def build_context_blok(self, broj_poglavlja: Optional[int] = None) -> str:
        """Gradi kompletni kontekst blok (sve sekcije zajedno)."""
        sekcije = []

        kandidati = [
            ("chapter_summary", self._inject_chapter_summary(broj_poglavlja)),
            ("glosar", self._inject_glosar()),
            ("blacklist", self._inject_blacklist()),
            ("jezicna_pravila", self._inject_jezicna_pravila()),
            ("few_shot", self._inject_few_shot_primjeri()),
        ]

        ukupno = 0
        for naziv, blok in kandidati:
            if not blok:
                continue
            if ukupno + len(blok) > self.max_ukupno_znakova:
                logger.debug(
                    f"[prompt_injector] Limit dostignut pri sekciji '{naziv}' "
                    f"({ukupno}/{self.max_ukupno_znakova})"
                )
                break
            sekcije.append(blok)
            ukupno += len(blok)

        if not sekcije:
            return ""

        return "\n\n---\n\n".join(sekcije)

    def build_system_prompt(
        self,
        base_prompt: str,
        broj_poglavlja: Optional[int] = None,
        model_name: str = "",
    ) -> str:
        """Gradi kompletni system prompt kombiniranjem baznog prompta s kontekstom."""
        kontekst = self.build_context_blok(broj_poglavlja)

        if kontekst:
            separator = "\n\n" + "="*60 + "\n## KONTEKST KNJIGE\n" + "="*60 + "\n\n"
            return base_prompt + separator + kontekst
        else:
            return base_prompt

    def statistika(self) -> dict:
        """Vraća info o dostupnim komponentama."""
        return {
            "blacklist": self.ukljuci_blacklist and bool(BLACKLIST_PROMPT_BLOK),
            "glosar": self.ukljuci_glosar and bool(self.ctx),
            "chapter_summary": self.ukljuci_summary and bool(self.ctx),
            "few_shot": self.ukljuci_few_shot and bool(self.ctx),
            "book_context_likovi": len(self.ctx._glosar) if self.ctx else 0,
            "few_shot_primjeri": len(self.ctx._few_shot_primjeri) if self.ctx else 0,
        }

    def __repr__(self) -> str:
        stat = self.statistika()
        aktivno = [k for k, v in stat.items() if v is True or (isinstance(v, int) and v > 0)]
        return f"PromptInjector(aktivno={aktivno})"


# ── Singleton helper ───────────────────────────────────────────────────────
_injector_cache: dict[str, PromptInjector] = {}

def get_injector(knjiga_id: str, **kwargs) -> PromptInjector:
    """Vraća PromptInjector instancu za danu knjigu (singleton per knjiga)."""
    if knjiga_id not in _injector_cache:
        if _BOOK_CONTEXT_OK:
            from analysis.book_context import BookContext
            ctx = BookContext(knjiga_id=knjiga_id)
        else:
            ctx = None
        _injector_cache[knjiga_id] = PromptInjector(book_context=ctx, **kwargs)
    return _injector_cache[knjiga_id]


# ── CLI test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== PromptInjector — lokalni test ===\n")

    injector_basic = PromptInjector()
    print(f"Injector (bez konteksta): {injector_basic}")
    print(f"Statistika: {injector_basic.statistika()}")
    print()

    bazni = "Ti si profesionalni prevodilac. Prevedi sljedeći tekst na bosanski."
    prompt = injector_basic.build_system_prompt(bazni)
    print(f"Prompt (bez konteksta): {len(prompt)} znakova")
    print(f"Blacklist uključen: {'APSOLUTNE ZABRANE' in prompt}")
    print()

    try:
        from analysis.book_context import BookContext
        ctx = BookContext(knjiga_id="test_injector")
        ctx.dodaj_likove_bulk([("Takeshi", "M"), ("Ana", "Ž"), "Bancroft"])
        ctx.dodaj_few_shot(
            "The room was dark and cold.",
            "Soba je bila tamna i hladna.",
            "Jednostavan prijevod bez kalkova"
        )

        injector_full = PromptInjector(book_context=ctx)
        print(f"Injector (s kontekstom): {injector_full}")
        prompt_full = injector_full.build_system_prompt(bazni, broj_poglavlja=1)
        print(f"Prompt (s kontekstom): {len(prompt_full)} znakova")
        print()
        print("=== PREVIEW PROMPTA (prvih 800 znakova) ===")
        print(prompt_full[:800])
        print("...")

    except ImportError as e:
        print(f"BookContext nije dostupan za test: {e}")
