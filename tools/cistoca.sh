#!/usr/bin/env bash
# tools/cistoca.sh — skeniranje i (opcionalno) čišćenje Python projekta
# Upotreba:
#   bash tools/cistoca.sh                  # samo izvještaj, ništa se ne mijenja
#   bash tools/cistoca.sh --fix            # backup + sigurne popravke + izvještaj
#   bash tools/cistoca.sh --dir /put/do/projekta
#   bash tools/cistoca.sh --bez-instalacije   # ne instaliraj alate
set -uo pipefail

FIX=0; DIR="."; INSTALL=1
while [ $# -gt 0 ]; do
  case "$1" in
    --fix) FIX=1 ;;
    --dir) shift; DIR="${1:-.}" ;;
    --bez-instalacije) INSTALL=0 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Nepoznata opcija: $1"; exit 2 ;;
  esac
  shift
done

cd "$DIR" || { echo "Ne mogu otvoriti $DIR"; exit 1; }
ROOT=$(pwd)
TS=$(date +%Y%m%d_%H%M%S)
WORK="$ROOT/.cistoca"; mkdir -p "$WORK"
REPORT="$ROOT/cistoca_izvjestaj.txt"
BACKUP="$WORK/backup_$TS.tar.gz"
KAR="$WORK/karantina_$TS"
FIXLOG="$WORK/fix_$TS.log"
PY=$(command -v python3 || command -v python || true)
[ -z "$PY" ] && { echo "Python nije pronađen"; exit 1; }

imaj() { command -v "$1" >/dev/null 2>&1; }

# ---------- pomoćno: pretraga fajlova uz izuzimanje smeća ----------
PRUNE=( -type d \( -name .git -o -name venv -o -name .venv -o -name env \
  -o -name node_modules -o -name __pycache__ -o -name .cistoca -o -name build \
  -o -name dist -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \
  -o -name site-packages \) -prune -o )
nadji() { find . "${PRUNE[@]}" "$@" -print; }
GEX=(--exclude-dir=.git --exclude-dir=venv --exclude-dir=.venv --exclude-dir=env
     --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=.cistoca
     --exclude-dir=build --exclude-dir=dist --exclude=cistoca_izvjestaj.txt)

mapfile -t PYF < <(nadji -type f -name '*.py')
[ "${#PYF[@]}" -eq 0 ] && { echo "Nema .py fajlova u $ROOT"; exit 1; }

# ---------- instalacija alata ----------
instaliraj_alate() {
  local par bin pkg
  for par in ruff:ruff vulture:vulture pylint:pylint bandit:bandit radon:radon \
             mypy:mypy deptry:deptry pytest:pytest; do
    bin="${par%%:*}"; pkg="${par##*:}"
    imaj "$bin" && continue
    echo "  instaliram $pkg ..."
    "$PY" -m pip install -q "$pkg" >/dev/null 2>&1 \
      || "$PY" -m pip install -q --break-system-packages "$pkg" >/dev/null 2>&1 \
      || echo "  (nije uspjelo: $pkg — sekcija će biti preskočena)"
  done
}

# ---------- embedded analizator (AST) ----------
cat > "$WORK/analiza.py" <<'PYEOF'
import ast, copy, collections, importlib.util, os, re, sys

root, mode = sys.argv[1], sys.argv[2]
SKIP = {".git", "venv", ".venv", "env", "node_modules", "__pycache__", ".cistoca",
        "build", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache", "site-packages"}
files = []
for d, ds, fs in os.walk(root):
    ds[:] = [x for x in ds if x not in SKIP]
    files += [os.path.join(d, f) for f in fs if f.endswith(".py")]

srcs, trees, errs = {}, {}, []
for p in files:
    try:
        srcs[p] = open(p, encoding="utf-8").read()
        trees[p] = ast.parse(srcs[p], p)
    except Exception as e:
        errs.append(f"[SINTAKSA] {p}: {e}")

def modname(p):
    rel = os.path.relpath(p, root)[:-3].replace(os.sep, ".")
    return rel[:-9] if rel.endswith(".__init__") else rel

def collect_imports():
    imported = collections.defaultdict(set)
    for p, t in trees.items():
        pkg = modname(p).split(".")
        is_init = os.path.basename(p) == "__init__.py"
        for n in ast.walk(t):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imported[a.name].add(p)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    base = pkg if is_init else pkg[:-1]
                    base = base[:max(0, len(base) - (n.level - 1))]
                    m = ".".join(base + ([n.module] if n.module else []))
                else:
                    m = n.module or ""
                imported[m].add(p)
                for a in n.names:
                    imported[(m + "." + a.name).strip(".")].add(p)
    return imported

if mode == "sintaksa":
    print("\n".join(errs))

elif mode == "importi":
    local = set()
    for p in files:
        local.add(modname(p).split(".")[0])
    for d in os.listdir(root):
        if os.path.isdir(os.path.join(root, d)):
            local.add(d)
    for p, t in trees.items():
        optional = set()
        for n in ast.walk(t):
            if isinstance(n, ast.Try):
                for b in n.body:
                    for x in ast.walk(b):
                        optional.add(id(x))
        for n in ast.walk(t):
            if id(n) in optional:
                continue
            names = []
            if isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
                names = [n.module]
            for nm in names:
                top = nm.split(".")[0]
                if top in local:
                    continue
                try:
                    ok = importlib.util.find_spec(top) is not None
                except Exception:
                    ok = False
                if not ok:
                    print(f"[NEMA MODULA] {p}:{n.lineno} import {nm}")

elif mode == "orfani":
    imported = collect_imports()
    ENTRY = re.compile(r"^(app|main|wsgi|asgi|manage|setup|conftest|run|cli)$|^test_|_test$")
    for p in sorted(files):
        base = os.path.basename(p)[:-3]
        if base == "__init__" or ENTRY.search(base):
            continue
        s = srcs.get(p, "")
        if "__name__ == \"__main__\"" in s or "__name__ == '__main__'" in s:
            continue
        m = modname(p)
        refs = {q for k, v in imported.items() if k == m or k.startswith(m + ".") for q in v} - {p}
        last = m.split(".")[-1]
        if not refs:
            refs = {q for k, v in imported.items() if k.split(".")[-1] == last for q in v} - {p}
        if not refs:
            dyn = [q for q, t in srcs.items() if q != p and re.search(r"['\"]%s['\"]" % re.escape(last), t)]
            extra = f"  (spominje se kao string u {dyn[0]} — možda dinamički import)" if dyn else ""
            print(f"[ORFAN] {p}{extra}")

elif mode == "duplikati":
    names = collections.defaultdict(set)
    bodies = collections.defaultdict(list)
    for p, t in trees.items():
        for n in t.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not n.name.startswith("__") and n.name not in ("main", "setup", "create_app"):
                    names[n.name].add(p)
        for n in ast.walk(t):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and (n.end_lineno - n.lineno) >= 5:
                c = copy.deepcopy(n)
                c.name = "_"
                c.decorator_list = []
                bodies[ast.dump(c)].append(f"{p}:{n.lineno} {n.name}()")
    for k, v in sorted(names.items()):
        if len(v) > 1:
            print(f"[ISTO IME] {k} definirano u: {', '.join(sorted(v))}")
    for v in bodies.values():
        if len(v) > 1:
            print("[ISTO TIJELO] " + "  ==  ".join(v))

elif mode == "velicina":
    for p, s in srcs.items():
        n = s.count("\n") + 1
        if n > 800:
            print(f"[VELIK FAJL] {p}: {n} redaka")
    for p, t in trees.items():
        for n in ast.walk(t):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                ln = n.end_lineno - n.lineno + 1
                if ln > 80:
                    print(f"[DUGA FUNKCIJA] {p}:{n.lineno} {n.name}() = {ln} redaka")
PYEOF

analiza() { "$PY" "$WORK/analiza.py" "$ROOT" "$1"; }

# =====================================================================
#  PROVJERE — svaka ispisuje SAMO nalaze (prazan izlaz = čisto)
# =====================================================================
# --- pokvareno ---
chk_sintaksa()   { analiza sintaksa; }
chk_importi()    { analiza importi; }
chk_ruff_bugovi(){ ruff check . --extend-exclude .cistoca --select F,E9,E722,B,PLE,PIE,S110 --output-format concise -q; }
chk_shell()      { local f; mapfile -t f < <(nadji -type f -name '*.sh'); [ "${#f[@]}" -gt 0 ] && shellcheck -S warning "${f[@]}"; }
chk_json() {
  local f
  while IFS= read -r f; do
    "$PY" -c "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))" "$f" 2>&1 | tail -n1 | sed "s|^|[JSON] $f: |"
  done < <(nadji -type f -name '*.json')
}
chk_testovi() {
  local ima; ima=$(nadji -type f \( -name 'test_*.py' -o -name '*_test.py' \) | head -n1)
  if [ -z "$ima" ]; then echo "nema testova — preporuka: bar smoke test za svaki provider i pipeline"; return; fi
  imaj pytest || { echo "pytest nije instaliran"; return; }
  "$PY" -m pytest -q --maxfail=5 2>&1 | grep -E 'FAILED|ERROR'
}
chk_tipovi()     { mypy --ignore-missing-imports --no-error-summary --exclude '(^|/)(venv|\.venv|env|node_modules|build|dist|\.cistoca)(/|$)' . 2>&1 | grep 'error:' | head -n 150; }

# --- ne koristi se / mrtvo ---
chk_mrtvi() {
  local vw=(); [ -f whitelist.py ] && vw=(whitelist.py)
  vulture "${PYF[@]}" "${vw[@]}" --min-confidence 80 \
    --ignore-decorators "@*.route,@*.errorhandler,@*.before_request,@*.after_request,@*.context_processor,@*.template_filter"
}
chk_orfani()     { analiza orfani; }
chk_deptry()     { { [ -f requirements.txt ] || [ -f pyproject.toml ]; } && deptry . --exclude 'venv|\.venv|env|\.cistoca|node_modules|build|dist' 2>&1 | grep -E 'DEP[0-9]+'; }
chk_zakomentirano(){ ruff check . --extend-exclude .cistoca --select ERA001 --output-format concise -q | head -n 150; }

# --- duplo ---
chk_dup_kod()    { pylint --disable=all --enable=duplicate-code --min-similarity-lines=8 "${PYF[@]}" 2>&1 | grep -vE '^\*+|rated at|^-+$|^$'; }
chk_dup_logika() { analiza duplikati; }
chk_dup_fajlovi(){ nadji -type f -size +0c ! -name '__init__.py' | xargs -r -d '\n' md5sum 2>/dev/null | sort | uniq -w32 -D; }

# --- smeće u projektu ---
chk_smece() {
  nadji -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.orig' -o -name '*.rej' -o -name '*.bak' \
    -o -name '*~' -o -name '*.swp' -o -name '.DS_Store' -o -name '*.tmp' \)
  find . "${PRUNE[@]/__pycache__/__nema__}" -type d -name __pycache__ -print 2>/dev/null | head -n 20
}
chk_sumnjiva_imena() {
  nadji -type f \( -iname '*_old*' -o -iname '*_copy*' -o -iname '*copy of*' -o -iname '*_backup*' \
    -o -iname '*_stari*' -o -iname '*_v[0-9]*' -o -iname '*_final*' -o -iname '*(1)*' -o -iname '*_tmp*' \)
}
chk_prazno() {
  nadji -type f -empty ! -name '__init__.py' ! -name '.gitkeep' | sed 's/^/[PRAZAN FAJL] /'
  find . "${PRUNE[@]}" -type d -empty -print | sed 's/^/[PRAZAN DIR] /'
}
chk_crlf()       { grep -rIlE "${GEX[@]}" $'\r' --include='*.py' --include='*.sh' . 2>/dev/null | sed 's/^/[CRLF] /'; }

# --- sigurnost ---
chk_bandit()     { bandit -q -r . -x ./venv,./.venv,./env,./.cistoca,./node_modules,./build,./dist -ll -f txt 2>/dev/null | grep -E '^>> Issue|Location:'; }
chk_tajne() {
  # ispisuje samo file:linija — nikad sam ključ
  grep -rnIE "${GEX[@]}" --exclude='.env*' \
    -e 'AIza[0-9A-Za-z_-]{35}' -e 'sk-[A-Za-z0-9_-]{20,}' -e 'ghp_[A-Za-z0-9]{36}' -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
    -e "(api[_-]?key|secret|token|passw(or)?d)[\"']?[[:space:]]*[=:][[:space:]]*[\"'][A-Za-z0-9_./+-]{16,}[\"']" . 2>/dev/null \
    | cut -d: -f1,2 | sed 's/^/[MOGUĆA TAJNA U KODU] /'
}

# --- debug ostaci i higijena koda ---
chk_debug() {
  grep -rnE "${GEX[@]}" --include='*.py' -e '\bbreakpoint\(\)' -e 'pdb\.set_trace' -e '^[[:space:]]*import i?pdb' . | cut -d: -f1,2
}
chk_print()      { ruff check . --extend-exclude .cistoca --select T20 --output-format concise -q | head -n 100; }
chk_todo()       { grep -rnIE "${GEX[@]}" --include='*.py' --include='*.sh' -e '\b(TODO|FIXME|XXX|HACK)\b' . | cut -c1-160 | head -n 100; }
chk_modeli() {
  # imena modela razbacana po kodu; trebaju biti na jednom mjestu (MODEL_MAP / config)
  grep -rnIE "${GEX[@]}" --include='*.py' -e "['\"](gemini|gemma|claude|gpt|mistral|llama|deepseek)-[A-Za-z0-9._-]+['\"]" . | cut -c1-140 | head -n 60
}
chk_slozenost()  { radon cc "${PYF[@]}" -n C -s; analiza velicina; }
chk_stil()       { ruff check . --extend-exclude .cistoca --select I,UP,C4,SIM,RET --output-format concise -q | head -n 200; }
chk_format()     { ruff format --check . --extend-exclude .cistoca 2>&1 | grep 'Would reformat'; }

# --- struktura projekta (best practice) ---
chk_higijena() {
  [ -f .gitignore ] || echo "nema .gitignore"
  { [ -f requirements.txt ] || [ -f pyproject.toml ]; } || echo "nema requirements.txt ni pyproject.toml (ovisnosti nisu zabilježene)"
  ls README* >/dev/null 2>&1 || echo "nema README"
  { [ -f pyproject.toml ] || [ -f ruff.toml ] || [ -f .ruff.toml ]; } || echo "nema konfiguracije alata (pyproject.toml ili ruff.toml)"
  if [ -f .env ]; then
    [ -f .env.example ] || echo "ima .env, ali nema .env.example (šablon bez tajni)"
    if git rev-parse --git-dir >/dev/null 2>&1; then
      git check-ignore -q .env || echo "KRITIČNO: .env nije u .gitignore"
      git ls-files --error-unmatch .env >/dev/null 2>&1 && echo "KRITIČNO: .env je praćen u gitu (rotiraj ključeve!)"
    else
      grep -qE '^\.env' .gitignore 2>/dev/null || echo "UPOZORENJE: .env nije u .gitignore"
    fi
  fi
  if [ -f requirements.txt ]; then
    grep -vE '^[[:space:]]*(#|$|-)' requirements.txt | grep -vE '==|@ ' | sed 's/^/nepinovano u requirements.txt: /'
  fi
  local d
  for d in $(nadji -type d | grep -vE '^\.$'); do
    ls "$d"/*.py >/dev/null 2>&1 && [ ! -f "$d/__init__.py" ] && [ "$d" != "./tools" ] && [ "$d" != "./tests" ] \
      && echo "folder sa .py fajlovima bez __init__.py: $d"
  done
}

# =====================================================================
#  POPRAVKE (samo uz --fix) — backup prije, provjera poslije, rollback ako pukne
# =====================================================================
napravi_backup() {
  tar -czf "$BACKUP" -C "$ROOT" \
    --exclude='./.cistoca' --exclude='./.git' --exclude='./venv' --exclude='./.venv' \
    --exclude='./env' --exclude='./node_modules' --exclude='__pycache__' . 2>/dev/null \
    && echo "  backup: $BACKUP"
}
vrati_backup() { tar -xzf "$BACKUP" -C "$ROOT" && echo "  ROLLBACK izvršen iz $BACKUP"; }

popravi() {
  echo "== POPRAVKE ==" | tee -a "$FIXLOG"
  if git rev-parse --git-dir >/dev/null 2>&1 && [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "  UPOZORENJE: ima nekomitovanih izmjena; preporučujem git commit prije --fix (backup svejedno postoji)"
  fi
  napravi_backup || { echo "  Backup nije uspio — prekidam, ništa nije mijenjano."; exit 1; }

  # 1) __pycache__ i *.pyc (sigurno, regenerišu se)
  find . \( -name .git -o -name venv -o -name .venv -o -name env -o -name node_modules \) -prune -o \
    -name __pycache__ -type d -print0 | xargs -0 -r rm -rf
  find . \( -name .git -o -name venv -o -name .venv -o -name env -o -name node_modules \) -prune -o \
    \( -name '*.pyc' -o -name '*.pyo' \) -type f -print0 | xargs -0 -r rm -f
  echo "  obrisani __pycache__ i *.pyc" | tee -a "$FIXLOG"

  # 2) .orig/.rej/.bak/~/.swp/.tmp -> karantina (reverzibilno, ništa se ne briše)
  local f n=0
  while IFS= read -r f; do
    mkdir -p "$KAR/$(dirname "$f")" && mv "$f" "$KAR/$f" && n=$((n+1))
  done < <(nadji -type f \( -name '*.orig' -o -name '*.rej' -o -name '*.bak' -o -name '*~' \
            -o -name '*.swp' -o -name '.DS_Store' -o -name '*.tmp' \))
  echo "  u karantinu: $n fajlova ($KAR)" | tee -a "$FIXLOG"

  # 3) .gitignore: kreiraj ili dopuni (uz kopiju stare verzije)
  [ -f .gitignore ] && cp .gitignore "$WORK/gitignore_$TS.bak"
  touch .gitignore
  local l
  for l in '__pycache__/' '*.pyc' '.venv/' 'venv/' '.env' '.env.*' '!.env.example' '.cistoca/' \
           '.ruff_cache/' '.mypy_cache/' '.pytest_cache/' '.coverage' '*.swp' '*.orig' '*.bak'; do
    grep -qxF -- "$l" .gitignore || echo "$l" >> .gitignore
  done
  echo "  .gitignore dopunjen" | tee -a "$FIXLOG"

  # 4) ruff: samo SIGURNE autopopravke (neiskorišteni importi, sortiranje importa, moderniji sintaks) + format
  if imaj ruff; then
    ruff check . --extend-exclude .cistoca --select F401,I,UP,C4,PIE --fix -q >>"$FIXLOG" 2>&1
    ruff format . --extend-exclude .cistoca -q >>"$FIXLOG" 2>&1
    echo "  ruff fix + format primijenjeni" | tee -a "$FIXLOG"
  else
    echo "  ruff nije instaliran — preskačem autopopravke" | tee -a "$FIXLOG"
  fi

  # 5) provjera da ništa nije puklo; ako jeste -> automatski rollback
  if [ -n "$(analiza sintaksa)" ]; then
    echo "  !! Nakon popravki postoje sintaksne greške:" | tee -a "$FIXLOG"
    analiza sintaksa | tee -a "$FIXLOG"
    vrati_backup
  else
    echo "  provjera sintakse: OK" | tee -a "$FIXLOG"
  fi
}

# =====================================================================
#  GLAVNI TOK
# =====================================================================
echo "Čistoća projekta: $ROOT  (mod: $([ $FIX -eq 1 ] && echo FIX || echo IZVJEŠTAJ))"
[ $INSTALL -eq 1 ] && { echo "Alati:"; instaliraj_alate; }
[ $FIX -eq 1 ] && popravi

{
  echo "ČISTOĆA — IZVJEŠTAJ  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Projekat: $ROOT"
  echo "Mod: $([ $FIX -eq 1 ] && echo 'FIX (stanje NAKON popravki)' || echo 'samo izvještaj')"
  echo "Broj u zagradi = redaka nalaza (0 = čisto)."
  [ $FIX -eq 1 ] && echo "Backup: $BACKUP | Karantina: $KAR"
} > "$REPORT"

declare -a SUM_N=() SUM_T=()
sekcija() {
  local naslov="$1" alat="$2"; shift 2
  local tmp n; tmp=$(mktemp)
  if [ "$alat" != "-" ] && ! imaj "$alat"; then
    printf '\n=== %s ===\nPRESKOČENO (nije instaliran: %s)\n' "$naslov" "$alat" >> "$REPORT"
    SUM_N+=("-"); SUM_T+=("$naslov"); printf '  [  -] %s\n' "$naslov"; rm -f "$tmp"; return
  fi
  "$@" > "$tmp" 2>&1 || true
  n=$(grep -c . "$tmp" || true)
  { printf '\n=== %s (%s) ===\n' "$naslov" "$n"; if [ "$n" -eq 0 ]; then echo "OK"; else cat "$tmp"; fi; } >> "$REPORT"
  SUM_N+=("$n"); SUM_T+=("$naslov")
  printf '  [%3s] %s\n' "$n" "$naslov"
  rm -f "$tmp"
}

echo; echo "Skeniram:"
echo " -- POKVARENO --"
sekcija "Sintaksne greške"                    -      chk_sintaksa
sekcija "Importi modula kojih nema"           -      chk_importi
sekcija "Bugovi (ruff: F,E9,B,PLE,PIE,S110)"  ruff   chk_ruff_bugovi
sekcija "Neispravni JSON fajlovi"             -      chk_json
sekcija "Shell skripte (shellcheck)"          shellcheck chk_shell
sekcija "Tipske greške (mypy)"                mypy   chk_tipovi
sekcija "Testovi"                             -      chk_testovi
echo " -- NE KORISTI SE --"
sekcija "Mrtav kod (vulture)"                 vulture chk_mrtvi
sekcija "Fajlovi koje niko ne importuje"      -      chk_orfani
sekcija "Ovisnosti: neiskorištene/nedostaju"  deptry chk_deptry
sekcija "Zakomentirani kod"                   ruff   chk_zakomentirano
echo " -- DUPLO --"
sekcija "Copy-paste blokovi (pylint)"         pylint chk_dup_kod
sekcija "Ista imena / ista tijela funkcija"   -      chk_dup_logika
sekcija "Identični fajlovi (md5)"             -      chk_dup_fajlovi
echo " -- SMEĆE --"
sekcija "Privremeni fajlovi i __pycache__"    -      chk_smece
sekcija "Sumnjiva imena (_old, _copy, _v2..)" -      chk_sumnjiva_imena
sekcija "Prazni fajlovi i folderi"            -      chk_prazno
sekcija "CRLF završeci redova"                -      chk_crlf
echo " -- SIGURNOST --"
sekcija "Bandit (srednji+ rizik, npr. debug=True)" bandit chk_bandit
sekcija "Moguće tajne/API ključevi u kodu"    -      chk_tajne
echo " -- KVALITET --"
sekcija "Debugger ostaci (breakpoint/pdb)"    -      chk_debug
sekcija "print() umjesto logging"             ruff   chk_print
sekcija "TODO/FIXME/HACK"                     -      chk_todo
sekcija "Imena modela razbacana po kodu"      -      chk_modeli
sekcija "Složenost i veličina (radon)"        radon  chk_slozenost
sekcija "Stil (importi, UP, SIM, RET)"        ruff   chk_stil
sekcija "Formatiranje (ruff format)"          ruff   chk_format
echo " -- STRUKTURA --"
sekcija "Higijena projekta"                   -      chk_higijena

UKUPNO=0
for n in "${SUM_N[@]}"; do [[ "$n" =~ ^[0-9]+$ ]] && UKUPNO=$((UKUPNO + n)); done
{
  echo; echo "=== SAŽETAK ==="
  for i in "${!SUM_T[@]}"; do printf '%5s  %s\n' "${SUM_N[$i]}" "${SUM_T[$i]}"; done
  echo "UKUPNO redaka nalaza: $UKUPNO"
  echo
  echo "REDOSLIJED RUČNOG ČIŠĆENJA:"
  echo " 1. Tajne u kodu / .env u gitu  -> odmah, i rotiraj ključ"
  echo " 2. Sintaksa, importi, bugovi   -> ono što ne radi"
  echo " 3. Orfani i mrtav kod          -> prvo grep po stringu (MODEL_MAP, rotacija po imenu)"
  echo " 4. Duplikati                   -> izvuci u zajedničku funkciju"
  echo " 5. Modeli razbacani po kodu    -> centralizuj u jedan config"
} >> "$REPORT"

echo; echo "UKUPNO redaka nalaza: $UKUPNO"
echo "Izvještaj: $REPORT"
[ $FIX -eq 1 ] && echo "Vraćanje: tar -xzf $BACKUP -C $ROOT"
exit 0
