"""
core/replacements.py — Moon+ Reader Text Replacement parser + applier.

Format (Moon+):
  # === komentar ===
  \\bSearch\\b#->#Replace      <- regex mode (word boundary)
  *Search#->#Replace          <- literal mode
  Search#->#Replace           <- literal mode (bez * — fallback)
  Search#->#                  <- brise se

Apply samo na tekstualne cvorove HTML-a, ne na tagove/atribute/CSS/JS.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Rule:
    search: str
    replace: str
    mode: str            # "regex" | "literal"
    pattern: re.Pattern  # kompajlirana
    source_line: int
    original: str


@dataclass
class Fire:
    rule: Rule
    count: int
    context: str         # prvih 50 znakova tekstualnog cvora


def load_moon_replacements(path: str) -> List[Rule]:
    """Parsira Moon+ Text Replacement fajl."""
    rules: List[Rule] = []
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Fajl ne postoji: {path}")

    for line_no, raw in enumerate(p.read_text("utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#") and "#->#" not in line:
            continue
        if "#->#" not in line:
            continue

        search_part, replace_part = line.split("#->#", 1)

        # Detektuj mode
        if search_part.startswith("*"):
            mode = "literal"
            search = search_part[1:]
        elif "\\b" in search_part or "\\B" in search_part or "\\w" in search_part:
            mode = "regex"
            search = search_part
        elif "\\" in search_part:
            # escape bez \b — tretiraj kao regex
            mode = "regex"
            search = search_part
        else:
            mode = "literal"
            search = search_part

        if not search:
            continue

        # Kompajliraj
        try:
            if mode == "regex":
                pattern = re.compile(search)
            else:
                pattern = re.compile(re.escape(search))
        except re.error as e:
            print(f"  ⚠️  linija {line_no}: regex greska ({e}) — preskacem: {raw[:60]}")
            continue

        rules.append(Rule(
            search=search, replace=replace_part, mode=mode,
            pattern=pattern, source_line=line_no, original=raw,
        ))

    return rules


def apply_to_text(text: str, rules: List[Rule]) -> tuple[str, List[Fire]]:
    """Primijeni pravila na plain tekst. Vraca (novi_tekst, fires)."""
    fires: List[Fire] = []
    for rule in rules:
        def repl(m):
            return rule.replace

        new_text, count = rule.pattern.subn(repl, text)
        if count > 0:
            fires.append(Fire(
                rule=rule, count=count,
                context=text[:50].replace("\n", " "),
            ))
            text = new_text
    return text, fires


def apply_to_html(html_bytes: bytes, rules: List[Rule]) -> tuple[bytes, List[Fire]]:
    """
    Primijeni pravila na HTML tekstualne cvorove.
    NE dira <style>, <script>, atribute, base64.
    Vraca (novi_bytes, fires).
    """
    try:
        from bs4 import BeautifulSoup, NavigableString
    except ImportError:
        raise ImportError("BeautifulSoup nije instaliran")

    soup = BeautifulSoup(html_bytes, "html.parser")

    # Ukloni <style> i <script> iz razmatranja (ostaju u HTML-u)
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()

    all_fires: List[Fire] = []

    for node in soup.find_all(string=True):
        if not isinstance(node, NavigableString):
            continue
        original = str(node)
        if not original.strip():
            continue
        new_text, fires = apply_to_text(original, rules)
        if new_text != original:
            node.replace_with(NavigableString(new_text))
            all_fires.extend(fires)

    return str(soup).encode("utf-8"), all_fires


def summarize(fires: List[Fire], total_rules: int) -> str:
    """Kratki sazetak za log."""
    if not fires:
        return f"0 fires od {total_rules} pravila"

    by_rule = {}
    for f in fires:
        key = (f.rule.source_line, f.rule.original)
        by_rule[key] = by_rule.get(key, 0) + f.count

    lines = [f"{len(by_rule)} pravila aktivirana (od {total_rules}):"]
    for (line, orig), cnt in sorted(by_rule.items(), key=lambda x: -x[1])[:20]:
        lines.append(f"  [{line}] {orig[:60]}  ({cnt}x)")
    if len(by_rule) > 20:
        lines.append(f"  ... i jos {len(by_rule) - 20} pravila")
    return "\n".join(lines)
