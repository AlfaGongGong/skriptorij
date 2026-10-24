"""
tests/golden/test_replacements.py
Golden test za core/replacements.py — deterministicka primena Moon+ pravila.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


FIXTURE_RULES = """# === TEST ===
\\bPratchett\\b#->#Pračet
\\bRikke\\b#->#Rike
*„#->#—
*”#->#
\\bii#->#i
"""


def test_apply_literal_and_regex(tmp_path):
    """Primena literal i regex pravila na HTML tekstualne cvorove."""
    from core.replacements import apply_to_text, load_moon_replacements

    rules_file = tmp_path / "rules.txt"
    rules_file.write_text(FIXTURE_RULES, encoding="utf-8")
    rules = load_moon_replacements(str(rules_file))
    assert len(rules) == 5

    # Regex: word boundary
    text = "Pratchett je rekao. Pratchettov prijatelj."
    out, fires = apply_to_text(text, rules)
    assert "Pračet" in out
    assert "Pratchettov" in out, "word boundary ne radi"

    # Literal: „ → —
    text2 = '„Rikke" i „Pratchett"'
    out2, _ = apply_to_text(text2, rules)
    assert "„" not in out2
    assert "—" in out2
    assert "Rike" in out2  # Rikke → Rike


def test_apply_html_only_text_nodes():
    """apply_to_html ne sme da dira atribute, tagove, CSS, JS."""
    import re

    from core.replacements import Rule

    rule = Rule(
        search="Pratchett",
        replace="Pračet",
        mode="literal",
        pattern=re.compile(r"Pratchett"),
        source_line=1,
        original="Pratchett",
    )

    html = b'<html><head><style>.Pratchett { color: red }</style></head><body class="Pratchett"><p>Pratchett</p><script>var x = "Pratchett";</script></body></html>'
    from core.replacements import apply_to_html

    out, fires = apply_to_html(html, [rule])
    out_str = out.decode("utf-8")

    # U tekstu: zamenjeno
    assert "<p>Pračet</p>" in out_str
    # U atributu: nije dirano
    assert 'class="Pratchett"' in out_str
    # U CSS-u: nije dirano
    assert ".Pratchett" in out_str
    # U JS-u: nije dirano
    assert 'var x = "Pratchett"' in out_str
    # Bar 1 fire (samo tekstualni cvor)
    assert sum(f.count for f in fires) == 1


def test_learn_from_fires():
    """learn_from_fires razdvaja imena (glosar) od konstrukcija (anti-pattern)."""
    import re

    from core.replacements import Fire, Rule
    from core.replacements_learn import learn_from_fires

    rule1 = Rule(
        search="Pratchett",
        replace="Pračet",
        mode="literal",
        pattern=re.compile("Pratchett"),
        source_line=1,
        original="",
    )
    rule2 = Rule(
        search="bio je rekao",
        replace="rekao je",
        mode="literal",
        pattern=re.compile("bio je rekao"),
        source_line=2,
        original="",
    )

    fires = [
        Fire(rule=rule1, count=5, context="x"),
        Fire(rule=rule2, count=3, context="y"),
    ]
    result = learn_from_fires(fires, [rule1, rule2])
    assert len(result.glosar_candidates) >= 1
    assert any(c.original == "Pratchett" for c in result.glosar_candidates)
    assert any(c.pattern == "bio je rekao" for c in result.anti_pattern_candidates)
