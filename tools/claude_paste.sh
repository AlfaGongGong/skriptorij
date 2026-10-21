#!/bin/bash
# Cita clipboard, trazi === FILE: X === blokove i CLAUDE_LOG unos.
# Upotreba: ./tools/claude_paste.sh
set -e
cd "$(dirname "$0")/.." || exit 1

read_clip() {
    if command -v termux-clipboard-get &>/dev/null; then
        termux-clipboard-get
    elif command -v xclip &>/dev/null; then
        xclip -selection clipboard -o
    elif command -v xsel &>/dev/null; then
        xsel --clipboard --output
    else
        echo "  ❌ nema clipboard alata"
        exit 1
    fi
}

TEXT=$(read_clip)
if [ -z "$TEXT" ]; then
    echo "  clipboard prazan"; exit 1
fi

echo "═══ 1. === FILE: X === blokovi ═══"
python3 - "$TEXT" << 'PYEOF'
import sys, re
from pathlib import Path
text = sys.argv[1]
files = re.findall(r'=== FILE: (.+?) ===\n(.*?)\n=== END FILE ===', text, re.DOTALL)
if not files:
    print("  (nema FILE blokova)")
for path, content in files:
    p = Path(path.strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, "utf-8")
    print(f"  ✅ {p}")
PYEOF

echo ""
echo "═══ 2. CLAUDE_LOG unos ═══"
python3 - "$TEXT" << 'PYEOF'
import sys, re
from pathlib import Path
text = sys.argv[1]
m = re.search(r'(## \[\d{4}-\d{2}-\d{2}.*?)(?=\n## \[|\n=== FILE|\Z)', text, re.DOTALL)
if not m:
    print("  (nema CLAUDE_LOG zapisa)")
    sys.exit(0)
entry = m.group(1).strip()
log = Path("CLAUDE_LOG.md")
if not log.exists():
    log.write_text("# CLAUDE LOG\n\n---\n\n", "utf-8")
src = log.read_text("utf-8")
if "---\n\n" in src:
    src = src.replace("---\n\n", f"---\n\n{entry}\n\n", 1)
else:
    src += "\n\n" + entry + "\n"
log.write_text(src, "utf-8")
print(f"  ✅ CLAUDE_LOG.md (+{len(entry)} bajtova)")
PYEOF

echo ""
echo "═══ 3. Git commit ═══"
git add -A 2>/dev/null || true
if git diff --cached --quiet; then
    echo "  nema promjena"
else
    git commit -m "claude: paste-back $(date +%H:%M)"
    echo "  ✅ commit $(git rev-parse --short HEAD)"
fi
