clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
MODE=${1:-dry}
LOG=".logs/adua_dup2_${MODE}_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export CHK=/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints
export APPLY=0; [ "$MODE" = "apply" ] && APPLY=1
if [ "$APPLY" = "1" ]; then
  tar czf /storage/emulated/0/Download/twoc_chk_bak_adua2_$TS.tar.gz -C "$(dirname "$CHK")" checkpoints \
    || { echo "FAIL: backup nije uspio, nista nije upisano"; exit 1; }
  ls -l /storage/emulated/0/Download/twoc_chk_bak_adua2_$TS.tar.gz
fi
{
echo "=== 1. ADUA v2 | mod: $MODE ==="
$PY - <<'PY'
import os, re, glob, collections
CHK = os.environ["CHK"]; APPLY = os.environ["APPLY"] == "1"
tagre = re.compile(r"(<[^>]*>)")
wre = re.compile(r"\bAdua\b")
GENP = r"iz|od|do|kraj|blizu|oko|ispred|iza|nakon|poslije|bez|zbog|tijekom|unutar|izvan|protiv|nasred|diljem"
GENN = r"zidinama|građanima|građani|sjedišta|klase|društva|okrugu|stjegova"
PR = [
 ("gen", "Adue", GENP, ""),
 ("dat", "Adui", r"prema|k|ka", ""),
 ("loc", "Adui", r"o|pri", ""),
 ("gen", "Adue", GENN, "?"),
 ("acc", "Aduu", r"za|posjetio|posjetila|posjetili", "?"),
]
PR = [(v, f, re.compile(r"(?<!\w)(?:" + rx + r")\s+$", re.I), fl) for v, f, rx, fl in PR]
UNA = re.compile(r"(?<!\w)(?:u|na)\s+$", re.I)
MOT = re.compile(r"\b(?:ići|ide|idu|išao|išla|išli|otišao|otišla|otišli|došao|došla|došli|doći|dolazi|dolaze|otići|odlazi|odlaze|stigao|stigla|stigli|stiže|stižu|vratio|vratila|vratili|vraća|vraćaju|vrati|vrate|krenuo|krenula|krenuli|kreće|pošao|pošla|pošli|poći|putuje|putovao|putovala|putovali|bježi|pobjegao|pobjegla|pobjegli|vodi|vode|odveo|odvela|odveli|uđe|ušao|ušla|ušli|ući|dođe|dođu|idem|vraćam|natrag|umarš\w+|dopremi\w+)\b", re.I)

def odluka(seg, m):
    L = seg[max(0, m.start() - 60):m.start()]
    for v, f, rx, fl in PR:
        if rx.search(L): return f, v, fl
    if UNA.search(L):
        return ("Aduu", "acc", "?") if MOT.search(L) else ("Adui", "loc", "?")
    return None, "nom/ostalo", "??"

forme = collections.Counter()
lista, brojac = [], collections.Counter()
promijenjeno = 0
for f in sorted(glob.glob(CHK + "/*.chk")):
    raw = open(f, encoding="utf-8", newline="").read()
    forme.update(re.findall(r"\b(Adua|Adue|Adui|Aduu|Aduom)\b", re.sub(r"<[^>]*>", "", raw)))
    dijelovi = tagre.split(raw)
    part = os.path.basename(f).split(".html")[0]
    izmjena = False
    for i in range(0, len(dijelovi), 2):
        seg = dijelovi[i]
        if "Adua" not in seg: continue
        def zam(m, seg=seg):
            novo, vrsta, fl = odluka(seg, m)
            L = seg[max(0, m.start() - 60):m.start()]
            ctx = " ".join((L[-35:] + "[[Adua->" + (novo or "Adua") + "]]" + seg[m.end():m.end() + 25]).split())
            lista.append((part, vrsta, fl, ctx, novo is not None))
            brojac[(vrsta, fl)] += 1
            return novo or m.group(0)
        novi = wre.sub(zam, seg)
        if novi != seg:
            dijelovi[i] = novi; izmjena = True
    if izmjena:
        promijenjeno += 1
        if APPLY: open(f, "w", encoding="utf-8", newline="").write("".join(dijelovi))

print("oblici u .chk (prije):", dict(forme))
izm = sum(1 for x in lista if x[4])
print(f"pojava 'Adua': {len(lista)} | MIJENJA SE: {izm} (ocekivano 25) | ostaje: {len(lista)-izm} (ocekivano 7)")
for (v, fl), n in sorted(brojac.items()):
    print(f"  {v:10s} {fl or ' ':2s} {n}")
print("\n-- SVE izmjene --")
for p, v, fl, c, ch in lista:
    if ch: print(f"{fl or ' '} {p} {v}: {c}")
print("\n-- ostaje nepromijenjeno --")
for p, v, fl, c, ch in lista:
    if not ch: print(f"  {p}: {c}")
if APPLY:
    ost = sum(len(wre.findall(re.sub(r"<[^>]*>", "", open(f, encoding="utf-8").read()))) for f in glob.glob(CHK + "/*.chk"))
    print(f"\nPOSLIJE upisa: preostalo golo 'Adua' u .chk = {ost} (ocekivano 7)")
else:
    print("\n(dry-run: nista nije upisano; za upis: bash tools/adua_dup2.sh apply)")
PY

if [ "$MODE" = "dry" ]; then
echo
echo "=== 2. DUPLIKATI: simulacija brisanja preklopljenog pocetka bloka (.chk, sve knjiga) ==="
$PY - <<'PY2'
import os, re, glob, json, difflib, html, collections
CHK = os.environ["CHK"]
tag = re.compile(r"<[^>]+>")
def sadrzaj(p):
    t = open(p, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", t)
    if t.strip().startswith("{"):
        try:
            d = json.loads(t)
            for k in ("finalno_polirano", "korektura", "tekst", "translated"):
                if isinstance(d.get(k), str): return d[k]
        except Exception: pass
    return t
def odlomci(t):
    ps = re.findall(r"<p[\s>].*?</p>", t, flags=re.S | re.I) if "<p" in t.lower() else re.split(r"\n\s*\n", t)
    out = []
    for x in ps:
        s = " ".join(html.unescape(tag.sub("", x)).split())
        if s: out.append(s)
    return out
def norm(s): return re.sub(r"\W+", " ", s.lower()).strip()
def slican(a, b):
    a, b = norm(a), norm(b)
    if not a or not b: return False
    if a == b: return True
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.real_quick_ratio() >= 0.85 and sm.quick_ratio() >= 0.85 and sm.ratio() >= 0.85
po = collections.defaultdict(dict)
for f in glob.glob(CHK + "/*.chk"):
    st = os.path.basename(f)[:-4]
    if st.endswith((".prevod", ".lektura")): continue
    m = re.match(r"(.+?)_blok_(\d+)$", st)
    if m: po[m.group(1)][int(m.group(2))] = f
res, parova = [], 0
for ch in sorted(po):
    idx = sorted(po[ch])
    P = [odlomci(sadrzaj(po[ch][i])) for i in idx]
    for a in range(len(idx) - 1):
        parova += 1
        pv, nx = P[a], P[a + 1]
        if not pv or not nx: continue
        for j in range(max(0, len(pv) - 60), len(pv)):
            if slican(pv[j], nx[0]):
                k = 0
                while j + k < len(pv) and k < len(nx) and slican(pv[j + k], nx[k]): k += 1
                if j + k == len(pv) and sum(len(norm(x)) for x in nx[:k]) >= 60:
                    res.append((ch, idx[a], idx[a + 1], k, sum(len(x.split()) for x in nx[:k]), pv[-1][-90:], nx[0][:90]))
                    break
print(f"susjednih parova blokova: {parova} | s preklapanjem: {len(res)} | odlomaka za brisanje: {sum(r[3] for r in res)} | rijeci: {sum(r[4] for r in res)}")
print("raspodjela k (odlomaka u preklapanju):", sorted(collections.Counter(r[3] for r in res).items()))
pc = collections.Counter()
for r in res: pc[r[0]] += r[3]
print("po poglavlju (odlomaka, top 12):", pc.most_common(12))
print("-- part0207 --")
for r in res:
    if r[0].startswith("part0207"): print(f"   blok {r[1]}->{r[2]}: k={r[3]} ({r[4]} rijeci) | pocetak next: {r[6]}")
print("-- 4 uzorka (kraj prev | pocetak next) --")
for r in sorted(res, key=lambda x: -x[3])[:4]:
    print(f"   {r[0]} {r[1]}->{r[2]} k={r[3]}")
    print(f"     prev: ...{r[5]}")
    print(f"     next: {r[6]}...")
PY2

echo
echo "=== 3. Funkcije koje trebam vidjeti za STARO/NOVO ==="
$PY - <<'PY3'
import ast, glob
names = {"_skrati_overlap", "_je_duplikat", "_spoji_blokove"}
nadjeno = set()
for p in sorted(glob.glob("epub/*.py") + glob.glob("core/*.py") + glob.glob("processing/*.py")):
    try:
        src = open(p, encoding="utf-8").read(); tree = ast.parse(src)
    except Exception:
        continue
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in names and n.name not in nadjeno:
            nadjeno.add(n.name)
            seg = ast.get_source_segment(src, n).splitlines()
            print(f"--- {p}:{n.lineno} {n.name} ({len(seg)} linija, prvih 80) ---")
            print("\n".join(seg[:80]))
print("nije nadjeno:", sorted(names - nadjeno))
PY3
fi
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
