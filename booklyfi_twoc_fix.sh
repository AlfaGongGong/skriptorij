#!/bin/bash
# TWOC: promocija 5 blokova + tipografija navodnika (kod + .chk) + repack
cd /root/skriptorij || exit 1
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "/root/skriptorij" ] || { echo "STOP"; exit 1; }
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/twoc_fix_$TS.log"
BK=".logs/twoc_bak_$TS"
mkdir -p "$BK/chk"
export CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
export EPUB_DIR="/storage/emulated/0/Books/MoonReader/STYLED"
export BOOK_FILE="The_Wisdom_of_Crowds.epub"

vrati_kod() { cp "$BK/text_utils.py" core/text_utils.py; echo ">>> text_utils.py vracen iz backupa"; }

{
echo "=== HEAD: $(git rev-parse --short HEAD) ==="
git status --short --untracked-files=no
cp core/text_utils.py "$BK/text_utils.py" || exit 1
cp "$CK"/*.chk "$BK/chk/" 2>/dev/null
cp "$CK/quality_scores.json" "$BK/" 2>/dev/null
echo "Backup: $BK ($(ls "$BK/chk" | wc -l) chk fajlova)"

echo
echo "=== 1. PATCH core/text_utils.py ==="
venv/bin/python3 << 'PYEOF'
import sys
P = "core/text_utils.py"
src = open(P, encoding="utf-8").read()

FUNK = r'''def _navodnici_u_tekstu(html: str) -> str:
    """2026-11-02: navodnici po stanju unutar odlomka (radi i preko <em>).
    Mijenja samo tekst izvan tagova: ASCII " i otvarajuci/zatvarajuci
    tipografski dobivaju oblik „ ... ”. Odlomak koji pocinje crticom, a ima
    neparan broj ASCII navodnika, ostaje netaknut (stray " rjesava kasniji
    korak)."""
    import re as _re

    otv, zat = "\u201e", "\u201d"
    izlaz = []
    for seg in _re.split(r"(?i)(?=<p[\s>])", html):
        dij = _re.split(r"(<[^>]+>)", seg)
        tekstovi = dij[0::2]
        if not any(c in t for t in tekstovi for c in ('"', "\u201c", "\u201d", "\u201e")):
            izlaz.append(seg)
            continue
        n_ascii = sum(t.count('"') for t in tekstovi)
        prvi = next((t.strip() for t in tekstovi if t.strip()), "")
        if prvi.startswith(("\u2014", "\u2013")) and n_ascii % 2 == 1:
            izlaz.append(seg)
            continue
        otvoren = False
        for i in range(0, len(dij), 2):
            nova = []
            for c in dij[i]:
                if c in ('"', "\u201c"):
                    if otvoren:
                        nova.append(zat)
                        otvoren = False
                    else:
                        nova.append(otv)
                        otvoren = True
                elif c == "\u201e":
                    nova.append(c)
                    otvoren = True
                elif c == "\u201d":
                    nova.append(c)
                    otvoren = False
                else:
                    nova.append(c)
            dij[i] = "".join(nova)
        izlaz.append("".join(dij))
    return "".join(izlaz)


'''

A1 = "def _post_process_tipografija(tekst: str) -> str:"
A2 = '    _linije = tekst.split("\\n")'
for naziv, a in (("A1", A1), ("A2", A2)):
    n = src.count(a)
    print(f"{naziv}: pojavljivanja = {n}")
    if n != 1:
        print("STOP"); sys.exit(1)
if "_navodnici_u_tekstu" in src:
    print("STOP: vec primijenjeno"); sys.exit(1)

src = src.replace(A1, FUNK + A1, 1)
src = src.replace(
    A2,
    "    # 2026-11-02: navodnici po stanju unutar odlomka (preko <em> itd.)\n"
    "    tekst = _navodnici_u_tekstu(tekst)\n" + A2, 1)
open(P, "w", encoding="utf-8").write(src)
print("izmjena upisana")
PYEOF
if [ $? -ne 0 ]; then vrati_kod; exit 1; fi

venv/bin/python3 -c "import ast; ast.parse(open('core/text_utils.py',encoding='utf-8').read()); print('ast OK')" \
  && venv/bin/python3 -m py_compile core/text_utils.py && echo "compile OK" \
  || { vrati_kod; exit 1; }

echo
echo "=== 2. TESTOVI funkcije ==="
venv/bin/python3 << 'PYEOF'
import sys
sys.path.insert(0, ".")
from core.text_utils import _navodnici_u_tekstu as f, _post_process_tipografija as pp
ok = True
def t(naziv, uvjet, info=""):
    global ok
    print(("OK    " if uvjet else "GRESKA"), naziv, info if not uvjet else "")
    if not uvjet: ok = False

r = f('<p>"Hej," rekao je.</p>')
t("ASCII par", r == '<p>\u201eHej,\u201d rekao je.</p>', r)
r = f('<p class="x">"Tekst <em>naglasak</em> dalje."</p>')
t("preko <em>, atribut netaknut", r == '<p class="x">\u201eTekst <em>naglasak</em> dalje.\u201d</p>', r)
r = f('<p>\u201cHej,\u201d rekao je.</p>')
t("“…” -> „…”", r == '<p>\u201eHej,\u201d rekao je.</p>', r)
r = f('<p>\u201eHej,\u201c rekao je.</p>')
t("„…“ -> „…”", r == '<p>\u201eHej,\u201d rekao je.</p>', r)
r = f('<p>\u2014 Reče on."</p>')
t("crtica + neparan ASCII ostaje", r == '<p>\u2014 Reče on."</p>', r)
r = f('<p>"A" i "B"</p><p>"C"</p>')
t("vise odlomaka, stanje se resetira", r == '<p>\u201eA\u201d i \u201eB\u201d</p><p>\u201eC\u201d</p>', r)
for u in ('<p>"Hej," rekao je.</p>', '<p>\u201cA\u201d</p>', '<p>\u201eA\u201d</p>'):
    t("idempotentno", f(f(u)) == f(u))
r = pp('<p class="x">"Hej," rekao je.</p>')
t("pun pp: atribut ok + citat", 'class="x"' in r and "\u201eHej,\u201d" in r, r)
print("\nTESTOVI PROSLI" if ok else "\nTESTOVI PALI")
sys.exit(0 if ok else 1)
PYEOF
if [ $? -ne 0 ]; then vrati_kod; exit 1; fi

echo
echo "=== 3+4. Promocija 5 blokova + navodnici u .chk ==="
venv/bin/python3 << 'PYEOF'
import os, re, sys, json, glob, shutil
sys.path.insert(0, ".")
from core.text_utils import _navodnici_u_tekstu as nav
CK = os.environ["CK"]
HDR = re.compile(r"<!--\s*chunk_sha[^>]*-->\s*\n?")
CUT = re.compile(r"<[^<>]*$")
def atomic(p, t):
    open(p + ".tmp", "w", encoding="utf-8").write(t)
    os.replace(p + ".tmp", p)

sc = json.load(open(CK + "/quality_scores.json", encoding="utf-8"))
PROM = ["part0189.html_blok_2", "part0192.html_blok_6", "part0192.html_blok_8",
        "part0235.html_blok_0", "part0244.html_blok_0"]
print("-- promocija")
for b in PROM:
    src, dst = f"{CK}/{b}.prevod.chk", f"{CK}/{b}.chk"
    raw = open(src, encoding="utf-8", errors="replace").read()
    cur = open(dst, encoding="utf-8", errors="replace").read() if os.path.exists(dst) else ""
    t = HDR.sub("", raw)
    if cur and "NEPREVEDENO" not in cur:
        print(f"  {b}: vec ima pravi sadrzaj, preskacem"); continue
    if (len(t.strip()) < 200 or CUT.search(t.rstrip()) or "NEPREVEDENO" in t
            or len(re.findall(r"<p\b", t)) != len(re.findall(r"</p>", t))):
        print(f"  {b}: prevod.chk NE PROLAZI provjeru, preskacem"); continue
    if not HDR.match(raw):
        m = HDR.match(cur)
        if m: raw = m.group(0).rstrip("\n") + "\n" + raw
    atomic(dst, raw)
    sc[b] = 6.0
    print(f"  {b}: promovisan ({len(t)} zn), ocjena 6.0, header={'da' if HDR.match(raw) else 'NE'}")
atomic(CK + "/quality_scores.json", json.dumps(sc, ensure_ascii=False))

print("-- navodnici u .chk")
tag = re.compile(r"<[^>]+>")
qch = "\"\u201c\u201d\u201e"
izm = skip = 0
pre = {"ascii": 0, "„": 0, "“": 0, "”": 0}
post = dict(pre)
def brojaci(d, t):
    p = tag.sub("", t)
    d["ascii"] += p.count('"'); d["„"] += p.count("„"); d["“"] += p.count("“"); d["”"] += p.count("”")
for p in sorted(glob.glob(CK + "/*.chk")):
    if p.endswith((".prevod.chk", ".lektura.chk")): continue
    t = open(p, encoding="utf-8", errors="replace").read()
    if "NEPREVEDENO" in t: continue
    n = nav(t)
    brojaci(pre, t); brojaci(post, n)
    if n == t: continue
    if tag.findall(t) != tag.findall(n) or \
       re.sub("[" + qch + "]", "", tag.sub("", t)) != re.sub("[" + qch + "]", "", tag.sub("", n)):
        skip += 1
        print("  PRESKOCEN (tagovi/slova bi se promijenili):", os.path.basename(p)); continue
    atomic(p, n); izm += 1
print(f"  izmijenjeno: {izm} | preskoceno: {skip}")
print(f"  znakova u tekstu PRIJE : {pre}")
print(f"  znakova u tekstu POSLIJE: {post}")
PYEOF
if [ $? -ne 0 ]; then echo "CHK KORAK PAO — backup u $BK"; exit 1; fi

echo
echo "=== 5. Repack EPUB-a ==="
venv/bin/python3 << 'PYEOF'
import os, re, sys, json, time, glob, zipfile, urllib.request
sys.path.insert(0, ".")
try:
    from core.quality import _CACHE_ACCEPT_SCORE as ACC
except Exception as e:
    ACC = None; print("ACCEPT nije citljiv:", repr(e))
print("_CACHE_ACCEPT_SCORE =", ACC)
if ACC is None or ACC > 6.0:
    print("SKIP: resume bi ponovo obradio blokove ispod praga. Pokreni Start u UI-ju ")
    print("      kad si spreman za to (promovisani blokovi imaju 6.0).")
    sys.exit(0)
def api(path, data=None):
    req = urllib.request.Request("http://127.0.0.1:8080" + path,
          data=json.dumps(data).encode() if data else None,
          headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())
try:
    st = api("/api/status")
    if any(k in str(st.get("status", "")).lower() for k in ("run", "proc", "pokret", "obrad")):
        print("server vec radi, ne pokrecem:", st.get("status")); sys.exit(0)
    print("start:", api("/api/start", {"book": os.environ["BOOK_FILE"]}))
except Exception as e:
    print("API nedostupan:", repr(e)); sys.exit(0)
t0 = time.time(); zadnji = ""
while time.time() - t0 < 1500:
    time.sleep(15)
    try: st = api("/api/status")
    except Exception: continue
    s = f"{st.get('status')} {st.get('pct')}% {st.get('ok')}"
    if s != zadnji: print("  ", s); zadnji = s
    if "ZAVR" in str(st.get("status", "")).upper() and time.time() - t0 > 20: break
else:
    print("timeout 25 min — provjeri status u UI-ju")
PYEOF

echo
echo "=== 6. EPUB poslije ==="
venv/bin/python3 << 'PYEOF'
import os, re, glob, zipfile
ep = sorted(glob.glob(os.environ["EPUB_DIR"] + "/*Wisdom*PREVEDENO_STYLED.epub"), key=os.path.getmtime)[-1]
print(os.path.basename(ep), "|", __import__("time").strftime("%H:%M:%S", __import__("time").localtime(os.path.getmtime(ep))))
z = zipfile.ZipFile(ep)
tot = {"ascii": 0, "„": 0, "“": 0, "”": 0}; nepr = []; baj = 0; dij_ascii = 0
for n in z.namelist():
    if n.lower().endswith((".xhtml", ".html", ".htm")):
        t = z.read(n).decode("utf-8", "replace")
        p = re.sub(r"<[^>]+>", "", t)
        tot["ascii"] += p.count('"'); tot["„"] += p.count("„"); tot["“"] += p.count("“"); tot["”"] += p.count("”")
        if "NEPREVEDENO" in t: nepr.append(os.path.basename(n))
        baj += len(re.findall(r"Bajaz", t))
print("znakova u EPUB-u:", tot)
print("NEPREVEDENO u:", nepr, "| Bajaz:", baj)
PYEOF

echo
echo "=== 7. Kako se gradi nav.xhtml / TOC (za part0170) ==="
grep -n "nav.xhtml\|def .*nav\|def .*toc\|def .*sadrzaj" epub/*.py processing/*.py core/*.py 2>/dev/null | head -20

echo
echo "=== git status ==="
git status --short --untracked-files=no
echo "Rollback koda: cp $BK/text_utils.py core/text_utils.py | chk: cp $BK/chk/*.chk \$CK/"
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
