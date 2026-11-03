clear
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
MODE=${1:-dry}
LOG=".logs/judge_${MODE}_$TS.log"
PY=venv/bin/python3; [ -x "$PY" ] || PY=python3
export CHK=/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints
export APPLY=0; [ "$MODE" = "apply" ] && APPLY=1
if [ "$APPLY" = "1" ]; then
  tar czf /storage/emulated/0/Download/twoc_chk_bak_$TS.tar.gz -C "$(dirname "$CHK")" checkpoints \
    || { echo "FAIL: backup nije uspio, nista nije upisano"; exit 1; }
  ls -l /storage/emulated/0/Download/twoc_chk_bak_$TS.tar.gz
fi
{
echo "=== Judge -> Sutkinja | mod: $MODE ==="
$PY - <<'PY'
import os, re, glob, collections
CHK = os.environ["CHK"]; APPLY = os.environ["APPLY"] == "1"
tagre = re.compile(r"(<[^>]*>)")
wre = re.compile(r"\bJudge(?:ine|in|a)?\b")
OKPREV = {"je", "se", "ali", "reče", "dobaci", "kako"}
GEN = {"od", "kritike", "sudbine", "prisutnost", "glave"}

def odluka(seg, m):
    o = m.group(0)
    if o == "Judgea":   return "Sutkinje", "gen", False
    if o == "Judgeine": return "Sutkinjine", "pos", True
    if o == "Judgein":  return "Sutkinjin", "pos", True
    mm = re.search(r"([^\W\d_]+)\s+$", seg[max(0, m.start() - 30):m.start()])
    prev = mm.group(1).lower() if mm else None
    if prev == "prema":    return "Sutkinji", "dat", False
    if prev == "građanko": return "Sutkinjo", "voc", False
    if prev in GEN:        return "Sutkinje", "gen", False
    return "Sutkinja", "nom", not (prev is None or prev in OKPREV)

lista, brojac, promijenjeno = [], collections.Counter(), 0
for f in sorted(glob.glob(CHK + "/*.chk")):
    raw = open(f, encoding="utf-8", errors="strict", newline="").read()
    dijelovi = tagre.split(raw)
    part = os.path.basename(f).split(".html")[0]
    izmjena = False
    for i in range(0, len(dijelovi), 2):
        seg = dijelovi[i]
        if "Judge" not in seg:
            continue
        def zam(m, seg=seg):
            novo, vrsta, upit = odluka(seg, m)
            ctx = seg[max(0, m.start() - 35):m.start()] + "[[" + m.group(0) + "->" + novo + "]]" + seg[m.end():m.end() + 25]
            lista.append((part, vrsta, upit, " ".join(ctx.split())))
            brojac[(vrsta, upit)] += 1
            return novo
        novi = wre.sub(zam, seg)
        if novi != seg:
            dijelovi[i] = novi
            izmjena = True
    if izmjena:
        promijenjeno += 1
        if APPLY:
            open(f, "w", encoding="utf-8", newline="").write("".join(dijelovi))

print(f"izmjena: {len(lista)} u {promijenjeno} fajlova")
for (v, u), n in sorted(brojac.items()):
    print(f"  {v:4s} {'?' if u else ' '}  {n}")
print("\n-- SVE oznacene s ? (pregledaj) --")
for p, v, u, c in lista:
    if u: print(f"? {p} {v}: {c}")
print("\n-- uzorak neoznacenih (3 po vrsti) --")
vidjeno = collections.Counter()
for p, v, u, c in lista:
    if not u and vidjeno[v] < 3:
        vidjeno[v] += 1
        print(f"  {p} {v}: {c}")
if APPLY:
    ost = sum(len(re.findall(r"\bJudge", re.sub(r"<[^>]*>", "", open(f, encoding='utf-8').read()))) for f in glob.glob(CHK + "/*.chk"))
    print(f"\nPOSLIJE upisa: preostalo 'Judge' u .chk = {ost}")
else:
    print("\n(dry-run: nista nije upisano; za upis: bash tools/judge_fix.sh apply)")
PY
} 2>&1 | tee "$LOG"
bash tools/out.sh "$LOG"
echo "Log: $LOG"
