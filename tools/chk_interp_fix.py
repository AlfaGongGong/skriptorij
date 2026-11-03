import re, glob, os, sys, shutil, time
D = "/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
APPLY = os.environ.get("APPLY") == "1"
OP, CL = "\u201e", "\u201d"
TAGS = re.compile(r"(<[^>]+>)")
CYR = {0x430: "a", 0x435: "e", 0x43e: "o", 0x440: "p", 0x441: "c", 0x445: "x", 0x443: "y", 0x456: "i"}
R_DBL = re.compile(r"(?<=[^\s(,]),{2,}")
R_HYP = re.compile(r"(?<=\w)" + OP + r"(?=-\w)")
R_CLO = re.compile(r"(?<=\S)" + OP + r"(?=\s|[,.;:!?)\u2014])")
R_WRD = re.compile(r"\w+")
R_C = re.compile(r",\s+\.")
R_D = re.compile(r"(?<=\w)" + OP)
LAT = re.compile(r"[A-Za-z\u00c0-\u024f]")
CYRL = re.compile(r"[\u0400-\u04ff]")
PAR = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S)

def rd(f):
    with open(f, encoding="utf-8", newline="") as h:
        return h.read()

def wr(f, v):
    with open(f, "w", encoding="utf-8", newline="") as h:
        h.write(v)

def short(n):
    return n.replace(".html_blok_", "/b").replace(".chk", "")

def sub_log(rx, rep, s, rule, name, log):
    def f(m):
        new = rep(m)
        if new != m.group(0):
            a, b = max(0, m.start() - 20), min(len(s), m.end() + 20)
            log.append((rule, name, s[a:m.start()] + "[" + m.group(0) + "]" + s[m.end():b],
                        s[a:m.start()] + "[" + new + "]" + s[m.end():b]))
        return new
    return rx.sub(f, s)

def fix_word(m):
    w = m.group(0)
    return w.translate(CYR) if LAT.search(w) and CYRL.search(w) else w

def fix(t, name, log):
    parts = TAGS.split(t)
    for i in range(0, len(parts), 2):
        s = parts[i]
        s = sub_log(R_DBL, lambda m: ",", s, "B  ,, -> ,", name, log)
        s = sub_log(R_HYP, lambda m: "", s, "D1 „ u imenu -> brisi", name, log)
        s = sub_log(R_CLO, lambda m: CL, s, "D2 „ -> ”", name, log)
        if s.endswith(OP) and len(s) > 1 and not s[-2].isspace() and i + 1 < len(parts) and parts[i + 1].startswith("</"):
            log.append(("D2 „ -> ” (kraj)", name, s[-20:] + parts[i + 1], s[-20:-1] + CL + parts[i + 1]))
            s = s[:-1] + CL
        s = sub_log(R_WRD, fix_word, s, "E  cirilica -> latinica", name, log)
        parts[i] = s
    return "".join(parts)

def susp(t):
    ps = [TAGS.sub("", p).strip() for p in PAR.findall(t)]
    return [p for i, p in enumerate(ps)
            if p.count(OP) > p.count(CL) and not (i + 1 < len(ps) and ps[i + 1].startswith(OP))]

files = sorted(f for f in glob.glob(D + "/*.chk") if not f.endswith(".prevod.chk"))
print("MOD:", "APPLY" if APPLY else "PREVIEW (nista se ne pise)", "| chk:", len(files))
if not files:
    sys.exit("FAIL: nema .chk")
log, old, new, c_list, rest, tails = [], {}, {}, [], [], []
sb = sa_n = 0
for f in files:
    n = os.path.basename(f)
    try:
        t = rd(f)
    except UnicodeDecodeError:
        print("SKIP (encoding):", n)
        continue
    nt = fix(t, n, log)
    sb += len(susp(t))
    sa = susp(nt)
    sa_n += len(sa)
    tails += [(n, p[-100:]) for p in sa]
    for seg in TAGS.split(nt)[0::2]:
        for m in R_C.finditer(seg):
            c_list.append((n, seg[max(0, m.start() - 45):m.end() + 25].replace("\n", " ")))
        for m in R_D.finditer(seg):
            rest.append((n, seg[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")))
    if nt != t:
        old[f], new[f] = t, nt

by = {}
for r, n, a, b in log:
    by.setdefault(r, []).append((n, a, b))
print(f"\nIZMJENA: {len(log)} u {len(new)} fajlova")
for r, l in sorted(by.items()):
    print(f"\n== {r}: {len(l)}")
    for n, a, b in l:
        print(f" {short(n)}\n  STARO {a}\n  NOVO  {b}")
print(f"\n== ', .' NE DIRAM (rucno): {len(c_list)}")
for n, c in c_list:
    print(f" {short(n)} {c}")
print(f"\n== „ uz slovo koji pravila NISU pokrila: {len(rest)}")
for n, c in rest:
    print(f" {short(n)} {c}")
print(f"\nodlomci s viskom „ (bez nastavka u sljedecem): prije {sb} -> poslije {sa_n}")
for n, p in tails[:6]:
    print(f" {short(n)} ...{p}")
chk2 = []
idem = all(fix(v, "", chk2) == v for v in new.values())
print("idempotentno (drugi prolaz 0 izmjena):", "DA" if idem and not chk2 else "NE")

if not APPLY:
    print("\nPREVIEW gotov, nista nije mijenjano.")
    sys.exit(0)
bak = "/storage/emulated/0/Download/twoc_chk_bak_interp_" + time.strftime("%Y%m%d_%H%M%S")
os.makedirs(bak)
for f in new:
    shutil.copy2(f, bak)
ok = True
try:
    for f, v in new.items():
        wr(f, v)
    for f, v in new.items():
        r = rd(f)
        if r != v or TAGS.findall(r) != TAGS.findall(old[f]) or r.count("</p>") != old[f].count("</p>"):
            ok = False
            print("FAIL provjera:", os.path.basename(f))
except Exception as e:
    ok = False
    print("FAIL izuzetak:", e)
if not ok:
    for f in new:
        shutil.copy2(os.path.join(bak, os.path.basename(f)), f)
    print("POVRAT izveden iz", bak)
    sys.exit(1)
print("backup:", bak, "| upisano:", len(new), "| VERDIKT: OK")
