#!/usr/bin/env bash
# tools/izvezi_kod.sh — izvozi u .md (i .txt kopiju) SAV kod koji aplikacija stvarno koristi.
# Šta ulazi: .py fajlovi dostižni iz ulaznih tačaka (import graf) + templates/*.html, static/*.js|css
# Šta ne ulazi: testovi, tools/, diag_*, backupi, venv, orfani — sve što app ne učitava.
# Ključevi/lozinke u kodu se zamjenjuju sa ***UKLONJENO***.
#
# Upotreba:
#   bash tools/izvezi_kod.sh                       # ulaz: app.py run.py main.py wsgi.py (koji postoje)
#   bash tools/izvezi_kod.sh --ulaz app.py run.py  # eksplicitne ulazne tačke
#   bash tools/izvezi_kod.sh --samo-py             # bez templates/static
#   bash tools/izvezi_kod.sh --max-kb 300          # manji dijelovi (default 500 KB)
#   bash tools/izvezi_kod.sh --izlaz /putanja      # default: Download/booklyfi ako postoji, inače ./izvoz
set -uo pipefail

DIR="."
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) shift; DIR="${1:-.}" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done
cd "$DIR" || { echo "Ne mogu otvoriti $DIR"; exit 1; }
ROOT=$(pwd)
if   [ -x "$ROOT/venv/bin/python" ];  then PY="$ROOT/venv/bin/python"
elif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"
else PY=$(command -v python3 || command -v python); fi
[ -z "${PY:-}" ] && { echo "Python nije pronađen"; exit 1; }

mkdir -p "$ROOT/.cistoca"
cat > "$ROOT/.cistoca/izvezi.py" <<'PYEOF'
import argparse, ast, os, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("root")
ap.add_argument("--ulaz", nargs="*")
ap.add_argument("--izlaz")
ap.add_argument("--max-kb", type=int, default=500)
ap.add_argument("--samo-py", action="store_true")
a = ap.parse_args()

ROOT = Path(a.root).resolve()
SKIP = {".git", "venv", ".venv", "env", "node_modules", "__pycache__", ".cistoca", "build", "dist",
        ".mypy_cache", ".ruff_cache", ".pytest_cache", "site-packages", "_izvoz", "izvoz"}


def walk():
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP]
        for f in fs:
            yield Path(d) / f


def rel(p):
    return str(p.relative_to(ROOT))


pyf = [p for p in walk() if p.suffix == ".py" and ".bak" not in p.name]
modmap, byname = {}, {}
for p in pyf:
    parts = rel(p)[:-3].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
        if not parts:
            continue
    modmap[".".join(parts)] = p
    byname.setdefault(p.name, p)

entries = a.ulaz or [n for n in ("app.py", "run.py", "main.py", "wsgi.py") if (ROOT / n).exists()]
entries = [ROOT / e for e in entries if (ROOT / e).exists()]
if not entries:
    sys.exit("Nema ulaznih tačaka (app.py/run.py/main.py). Zadaj ih sa --ulaz.")


def cands(m):
    parts, res = m.split("."), set()
    for i in range(1, len(parts) + 1):
        k = ".".join(parts[:i])
        if k in modmap:
            res.add(modmap[k])
    return res


def deps(p):
    try:
        t = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        return set()
    parts = rel(p)[:-3].split(os.sep)
    is_init = parts[-1] == "__init__"
    pkg = parts[:-1] if not is_init else parts[:-1]
    out = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            for al in n.names:
                out |= cands(al.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg[:max(0, len(pkg) - (n.level - 1))]
                m = ".".join(base + ([n.module] if n.module else []))
            else:
                m = n.module or ""
            if m:
                out |= cands(m)
            for al in n.names:
                out |= cands((m + "." + al.name).strip("."))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and 0 < len(n.value) < 120:
            s = n.value
            if s in modmap:                       # importlib.import_module("x.y")
                out |= cands(s)
            elif s.endswith(".py") and Path(s).name in byname:   # subprocess ... "run.py"
                out.add(byname[Path(s).name])
    return out


reach, why, queue = {}, {}, list(entries)
for e in entries:
    reach[e], why[e] = 0, "ulazna tačka"
while queue:
    cur = queue.pop(0)
    for d in sorted(deps(cur), key=str):
        if d not in reach and d.exists():
            reach[d] = len(reach)
            why[d] = f"učitava ga {rel(cur)}"
            queue.append(d)

sel = sorted(reach, key=lambda p: (p not in entries, rel(p)))
front = []
if not a.samo_py:
    bad = {"vendor", "lib", "libs", "node_modules", "min", "dist"}
    for p in walk():
        r = Path(rel(p))
        if p.suffix.lower() not in (".html", ".js", ".css") or ".bak" in p.name or ".min." in p.name:
            continue
        if not (r.parts[0] in ("templates", "static")) or any(x in bad for x in r.parts) or p.stat().st_size > 300_000:
            continue
        front.append(p)
    front.sort(key=rel)
omitted = sorted(rel(p) for p in pyf if p not in reach)

KEY1 = re.compile(r"AIza[0-9A-Za-z_\-]{35}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{36}|xox[baprs]-[A-Za-z0-9\-]{10,}")
KEY2 = re.compile(r"""((?:api[_-]?key|secret|token|passw(?:or)?d)["']?\s*[=:]\s*["'])([A-Za-z0-9_./+\-]{16,})(["'])""", re.I)
LANG = {".py": "python", ".js": "javascript", ".css": "css", ".html": "html"}
redacted = 0


def clean(txt):
    global redacted
    n1 = len(KEY1.findall(txt)) + len(KEY2.findall(txt))
    redacted += n1
    return KEY2.sub(r"\1***UKLONJENO***\3", KEY1.sub("***UKLONJENO***", txt))


def block(p, label):
    txt = clean(p.read_text(encoding="utf-8", errors="replace")).rstrip("\n")
    fence = "`" * max(3, max((len(m) for m in re.findall(r"`+", txt)), default=0) + 1)
    n = txt.count("\n") + 1
    return f"## {rel(p)}  ({n} redaka — {label})\n\n{fence}{LANG[p.suffix]}\n{txt}\n{fence}\n\n"


items = [(p, why[p]) for p in sel] + [(p, "frontend") for p in front]
blocks = [(p, block(p, w)) for p, w in items]

limit = a.max_kb * 1024
parts, cur, size = [], [], 0
for p, b in blocks:
    bs = len(b.encode("utf-8"))
    if cur and size + bs > limit:
        parts.append(cur)
        cur, size = [], 0
    cur.append((p, b))
    size += bs
if cur:
    parts.append(cur)

out = Path(a.izlaz) if a.izlaz else None
if out is None:
    dl = Path("/storage/emulated/0/Download/booklyfi")
    out = dl if dl.parent.exists() and os.access(dl.parent, os.W_OK) else ROOT / "izvoz"
out.mkdir(parents=True, exist_ok=True)

N = len(parts)
toc_all = "\n".join(f"- `{rel(p)}` — {w}" for p, w in items)
names = []
for i, grp in enumerate(parts, 1):
    head = f"# {ROOT.name} — izvoz koda (dio {i}/{N})\n\n"
    head += ("Samo kod koji aplikacija stvarno koristi (import graf od ulaznih tačaka"
             + ("" if a.samo_py else " + templates/static") + ").\n\n")
    if i == 1:
        head += f"## Sadržaj (svi dijelovi)\n\n{toc_all}\n\n"
        head += (f"## Izostavljeno ({len(omitted)} .py fajlova koje app ne učitava)\n\n"
                 + "\n".join(f"- `{x}`" for x in omitted[:80]) + ("\n- ..." if len(omitted) > 80 else "") + "\n\n---\n\n")
    else:
        head += "Fajlovi u ovom dijelu:\n" + "\n".join(f"- `{rel(p)}`" for p, _ in grp) + "\n\n---\n\n"
    body = head + "".join(b for _, b in grp)
    stem = "booklyfi_kod" if N == 1 else f"booklyfi_kod_{i:02d}"
    for ext in ("md", "txt"):
        (out / f"{stem}.{ext}").write_text(body, encoding="utf-8")
    names.append(f"{stem}  ({len(body.encode('utf-8')) // 1024} KB)")

print(f"Ulazne tačke: {', '.join(rel(e) for e in entries)}")
print(f"Uključeno: {len(sel)} .py + {len(front)} frontend fajlova | izostavljeno .py: {len(omitted)}")
print(f"Uklonjeno ključeva/lozinki: {redacted}")
print(f"Izlaz: {out}")
for n in names:
    print(f"  {n}  (.md i .txt)")
PYEOF

"$PY" "$ROOT/.cistoca/izvezi.py" "$ROOT" "${ARGS[@]}"
