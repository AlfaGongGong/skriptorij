import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bs4 import BeautifulSoup
import epub.styler as S

LONG = "Ovo je dugacak odlomak koji pocinje pravim tekstom poglavlja i ima vise od sezdeset znakova da bi dropcap mogao na njega. " * 4
def doc(body, title="Prince of Thorns"):
    pad = "<p>" + LONG + "</p>" * 0
    return BeautifulSoup('<html><head><title>%s</title></head><body><div style="text-align:center;"><img class="booklyfi-vijenac" src="x"/></div>%s</body></html>' % (title, body), "html.parser")

def run(body, naslov=None, broj=7, knjiga="Prince of Thorns", title="Prince of Thorns"):
    s = doc(body, title)
    r = S._dodaj_naslov(s, broj, naslov=naslov, knjiga=knjiga)
    h1 = s.find("h1")
    ps = [p.get_text(strip=True)[:30] for p in s.find_all("p")]
    return r, (h1.get_text() if h1 else None), ps, s

ok = True
def chk(name, cond, info=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + (" | " + str(info) if not cond else ""))
    ok &= bool(cond)

def _all():
    global ok
    ok = True

    P = "<p>%s</p>" % LONG
    # T1 Prince: broj u tijelu, TOC generic odbijen, <title> = naslov knjige
    r, h, ps, s = run("<p>2</p>" + P)
    chk("T1 broj iz tijela, ne naslov knjige", r == "POGLAVLJE 2" and h == "POGLAVLJE 2" and ps[0].startswith("Ovo"), (r, h, ps))
    # T2 broj+podnaslov, TOC engleski
    r, h, ps, s = run("<p>5</p><p>Četiri godine ranije</p>" + P, naslov="Chapter 5 - Four years earlier")
    chk("T2 broj+naslov preferira tijelo", h == "POGLAVLJE 5 – Četiri godine ranije" and ps[0].startswith("Ovo") and len(ps) == 1, (h, ps))
    # T3 Neverland: naslov + autor; naziv fajla iz TOC-a odbijen
    r, h, ps, s = run("<p>Obmana</p><p>Mark Lawrence</p>" + P, naslov="Part0000 Split 003", title="Onbekend")
    chk("T3 naslov iz tijela, bajlajn ostaje", h == "Obmana" and ps[0] == "Mark Lawrence", (h, ps))
    # T4 valid TOC naslov jednak vodecem p -> samo jedan
    r, h, ps, s = run("<p>Predgovor</p>" + P, naslov="Predgovor")
    chk("T4 naslov nije ponovljen u tijelu", h == "Predgovor" and ps[0].startswith("Ovo"), (h, ps))
    # T5 broj spojen s odlomkom
    r, h, ps, s = run("<p>12 Prije četiri godine. " + LONG + "</p>")
    chk("T5 broj spojen s odlomkom", h == "POGLAVLJE 12" and ps[0].startswith("Prije"), (h, ps))
    # T5c prefiks se skida i uz TOC naslov
    r, h, ps, s = run("<p>12 Prije četiri godine. " + LONG + "</p>", naslov="Chapter 5 - Four years earlier")
    chk("T5c prefiks skinut uz TOC naslov", h == "Chapter 5 - Four years earlier" and ps[0].startswith("Prije"), (h, ps))
    # T5d ornament-fallback p ne smeta
    r, h, ps, s = run('<p class="booklyfi-vijenac">— ✠ —</p><p>2</p>' + P)
    chk("T5d ornament p preskocen", h == "POGLAVLJE 2", (h, ps))
    # T5b godina ne smije biti prefiks
    r, h, ps, s = run("<p>1066 Normani su. " + LONG + "</p>")
    chk("T5b godina ostaje", h == "POGLAVLJE 7" and ps[0].startswith("1066"), (h, ps))
    # T6 nema vodeceg, <title>=naslov knjige -> POGLAVLJE n
    r, h, ps, s = run(P)
    chk("T6 fallback nije naslov knjige", h == "POGLAVLJE 7", h)
    # T7 <title> = naziv fajla
    r, h, ps, s = run(P, title="Part0000 Split 003")
    chk("T7 title naziv fajla odbijen", h == "POGLAVLJE 7", h)
    # T7b <title> dobar
    r, h, ps, s = run(P, title="Vražji dvorac")
    chk("T7b dobar title se koristi", h == "Vražji dvorac", h)
    # T8 postojeci h1 = naslov knjige + vodeci naslov
    r, h, ps, s = run("<h1>Prince of Thorns</h1><p>Zveket kostiju</p>" + P)
    chk("T8 los h1 zamijenjen", h == "Zveket kostiju" and len(s.find_all("h1")) == 1, (h,))
    # T8b dobar h1 u fajlu se cuva
    r, h, ps, s = run("<h1>Jedna crna mrlja</h1>" + P)
    chk("T8b dobar h1 ostaje", h == "Jedna crna mrlja" and r == "Jedna crna mrlja", (r, h))
    # T9 Conan: separator "*" -> POGLAVLJE n
    r, h, ps, s = run("<p>*</p><p>PRVI DIO</p>" + P, broj=3)
    chk("T9 separator prekida", h == "POGLAVLJE 3" and ps[0] == "*", (h, ps))
    # T10 NEPREVEDENO placeholder odbijen
    r, h, ps, s = run(P, naslov="[[NEPREVEDENO: blok 0]]")
    chk("T10 placeholder odbijen", h == "POGLAVLJE 7", h)
    # T11 kratki dokument bez naslova -> None
    r, h, ps, s = run("<p>Kratko.</p>")
    chk("T11 kratko bez naslova", r is None and h is None, (r, h))
    # T12 dijalog nije naslov
    r, h, ps, s = run("<p>\u201eKamo idemo\u201d</p>" + P, broj=4)
    chk("T12 dijalog nije naslov", h == "POGLAVLJE 4", h)
    # T13 rimski broj + naslov
    r, h, ps, s = run("<p>III</p><p>Crvene sjene</p>" + P)
    chk("T13 rimski broj", h == "POGLAVLJE III – Crvene sjene", h)
    # T14 TOC naslov s novim redom (stari FIX) i dalje radi
    r, h, ps, s = run("<p>Pitanja Poradili su mu na ruci rane od ceste. " + LONG + "</p>", naslov="Pitanja\nPoradili su mu na ruci")
    chk("T14 stari FIX \\n", h == "Pitanja", (h, ps))
    # T15 literalni \n
    s = BeautifulSoup('<body><p class="x">Prva.\\n\\nDruga recenica.\\n\\nTreca.</p><p>Ostalo <em>x</em>\\n</p></body>', "html.parser")
    n = S._razdvoji_literalne_nl(s)
    t = [p.get_text() for p in s.find_all("p")]
    chk("T15 literalni \\n razdvojen", n == 1 and t[:3] == ["Prva.", "Druga recenica.", "Treca."] and s.find_all("p")[1].get("class") == ["x"], (n, t))
    # T16 dropcap nakon naslova ne pada
    _dm, _pb = S.DROPCAP_MAP, S._png_b64
    S.DROPCAP_MAP = {"O": "o.png", "P": "p.png"}
    S._png_b64 = lambda f: "AAAA"
    r, h, ps, s = run("<p>5</p><p>Naslov poglavlja</p>" + P)
    dc = S._dodaj_dropcap(s)
    chk("T16 dropcap na prvom pravom odlomku", dc and s.find("img", class_="booklyfi-dropcap") is not None, h)
    S.DROPCAP_MAP, S._png_b64 = _dm, _pb
    return ok


def test_naslovi_v2():
    assert _all()


if __name__ == "__main__":
    good = _all()
    print("UKUPNO:", "OK" if good else "FAIL")
    sys.exit(0 if good else 1)
