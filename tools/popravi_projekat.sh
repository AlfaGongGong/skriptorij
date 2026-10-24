#!/usr/bin/env bash
# tools/popravi_projekat.sh — automatske popravke na osnovu cistoca_izvjestaj.txt
# Upotreba:  bash tools/popravi_projekat.sh [--dir /put/do/projekta]
# Sigurnost: backup prije svega; ako nakon popravki nešto pukne (sintaksa ili
#            NOVA nedefinisana imena), sve se automatski vraća iz backupa.
set -uo pipefail

DIR="."
while [ $# -gt 0 ]; do
  case "$1" in
    --dir) shift; DIR="${1:-.}" ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Nepoznata opcija: $1"; exit 2 ;;
  esac
  shift
done
cd "$DIR" || { echo "Ne mogu otvoriti $DIR"; exit 1; }
ROOT=$(pwd)

# koristi python iz venv-a projekta (tamo su ruff/deptry/ovisnosti)
if   [ -x "$ROOT/venv/bin/python" ];  then PY="$ROOT/venv/bin/python"
elif [ -x "$ROOT/.venv/bin/python" ]; then PY="$ROOT/.venv/bin/python"
else PY=$(command -v python3 || command -v python); fi
[ -z "${PY:-}" ] && { echo "Python nije pronađen"; exit 1; }

mkdir -p "$ROOT/.cistoca"
for p in ruff deptry vulture; do
  "$PY" -m pip show "$p" >/dev/null 2>&1 \
    || "$PY" -m pip install -q "$p" >/dev/null 2>&1 \
    || "$PY" -m pip install -q --break-system-packages "$p" >/dev/null 2>&1 \
    || echo "  (nije uspjela instalacija: $p — taj korak se preskače)"
done

cat > "$ROOT/.cistoca/popravi.py" <<'PYEOF'
import ast, importlib.metadata as md, json, os, re, shutil, subprocess, sys, tarfile, time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
TS = time.strftime("%Y%m%d_%H%M%S")
WORK = ROOT / ".cistoca"
WORK.mkdir(exist_ok=True)
os.chmod(WORK, 0o700)
BACKUP = WORK / f"backup_popravi_{TS}.tar.gz"
KAR = WORK / f"karantina_{TS}"
BIN = Path(sys.executable).parent
SKIP = {".git", "venv", ".venv", "env", "node_modules", "__pycache__", ".cistoca",
        "build", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache", "site-packages"}
STD = set(getattr(sys, "stdlib_module_names", set()))
LOG = []


def log(s=""):
    print(s)
    LOG.append(s)


def tool(name):
    p = BIN / name
    return str(p) if p.exists() else shutil.which(name)


def run(cmd, timeout=600):
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R:  # noqa
            returncode, stdout, stderr = 1, "", str(e)
        return R()


def walk(skip=SKIP):
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in skip]
        for f in fs:
            yield Path(d) / f


def py_files():
    return [p for p in walk() if p.suffix == ".py"]


def ruff_json(select, files=None):
    r = tool("ruff")
    if not r:
        return []
    cmd = [r, "check", *(files or ["."]), "--select", select, "--extend-exclude", ".cistoca",
           "--output-format", "json", "--no-fix", "-q", "--exit-zero"]
    out = run(cmd).stdout
    try:
        return json.loads(out or "[]")
    except Exception:
        return []


def syntax_errors():
    bad = []
    for p in py_files():
        try:
            ast.parse(p.read_text(encoding="utf-8"), str(p))
        except Exception as e:
            bad.append(f"{p.relative_to(ROOT)}: {e}")
    return bad


def rel(p):
    return str(Path(p).resolve().relative_to(ROOT))


# ------------------------------------------------------------ backup
def backup():
    def filt(ti):
        parts = Path(ti.name).parts
        if any(x in SKIP for x in parts) or ti.name.endswith((".db", ".pyc")):
            return None
        return ti
    with tarfile.open(BACKUP, "w:gz") as t:
        t.add(ROOT, arcname=".", filter=filt)
    log(f"backup: {BACKUP}")


def rollback():
    with tarfile.open(BACKUP) as t:
        t.extractall(ROOT)
    log(f"!! ROLLBACK izvršen iz {BACKUP}")


# ------------------------------------------------------------ koraci
def korak_karantina():
    junk = lambda n: (".bak" in n or ".corrupt" in n or "_RECOVERED" in n
                      or n.endswith((".orig", ".rej", "~", ".swp", ".tmp")) or n == ".DS_Store")
    srcs = {p: p.read_text(encoding="utf-8", errors="ignore") for p in py_files()}
    n = 0
    for p in list(walk()):
        if not p.exists():
            continue
        move = junk(p.name)
        if not move and p.stat().st_size == 0 and p.name not in ("__init__.py", ".gitkeep"):
            move = True
            if p.suffix == ".py":  # prazan .py koji se negdje spominje ostaje
                stem = re.escape(p.stem)
                if any(q != p and re.search(rf"\b{stem}\b", s) for q, s in srcs.items()):
                    move = False
        if move:
            dst = KAR / p.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(dst))
            n += 1
    log(f"[1] karantina: {n} fajlova (.bak*, .corrupt*, RECOVERED, prazni) -> {KAR}")


def korak_pycache():
    n = 0
    for d, ds, _ in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in {".git", "venv", ".venv", "env", "node_modules", ".cistoca"}]
        for x in list(ds):
            if x == "__pycache__":
                shutil.rmtree(Path(d) / x, ignore_errors=True)
                ds.remove(x)
                n += 1
    log(f"[2] obrisano __pycache__ foldera: {n}")


def korak_pyproject():
    pp = ROOT / "pyproject.toml"
    if pp.exists():
        log("[3] pyproject.toml već postoji — ne diram (provjeri da ima testpaths=[\"tests\"])")
    else:
        pp.write_text(
            '[tool.pytest.ini_options]\n'
            'testpaths = ["tests"]\n'
            'addopts = "-q"\n\n'
            '[tool.ruff]\n'
            'target-version = "py311"\n'
            'extend-exclude = [".cistoca", "venv", ".venv"]\n\n'
            '[tool.ruff.lint]\n'
            'select = ["F", "E9", "B", "I", "UP"]\n'
            '# B905 (zip strict) i B007 (nekorištena petlja) su stil, ne bug\n'
            'ignore = ["B905", "B007"]\n', encoding="utf-8")
        log("[3] napravljen pyproject.toml (pytest samo nad tests/, ruff konfiguracija)")
    r = run([sys.executable, "-m", "pytest", "--collect-only", "-q"], timeout=300)
    txt = (r.stdout or "") + (r.stderr or "")
    if "INTERNALERROR" in txt:
        log("    pytest i dalje pada pri skupljanju testova (INTERNALERROR) — vidi RUCNO_ZA_POPRAVITI.md")
    else:
        last = [ln for ln in txt.strip().splitlines() if ln.strip()][-1:] or ["?"]
        log(f"    pytest skupljanje: {last[0]}")


def korak_json():
    n = 0
    for p in ROOT.glob("static/**/*.json"):
        try:
            text = p.read_text(encoding="utf-8")
            json.loads(text)
        except json.JSONDecodeError as e:
            if e.msg != "Extra data":
                log(f"[4] {rel(p)}: {e} — ručno")
                continue
            dec = json.JSONDecoder()
            i = len(text) - len(text.lstrip())
            obj, end = dec.raw_decode(text, i)
            shutil.copy2(p, WORK / f"{p.name}.{TS}.orig")
            p.write_text(text[:end].rstrip() + "\n", encoding="utf-8")
            log(f"[4] {rel(p)}: odbačen višak iza prvog JSON objekta ({len(text) - end} znakova); original u .cistoca/")
            n += 1
    if n == 0:
        log("[4] JSON: nema ništa za popraviti automatski")


def korak_f821_stdlib(top=True):
    n = 0
    for d in ruff_json("F821"):
        m = re.search(r"Undefined name `(\w+)`", d["message"])
        if not m or m.group(1) not in STD:
            continue
        name, path = m.group(1), Path(d["filename"])
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        if any(isinstance(x, ast.Import) and any((a.asname or a.name) == name for a in x.names) for x in tree.body):
            continue
        lines = src.splitlines(keepends=True)
        idx = 0
        for x in tree.body:
            is_doc = isinstance(x, ast.Expr) and isinstance(getattr(x, "value", None), ast.Constant) and isinstance(x.value.value, str)
            if is_doc or (isinstance(x, ast.ImportFrom) and x.module == "__future__"):
                idx = x.end_lineno
            else:
                break
        while idx == 0 and idx < len(lines) and re.match(r"#(!|.*coding[:=])", lines[idx]):
            idx += 1
        lines.insert(idx, f"import {name}\n")
        path.write_text("".join(lines), encoding="utf-8")
        log(f"[5] {rel(path)}: dodan 'import {name}' (nedostajao)")
        n += 1
        # nakon umetanja brojevi linija se pomjeraju — ponovo čitaj ruff izlaz
        return korak_f821_stdlib(False)
    if n == 0 and top:
        log("[5] F821: nema nedostajućih stdlib importa")


def collect_imports(files):
    imported, srcs = {}, {}
    def modname(p):
        r = str(p.relative_to(ROOT).with_suffix("")).replace(os.sep, ".")
        return r[:-9] if r.endswith(".__init__") else r
    for p in files:
        try:
            srcs[p] = p.read_text(encoding="utf-8")
            t = ast.parse(srcs[p])
        except Exception:
            continue
        pkg = modname(p).split(".")
        is_init = p.name == "__init__.py"
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imported.setdefault(a.name, set()).add(p)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg if is_init else pkg[:-1]
                    base = base[:max(0, len(base) - (n.level - 1))]
                    m = ".".join(base + ([n.module] if n.module else []))
                else:
                    m = n.module or ""
                imported.setdefault(m, set()).add(p)
                for a in n.names:
                    imported.setdefault((m + "." + a.name).strip("."), set()).add(p)
    return imported, srcs, modname


def korak_f401():
    diags = ruff_json("F401")
    if not diags:
        log("[6] F401: nema nalaza (ili ruff nije dostupan)")
        return
    files = py_files()
    imported, srcs, modname = collect_imports(files)
    byfile = {}
    for d in diags:
        byfile.setdefault(Path(d["filename"]), []).append(d)

    def used_elsewhere(f, name):
        if f.name == "__init__.py":
            return True
        mod = modname(f)
        if (imported.get(f"{mod}.{name}", set()) | imported.get(f"{mod}.*", set())) - {f}:
            return True
        last = re.escape(mod.split(".")[-1])
        pat = re.compile(rf"\b{last}\.{re.escape(name)}\b")
        return any(q != f and (f"{mod}.{name}" in s or pat.search(s)) for q, s in srcs.items())

    safe, keep = [], []
    for f, ds in byfile.items():
        names = []
        for d in ds:
            m = re.match(r"`([^`]+)` imported but unused", d["message"])
            names.append(m.group(1).split(".")[-1] if m else "")
        hits = [n for n in names if n and used_elsewhere(f, n)]
        (keep if hits else safe).append((f, hits))
    if safe:
        run([tool("ruff"), "check", "--select", "F401", "--fix", "-q", "--exit-zero",
             "--extend-exclude", ".cistoca", *[str(f) for f, _ in safe]])
    log(f"[6] F401: očišćeni neiskorišteni importi u {len(safe)} fajlova")
    for f, hits in keep:
        log(f"    PRESKOČENO {rel(f)} — uvozi se negdje drugdje (re-export?): {', '.join(sorted(set(hits)))}")


def korak_ruff_sigurno():
    r = tool("ruff")
    if not r:
        log("[7] ruff nije instaliran — preskačem")
        return
    run([r, "check", ".", "--extend-exclude", ".cistoca", "--select",
         "F541,F811,B033,PIE790,I,UP,C4,F841", "--fix", "-q", "--exit-zero"])
    run([r, "format", ".", "--extend-exclude", ".cistoca", "-q"])
    log("[7] ruff: sigurne autopopravke (f-stringovi, duplikati u setu, sortiranje importa, moderniji tipovi) + format")


SEC = re.compile(r"AIza[0-9A-Za-z_\-]{35}|gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|ghp_[A-Za-z0-9]{36}"
                 r"|xox[baprs]-[A-Za-z0-9\-]{10,}"
                 r"|(api[_-]?key|secret|token|passw(or)?d)[\"']?\s*[=:]\s*[\"'][A-Za-z0-9_./+\-]{16,}[\"']", re.I)


def korak_tajne():
    gi = ROOT / ".gitignore"
    cur = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    if gi.exists():
        shutil.copy2(gi, WORK / f"gitignore_{TS}.bak")
    add = []
    for want in (".cistoca/", ".env", ".env.*", "!.env.example", "__pycache__/", "*.pyc", "*.bak*", "*.corrupt*"):
        if want not in cur:
            add.append(want)
    git = (ROOT / ".git").exists()
    found = []
    for p in walk():
        if p.suffix in (".json", ".txt", ".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".ini", ".cfg") and p.stat().st_size < 5_000_000:
            try:
                if SEC.search(p.read_text(encoding="utf-8", errors="ignore")):
                    found.append(p)
            except Exception:
                pass
    for p in found:
        os.chmod(p, 0o600)
        if p.suffix in (".json", ".txt") and rel(p) not in cur and rel(p) not in add:
            add.append(rel(p))
    if add:
        with gi.open("a", encoding="utf-8") as fh:
            if cur and cur[-1] != "":
                fh.write("\n")
            fh.write("\n".join(add) + "\n")
    log(f"[8] tajne: {len(found)} fajlova sa ključevima -> chmod 600, dodani u .gitignore")
    for p in found:
        tracked = git and run(["git", "ls-files", "--error-unmatch", rel(p)]).returncode == 0
        if tracked:
            log(f"    !! {rel(p)} JE U GITU. Ključeve rotiraj, pa: git rm --cached {rel(p)}")
        elif p.suffix == ".py":
            log(f"    !! {rel(p)} ima ključ u kodu — prebaci u .env (ručno)")
        else:
            log(f"    {rel(p)}")


def korak_env_example():
    env, ex = ROOT / ".env", ROOT / ".env.example"
    if env.exists() and not ex.exists():
        keys = []
        for ln in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", ln)
            if m:
                keys.append(f"{m.group(1)}=")
        ex.write_text("\n".join(keys) + "\n", encoding="utf-8")
        log(f"[9] .env.example napravljen ({len(keys)} ključeva, bez vrijednosti)")
    else:
        log("[9] .env.example: ništa za raditi")


def korak_requirements():
    req = ROOT / "requirements.txt"
    d = tool("deptry")
    if not req.exists() or not d:
        log("[10] requirements: preskočeno (nema requirements.txt ili deptry)")
        return
    out = WORK / "deptry.json"
    run([d, ".", "--exclude", r"venv|\.venv|env|\.cistoca|node_modules|build|dist", "--json-output", str(out)])
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        log("[10] deptry izlaz nije čitljiv — preskočeno")
        return
    local = {p.name for p in ROOT.iterdir() if p.is_dir()} | {ROOT.name}
    dists = md.packages_distributions()
    have = {re.split(r"[<>=!~\[; ]", ln.strip(), 1)[0].lower().replace("_", "-")
            for ln in req.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith(("#", "-"))}
    add, manual = [], []
    for it in data:
        code = (it.get("error") or {}).get("code")
        mod = it.get("module")
        if code not in ("DEP001", "DEP003") or not mod or mod in add:
            continue
        cand = dists.get(mod.split(".")[0])
        if mod in local or not cand:
            manual.append(mod)
            continue
        name = cand[0]
        if name.lower().replace("_", "-") in have:
            continue
        line = f"{name}>={md.version(name)}"
        if line not in add:
            add.append(line)
    if add:
        shutil.copy2(req, WORK / f"requirements_{TS}.bak")
        with req.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(add) + "\n")
    log(f"[10] requirements.txt: dodano {len(add)} ovisnosti koje kod stvarno koristi: {', '.join(add) or '-'}")
    for m in sorted(set(manual)):
        log(f"     ručno: modul '{m}' se uvozi, ali nije lokalni ni instaliran paket")
    unused = sorted({it.get('module') for it in data if (it.get('error') or {}).get('code') == "DEP002"})
    if unused:
        log(f"     napomena: deklarisano a ne uvozi se direktno: {', '.join(map(str, unused))} "
            "(lxml se koristi kao parser preko bs4 — ostavi)")
    if sys.prefix != sys.base_prefix:
        r = run([sys.executable, "-m", "pip", "freeze"])
        if r.returncode == 0 and r.stdout.strip():
            (ROOT / "requirements.lock.txt").write_text(r.stdout, encoding="utf-8")
            log("     requirements.lock.txt (tačne verzije) osvježen")


def korak_readme():
    if list(ROOT.glob("README*")):
        log("[11] README već postoji")
        return
    items = sorted(p for p in ROOT.iterdir() if p.name not in SKIP and not p.name.startswith("."))
    tree = "\n".join(f"- `{p.name}{'/' if p.is_dir() else ''}`" for p in items if p.is_dir() or p.suffix in (".py", ".sh", ".txt"))
    (ROOT / "README.md").write_text(
        f"# {ROOT.name}\n\n_Kostur generisan automatski — dopuni opis i pokretanje._\n\n"
        f"## Struktura\n{tree}\n\n## Pokretanje\n```bash\npip install -r requirements.txt\ncp .env.example .env   # popuni ključeve\n```\n",
        encoding="utf-8")
    log("[11] README.md kostur napravljen")


def korak_rucno():
    items = []
    for d in ruff_json("F821,F841,B023,B018,PLE2510,F811"):
        items.append((d["code"], Path(d["filename"]), d["location"]["row"], d["message"]))
    v = tool("vulture")
    if v:
        r = run([v, *[str(p) for p in py_files()], "--min-confidence", "100"])
        for ln in r.stdout.splitlines():
            m = re.match(r"(.+?):(\d+): (unsatisfiable|unreachable|unused variable)(.*)", ln)
            if m and "unused variable" not in m.group(3):
                items.append(("VULTURE", Path(m.group(1)), int(m.group(2)), ln.split(": ", 1)[1]))
    out = ["# Ručno za popraviti", "",
           "Ovo skripta ne smije mijenjati bez da vidi namjeru koda. Zalijepi sadržaj (ili pojedine blokove) u chat i riješit ćemo.", ""]
    for code, p, row, msg in sorted(items, key=lambda x: (str(x[1]), x[2]))[:80]:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        a, b = max(0, row - 6), min(len(lines), row + 5)
        out.append(f"## {code} — {rel(p)}:{row}\n{msg}\n```python")
        for i in range(a, b):
            out.append(f"{'>>' if i + 1 == row else '  '} {i + 1:5d}  {lines[i].replace(chr(8), '<BACKSPACE>')}")
        out.append("```\n")
    (ROOT / "RUCNO_ZA_POPRAVITI.md").write_text("\n".join(out), encoding="utf-8")
    log(f"[12] RUCNO_ZA_POPRAVITI.md: {min(len(items), 80)} mjesta sa kontekstom koda")


# ------------------------------------------------------------ glavni tok
log(f"POPRAVKE — {ROOT}")
pre = syntax_errors()
if pre:
    log("!! Projekat već ima sintaksne greške, prekidam (popravi ih prvo):")
    log("\n".join(pre))
    sys.exit(1)
backup()
f821_prije = len(ruff_json("F821"))

for k in (korak_karantina, korak_pycache, korak_pyproject, korak_json, korak_f821_stdlib,
          korak_f401, korak_ruff_sigurno, korak_tajne, korak_env_example, korak_requirements, korak_readme):
    try:
        k()
    except Exception as e:
        log(f"!! {k.__name__} nije uspio: {e}")

post = syntax_errors()
f821_poslije = len(ruff_json("F821"))
if post or f821_poslije > f821_prije:
    log("!! Provjera nakon popravki NIJE prošla:")
    log("\n".join(post) or f"   nedefinisana imena: {f821_prije} -> {f821_poslije}")
    rollback()
    sys.exit(1)
log(f"provjera: sintaksa OK, nedefinisana imena {f821_prije} -> {f821_poslije}")
korak_rucno()
(WORK / f"popravi_{TS}.log").write_text("\n".join(LOG), encoding="utf-8")
log(f"\nVraćanje u prvobitno stanje: tar -xzf {BACKUP} -C {ROOT}")
PYEOF

"$PY" "$ROOT/.cistoca/popravi.py" "$ROOT"
RC=$?
[ $RC -eq 0 ] && echo && echo "Dalje: otvori RUCNO_ZA_POPRAVITI.md, pa ponovo pokreni tools/cistoca.sh"
exit $RC
