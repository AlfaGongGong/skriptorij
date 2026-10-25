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
from dataclasses import dataclass
from pathlib import Path
@dataclass
class Rule:
    search: str
    replace: str
    mode: str  # "regex" | "literal"
    pattern: re.Pattern  # kompajlirana
    source_line: int
    original: str


@dataclass
class Fire:
    rule: Rule
    count: int
    context: str  # prvih 50 znakova tekstualnog cvora


def load_moon_replacements(path: str) -> list[Rule]:
    """Parsira Moon+ Text Replacement fajl."""
    rules: list[Rule] = []
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

        rules.append(
            Rule(
                search=search,
                replace=replace_part,
                mode=mode,
                pattern=pattern,
                source_line=line_no,
                original=raw,
            )
        )

    return rules


def apply_to_text(text: str, rules: list[Rule]) -> tuple[str, list[Fire]]:
    """Primijeni pravila na plain tekst. Vraca (novi_tekst, fires)."""
    fires: list[Fire] = []
    for rule in rules:

        def repl(m, _r=rule):
            return _r.replace

        new_text, count = rule.pattern.subn(repl, text)
        if count > 0:
            fires.append(
                Fire(
                    rule=rule,
                    count=count,
                    context=text[:50].replace("\n", " "),
                )
            )
            text = new_text
    return text, fires


def apply_to_html(html_bytes: bytes, rules: list[Rule]) -> tuple[bytes, list[Fire]]:
    """
    Primijeni pravila na HTML tekstualne cvorove.
    NE dira <style>, <script>, atribute, base64, XML deklaraciju.
    Vraca (novi_bytes, fires).

    Koristi regex-based pristup (ne BeautifulSoup) — cuva originalnu
    XML strukturu sto je neophodno za EPUB (XHTML = XML).
    """
    import re as _re
    import uuid

    html = html_bytes.decode("utf-8", errors="strict")

    # 1. Sacuvaj <script> i <style> (ne diramo sadrzaj)
    saved = []
    token_prefix = "___SAVED_" + uuid.uuid4().hex[:8] + "_"

    def _save_block(m):
        saved.append(m.group(0))
        return f"{token_prefix}{len(saved) - 1}___"

    html = _re.sub(
        r"<script\b[^>]*>.*?</script>",
        _save_block,
        html,
        flags=_re.DOTALL | _re.IGNORECASE,
    )
    html = _re.sub(
        r"<style\b[^>]*>.*?</style>",
        _save_block,
        html,
        flags=_re.DOTALL | _re.IGNORECASE,
    )

    # 2. Iteriraj kroz tagove i tekst izmedju njih
    all_fires: list[Fire] = []
    parts: list[str] = []
    pos = 0

    for tag_match in _re.finditer(r"<[^>]+>", html):
        # Tekst pre taga
        text = html[pos : tag_match.start()]
        if text:
            new_text, fires = apply_to_text(text, rules)
            if fires:
                all_fires.extend(fires)
            parts.append(new_text)
        # Tag kao sto je
        parts.append(tag_match.group(0))
        pos = tag_match.end()

    # Preostali tekst
    if pos < len(html):
        text = html[pos:]
        new_text, fires = apply_to_text(text, rules)
        if fires:
            all_fires.extend(fires)
        parts.append(new_text)

    result = "".join(parts)

    # 3. Vrati <script> i <style>
    for i, block in enumerate(saved):
        result = result.replace(f"{token_prefix}{i}___", block)

    return result.encode("utf-8"), all_fires


def summarize(fires: list[Fire], total_rules: int) -> str:
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
