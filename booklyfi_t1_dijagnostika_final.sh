#!/bin/bash
# T1 jedina preostala dijagnostika — samo citanje
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_dijagnostika_final_$TS.log"

{
echo "=== A: twp_names.json ==="
TWP="/storage/emulated/0/Download/booklyfi_audit/twp_names.json"
ls -la "$TWP" 2>&1
venv/bin/python3 << 'PYEOF'
import json, os
p = "/storage/emulated/0/Download/booklyfi_audit/twp_names.json"
if os.path.exists(p):
    d = json.load(open(p, encoding="utf-8"))
    print("unosa:", len(d))
    for k in ("Bayaz", "Bajaz", "Glokta", "Rikke", "Savine", "Leo"):
        print(f"  {k!r}: {d.get(k)!r}")
    print("  hr != en (prvih 15):", [(k, v) for k, v in d.items() if k != v][:15])
    print("  vrijednosti koje sadrze 'Bajaz':", [(k, v) for k, v in d.items() if "Bajaz" in str(v)])
else:
    print("NE POSTOJI")
PYEOF

echo
echo "=== B: engine wrapper za prevodilac prompt ==="
grep -n "def _get_prevodilac_prompt" -A 22 core/engine.py

echo
echo "=== C: EPUB knjige ==="
EPUB=$(find /storage/emulated/0 -maxdepth 6 -iname "*Wisdom*Crowds*.epub" 2>/dev/null | grep -vi "PREVEDENO" | head -1)
[ -z "$EPUB" ] && EPUB=$(find /storage/emulated/0 -maxdepth 6 -iname "*Wisdom*Crowds*.epub" 2>/dev/null | head -1)
echo "EPUB: $EPUB"
export T1_EPUB="$EPUB"

echo
echo "=== D: simulacija stvarnog prompta ==="
venv/bin/python3 << 'PYEOF'
import os, re, sys, zipfile, types, inspect
sys.path.insert(0, ".")
epub = os.environ.get("T1_EPUB", "")
if not epub:
    print("nema EPUB-a, preskacem"); sys.exit(0)

# 1. glosar kroz pravu engine funkciju
try:
    import core.engine as E
    cls = next(o for n, o in vars(E).items()
               if inspect.isclass(o) and hasattr(o, "_ucitaj_kanon_glosar"))
    glos = cls._ucitaj_kanon_glosar(types.SimpleNamespace(book_path=epub))
except Exception as e:
    print("ENGINE IMPORT/POZIV PAO:", repr(e)); sys.exit(0)
linije = glos.splitlines()
print(f"glosar linija: {len(linije)}")
for l in linije:
    if "Bayaz" in l or "Bajaz" in l:
        print("  ", l)

# 2. pravi blok sa Bayazom
chunk = ""
with zipfile.ZipFile(epub) as z:
    for n in sorted(z.namelist()):
        if n.endswith((".xhtml", ".html", ".htm")):
            h = z.read(n).decode("utf-8", "replace")
            if "Bayaz" in h:
                ps = re.findall(r"<p\b[^>]*>.*?</p>", h, re.S)
                i = next((k for k, p in enumerate(ps) if "Bayaz" in p), 0)
                chunk = "\n".join(ps[max(0, i - 1):i + 5])
                print(f"blok iz {n}, {len(chunk)} znakova")
                break
if not chunk:
    print("nema bloka sa Bayaz"); sys.exit(0)

# 3. relevantni glosar: trenutni filter vs striktni (granice rijeci)
from analysis.book_context import BookContextManager
m = BookContextManager.__new__(BookContextManager); m._glosar = {}
rel = m.extract_relevant_glossary(chunk, glos)
strict = []
for l in linije:
    mm = re.match(r"^-\s+(.+?)\s+(?:->|\()", l)
    if mm and re.search(r"\b" + re.escape(mm.group(1)) + r"\b", chunk, re.I):
        strict.append(l)
print(f"\nrelevantno (trenutni filter): {len(rel.splitlines())} | striktno: {len(strict)}")
lazni = [l for l in rel.splitlines() if l not in strict]
print("LAZNI POGOCI:", lazni)

# 4. cijeli prompt + few-shot
from core.prompts import get_prevodilac_prompt
prompt = get_prevodilac_prompt({}, rel, "", "naracija")
print(f"\nprompt duzina: {len(prompt)} znakova (~{len(prompt)//3} tokena)")
i = prompt.find("GLOSAR")
print(prompt[i:i + 500])

try:
    from core.few_shot_global import formatiraj_za_prompt
    plain = re.sub(r"<[^>]+>", "", chunk)[:300]
    fs = formatiraj_za_prompt(plain, "naracija", max_n=2)
    print("\nFEW-SHOT u promptu:", "da" if fs else "ne")
    print("  Bajaz u few-shotu:", fs.count("Bajaz"), "| Bayaz:", fs.count("Bayaz"))
    print(fs[:600])
except Exception as e:
    print("few-shot greska:", repr(e))
PYEOF

echo
echo "=== E: zadnji log glosara iz stvarnih runova ==="
grep -rhn "📖 Glosar" .logs /storage/emulated/0/Download/*.log 2>/dev/null | tail -5

echo
echo "=== F: get_system_prompt (da li je PREVODILAC template stvarno u upotrebi) ==="
sed -n '804,855p' core/prompts.py
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
