#!/usr/bin/env bash
# booklyfi_chk_final_fix3.sh
#   - 6 rucnih paragrafa (dash-dijalog / govor), Calder u .chk (tag-tolerantno)
#   - Clover/Calder u text/*.html (part0225, part0238, part0211)
#   - backup .chk + text/, rebuild+gate, provjera zabranjenih imena, kontekst iz EPUB-a
set -u
REPO="/root/skriptorij"
WD="/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds"
BK="/storage/emulated/0/booklyfi_checkpoints/_backup"

# REPO GUARD (P18)
cd "$REPO" 2>/dev/null || { echo "STOP: nema $REPO"; exit 1; }
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$REPO" ] || { echo "STOP: nije repo"; exit 1; }
[ -d "$WD/checkpoints" ] && [ -d "$WD/text" ] || { echo "STOP: nema $WD/checkpoints ili text"; exit 1; }

PY="venv/bin/python3"; [ -x "$PY" ] || PY="python3"
mkdir -p .logs "$BK"
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/chk_final_fix3_$TS.log"
clear

main() {
    T1="$BK/chk_pre_final_fix3_$TS.tar.gz"
    T2="$BK/text_pre_final_fix3_$TS.tar.gz"
    tar -czf "$T1" -C "$WD/checkpoints" . || { echo "Backup .chk NEUSPJEO"; return 1; }
    tar -czf "$T2" -C "$WD" text || { echo "Backup text/ NEUSPJEO"; return 1; }
    echo "Backup  : $T1"
    echo "Backup  : $T2"
    echo "Rollback: tar -xzf $T1 -C $WD/checkpoints && tar -xzf $T2 -C $WD"

    WD="$WD" "$PY" - << 'EOF_PY'
import os, re, sys
from pathlib import Path

WD = Path(os.environ["WD"])
CK = WD / "checkpoints"
TX = WD / "text"
P_PARA = re.compile(r'(?s)(<p\b[^>]*>.*?</p>)')

# (fajl, [(staro, novo), ...]) -- svi 'staro' moraju biti u ISTOM paragrafu, svaki tacno 1x
RUCNO = [
    ("part0179.html_blok_4.chk", [
        ('uz to", zaklikta Hardbread, "a Nightfallovi', 'uz to — zaklikta Hardbread — a Nightfallovi'),
        ('za borbu.”', 'za borbu.')]),
    ("part0197.html_blok_6.chk", [
        ('Top!" Bilo', 'Top! Bilo'),
        ('prstiju." I ona', 'prstiju. I ona')]),
    ("part0197.html_blok_6.chk", [
        ('mene." Bayazove', 'mene. Bayazove'),
        ('zelene. "Ali', 'zelene. — Ali'),
        ('kratkovidne pogreške.”', 'kratkovidne pogreške.')]),
    ("part0197.html_blok_6.chk", [
        ('hrabra," reče', 'hrabra — reče'),
        ('vjetru.” Nagnuo', 'vjetru. Nagnuo'),
        ('u pepeo."', 'u pepeo.')]),
    ("part0206.html_blok_1.chk", [
        ('Stani, šapnu Šola', 'Stani — šapnu Šola'),
        ('Stani." Trzala', 'Stani. Trzala'),
        ('njega. "Nitko… jebeno… ne mrdaj.” Bio', 'njega. — Nitko… jebeno… ne mrdaj. Bio')]),
    ("part0210.html_blok_1.chk", [
        ('Anglanda. "Dok sam', 'Anglanda. „Dok sam'),
        ('poraza." Neke', 'poraza.” Neke'),
        ('razvedravati. "Znam', 'razvedravati. „Znam'),
        ('ispraviti." Vojnici', 'ispraviti.” Vojnici'),
        ('plaćeni. "Ali', 'plaćeni. „Ali'),
        ('bogalj." Cerio', 'bogalj.” Cerio')]),
]
# Calder u .chk: slova mogu biti razdvojena tagom -> mijenja se samo prvo slovo C->K
T = r'(?:<[^>]+>)*'
CALDER_TAG = re.compile(r'(?<![A-Za-zČĆŠŽĐčćšžđ])C(?=' + T + 'a' + T + 'l' + T + 'd' + T + 'e' + T + r'r(?![A-Za-z]))')
# tacne zamjene u text/*.html: (fajl, staro, novo), raw count mora biti tacno 1
HTML = [
    ("part0225.html", "Clover", "Klover"),
    ("part0238.html", "Clover", "Klover"),
    ("part0211.html", "Calder", "Kalder"),
]

P_TAG = re.compile(r'<[^>]+>')

def vmap(raw):
    """vidljivi tekst + mapa: indeks vidljivog znaka -> indeks u sirovom tekstu"""
    vis, idx, pos = [], [], 0
    for m in P_TAG.finditer(raw):
        for k in range(pos, m.start()):
            vis.append(raw[k]); idx.append(k)
        pos = m.end()
    for k in range(pos, len(raw)):
        vis.append(raw[k]); idx.append(k)
    return "".join(vis), idx

def vis_replace(raw, old, new):
    """zamijeni 'old' u VIDLJIVOM tekstu (tagovi izmedju znakova ostaju); mijenja samo razliku old/new"""
    vis, idx = vmap(raw)
    if vis.count(old) != 1:
        return None
    s0 = vis.find(old)
    pre = len(os.path.commonprefix([old, new]))
    suf = len(os.path.commonprefix([old[pre:][::-1], new[pre:][::-1]]))
    old_mid = old[pre:len(old) - suf]
    new_mid = new[pre:len(new) - suf]
    a = s0 + pre
    if old_mid:
        ra, rb = idx[a], idx[a + len(old_mid) - 1] + 1
        kept = "".join(P_TAG.findall(raw[ra:rb]))
        return raw[:ra] + new_mid + kept + raw[rb:]
    ra = idx[a] if a < len(idx) else len(raw)
    return raw[:ra] + new_mid + raw[ra:]

def vsnip(old_raw, new_raw, w=40):
    a, b = P_TAG.sub("", old_raw), P_TAG.sub("", new_raw)
    i = len(os.path.commonprefix([a, b]))
    s0 = max(0, i - w)
    return a[s0:i + 70].replace("\n", "\\n"), b[s0:i + 70].replace("\n", "\\n")

def ctx(s, i, n):
    return s[max(0, i - 45): i + n + 45].replace("\n", "\\n")

fail = []
plan = []   # (path, novi_tekst, [(staro_ctx, novo_ctx)])

# --- 1) ručni paragrafi + Calder u .chk (grupirano po fajlu)
by_file = {}
for fn, edits in RUCNO:
    by_file.setdefault(fn, {"edits": [], "calder": False})["edits"].append(edits)
by_file.setdefault("part0211.html_blok_0.chk", {"edits": [], "calder": False})["calder"] = True

for fn, spec in by_file.items():
    p = CK / fn
    if not p.is_file():
        fail.append(f"nema fajla {fn}"); continue
    raw = p.read_text("utf-8", "replace")
    ev = []
    for edits in spec["edits"]:
        def has_all(m):
            v = P_TAG.sub("", m.group(1))
            return all(v.count(o) == 1 for o, _ in edits)
        paras = [m for m in P_PARA.finditer(raw) if has_all(m)]
        if len(paras) != 1:
            fail.append(f"{fn}: paragraf za '{edits[0][0][:30]}...' nadjen {len(paras)}x (treba 1)"); continue
        m = paras[0]
        newp = m.group(1)
        ok = True
        for o, n in edits:
            before = newp
            res = vis_replace(before, o, n)
            if res is None:
                fail.append(f"{fn}: '{o}' nije 1x u vidljivom tekstu"); ok = False; break
            ev.append(vsnip(before, res))
            newp = res
        if ok:
            raw = raw[:m.start(1)] + newp + raw[m.end(1):]
    if spec["calder"]:
        hits = list(CALDER_TAG.finditer(raw))
        if len(hits) != 1:
            fail.append(f"{fn}: Calder (tag-tolerantno) nadjen {len(hits)}x (treba 1)")
        else:
            h = hits[0]
            old_c = ctx(raw, h.start(), 12)
            raw = raw[:h.start()] + "K" + raw[h.end():]
            ev.append((old_c, ctx(raw, h.start(), 12)))
    plan.append((p, raw, ev))

# --- 2) text/*.html tacne zamjene
for fn, old, new in HTML:
    p = TX / fn
    if not p.is_file():
        fail.append(f"nema fajla text/{fn}"); continue
    raw = p.read_text("utf-8", "replace")
    n = raw.count(old)
    if n != 1:
        fail.append(f"text/{fn}: '{old}' x{n} (treba 1)"); continue
    i = raw.find(old)
    plan.append((p, raw.replace(old, new, 1), [(ctx(raw, i, len(old)), ctx(raw, i, len(old)).replace(old, new))]))

if fail:
    print("STOP: nista nije upisano.")
    for f in fail:
        print("  -", f)
    sys.exit(2)

for p, newraw, ev in plan:
    print(f"\n--- {p.relative_to(WD)}")
    for a, b in ev:
        print(f"  STARO: ...{a}")
        print(f"  NOVO : ...{b}")
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(newraw, encoding="utf-8")
    os.replace(tmp, p)

TAG = re.compile(r"<[^>]+>")
files = [f for f in sorted(CK.glob("*.chk")) if not f.name.endswith((".prevod.chk", ".lektura.chk"))]
q = z = c = 0
for f in files:
    vis = TAG.sub("", f.read_text("utf-8", "replace"))
    q += vis.count('"'); z += len(re.findall(r"„\s?,", vis)); c += len(re.findall(r"\bCalder", vis))
print(f"\n=== Preostalo u .chk: ASCII \"={q} | „,={z} | Calder={c} (ocekivano 0 | 0 | 0) ===")
EOF_PY
    RC=$?
    [ $RC -eq 0 ] || { echo "STOP (rc=$RC): rebuild se ne pokrece. Nista nije upisano."; return $RC; }

    echo
    echo "=== Rebuild + gate ==="
    bash tools/booklyfi_rebuild_gate.sh
    GRC=$?

    echo
    echo "=== Zabranjena imena + velicina finalnog EPUB-a ==="
    P=$(ls -t .logs/last_styled_*.path 2>/dev/null | head -1)
    FINAL=$(cat "$P" 2>/dev/null)
    ls -l "$FINAL"
    "$PY" tools/epub_gate.py "$FINAL" --forbid Clover,Calder,Nail
    echo "forbid rc=$?"

    echo
    echo "=== Sirovi kontekst Clover/Calder/Nail u EPUB-u (max 8) ==="
    FINAL="$FINAL" "$PY" - << 'EOF_Z'
import os, re, zipfile
z = zipfile.ZipFile(os.environ["FINAL"])
pat = re.compile(r"\b(?:Clover|Calder|Nail)")
n = 0
for name in z.namelist():
    if not name.lower().endswith((".xhtml", ".html", ".htm", ".ncx", ".opf")):
        continue
    s = z.read(name).decode("utf-8", "replace")
    for m in pat.finditer(s):
        n += 1
        if n <= 8:
            print(f"{name}: ...{s[max(0, m.start()-90):m.end()+60]!r}")
print(f"ukupno pojava u EPUB-u: {n}")
EOF_Z
    return $GRC
}

main 2>&1 | tee "$LOG"
RC=${PIPESTATUS[0]}
[ -x tools/out.sh ] && bash tools/out.sh "$LOG"
echo "Log: $LOG"
exit $RC
