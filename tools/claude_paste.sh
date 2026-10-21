#!/bin/bash
# Cita clipboard, primjenjuje === FILE: === blokove.
# Podrzava:
#   - === FILE: CLAUDE_LOG_ENTRY ===  (ide u CLAUDE_LOG.md na vrh)
#   - === FILE: putanja ===            (Write/overwrite)
#   - [STARO] / [NOVO] unutar fajla  (line-based diff)
# Upotreba: ./tools/claude_paste.sh
set -e
cd "$(dirname "$0")/.." || exit 1

read_clip() {
    if command -v termux-clipboard-get &>/dev/null; then termux-clipboard-get
    elif command -v xclip &>/dev/null; then xclip -selection clipboard -o
    elif command -v xsel &>/dev/null; then xsel --clipboard --output
    else echo "  ❌ nema clipboard alata"; exit 1
    fi
}

TEXT=$(read_clip)
if [ -z "$TEXT" ]; then echo "  clipboard prazan"; exit 1; fi

# Sanity check
N_FILES=$(printf '%s' "$TEXT" | grep -c "^=== FILE:" || true)
N_END=$(printf '%s' "$TEXT" | grep -c "^=== END FILE" || true)
echo "═══ 0. Clipboard: $N_FILES FILE blokova, $N_END END blokova"
if [ "$N_FILES" -eq 0 ]; then
    echo "  ❌ nema === FILE: blokova. Kopiraj cijeli Claude odgovor."
    exit 1
fi
if [ "$N_FILES" -ne "$N_END" ]; then
    echo "  ⚠️  nesklad: $N_FILES FILE vs $N_END END. Kopiraj ponovo cijeli odgovor."
    exit 1
fi

echo ""
echo "═══ 1. Primjena blokova ═══"
python3 - "$TEXT" << 'PYEOF'
import sys, re, subprocess
from pathlib import Path
text = sys.argv[1]

files = re.findall(r'^=== FILE: (.+?) ===\n(.*?)^=== END FILE ===', text, re.DOTALL | re.MULTILINE)
log_entry = None
created, modified = [], []

for name, content in files:
    name = name.strip()
    content = content.rstrip("\n") + "\n"
    if name == "CLAUDE_LOG_ENTRY":
        log_entry = content.strip()
        continue
    p = Path(name)
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)

    # Diff format: [STARO]/[NOVO]
    if "[STARO]" in content and "[NOVO]" in content:
        old = p.read_text("utf-8") if existed else ""
        m = re.search(r'\[STARO\]\n(.*?)\n\[NOVO\]\n(.*?)(?:\n\[|$)', content, re.DOTALL)
        if not m:
            print(f"  ⚠️  {name}: diff format neispravan, preskacem")
            continue
        staro, novo = m.group(1).rstrip(), m.group(2).rstrip()
        if staro in old:
            new_content = old.replace(staro, novo, 1)
            p.write_text(new_content, "utf-8")
            print(f"  🔧 {name} (diff, {len(staro.splitlines())} linija)")
            (modified if existed else created).append(name)
        else:
            print(f"  ⚠️  {name}: STARO nije nađen, preskacem")
    else:
        p.write_text(content, "utf-8")
        print(f"  {'🔧' if existed else '✨'} {name} ({'izmenjen' if existed else 'nov'})")
        (modified if existed else created).append(name)

# CLAUDE_LOG
if log_entry:
    log = Path("CLAUDE_LOG.md")
    if not log.exists():
        log.write_text("# CLAUDE LOG\n\n---\n\n", "utf-8")
    src = log.read_text("utf-8")
    if "---\n\n" in src:
        src = src.replace("---\n\n", f"---\n\n{log_entry}\n\n", 1)
    else:
        src = src.rstrip() + "\n\n" + log_entry + "\n"
    log.write_text(src, "utf-8")
    print(f"  📝 CLAUDE_LOG.md (+{len(log_entry)} bajtova)")

# Sazetak
print()
if created:
    print(f"Kreirano:  {len(created)} fajlova")
    for f in created: print(f"  + {f}")
if modified:
    print(f"Izmijenjeno: {len(modified)} fajlova")
    for f in modified: print(f"  ~ {f}")

# ast.parse za .py
py_files = [f for f in created + modified if f.endswith(".py")]
if py_files:
    print()
    print("Sintaksa:")
    for f in py_files:
        r = subprocess.run(["python3", "-c", f"import ast; ast.parse(open('{f}').read())"],
                           capture_output=True)
        print(f"  {'✅' if r.returncode == 0 else '❌'} {f}")
PYEOF

echo ""
echo "═══ 2. Git commit ═══"
git add -A
if git diff --cached --quiet; then
    echo "  nema promjena"
else
    git commit -m "claude: $(date +%H:%M)"
    echo "  ✅ $(git rev-parse --short HEAD)"
fi

echo ""
echo "═══ 3. Fajlovi u Download za sljedeći acc ═══"
DEST="/storage/emulated/0/Download/claude_upload"
mkdir -p "$DEST"
cp -f KONTEKST.md HANDOFF.md CLAUDE_LOG.md "$DEST/" 2>/dev/null
echo "  ✅ $DEST (KONTEKST.md, HANDOFF.md, CLAUDE_LOG.md)"
echo "  ➕ rucno dodaj task-specific fajlove"
