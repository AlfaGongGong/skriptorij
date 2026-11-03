import sys, glob, os, re
sys.path.insert(0, "/root/skriptorij")
from core.lint_hr import lint_blok, OP, CL

O, C = OP, CL
CASES = [
    ("<p>Vick je,, imala.</p>", "<p>Vick je, imala.</p>"),
    (f"<p>{O}Molim te.{O} Savine.</p>", f"<p>{O}Molim te.{C} Savine.</p>"),
    (f"<p>{O}Dobro.{O}</p>", f"<p>{O}Dobro.{C}</p>"),
    (f"<p>Stand-i{O}-the-Barrows</p>", "<p>Stand-i-the-Barrows</p>"),
    ("<p>kompr\u043emisa</p>", "<p>kompromisa</p>"),
    (f'<p class="a{O}b" id="x">{O}Ne{C}, rekla je. \u2014 Idemo.</p>',
     f'<p class="a{O}b" id="x">{O}Ne{C}, rekla je. \u2014 Idemo.</p>'),
    ("<p>Skarling\u2019s Chair, .</p>", "<p>Skarling\u2019s Chair, .</p>"),
]
ok = True
for i, (ulaz, ocekivano) in enumerate(CASES):
    out, _ = lint_blok(ulaz)
    out2, r2 = lint_blok(out)
    if out != ocekivano or out2 != out or r2["fix"]:
        ok = False
        print(f"FAIL unit {i}: {out!r} (ocekivano {ocekivano!r})")
_, r = lint_blok(CASES[-1][0])
if r["flag"].get("zarez_tocka_ispalo_nesto") != 1 or r["flag"].get("engleski_posvojni_oblik") != 1:
    ok = False
    print("FAIL oznake:", r["flag"])
print("unit testovi:", "OK" if ok else "FAIL")

D = "/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints"
files = sorted(f for f in glob.glob(D + "/*.chk") if not f.endswith(".prevod.chk"))
print("chk:", len(files))
if not files:
    sys.exit("FAIL: nema .chk")
tot = {"fix": {}, "flag": {}}
bad = []
tg = re.compile(r"<[^>]+>")
for f in files:
    t = open(f, encoding="utf-8", newline="").read()
    o, r = lint_blok(t)
    if tg.findall(o) != tg.findall(t) or o.count("</p>") != t.count("</p>"):
        bad.append("TAGOVI " + os.path.basename(f))
    if lint_blok(o)[0] != o:
        bad.append("NEIDEMPOTENTNO " + os.path.basename(f))
    for k in ("fix", "flag"):
        for a, n in r[k].items():
            tot[k][a] = tot[k].get(a, 0) + n
print("stvarni .chk, popravci:", tot["fix"] or "nema")
print("stvarni .chk, oznake:  ", tot["flag"] or "nema")
print("invarijante:", "OK" if not bad else bad[:10])
if not ok or bad:
    sys.exit(1)
print("VERDIKT: OK")
