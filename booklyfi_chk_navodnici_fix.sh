#!/usr/bin/env bash
# booklyfi_chk_navodnici_fix.sh (v2)
#   bash booklyfi_chk_navodnici_fix.sh           -> dry-run (STARO/NOVO)
#   bash booklyfi_chk_navodnici_fix.sh --apply   -> backup + primjena + rebuild + gate
#   SIROCAD=convert ...                          -> i "siroce" zatvaranja idu u ” (nije preporuceno)
set -u
REPO="/root/skriptorij"
CK="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
BK="/storage/emulated/0/booklyfi_checkpoints/_backup"
MODE="dry"; [ "${1:-}" = "--apply" ] && MODE="apply"
SIROCAD="${SIROCAD:-rucno}"

# REPO GUARD (P18)
cd "$REPO" 2>/dev/null || { echo "STOP: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "STOP: nije repo"; exit 1; }
[ -d "$CK" ] || { echo "STOP: nema $CK"; exit 1; }

PY="venv/bin/python3"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs "$BK"
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/chk_navodnici_fix_$TS.log"
clear

main() {
    echo "=== chk_navodnici_fix v2 | mod=$MODE | sirocad=$SIROCAD | $TS ==="
    if [ "$MODE" = "apply" ]; then
        TAR="$BK/chk_pre_navodnici_fix_$TS.tar.gz"
        tar -czf "$TAR" -C "$CK" . || { echo "Backup NEUSPJEO, prekid."; return 1; }
        echo "Backup: $TAR"
    fi

    CK="$CK" MODE="$MODE" SIROCAD="$SIROCAD" "$PY" - << 'EOF_PY'
import os, re
from pathlib import Path

CK = Path(os.environ["CK"])
MODE = os.environ["MODE"]
CONVERT_ORPHANS = os.environ["SIROCAD"] == "convert"

P_PARA = re.compile(r'(?s)(<p\b[^>]*>.*?</p>)')
P_TAG = re.compile(r'(<[^>]+>)')
P_DASH = re.compile(r'([—–])[ \t\u00a0]+(”)')
P_ZAR = re.compile(r'„\s?,')
STRIP = re.compile(r'<[^>]+>')
APOS_BAD, APOS_OK = 'Stand-i"-the-Barrows', 'Stand-i’-the-Barrows'

cnt = {"quote": 0, "dash": 0, "rucno": 0, "apos": 0}
manual = []
zarez = []
changed_files = 0

def snip(old, new, w1=35, w2=45):
    a, b = STRIP.sub("", old), STRIP.sub("", new)
    i = len(os.path.commonprefix([a, b]))
    s = max(0, i - w1)
    return a[s:i + w2].replace("\n", "\\n"), b[s:i + w2].replace("\n", "\\n")

def conv_para(p):
    """Vraca (novi_p, n_conv, status); status: ok | rucno:<razlog>"""
    toks = P_TAG.split(p)
    out = []
    open_ = False
    last = ""
    n = nb = 0
    ambig = False
    for i, tok in enumerate(toks):
        if i % 2 == 1:
            out.append(tok)
            continue
        res = []
        for j, ch in enumerate(tok):
            if ch == "„":
                open_ = True
            elif ch == "”":
                open_ = False
            if ch != '"':
                res.append(ch)
                continue
            prev = tok[j - 1] if j > 0 else last
            nxt = tok[j + 1] if j + 1 < len(tok) else ""
            if open_:
                if (prev == "" or prev.isspace()) and nxt.isalnum():
                    ambig = True
                    res.append(ch)
                    continue
                res.append("”"); open_ = False; n += 1
            else:
                if prev and not prev.isspace() and prev not in "—–(" and not nxt.isalnum():
                    res.append("”"); nb += 1
                else:
                    res.append("„"); open_ = True; n += 1
        out.append("".join(res))
        if tok:
            last = tok[-1]
    if ambig:
        return p, 0, "rucno:dvosmisleno"
    if open_:
        return p, 0, "rucno:nezatvoreno (nastavlja se u sljedeci paragraf?)"
    if nb and not CONVERT_ORPHANS:
        return p, 0, f"rucno:{nb}x zatvaranje bez otvaranja (dash-dijalog)"
    return "".join(out), n, "ok"

for f in sorted(CK.glob("*.chk")):
    if f.name.endswith((".prevod.chk", ".lektura.chk")):
        continue
    orig = f.read_text("utf-8", "replace")
    work = orig
    ev = []

    # 0) mangled apostrof
    na = work.count(APOS_BAD)
    if na:
        cnt["apos"] += na
        ev.append(("APOSTROF", APOS_BAD, APOS_OK))
        work = work.replace(APOS_BAD, APOS_OK)

    # 1) ASCII navodnici po paragrafima
    def para_sub(m):
        p = m.group(1)
        if '"' not in STRIP.sub("", p):
            return p
        np_, n, st = conv_para(p)
        if st != "ok":
            cnt["rucno"] += 1
            manual.append((f.name, st, STRIP.sub("", p)[:110].replace("\n", "\\n")))
            return p
        if np_ != p:
            cnt["quote"] += n
            a, b = snip(p, np_)
            ev.append(("NAVODNIK", a, b))
        return np_
    t = P_PARA.sub(para_sub, work)

    # 2) razmak izmedju crte i ”
    toks = P_TAG.split(t)
    for i in range(0, len(toks), 2):
        for m in P_DASH.finditer(toks[i]):
            cnt["dash"] += 1
            a = toks[i][max(0, m.start() - 30):m.end() + 8].replace("\n", "\\n")
            ev.append(("CRTA", a, a.replace(m.group(0), m.group(1) + m.group(2))))
        toks[i] = P_DASH.sub(r"\1\2", toks[i])
    t = "".join(toks)

    # 3) samo prijava: zarez odmah iza otvarajuceg „
    tk = P_TAG.split(t)
    for i in range(0, len(tk), 2):
        for m in P_ZAR.finditer(tk[i]):
            zarez.append((f.name, tk[i][max(0, m.start() - 25):m.end() + 25].replace("\n", "\\n")))

    if t != orig:
        changed_files += 1
        print(f"\n--- {f.name}")
        for k, a, b in ev:
            print(f"  [{k}] STARO: ...{a}")
            print(f"           NOVO : ...{b}")
        if MODE == "apply":
            tmp = f.with_suffix(".chk.tmp")
            tmp.write_text(t, encoding="utf-8")
            os.replace(tmp, f)

print("\n=== RUCNO (nije dirano) ===")
if not manual:
    print("  nema")
for fn, st, tx in manual:
    print(f"  {fn} [{st}]: {tx}")

print("\n=== PRIJAVA: zarez iza otvarajuceg „ (izbrisana rijec? nije dirano) ===")
if not zarez:
    print("  nema")
for fn, tx in zarez:
    print(f"  {fn}: ...{tx}...")

print("\n=== Sazetak ===")
print(f"Fajlova za izmjenu    : {changed_files}")
print(f"Navodnika pretvoreno  : {cnt['quote']}")
print(f"Apostrof popravljen   : {cnt['apos']}")
print(f"Crta+razmak+” popravak: {cnt['dash']}")
print(f"Paragrafa za rucno    : {cnt['rucno']}")
print(f"'„,' ostataka (prijava): {len(zarez)}")

if MODE == "apply":
    left_q = left_d = 0
    for f in CK.glob("*.chk"):
        if f.name.endswith((".prevod.chk", ".lektura.chk")):
            continue
        tk = P_TAG.split(f.read_text("utf-8", "replace"))
        for i in range(0, len(tk), 2):
            left_q += tk[i].count('"')
            left_d += len(P_DASH.findall(tk[i]))
    print(f"Preostalo nakon primjene: ASCII \"={left_q} (ocekivano samo RUCNO), crta+razmak+”={left_d}")
else:
    print("\nDRY-RUN: nista nije upisano. Primjena: bash booklyfi_chk_navodnici_fix.sh --apply")
EOF_PY
    RC=$?
    [ $RC -eq 0 ] || return $RC

    if [ "$MODE" = "apply" ]; then
        echo
        echo "=== Rebuild + gate ==="
        bash tools/booklyfi_rebuild_gate.sh
        return $?
    fi
    return 0
}

main 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
[ -x tools/out.sh ] && bash tools/out.sh "$LOG"
echo "Log: $LOG"
exit $RC
