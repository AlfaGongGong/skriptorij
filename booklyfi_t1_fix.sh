#!/bin/bash
# T1: F1 filter s granicama rijeci, F2 pravilo + budzet glosara, F3 few-shot filter
cd /root/skriptorij || exit 1
clear
mkdir -p .logs
TS=$(date +%Y%m%d_%H%M%S)
LOG=".logs/t1_fix_$TS.log"
BK=".logs/t1_bak_$TS"
mkdir -p "$BK"

vrati() {
    echo ">>> VRACAM SVE IZ BACKUPA"
    cp "$BK/book_context.py" analysis/book_context.py
    cp "$BK/prompts.py" core/prompts.py
    cp "$BK/few_shot_global.py" core/few_shot_global.py
}

{
echo "=== HEAD ==="
git log --oneline -1
cp analysis/book_context.py "$BK/book_context.py" || exit 1
cp core/prompts.py "$BK/prompts.py" || exit 1
cp core/few_shot_global.py "$BK/few_shot_global.py" || exit 1
echo "Backup: $BK"

echo
echo "=== PRIMJENA ==="
venv/bin/python3 << 'PYEOF'
import sys

def primijeni(putanja, izmjene):
    src = open(putanja, encoding="utf-8").read()
    for i, (staro, novo) in enumerate(izmjene, 1):
        n = src.count(staro)
        print(f"{putanja} E{i}: pojavljivanja STARO = {n}")
        if n != 1:
            print("STOP: ocekivano tacno 1")
            sys.exit(1)
    for staro, novo in izmjene:
        src = src.replace(staro, novo, 1)
    open(putanja, "w", encoding="utf-8").write(src)

# ---------- F1: analysis/book_context.py ----------
primijeni("analysis/book_context.py", [(
'''            for linija in glosar_tekst.split("\\n"):
                m = _re.match(r"^-\\s+([^\\s(]+)", linija)
                if m:
                    en_ime = m.group(1).strip()
                    if en_ime and en_ime.lower() in chunk_lower:
                        linije.append(linija)
''',
'''            # 2026-11-02 T1: cijelo ime (i viseriјecno) + granice rijeci.
            # Prije: substring na prvoj rijeci ("Leo" pogadja "Leopold",
            # "Dow" pogadja "window").
            for linija in glosar_tekst.split("\\n"):
                m = _re.match(r"^-\\s+(.+?)\\s+(?:->|\\()", linija)
                if m:
                    en_ime = m.group(1).strip()
                    if en_ime and _re.search(
                        r"(?<!\\w)" + _re.escape(en_ime) + r"(?!\\w)",
                        chunk_text,
                        _re.I,
                    ):
                        linije.append(linija)
''')])

# ---------- F2: core/prompts.py ----------
primijeni("core/prompts.py", [(
'''vrati prazan string — ne objašnjavaj zašto.

IZLAZ: SAMO finalni tekst. Nula komentara. Nula uvoda. Nula JSON omotača.
"""''',
'''vrati prazan string — ne objašnjavaj zašto.

9. VLASTITA IMENA (KRITIČNO!): Imena iz GLOSARA prepiši TAČNO kako piše u glosaru.
   "(OSTAVI KAKO JEST)" znači slovo po slovo kao u originalu: "Bayaz" ostaje "Bayaz"
   (NIKAD "Bajaz"), ne transliteriraj i ne prilagođavaj izgovor. Glosar ima apsolutni
   prioritet nad primjerima i nad tvojim uobičajenim oblicima. Padeže tvori dodavanjem
   nastavka na nepromijenjeno ime ("Bayazu", "Bayazom").

IZLAZ: SAMO finalni tekst. Nula komentara. Nula uvoda. Nula JSON omotača.
"""'''),
(
'''def get_prevodilac_prompt(
    book_context: dict,''',
'''def _skrati_glosar(glosar: str, max_znakova: int = 4000) -> str:
    """2026-11-02 T1: budzet glosara u promptu. Reze po cijelim linijama."""
    if not glosar or len(glosar) <= max_znakova:
        return glosar
    izlaz, duzina = [], 0
    for linija in glosar.split("\\n"):
        if duzina + len(linija) + 1 > max_znakova:
            break
        izlaz.append(linija)
        duzina += len(linija) + 1
    return "\\n".join(izlaz)


def get_prevodilac_prompt(
    book_context: dict,'''),
(
'''        autor_stil=autor_stil,
        glosar_injekcija=glosar_injekcija or "Nema glosara.",''',
'''        autor_stil=autor_stil,
        glosar_injekcija=_skrati_glosar(glosar_injekcija) or "Nema glosara.",''')])

# ---------- F3: core/few_shot_global.py ----------
primijeni("core/few_shot_global.py", [(
'''def _similarity(a, b):''',
'''def _zabranjeni_regex():
    """2026-11-02 T1: oblici koji ne smiju uci u few-shot (uce model
    pogresnom imenu). Bajaz = pogresno za Bayaz; plus odbacene_varijante
    iz svih kanona."""
    oblici = {"Bajaz"}
    try:
        kd = Path(__file__).parent.parent / "data" / "kanon" / "knjige"
        for p in kd.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for v in (d.get("termini") or {}).values():
                for o in (v.get("odbacene_varijante") or []):
                    if isinstance(o, str) and len(o) >= 3:
                        oblici.add(o)
    except Exception:
        pass
    return re.compile(
        r"(?<!\\w)(?:" + "|".join(re.escape(o) + r"\\w*" for o in sorted(oblici)) + ")"
    )


_ZABRANJENI = _zabranjeni_regex()


def _similarity(a, b):'''),
(
'''    if not en_text or not bs_text:
        return
''',
'''    if not en_text or not bs_text:
        return
    if _ZABRANJENI.search(bs_text):
        return  # T1: ne ucimo pogresna imena
'''),
(
'''    shots = load_shots()
    if tip_bloka:
        shots = [s for s in shots if s.get("tip") == tip_bloka]
''',
'''    shots = load_shots()
    shots = [s for s in shots if not _ZABRANJENI.search(str(s.get("bs", "")))]
    if tip_bloka:
        shots = [s for s in shots if s.get("tip") == tip_bloka]
''')])
print("Sve izmjene upisane")
PYEOF
if [ $? -ne 0 ]; then vrati; exit 1; fi

echo
echo "=== ast.parse + py_compile ==="
for f in analysis/book_context.py core/prompts.py core/few_shot_global.py; do
  venv/bin/python3 -c "import ast,sys; ast.parse(open('$f',encoding='utf-8').read()); print('ast OK  $f')" \
    && venv/bin/python3 -m py_compile "$f" && echo "compile OK  $f" \
    || { echo "SINTAKSA PALA: $f"; vrati; exit 1; }
done

echo
echo "=== TESTOVI ==="
venv/bin/python3 << 'PYEOF'
import sys, re
ok = True
def prov(naziv, uvjet):
    global ok
    print(("OK    " if uvjet else "GRESKA"), naziv)
    if not uvjet: ok = False

# F1
from analysis.book_context import BookContextManager
m = BookContextManager.__new__(BookContextManager); m._glosar = {}
glos = "\n".join([
    "- Bayaz (OSTAVI KAKO JEST, ne prevodi) [lik]",
    "- Leo (OSTAVI KAKO JEST, ne prevodi) [lik]",
    "- Dow (OSTAVI KAKO JEST, ne prevodi) [lik]",
    "- Crown -> Kruna [termin]",
    "- Black Dow -> Crni Dow [lik]",
])
rel = m.extract_relevant_glossary("Bayaz opened the window. Leopold nodded. The Crown waited.", glos)
prov("F1 Bayaz pogodjen", "Bayaz" in rel)
prov("F1 Crown pogodjen", "Crown" in rel)
prov("F1 Leo NE pogadja Leopold", "- Leo " not in rel)
prov("F1 Dow NE pogadja window", "- Dow " not in rel)
rel2 = m.extract_relevant_glossary("Black Dow's men came. Leo's sword.", glos)
prov("F1 viseriјecno 'Black Dow' pogodjeno", "Black Dow" in rel2)
prov("F1 posesiv Leo's pogodjen", "- Leo " in rel2)

# F2
from core.prompts import get_prevodilac_prompt, _skrati_glosar
p = get_prevodilac_prompt({}, "- Bayaz (OSTAVI KAKO JEST, ne prevodi) [lik]", "", "naracija")
prov("F2 pravilo 9 u promptu", "VLASTITA IMENA" in p and "NIKAD \"Bajaz\"" in p)
prov("F2 glosar u promptu", "- Bayaz (OSTAVI" in p)
veliki = "\n".join(f"- Ime{i} (OSTAVI KAKO JEST) [lik]" for i in range(500))
sk = _skrati_glosar(veliki)
prov("F2 budzet <= 4000 i cijele linije", len(sk) <= 4000 and sk.endswith("[lik]"))
prov("F2 prazan glosar -> 'Nema glosara.'",
     "Nema glosara." in get_prevodilac_prompt({}, "", "", "naracija"))

# F3
import core.few_shot_global as fs
shots = [
    {"en": "Bayaz looked at the gardens", "bs": "Bajaz pogleda vrtove", "score": 9.5, "tip": "naracija"},
    {"en": "Bayaz looked at the gardens now", "bs": "Bayaz pogleda vrtove", "score": 9.5, "tip": "naracija"},
]
fs.load_shots = lambda: shots
rez = fs.pronadji_slicne("Bayaz looked at the gardens", "naracija", 5)
prov("F3 Bajaz par filtriran", all("Bajaz" not in r["bs"] for r in rez))
prov("F3 cist par ostaje", any("Bayaz" in r["bs"] for r in rez))
sacuvano = []
fs.save_shots = lambda s: sacuvano.append(s)
fs.dodaj_odlican_prevod("Bayaz spoke slowly to everyone", "Bajaz govori sporo", 9.5, "naracija")
prov("F3 dodaj_odlican_prevod odbija Bajaz", not sacuvano)

# pipeline import i dalje radi
try:
    import processing.pipeline  # noqa
    prov("pipeline import", True)
except Exception as e:
    print("pipeline import:", repr(e)); prov("pipeline import", False)

print("\nTESTOVI PROSLI" if ok else "\nTESTOVI PALI")
sys.exit(0 if ok else 1)
PYEOF
if [ $? -ne 0 ]; then vrati; exit 1; fi

echo
echo "=== Few-shot u bazi: koliko parova sada biva odbaceno ==="
venv/bin/python3 -c "
import core.few_shot_global as f
s=f.load_shots(); b=[x for x in s if f._ZABRANJENI.search(str(x.get('bs','')))]
print(f'ukupno {len(s)}, filtrirano pri citanju {len(b)}')"

echo
echo "=== git diff --stat ==="
git diff --stat -- analysis/book_context.py core/prompts.py core/few_shot_global.py
echo
echo "T1 GOTOV. Nije commitovano."
} 2>&1 | tee "$LOG"

bash tools/out.sh "$LOG"
