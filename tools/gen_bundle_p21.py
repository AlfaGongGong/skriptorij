import re
from pathlib import Path

DL = Path("/storage/emulated/0/Download")
OUT = DL / "CLAUDE_BUNDLE_P21.md"
REPO = Path("/root/skriptorij")


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return "[GRESKA: %s]" % e


def extract_fn(src, fn_name):
    lines = src.split("\n")
    out = []
    in_fn = False
    indent = 0
    for line in lines:
        if re.match(rf"^(async\s+)?def\s+{re.escape(fn_name)}\s*\(", line):
            in_fn = True
            out.append(line)
            indent = len(line) - len(line.lstrip())
            continue
        if in_fn:
            if line.strip() == "":
                out.append(line)
                continue
            cur = len(line) - len(line.lstrip())
            if cur <= indent and line.strip() and not line.strip().startswith("#"):
                break
            out.append(line)
    return "\n".join(out)


F_MD = "````markdown\n"
F_PY = "````python\n"
F_END = "\n````\n"

parts = []
parts.append("# CLAUDE BUNDLE — P2.1 Verifikator (T3)\n\n")
parts.append("**VAZNO:** 4-struki backtick fence za blokove koda, jer unutrasnji sadrzaj ima 3-struki.\n\n")
parts.append("Generisano: 2026-11-04\nRepo HEAD: afe0d1a\n\n---\n\n")

parts.append("## 1. PROMPT ZA CLAUDE-A\n\n")
parts.append(
    "Nastavljamo BOOKLYFI projekat. Procitao sam handoff, AI log i KONTEKST v9.1.\n\n"
    "STANJE:\n"
    "- HEAD: afe0d1a (P1.1 Claude, 43 testa)\n"
    "- Sinhroni smo. Faza 0 (P0.1-P0.6) i Faza 1 (P1.1-P1.4) OK\n"
    "- P2.1 (Verifikator T3) - tvoj zadatak\n"
    "- P2.3 (EN paralelni prikaz) - DeepSeekov zadatak, dogovoreno: pipeline pise .en.chk\n\n"
    "P2.1 - VERIFIKATOR:\n"
    "- Novi modul core/verifier.py\n"
    "- Model dobija EN + HR blok i trazi specificne greske (smisao), ne ponovno prevodjenje\n"
    "- Vrati JSON {ok: bool, greske: [{tip, en_fragment, hr_fragment, objasnjenje}]}\n\n"
    "VAZNO - PODJELA:\n"
    "- DeepSeek paralelno radi P2.3 (_chk_write .en.chk u pipeline.py, nova ruta /api/review/en/stem)\n"
    "- NE DIRAJ pipeline.py - samo core/verifier.py (novi) + tests/unit/test_verifier.py (novi)\n\n"
    "PRAVILA:\n"
    "- P1-P19 iz KONTEKST.md\n"
    "- STARO/NOVO prije primjene\n"
    "- ast.parse + py_compile + pytest prije commita\n"
    "- Auto-log kroz tools/auto_log.sh\n\n"
    "PRVI KORAK: potvrdi da si procitao KONTEKST i da razumijes podjelu.\n"
)
parts.append("\n---\n\n")

parts.append("## 2. KONTEKST.md (v9.1)\n\n")
parts.append(F_MD + read(DL / "KONTEKST.md") + F_END)
parts.append("\n---\n\n")

parts.append("## 3. BOOKLYFI_DEEPSEEK_HANDOFF.md\n\n")
parts.append(F_MD + read(DL / "BOOKLYFI_DEEPSEEK_HANDOFF.md") + F_END)
parts.append("\n---\n\n")

parts.append("## 4. BOOKLYFI_AI_LOG.md (zadnjih 15)\n\n")
log = read(DL / "BOOKLYFI_AI_LOG.md")
entries = re.split(r"\n(?=## \[)", log)
recent = "\n".join(entries[-15:]) if len(entries) > 15 else log
parts.append(F_MD + recent + F_END)
parts.append("\n---\n\n")

parts.append("## 5. core/quality.py\n\n")
q = read(REPO / "core" / "quality.py")
parts.append(F_PY)
for fn in ["_scoruj_kvalitetu", "_izracunaj_heuristicki_score", "_je_nonprose_blok", "quality_summary"]:
    code = extract_fn(q, fn)
    if code:
        parts.append("\n### %s\n\n%s\n" % (fn, code))
parts.append(F_END)
parts.append("\n---\n\n")

parts.append("## 6. core/metrics.py (T3)\n\n")
m = read(REPO / "core" / "metrics.py")
parts.append(F_PY)
for fn in ["check_accuracy", "accuracy_shadow", "_plain_za_provjeru", "_nadji_brojeve"]:
    code = extract_fn(m, fn)
    if code:
        parts.append("\n### %s\n\n%s\n" % (fn, code))
parts.append(F_END)
parts.append("\n---\n\n")

parts.append("## 7. processing/pipeline.py (REFERENCA, NE DIRATI)\n\n")
p = read(REPO / "processing" / "pipeline.py")
parts.append(F_PY)
for fn in ["_chk_path", "_chk_read", "_chk_write", "process_chunk_with_ai", "_quality_scoring"]:
    code = extract_fn(p, fn)
    if code:
        parts.append("\n### %s\n\n%s\n" % (fn, code))
parts.append(F_END)
parts.append("\n---\n\n")

parts.append("## 8. core/chunking.py\n\n")
parts.append(F_PY + read(REPO / "core" / "chunking.py") + F_END)
parts.append("\n---\n\n")

parts.append("## 9. ZADATAK\n\n")
parts.append(
    "### KORAK 1: Procitaj sve. Potvrdi razumijevanje.\n\n"
    "### KORAK 2: Napravi core/verifier.py (novi)\n\n"
    "Struktura:\n\n"
    "```python\n"
    "def provjeri_blok(en_text, hr_text, glosar, fleet=None):\n"
    "    # vrati {ok, greske: [{tip, en_fragment, hr_fragment, objasnjenje}], score, model}\n"
    "    ...\n"
    "```\n\n"
    "### KORAK 3: Napravi tests/unit/test_verifier.py\n\n"
    "Testovi: mock model s greskama, mock model prazan, malformed JSON, timeout, integritet.\n\n"
    "### KORAK 4: NE DIRAJ pipeline.py\n\n"
    "### KORAK 5: Commit\n\n"
    "```bash\n"
    "git add core/verifier.py tests/unit/test_verifier.py\n"
    "git commit -m 'P2.1: T3 verifikator'\n"
    "bash tools/auto_log.sh 'P2.1 Verifikator' 'core/verifier.py + testovi' 'AI provjera smisla EN vs HR' 'OK'\n"
    "```\n\n"
    "### KORAK 6: Javi DeepSeek-u (za hook u pipeline.py)\n"
)
parts.append("\n---\n\n")

parts.append("## 10. METADATA\n\n")
parts.append("- Bundle: 2026-11-04\n")
parts.append("- Repo: /root/skriptorij\n")
parts.append("- HEAD: afe0d1a\n")
parts.append("- Zadatak: P2.1\n")
parts.append("- Vlasnik: Claude\n")
parts.append("- Smije dirati: core/verifier.py, tests/unit/test_verifier.py\n")
parts.append("- NE smije dirati: processing/pipeline.py, main.js, style.css, app.py\n")
parts.append("- DeepSeek paralelno: P2.3\n\n")
parts.append("**KRAJ BUNDLE-A**\n")

content = "".join(parts)
OUT.write_text(content, encoding="utf-8")
size = OUT.stat().st_size
n4 = content.count("````")
n3 = content.count("```")
print("  Bundle: %s" % OUT)
print("  Velicina: %s B (%.1f KB)" % (size, size / 1024))
print("  Linija: %d" % content.count("\n"))
print("  4-backtick: %d %s" % (n4, "OK" if n4 % 2 == 0 else "NEPARAN"))
print("  3-backtick: %d %s" % (n3, "OK" if n3 % 2 == 0 else "NEPARAN"))
