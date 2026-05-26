"""
core/kalkovi/engine.py
======================
KalkoviEngine — deterministički post-processing sloj za BooklyFi.

Kompajlira SVE_LISTE jednom pri importu (nulti runtime penalty).
Primjenjuje regex zamjene na tekst:
  - HTML-safe: ne dirá sadržaj unutar tagova
  - Whitelist: vlastita imena iz glosara se preskáču
  - Fail-safe: greška u jednoj zamjeni ne ruši pipeline
  - Statistike: broji primijenjene zamjene (za audit log)
  - Hot-reload: reload() osvježava patterne bez restarta servera
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interni tip za kompajlirani pattern
# ---------------------------------------------------------------------------

@dataclass
class _KompajliraniPattern:
    izvorni_pattern: str
    zamjena: str
    compiled: re.Pattern
    kategorija: str = ""


# ---------------------------------------------------------------------------
# Pomoćni regex za HTML-safe mod
# ---------------------------------------------------------------------------
# Lookahead koji osigurava da match nije unutar HTML taga.
# Dodaje se na kraj svakog patterná koji ne sadrži vlastiti lookahead.
_HTML_LOOKAHEAD = r"(?![^<]*>)"

# Regex koji prepoznaje HTML tagove (za whitelist zaštitu)
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.UNICODE)

# ---------------------------------------------------------------------------
# Whitelist: zaštita vlastitih imena iz glosara
# ---------------------------------------------------------------------------

def _izgradi_whitelist_re(glosar: dict) -> Optional[re.Pattern]:
    """
    Prima glosar {originalni_termin: prijevod} ili {termin: None}.
    Vraća kompajlirani pattern koji matchuje sve termine koje treba zaštititi,
    ili None ako je glosar prazan.
    """
    if not glosar:
        return None
    termini = sorted(glosar.keys(), key=len, reverse=True)  # duži prvi
    escaped = [re.escape(t) for t in termini if t.strip()]
    if not escaped:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(escaped) + r")(?!\w)",
                      re.IGNORECASE | re.UNICODE)


def _zamijeni_s_whitelistom(
    tekst: str,
    whitelist_re: Optional[re.Pattern],
    compiled_patterns: list[_KompajliraniPattern],
) -> tuple[str, int]:
    """
    Primjenjuje patterne na tekst uz zaštitu whitelist termina.

    Strategija:
      1. Pronađi sve whitelist matcheve i zamijeni ih privremenim
         placeholder-ima koji ne mogu biti zahvaćeni kalkovima.
      2. Primijeni kalkove.
      3. Vrati originalne whitelist termine.
    """
    placeholders: dict[str, str] = {}

    if whitelist_re:
        konter = [0]

        def _sacuvaj(m: re.Match) -> str:
            key = f"\x00WL{konter[0]}\x00"
            placeholders[key] = m.group(0)
            konter[0] += 1
            return key

        tekst = whitelist_re.sub(_sacuvaj, tekst)

    ukupno_zamjena = 0
    for kp in compiled_patterns:
        try:
            novi_tekst, n = kp.compiled.subn(kp.zamjena, tekst)
            if n:
                ukupno_zamjena += n
                tekst = novi_tekst
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[kalkovi] Greška u patternu %r → %r: %s",
                kp.izvorni_pattern,
                kp.zamjena,
                exc,
            )

    # Vrati whitelist termine
    for key, original in placeholders.items():
        tekst = tekst.replace(key, original)

    return tekst, ukupno_zamjena


# ---------------------------------------------------------------------------
# Glavni engine
# ---------------------------------------------------------------------------

class KalkoviEngine:
    """
    Singleton-like engine koji kompajlira SVE_LISTE jednom pri instanciranju.

    Preporučeno korištenje (u pipeline.py ili text_utils.py):

        from core.kalkovi.engine import kalkovi_engine  # gotova instanca

        ispravljeni, n = kalkovi_engine.primijeni(tekst, glosar=book_ctx.glosar)
    """

    def __init__(self, liste: list[tuple[str, str]], html_safe: bool = True):
        """
        :param liste:     Lista (pattern, zamjena) tuplova iz SVE_LISTE.
        :param html_safe: Ako True, zamjene ne diraju sadržaj HTML tagova.
        """
        self._html_safe = html_safe
        self._compiled: list[_KompajliraniPattern] = []
        self._kompajliraj(liste)
        logger.info(
            "[kalkovi] Engine inicijaliziran: %d kompajliranih patterna.",
            len(self._compiled),
        )

    # ------------------------------------------------------------------
    # Privatne metode
    # ------------------------------------------------------------------

    def _kompajliraj(self, liste: list[tuple[str, str]]) -> None:
        """Kompajlira sve patterne — poziva se jednom pri startu."""
        uspjesno = 0
        neuspjesno = 0
        self._compiled = []

        for entry in liste:
            # Podržavamo i 2-tuple i 3-tuple (pattern, zamjena, kategorija)
            if len(entry) == 3:
                pattern_str, zamjena, kategorija = entry
            else:
                pattern_str, zamjena = entry
                kategorija = ""

            try:
                finalni_pattern = pattern_str
                if self._html_safe and _HTML_LOOKAHEAD not in pattern_str:
                    finalni_pattern = pattern_str + _HTML_LOOKAHEAD

                compiled = re.compile(
                    finalni_pattern, re.IGNORECASE | re.UNICODE
                )
                self._compiled.append(
                    _KompajliraniPattern(
                        izvorni_pattern=pattern_str,
                        zamjena=zamjena,
                        compiled=compiled,
                        kategorija=kategorija,
                    )
                )
                uspjesno += 1
            except re.error as exc:
                logger.error(
                    "[kalkovi] Neispravan regex %r — preskačem: %s",
                    pattern_str,
                    exc,
                )
                neuspjesno += 1

        if neuspjesno:
            logger.warning(
                "[kalkovi] %d patterna nije kompajlirano (pogledaj greške iznad).",
                neuspjesno,
            )

    # ------------------------------------------------------------------
    # Javno sučelje
    # ------------------------------------------------------------------

    def primijeni(
        self,
        tekst: str,
        glosar: Optional[dict] = None,
        blok_id: str = "",
    ) -> tuple[str, int]:
        """
        Primijeni sve kalkove na tekst.

        :param tekst:    Ulazni tekst (može biti HTML).
        :param glosar:   Rječnik vlastitih imena koja se ne smiju mijenjati.
                         Format: {termin: prijevod} ili {termin: None}.
        :param blok_id:  Identifikator bloka za audit log (npr. "ch03_blok_042").
        :returns:        (ispravljeni_tekst, broj_zamjena)
        """
        if not tekst or not tekst.strip():
            return tekst, 0

        if not self._compiled:
            logger.debug("[kalkovi] Nema kompajliranih patterna — tekst nepromijenjen.")
            return tekst, 0

        t_start = time.perf_counter()

        whitelist_re = _izgradi_whitelist_re(glosar or {})

        try:
            rezultat, n_zamjena = _zamijeni_s_whitelistom(
                tekst, whitelist_re, self._compiled
            )
        except Exception as exc:  # noqa: BLE001
            # Fail-safe: iznimka ne smije srušiti pipeline
            logger.error(
                "[kalkovi] Kritična greška u engine.primijeni() [blok=%s]: %s — "
                "vraćam originalni tekst.",
                blok_id or "?",
                exc,
            )
            return tekst, 0

        t_kraj = time.perf_counter()

        if n_zamjena:
            logger.info(
                "[kalkovi] blok=%-20s  zamjena=%3d  t=%.1fms",
                blok_id or "-",
                n_zamjena,
                (t_kraj - t_start) * 1000,
            )
        else:
            logger.debug(
                "[kalkovi] blok=%s — nema zamjena (%.1fms)",
                blok_id or "-",
                (t_kraj - t_start) * 1000,
            )

        return rezultat, n_zamjena

    def reload(self, liste: list[tuple[str, str]]) -> None:
        """
        Hot-reload: ponovo kompajlira patterne bez restarta servera.
        Koristi tokom razvoja nakon izmjene kalkovi modula.
        """
        logger.info("[kalkovi] Hot-reload: rekompajliram %d patterna ...", len(liste))
        self._kompajliraj(liste)
        logger.info("[kalkovi] Hot-reload završen: %d patterna aktivno.", len(self._compiled))

    @property
    def broj_patterna(self) -> int:
        """Broj uspješno kompajliranih patterna."""
        return len(self._compiled)

    def statistike(self) -> dict:
        """Vraća rječnik s osnovnim info o engineu (za /api/status endpoint)."""
        kategorije: dict[str, int] = {}
        for kp in self._compiled:
            kategorije[kp.kategorija or "ostalo"] = (
                kategorije.get(kp.kategorija or "ostalo", 0) + 1
            )
        return {
            "ukupno_patterna": len(self._compiled),
            "html_safe": self._html_safe,
            "kategorije": kategorije,
        }


# ---------------------------------------------------------------------------
# Gotova instanca — importira se u pipeline.py / text_utils.py
# ---------------------------------------------------------------------------

def _inicijaliziraj_engine() -> KalkoviEngine:
    """
    Kreira gotovu instancu pri importu modula.
    Fail-safe: ako SVE_LISTE nije dostupan, vraća prazni engine.
    """
    try:
        from core.kalkovi import SVE_LISTE  # noqa: PLC0415
        return KalkoviEngine(SVE_LISTE)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[kalkovi] Ne mogu učitati SVE_LISTE: %s — engine je prazan (fallback).",
            exc,
        )
        return KalkoviEngine([])


kalkovi_engine: KalkoviEngine = _inicijaliziraj_engine()


# ---------------------------------------------------------------------------
# CLI: python3 -m core.kalkovi.engine "tekst za test"
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) < 2:
        print("Upotreba: python3 -m core.kalkovi.engine \"tekst za test\"")
        sys.exit(1)

    ulaz = sys.argv[1]
    izlaz, n = kalkovi_engine.primijeni(ulaz, blok_id="cli_test")
    print(f"\nUlaz : {ulaz}")
    print(f"Izlaz: {izlaz}")
    print(f"Zamjena: {n}")
    print(f"Patterna u engineu: {kalkovi_engine.broj_patterna}")

# ── HTML-safe wrapper za text_utils kompatibilnost ─────────────────────────
def primijeni_html_safe(tekst, glosar=None):
    """
    HTML-safe verzija primijeni() za upotrebu u text_utils.py.
    Štiti HTML tagove od zamjena.
    """
    return kalkovi_engine.primijeni(tekst, glosar=glosar)
