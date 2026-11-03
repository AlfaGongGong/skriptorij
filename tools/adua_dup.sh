clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
MODE=${1:-dry}
LOG=".logs/adua_dup_${MODE}_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export CHK=/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints
export S=/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub
export APPLY=0; [ "$MODE" = "apply" ] && APPLY=1
if [ "$APPLY" = "1" ]; then
  tar czf /storage/emulated/0/Download/twoc_chk_bak_adua_$TS.tar.gz -C "$(dirname "$CHK")" checkpoints \
    || { echo "FAIL: backup nije uspio, nista nije upisano"; exit 1; }
  ls -l /storage/emulated/0/Download/twoc_chk_bak_adua_$TS.tar.gz
fi
{
echo "=== 1. ADUA | mod: $MODE ==="
$PY - <<'PY'
import os, re, glob, collections
CHK = os.environ["CHK"]; APPLY = os.environ["APPLY"] == "1"
tagre = re.compile(r"(<[^>]*>)")
wre = re.compile(r"\bAdua\b")
PR = [
 ("gen", "Adue", r"iz|od|do|kraj|blizu|oko|ispred|iza|nakon|poslije|bez|zbog|tijekom|unutar|izvan|protiv|nasred"),
 ("dat", "Adui", r"prema|k|ka"),
 ("loc", "Adui", r"o|pri"),
]
PR = [(v, f, re.compile(r"(?<!\w)(?:" + rx + r")\s+$", re.I)) for v, f, rx in PR]
UNA = re.compile(r"(?<!\w)(?:u|na)\s+$", re.I)
SSA = re.compile(r"(?<!\w)(?:s|sa)\s+$", re.I)
MOT = re.compile(r"\b(?:ići|ide|idu|išao|išla|išli|otišao|otišla|otišli|došao|došla|došli|doći|dolazi|dolaze|otići|odlazi|odlaze|stigao|stigla|stigli|stiže|stižu|vratio|vratila|vratili|vraća|vraćaju|krenuo|krenula|krenuli|kreće|pošao|pošla|pošli|poći|putuje|putovao|putovala|putovali|bježi|pobjegao|pobjegla|pobjegli|vodi|vode|odveo|odvela|odveli|uđe|ušao|ušla|ušli|ući|dođe|dođu|idem|vraćam)\b", re.I)

def odluka(seg, m):
    L = seg[max(0, m.start() - 60):m.start()]
    for v, f, rx in PR:
        if rx.search(L): return f, v, ""
    if UNA.search(L):
        return ("Aduu", "acc", "?") if MOT.search(L) else ("Adui", "loc", "?")
    if SSA.search(L): return None, "s/sa", "??"
    return None, "nom/ostalo", "??"

forme = collections.Counter()
lista, brojac, prev = [], collections.Counter(), collections.Counter()
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
            lista.append((part, vrsta, fl, ctx))
            brojac[(vrsta, fl)] += 1
            if fl == "??":
                mm = re.search(r"([^\W\d_]+)\W*$", L)
                prev[(mm.group(1).lower() if mm else "-")] += 1
            return novo or m.group(0)
        novi = wre.sub(zam, seg)
        if novi != seg:
            dijelovi[i] = novi; izmjena = True
    if izmjena:
        promijenjeno += 1
        if APPLY: open(f, "w", encoding="utf-8", newline="").write("".join(dijelovi))

print("oblici u .chk (prije):", dict(forme))
print(f"pojava 'Adua': {len(lista)} | mijenja se u {promijenjeno} fajlova")
for (v, fl), n in sorted(brojac.items()):
    print(f"  {v:10s} {fl or ' ':2s} {n}")
print("\n-- ? (u/na: primjenjuje se, PREGLEDAJ) --")
for p, v, fl, c in lista:
    if fl == "?": print(f"? {p} {v}: {c}")
print("\n-- ?? prethodna rijec (ne mijenja se), top 20 --")
print(prev.most_common(20))
print("\n-- ?? uzorak (30) --")
k = 0
for p, v, fl, c in lista:
    if fl == "??" and k < 30:
        print(f"?? {p} {v}: {c}"); k += 1
print("\n-- sigurno, uzorak (2 po vrsti) --")
vid = collections.Counter()
for p, v, fl, c in lista:
    if not fl and vid[v] < 2:
        vid[v] += 1; print(f"  {p} {v}: {c}")
if APPLY:
    ost = sum(len(wre.findall(re.sub(r"<[^>]*>", "", open(f, encoding="utf-8").read()))) for f in glob.glob(CHK + "/*.chk"))
    print(f"\nPOSLIJE upisa: preostalo golo 'Adua' u .chk = {ost}")
else:
    print("\n(dry-run: nista nije upisano; za upis: bash tools/adua_dup.sh apply)")
PY
if [ "$MODE" = "dry" ]; then
echo
echo "=== 2. DUPLIKATI u STYLED (recenice >=50 znakova, po poglavlju) ==="
$PY - <<'PY2'
import os, re, zipfile, html, collections
tag = re.compile(r"<[^>]+>"); par = re.compile(r"<p[\s>].*?</p>", re.S | re.I)
z = zipfile.ZipFile(os.environ["S"])
grupe = []
for nm in sorted(z.namelist()):
    if not nm.lower().endswith((".xhtml", ".html")): continue
    ps = [html.unescape(tag.sub("", x)).strip() for x in par.findall(z.read(nm).decode("utf-8", "ignore"))]
    poz = collections.defaultdict(list)
    for i, t in enumerate(ps):
        for s in re.split(r"(?<=[.!?\u2026\u201d\"])\s+", t):
            k = re.sub(r"\W+", " ", s).strip().lower()
            if len(k) >= 50: poz[k].append(i)
    for k, v in poz.items():
        if len(v) > 1: grupe.append((nm.split("/")[-1], len(v), v, k))
isti = [g for g in grupe if len(set(g[2])) < len(g[2])]
susj = [g for g in grupe if g not in isti and max(g[2]) - min(g[2]) <= 3]
dalj = [g for g in grupe if g not in isti and g not in susj]
print(f"grupa: {len(grupe)} | isti odlomak: {len(isti)} | susjedni (<=3 odlomka): {len(susj)} | dalji: {len(dalj)}")
po = collections.Counter(g[0] for g in grupe)
print("po poglavlju (top 10):", po.most_common(10))
print("-- 25 grupa (najvise ponavljanja) | poglavlje, x, odlomci, tekst --")
for g in sorted(grupe, key=lambda x: -x[1])[:25]:
    print(f"  {g[0]} x{g[1]} {g[2]}: {g[3][:70]}")
PY2
echo
echo "=== 3. styler.py 1318-1395 (logika uklanjanja duplikata) ==="
sed -n '1318,1395p' epub/styler.py
fi
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
