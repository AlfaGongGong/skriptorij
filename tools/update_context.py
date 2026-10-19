#!/usr/bin/env python3
"""Azurira AUTO sekciju u KONTEKST.md. Ne dira ostalo."""
import ast, subprocess, sys, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KONTEKST = ROOT / "KONTEKST.md"
START = "<!-- AUTO:START -->"
END = "<!-- AUTO:END -->"

def _run(cmd):
    try:
        return subprocess.run(
            cmd, cwd=ROOT, shell=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception as e:
        return f"(greska: {e})"

def _count_lines(p):
    try:
        return sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore"))
    except Exception:
        return 0

def _module_stats(path):
    try:
        tree = ast.parse(path.read_text("utf-8"))
        funcs = sum(1 for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        classes = sum(1 for n in tree.body if isinstance(n, ast.ClassDef))
        return f"{funcs}f/{classes}c/{_count_lines(path)}L"
    except Exception:
        return "?"

def build_auto():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    head = _run("git -c core.hooksPath=/dev/null log --oneline -1")
    last5 = _run("git -c core.hooksPath=/dev/null log --oneline -5")
    status = _run("git -c core.hooksPath=/dev/null status --short")
    status = status if status else "(clean)"

    moduli = [
        ("epub/styler.py", ROOT / "epub/styler.py"),
        ("epub/normalizer.py", ROOT / "epub/normalizer.py"),
        ("processing/pipeline.py", ROOT / "processing/pipeline.py"),
        ("network/http_client.py", ROOT / "network/http_client.py"),
        ("network/provider_router.py", ROOT / "network/provider_router.py"),
        ("core/engine.py", ROOT / "core/engine.py"),
    ]
    mod_lines = "\n".join(
        f"  - {name}: {_module_stats(p)}" for name, p in moduli if p.exists()
    )

    test_out = _run("python3 -m pytest tests/ -q --no-header 2>&1 | tail -3")
    if not test_out or "no tests ran" in test_out.lower():
        test_out = "(pytest nema rezultat / tests/ prazan)"

    parts = [
        START,
        "",
        "### Auto-generisano: " + now,
        "",
        "**Git:**",
        "- HEAD: " + head,
        "- Status: " + status,
        "",
        "**Zadnjih 5 commitova:**",
        last5,
        "",
        "**Kljucni moduli (funkcije/klase/linije):**",
        mod_lines,
        "",
        "**Testovi:**",
        test_out,
        "",
        END,
    ]
    return "\n".join(parts)


def main():
    if not KONTEKST.exists():
        print(f"❌ {KONTEKST} ne postoji", file=sys.stderr)
        return 1

    src = KONTEKST.read_text("utf-8")
    i = src.find(START)
    j = src.find(END)

    if i == -1 or j == -1:
        print(f"❌ Markeri {START} / {END} nisu u {KONTEKST.name}", file=sys.stderr)
        print("   Dodaj ih rucno pre prvog pokretanja.", file=sys.stderr)
        return 2

    if j < i:
        print("❌ END marker pre START markera", file=sys.stderr)
        return 3

    novo_auto = build_auto()
    novo = src[:i] + novo_auto + src[j + len(END):]

    tmp = KONTEKST.with_suffix(".md.tmp")
    tmp.write_text(novo, "utf-8")
    tmp.replace(KONTEKST)
    print(f"✅ Azurirano: {KONTEKST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
