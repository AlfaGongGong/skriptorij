import re, glob, os, sys, shutil, time, collections
D = "/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
APPLY = os.environ.get("APPLY") == "1"
LOWER = True   # True: stolica/dvorana malim slovom; False: Stolica/Dvorana
TAGS = re.compile(r"(<[^>]+>)")
AP = "[\u201e'\u2019]"

def nm(w):
    return w.lower() if LOWER else w.capitalize()

SFX = {
    ("Chair", "u"): "Skarlingovoj " + nm("stolici"),
    ("Chair", "a"): "Skarlingove " + nm("stolice"),
    ("Chair", "om"): "Skarlingovom " + nm("stolicom"),
    ("Hall", "u"): "Skarlingovoj " + nm("dvorani"),
    ("Hall", "a"): "Skarlingove " + nm("dvorane"),
    ("Hall", "om"): "Skarlingovom " + nm("dvoranom"),
}
ACC = {"Chair": "Skarlingovu " + nm("stolicu"), "Hall": "Skarlingovu " + nm("dvoranu")}
MRG = {"dvorane": "Skarlingove " + nm("dvorane"),
       "dvoranom": "Skarlingovom " + nm("dvoranom"),
       "stolice": "Skarlingove " + nm("stolice")}

R_MRG = re.compile(r"\b([Dd]vorane|[Dd]voranom|[Ss]tolice)\s+Skarling" + AP + r"s\s+(Hall|Chair)\b")
R_ACC = re.compile(r"\b([uU])\s+Skarling" + AP + r"s\s+(Hall|Chair)\b")
R_SFX = re.compile(r"Skarling" + AP + r"s\s+(Chair|Hall)(u|a|om)\b")
R_LIT1 = re.compile(r"se nalazilo Skarling" + AP + r"s Chair\b")
R_LIT2 = re.compile(r"kako se Skarling" + AP + r"s Chair cijepa\b")
R_N = re.compile(r"(Skarlingov\w+) (Stolic\w+|Dvoran\w+|stolic\w+|dvoran\w+)")
R_C = re.compile(r",[ \t]+\.(?!\.)")
R_REST = re.compile(r"Skarling" + AP + r"s\s+(?:Hall|Chair)\w*")
R_ODD = re.compile(r"Skarlingov\w*\s+stolc\w*")

def rd(f):
    with open(f, encoding="utf-8", newline="") as h:
        return h.read()

def wr(f, v):
    with open(f, "w", encoding="utf-8", newline="") as h:
        h.write(v)

def short(n):
    return n.replace(".html_blok_", "/b").replace(".chk", "")

def ctx(s, m, rep):
    a, b = max(0, m.start() - 25), min(len(s), m.end() + 25)
    return (s[a:m.start()] + "[" + m.group(0) + "]" + s[m.end():b],
            s[a:m.start()] + "[" + rep + "]" + s[m.end():b])

def run(rx, fn, s, rule, name, log):
    def f(m):
        rep = fn(m, s)
        if rep is None or rep == m.group(0):
            return m.group(0)
        a, b = ctx(s, m, rep)
        log.append((rule, name, a, b))
        return rep
    return rx.sub(f, s)

def mrg(m, s):
    n, w = m.group(1).lower(), m.group(2)
    if (n.startswith("dvoran") and w == "Hall") or (n == "stolice" and w == "Chair"):
        return MRG[n]
    return None

def fix(t, name, log):
    parts = TAGS.split(t)
    for i in range(0, len(parts), 2):
        s = parts[i]
        s = run(R_MRG, mrg, s, "S1 imenica + Skarling's -> spojeno", name, log)
        s = run(R_ACC, lambda m, s: m.group(1) + " " + ACC[m.group(2)], s, "S2 u + Skarling's -> akuzativ", name, log)
        s = run(R_SFX, lambda m, s: SFX[(m.group(1), m.group(2))], s, "S3 Skarling's + nastavak -> padez", name, log)
        s = run(R_LIT1, lambda m, s: "se nalazila Skarlingova " + nm("stolica"), s, "S4 nominativ (glagol u zenski rod)", name, log)
        s = run(R_LIT2, lambda m, s: "kako se Skarlingova " + nm("stolica") + " cijepa", s, "S4 nominativ", name, log)
        s = run(R_N, lambda m, s: m.group(1) + " " + nm(m.group(2)), s, "N  ujednacavanje velikih/malih slova", name, log)
        s = run(R_C, lambda m, s: None if "Sutkinjo" in s[max(0, m.start() - 25):m.start()] else ".", s, "C  ', .' -> '.'", name, log)
        parts[i] = s
    return "".join(parts)

files = sorted(f for f in glob.glob(D + "/*.chk") if not f.endswith(".prevod.chk"))
print("MOD:", "APPLY" if APPLY else "PREVIEW (nista se ne pise)", "| chk:", len(files), "| LOWER =", LOWER)
if not files:
    sys.exit("FAIL: nema .chk")
log, old, new, left, unh, odd = [], {}, {}, [], [], []
cnt = collections.Counter()
for f in files:
    n = os.path.basename(f)
    try:
        t = rd(f)
    except UnicodeDecodeError:
        print("SKIP (encoding):", n)
        continue
    nt = fix(t, n, log)
    for seg in TAGS.split(nt)[0::2]:
        for m in R_C.finditer(seg):
            left.append((n, seg[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")))
        for m in R_REST.finditer(seg):
            unh.append((n, seg[max(0, m.start() - 40):m.end() + 30].replace("\n", " ")))
        for m in R_ODD.finditer(seg):
            odd.append((n, seg[max(0, m.start() - 40):m.end() + 30].replace("\n", " ")))
        for m in re.finditer(r"Skarling\S*(?:\s+\S+)?", seg):
            cnt[m.group(0).strip(".,;:!?\u201d\u201e)(")] += 1
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
print(f"\n== Skarling's koji ostaje (ne diram): {len(unh)}")
for n, c in unh:
    print(f" {short(n)} {c}")
print(f"\n== sumnjivo 'Skarlingova stolca' (ne diram): {len(odd)}")
for n, c in odd:
    print(f" {short(n)} {c}")
print(f"\n== ', .' ostaje (rucno): {len(left)}")
for n, c in left:
    print(f" {short(n)} {c}")
print("\n== 'Skarling' u .chk poslije izmjene (top 15):")
for w, c in cnt.most_common(15):
    print(f"  {c:3d}x {w}")
tmp = []
idem = all(fix(v, "", tmp) == v for v in new.values())
print("idempotentno (drugi prolaz 0 izmjena):", "DA" if idem and not tmp else "NE")

if not APPLY:
    print("\nPREVIEW gotov, nista nije mijenjano.")
    sys.exit(0)
bak = "/storage/emulated/0/Download/twoc_chk_bak_interp2_" + time.strftime("%Y%m%d_%H%M%S")
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
