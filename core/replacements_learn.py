"""
core/replacements_learn.py — učenje iz Moon+ Text Replacement fajlova.

Posle primene (`apply_to_html`), imamo listu `Fire` — koja pravila su se
stvarno aktivirala, koliko puta, gde.

Ovaj modul analizira `Fire` listu i generiše:
  - glosar_candidates — imena likova, mesta, termina (za book_context.glosar)
  - anti_pattern_candidates — konstrukcije (za core/kalkovi)
  - unused_rules — pravila koja se nikad nisu aktivirala

Ne piše u pipeline. Samo priprema podatke.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Marker za ime/mesto: kratko, veliko slovo, bez razmaka, word boundary
_IME_RX = re.compile(r'^\\b([A-ZČĆŽŠĐ][a-zčćžšđA-ZČĆŽŠĐ\-]+)\\b$')

# Marker za rečenicu/konstrukciju: sadrži razmak, tačku, navodnik
_KONSTRUKCIJA_RX = re.compile(r'[\s.,;:!?"„”\'—–-]')


@dataclass
class GlosarCandidate:
    original: str        # "Pratchett"
    prevod: str          # "Pračet"
    count: int           # koliko puta se aktiviralo
    confidence: float    # 0-1, na osnovu broja pojava
    source_line: int


@dataclass
class AntiPatternCandidate:
    pattern: str         # "bio je rekao"
    replacement: str     # "rekao je"
    count: int
    confidence: float
    source_line: int


@dataclass
class UnusedRule:
    search: str
    replace: str
    source_line: int


@dataclass
class LearnResult:
    glosar_candidates: list[GlosarCandidate] = field(default_factory=list)
    anti_pattern_candidates: list[AntiPatternCandidate] = field(default_factory=list)
    unused_rules: list[UnusedRule] = field(default_factory=list)
    total_fires: int = 0
    unique_rules_fired: int = 0
    total_rules: int = 0


def _izvuci_iz_search(search: str) -> str:
    """Izvuci čist tekst iz regex patterna (ukloni \\b, \\B, grupe)."""
    s = search
    s = re.sub(r'^\\[bB]', '', s)
    s = re.sub(r'\\[bB]$', '', s)
    s = s.replace('\\', '')
    return s.strip()


def _je_ime(search: str) -> bool:
    """Da li je search ime/mesto (jedna reč, veliko slovo, bez razmaka)?"""
    cist = _izvuci_iz_search(search)
    if not cist:
        return False
    if _KONSTRUKCIJA_RX.search(cist):
        return False
    # Prvo slovo veliko, ostalo slova
    if not cist[0].isupper():
        return False
    if not all(c.isalpha() or c in "-'" for c in cist):
        return False
    return True


def _je_konstrukcija(search: str) -> bool:
    """Da li je search konstrukcija (sadrži razmak, tačku, navodnik)?"""
    cist = _izvuci_iz_search(search)
    return bool(cist and _KONSTRUKCIJA_RX.search(cist))


def _confidence(count: int) -> float:
    """Konfidenca na osnovu broja pojava: 1→0.5, 5→0.75, 20+→1.0."""
    if count <= 0:
        return 0.0
    if count >= 20:
        return 1.0
    # Logaritamska skala: 1→0.5, 5→0.75, 20→1.0
    import math
    return min(1.0, 0.5 + math.log10(count) / 2.6)


def learn_from_fires(fires: list, all_rules: list) -> LearnResult:
    """
    Analizira listu `Fire` objekata (iz replacements.py) i sve `Rule` objekte.

    Args:
        fires: lista Fire objekata (samo aktivirana pravila)
        all_rules: lista svih Rule objekata (da nađemo neaktivna)

    Returns:
        LearnResult sa kandidatima.
    """
    result = LearnResult()

    # Grupisi fires po rule
    po_rule: dict[tuple, list] = {}
    for f in fires:
        key = (f.rule.source_line, f.rule.search, f.rule.replace)
        po_rule.setdefault(key, []).append(f)

    result.total_fires = sum(f.count for f in fires)
    result.unique_rules_fired = len(po_rule)
    result.total_rules = len(all_rules)

    fired_lines = {k[0] for k in po_rule.keys()}

    # Za svako aktivirano pravilo
    for (line, search, replace), fires_for_rule in po_rule.items():
        # 2026-10-23: preskoči no-op (search == replace, ne donosi nista)
        _search_clean = _izvuci_iz_search(search)
        if _search_clean == replace:
            continue
        total_count = sum(f.count for f in fires_for_rule)
        conf = _confidence(total_count)

        if _je_ime(search):
            result.glosar_candidates.append(GlosarCandidate(
                original=_izvuci_iz_search(search),
                prevod=replace,
                count=total_count,
                confidence=conf,
                source_line=line,
            ))
        elif _je_konstrukcija(search):
            result.anti_pattern_candidates.append(AntiPatternCandidate(
                pattern=_izvuci_iz_search(search),
                replacement=replace,
                count=total_count,
                confidence=conf,
                source_line=line,
            ))

    # Neaktivna pravila
    for rule in all_rules:
        if rule.source_line not in fired_lines:
            result.unused_rules.append(UnusedRule(
                search=rule.search,
                replace=rule.replace,
                source_line=rule.source_line,
            ))

    # Sortiraj: glosar po count desc, anti-pattern po count desc
    result.glosar_candidates.sort(key=lambda c: -c.count)
    result.anti_pattern_candidates.sort(key=lambda c: -c.count)

    return result


def to_glosar_dict(result: LearnResult, min_confidence: float = 0.7) -> dict:
    """
    Konvertuj glosar_candidates u dict za book_context.glosar.

    Args:
        result: LearnResult
        min_confidence: minimalna konfidenca (default 0.7 = ~3+ pojava)

    Returns:
        {"Pratchett": "Pračet", "Rikke": "Rike", ...}
    """
    return {
        c.original: c.prevod
        for c in result.glosar_candidates
        if c.confidence >= min_confidence and c.original != c.prevod
    }


def to_kalkovi_list(result: LearnResult, min_confidence: float = 0.85) -> list[dict]:
    """
    Konvertuj anti_pattern_candidates u listu za core/kalkovi.

    Args:
        result: LearnResult
        min_confidence: minimalna konfidenca (default 0.85 = ~10+ pojava)

    Returns:
        [{"pattern": "bio je rekao", "replacement": "rekao je", "confidence": 0.95}, ...]
    """
    return [
        {
            "pattern": c.pattern,
            "replacement": c.replacement,
            "confidence": c.confidence,
        }
        for c in result.anti_pattern_candidates
        if c.confidence >= min_confidence and c.pattern != c.replacement
    ]


def summarize(result: LearnResult) -> str:
    """Kratki tekstualni sažetak."""
    lines = [
        f"Ukupno pravila: {result.total_rules}",
        f"Aktivirano: {result.unique_rules_fired} ({100*result.unique_rules_fired//max(1,result.total_rules)}%)",
        f"Ukupno zamena: {result.total_fires}",
        f"Glosar kandidata: {len(result.glosar_candidates)}",
        f"Anti-pattern kandidata: {len(result.anti_pattern_candidates)}",
        f"Neaktivnih: {len(result.unused_rules)}",
    ]
    if result.glosar_candidates:
        lines.append("\nTop 10 glosar kandidata:")
        for c in result.glosar_candidates[:10]:
            lines.append(f"  {c.original:20} -> {c.prevod:20} ({c.count}x, conf={c.confidence:.2f})")
    if result.anti_pattern_candidates:
        lines.append("\nTop 10 anti-pattern kandidata:")
        for c in result.anti_pattern_candidates[:10]:
            lines.append(f"  {c.pattern:30} -> {c.replacement:30} ({c.count}x, conf={c.confidence:.2f})")
    return "\n".join(lines)
