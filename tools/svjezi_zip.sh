#!/usr/bin/env bash
# svjezi_zip: pakira svjez kod (radno stanje, bez kljuceva) u KOD_ZA_CLAUDE.zip za novi chat.
# Koristenje: svjezi_zip [dodatna_datoteka ...]   (dodatne datoteke idu u primjeri/)
SELF=$(readlink -f "$0")
REPO=$(dirname "$(dirname "$SELF")")
cd "$REPO" || { echo "FAIL: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "FAIL: $REPO nije git repo"; exit 1; }
PK=/storage/emulated/0/Download/CLAUDE_HANDOFF_PACKAGE
mkdir -p "$PK" || { echo "FAIL: nema $PK"; exit 1; }
PY=python3; [ -x venv/bin/python ] && PY=venv/bin/python
export OUT="$PK/KOD_ZA_CLAUDE.zip"
"$PY" - "$@" <<'EOP'
import os, re, sys, zipfile, subprocess, datetime, hashlib
OUT = os.environ["OUT"]
def sh(*a): return subprocess.run(a, capture_output=True, text=True).stdout.splitlines()
head = sh("git", "rev-parse", "HEAD")[0]
nepohr = sh("git", "status", "--porcelain")
fajlovi = sorted(set(sh("git", "ls-files") + sh("git", "ls-files", "-o", "--exclude-standard")))
ISKLJ_DIR = (".logs/", "venv/", "__pycache__/", "node_modules/", ".git/")
ISKLJ_EXT = (".pyc", ".epub", ".zip", ".7z", ".gz", ".sqlite", ".db", ".so")
ISKLJ_IME = re.compile(r"(^|/)(\.env[^/]*|[^/]*quota_cooldowns\.json|[^/]*api[_-]?keys?[^/]*|[^/]*secrets?[^/]*|[^/]*credentials[^/]*|keys\.[a-z]+)$", re.I)
KLJUC = re.compile(r"(AIza[0-9A-Za-z_\-]{30,}|AQ\.[0-9A-Za-z_\-]{30,}|gsk_[0-9A-Za-z]{30,}|nvapi-[0-9A-Za-z_\-]{30,}|sk-[0-9A-Za-z_\-]{30,}|hf_[0-9A-Za-z]{30,}|csk-[0-9a-z]{30,})")
uk = 0; vel = 0; sumnjivi = []; dodatno = []
tmp = OUT + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for f in fajlovi:
        if not os.path.isfile(f) or f.startswith(ISKLJ_DIR) or "/__pycache__/" in f: continue
        if f.lower().endswith(ISKLJ_EXT) or os.path.getsize(f) > 1_500_000: continue
        if ISKLJ_IME.search(f): sumnjivi.append(f + " (ime)"); continue
        b = open(f, "rb").read()
        try: s = b.decode("utf-8")
        except UnicodeDecodeError: s = None
        if s is not None and KLJUC.search(s): sumnjivi.append(f + " (sadrzaj)"); continue
        z.writestr("kod/" + f, b); uk += 1; vel += len(b)
    for p in sys.argv[1:]:
        if os.path.isfile(p) and os.path.getsize(p) < 20_000_000:
            z.write(p, "primjeri/" + os.path.basename(p)); dodatno.append(os.path.basename(p))
        else:
            print(">> PRESKOCENO (nema ili preveliko):", p)
    info = [f"HEAD: {head}", f"vrijeme: {datetime.datetime.now():%F %T}",
            f"nepohranjenih izmjena u radnom stablu: {len(nepohr)}", "", "== status ==", *nepohr[:60],
            "", "== grane ==", *sh("git", "branch", "-a"), "", "== log (120) ==", *sh("git", "log", "--format=%h %ci %s", "-120")]
    z.writestr("GIT_INFO.txt", "\n".join(info))
os.replace(tmp, OUT)
sz = os.path.getsize(OUT)
print(f">> zip: {OUT}")
print(f">> {uk} fajlova koda ({vel//1024} KB), zip {sz//1024} KB, HEAD {head[:7]}, sha1 {hashlib.sha1(open(OUT,'rb').read()).hexdigest()[:10]}")
if dodatno: print(">> dodatno u primjeri/:", dodatno)
if nepohr: print(f">> UPOZORENJE: {len(nepohr)} nepohranjenih izmjena (zip sadrzi radno stanje, ne samo commit)")
for s in sumnjivi[:25]: print(">> SUMNJIVO (izbaceno):", s)
if sz > 25_000_000: print(">> UPOZORENJE: zip veci od 25 MB, upload ga mozda odbije")
EOP
RC=$?
echo ">> ZA NOVI CHAT posalji:"
for f in 01_PRAVILA.md 04_HANDOFF.md KOD_ZA_CLAUDE.zip; do
  if [ -f "$PK/$f" ]; then echo ">>   OK   $f ($(wc -c < "$PK/$f") B, $(stat -c %y "$PK/$f" | cut -c1-16))"; else echo ">>   NEMA $f"; fi
done
exit $RC
