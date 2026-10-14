# core/kalkovi/glagoli_mapa.py
"""
Mapa glagolskih oblika za determinističku konjugaciju.

Format paradigme: (infinitiv, 1sg, 2sg, 3sg, 1pl, 2pl, 3pl)
Iz ovoga se automatski generira GLAGOLI_MAPA koja mapira
svaki prezent oblik na (infinitiv, lice).

Lica: 1sg, 2sg, 3sg, 1pl, 2pl, 3pl

Dodano 2026-09-25 za fix kalkova "modal + da + glagol" → "modal + infinitiv".
"""

from __future__ import annotations
from typing import Iterator

# ═══════════════════════════════════════════════════════════════════════════
# PARADIGME — (infinitiv, 1sg, 2sg, 3sg, 1pl, 2pl, 3pl)
# ═══════════════════════════════════════════════════════════════════════════
GLAGOLI_PARADIGME: list[tuple[str, str, str, str, str, str, str]] = [
    # ── biti (nepravilan) ──
    ("biti",    "budem",   "budeš",   "bude",   "budemo",  "budete",  "budu"),
    ("biti",    "jesam",   "jesi",    "jest",   "jesmo",   "jeste",   "jesu"),

    # ── htjeti (nepravilan) ──
    ("htjeti",  "hoću",    "hoćeš",   "hoće",   "hoćemo",  "hoćete",  "hoće"),
    ("htjeti",  "htjednem", "htjedneš", "htjedne", "htjednemo", "htjednete", "htjednu"),

    # ── željeti ──
    ("željeti", "želim",   "želiš",   "želi",   "želimo",  "želite",  "žele"),

    # ── moći (nepravilan) ──
    ("moći",    "mogu",    "možeš",   "može",   "možemo",  "možete",  "mogu"),

    # ── morati ──
    ("morati",  "moram",   "moraš",   "mora",   "moramo",  "morate",  "moraju"),

    # ── smjeti ──
    ("smjeti",  "smijem",  "smiješ",  "smije",  "smijemo", "smijete", "smiju"),

    # ── trebati ──
    ("trebati", "trebam",  "trebaš",  "treba",  "trebamo", "trebate", "trebaju"),

    # ── znati ──
    ("znati",   "znam",    "znaš",    "zna",    "znamo",   "znate",   "znaju"),

    # ── umjeti ──
    ("umjeti",  "umijem",  "umiješ",  "umije",  "umijemo", "umijete", "umiju"),

    # ── smjeti / moći (alternativni oblik) ──
    ("htjeti",  "želim",   "želiš",   "želi",   "želimo",  "želite",  "žele"),

    # ═══════════════════════════════════════════════════════════════════════
    # PRAVILNI GLAGOLI NA -ATI (a-konjugacija)
    # ═══════════════════════════════════════════════════════════════════════
    ("raditi",   "radim",   "radiš",   "radi",   "radimo",  "radite",  "rade"),

    ("davati",   "dajem",   "daješ",   "daje",   "dajemo",  "dajete",  "daju"),
    ("dati",     "dam",     "daš",     "da",     "damo",    "date",    "daju"),

    ("imati",    "imam",    "imaš",    "ima",    "imamo",   "imate",   "imaju"),

    ("gledati",  "gledam",  "gledaš",  "gleda",  "gledamo", "gledate", "gledaju"),
    ("vidjeti",  "vidim",   "vidiš",   "vidi",   "vidimo",  "vidite",  "vide"),
    ("gledati",  "gledam",  "gledaš",  "gleda",  "gledamo", "gledate", "gledaju"),

    ("slušati",  "slušam",  "slušaš",  "sluša",  "slušamo", "slušate", "slušaju"),
    ("čuti",     "čujem",   "čuješ",   "čuje",   "čujemo",  "čujete",  "čuju"),

    ("govoriti", "govorim", "govoriš", "govori", "govorimo","govorite","govore"),
    ("reći",     "rečem",   "rečeš",   "reče",   "rečemo",  "rečete",  "reku"),
    ("kazati",   "kažem",   "kažeš",   "kaže",   "kažemo",  "kažete",  "kažu"),

    ("pitati",   "pitam",   "pitaš",   "pita",   "pitamo",  "pitate",  "pitaju"),
    ("odgovoriti","odgovorim","odgovoriš","odgovori","odgovorimo","odgovorite","odgovore"),

    ("misliti",  "mislim",  "misliš",  "misli",  "mislimo", "mislite", "misle"),
    ("pamtiti",  "pamtim",  "pamtiš",  "pamti",  "pamtimo", "pamtite", "pamte"),

    ("osjećati", "osjećam", "osjećaš", "osjeća", "osjećamo","osjećate","osjećaju"),
    ("osjetiti", "osjetim", "osjetiš", "osjeti", "osjetimo","osjetite","osjete"),

    ("željeti",  "žudim",   "žudiš",   "žudi",   "žudimo",  "žudite",  "žude"),
    ("nadati",   "nadam",   "nadaš",   "nada",   "nadamo",  "nadate",  "nadaju"),

    ("čekati",   "čekam",   "čekaš",   "čeka",   "čekamo",  "čekate",  "čekaju"),
    ("tražiti",  "tražim",  "tražiš",  "traži",  "tražimo", "tražite", "traže"),
    ("naći",     "nađem",   "nađeš",   "nađe",   "nađemo",  "nađete",  "nađu"),
    ("izgubiti", "izgubim", "izgubiš", "izgubi", "izgubimo","izgubite","izgube"),

    ("kupiti",   "kupim",   "kupiš",   "kupi",   "kupimo",  "kupite",  "kupe"),
    ("prodati",  "prodajem","prodaješ","prodaje","prodajemo","prodajete","prodaju"),
    ("platiti",  "platim",  "platiš",  "plati",  "platimo", "platite", "plate"),

    ("otvoriti", "otvorim", "otvoriš", "otvori", "otvorimo","otvorite","otvore"),
    ("zatvoriti","zatvorim","zatvoriš","zatvori","zatvorimo","zatvorite","zatvore"),

    ("baciti",   "bacim",   "baciš",   "baci",   "bacimo",  "bacite",  "bace"),
    ("uhvatiti", "uhvatim", "uhvatiš", "uhvati", "uhvatimo","uhvatite","uhvate"),

    ("staviti",  "stavim",  "staviš",  "stavi",  "stavimo", "stavite", "stave"),
    ("držati",   "držim",   "držiš",   "drži",   "držimo",  "držite",  "drže"),

    ("pustiti",  "pustim",  "pustiš",  "pusti",  "pustimo", "pustite", "puste"),

    ("krenuti",  "krenem",  "kreneš",  "krene",  "krenemo", "krenete", "krenu"),
    ("stati",    "stanem",  "staneš",  "stane",  "stanemo", "stanete", "stanu"),
    ("ustati",   "ustanem", "ustaneš", "ustane", "ustanemo","ustanete","ustanu"),

    ("sjesti",   "sjednem", "sjedneš", "sjedne", "sjednemo","sjednete","sjednu"),
    ("leći",     "legnem",  "legneš",  "legne",  "legnemo", "legnete", "legnu"),

    ("jesti",    "jedem",   "jedeš",   "jede",   "jedemo",  "jedete",  "jedu"),
    ("piti",     "pijem",   "piješ",   "pije",   "pijemo",  "pijete",  "piju"),

    ("spavati",  "spavam",  "spavaš",  "spava",  "spavamo", "spavate", "spavaju"),
    ("sanjariti","sanjarim","sanjaš",  "sanja",  "sanjamo", "sanjate", "sanjaju"),

    ("trčati",   "trčim",   "trčiš",   "trči",   "trčimo",  "trčite",  "trče"),
    ("hodati",   "hodam",   "hodaš",   "hoda",   "hodamo",  "hodate",  "hodaju"),

    ("skočiti",  "skočim",  "skočiš",  "skoči",  "skočimo", "skočite", "skoče"),
    ("pasti",    "padnem",  "padneš",  "padne",  "padnemo", "padnete", "padnu"),

    ("letjeti",  "letim",   "letiš",   "leti",   "letimo",  "letite",  "lete"),

    ("pjevati",  "pjevam",  "pjevaš",  "pjeva",  "pjevamo", "pjevate", "pjevaju"),
    ("plesati",  "plešem",  "plešeš",  "pleše",  "plešemo", "plešete", "plešu"),

    ("radovati", "radujem", "raduješ", "raduje", "radujemo","radujete","raduju"),
    ("veseliti", "veselim", "veseliš", "veseli", "veselimo","veselite","vesele"),

    ("plakati",  "plačem",  "plačeš",  "plače",  "plačemo", "plačete", "plaču"),
    ("smijati",  "smijem",  "smiješ",  "smije",  "smijemo", "smijete", "smiju"),

    ("umrijeti", "umrem",   "umreš",   "umre",   "umremo",  "umrete",  "umru"),
    ("živjeti",  "živim",   "živiš",   "živi",   "živimo",  "živite",  "žive"),

    # ═══════════════════════════════════════════════════════════════════════
    # PRAVILNI GLAGOLI NA -ITI (i-konjugacija)
    # ═══════════════════════════════════════════════════════════════════════
    ("voljeti",  "volim",   "voliš",   "voli",   "volimo",  "volite",  "vole"),
    ("mrziti",   "mrzim",   "mrziš",   "mrzi",   "mrzimo",  "mrzite",  "mrze"),

    ("braniti",  "branim",  "braniš",  "brani",  "branimo", "branite", "brane"),
    ("napadati", "napadam", "napadaš", "napada", "napadamo","napadate","napadaju"),

    ("braniti",  "branim",  "braniš",  "brani",  "branimo", "branite", "brane"),

    ("počinjati","počinjem","počinješ","počinje","počinjemo","počinjete","počinju"),
    ("početi",   "počnem",  "počneš",  "počne",  "počnemo", "počnete", "počnu"),

    ("prestajati","prestajem","prestaješ","prestaje","prestajemo","prestajete","prestaju"),
    ("prestati", "prestanem","prestaneš","prestane","prestanemo","prestanete","prestanu"),

    ("nastavljati","nastavljam","nastavljaš","nastavlja","nastavljamo","nastavljate","nastavljaju"),
    ("nastaviti","nastavim","nastaviš","nastavi","nastavimo","nastavite","nastave"),

    ("pokušavati","pokušavam","pokušavaš","pokušava","pokušavamo","pokušavate","pokušavaju"),
    ("pokušati", "pokušam", "pokušaš", "pokuša", "pokušamo","pokušate","pokušaju"),

    ("uspijevati","uspijevam","uspijevaš","uspijeva","uspijevamo","uspijevate","uspijevaju"),
    ("uspjeti",  "uspijem", "uspiješ", "uspije", "uspijemo","uspijete","uspiju"),

    ("završavati","završavam","završavaš","završava","završavamo","završavate","završavaju"),
    ("završiti", "završim", "završiš", "završi", "završimo","završite","završe"),

    ("započinjati","započinjem","započinješ","započinje","započinjemo","započinjete","započinju"),
    ("započeti","započnem","započneš","započne","započnemo","započnete","započnu"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI KRETANJA
    # ═══════════════════════════════════════════════════════════════════════
    ("ići",     "idem",   "ideš",   "ide",   "idemo",  "idete",  "idu"),
    ("doći",    "dođem",  "dođeš",  "dođe",  "dođemo", "dođete", "dođu"),
    ("otići",   "otići ću","otići ćeš","otići će","otići ćemo","otići ćete","otići će"),
    ("otići",   "odem",   "odeš",   "ode",   "odemo",  "odete",  "odu"),
    ("poći",    "pođem",  "pođeš",  "pođe",  "pođemo", "pođete", "pođu"),
    ("doći",    "dođem",  "dođeš",  "dođe",  "dođemo", "dođete", "dođu"),

    ("doći",    "stižem", "stižeš", "stiže", "stižemo","stižete", "stižu"),
    ("stizati", "stižem", "stižeš", "stiže", "stižemo","stižete", "stižu"),

    ("putovati","putujem","putuješ","putuje","putujemo","putujete","putuju"),
    ("voziti",  "vozim",  "voziš",  "vozi",  "vozimo", "vozite", "voze"),
    ("letjeti", "letim",  "letiš",  "leti",  "letimo", "letite", "lete"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI PERCEPCIJE I MENTALNIH AKTIVNOSTI
    # ═══════════════════════════════════════════════════════════════════════
    ("razumjeti","razumijem","razumiješ","razumije","razumijemo","razumijete","razumiju"),
    ("shvatiti",  "shvatim","shvatiš","shvati","shvatimo","shvatite","shvate"),
    ("sjetiti",   "sjetim", "sjetiš", "sjeti", "sjetimo","sjetite", "sjete"),
    ("zaboraviti","zaboravim","zaboraviš","zaboravi","zaboravimo","zaboravite","zaborave"),

    ("vjerovati","vjerujem","vjeruješ","vjeruje","vjerujemo","vjerujete","vjeruju"),
    ("sumnjati", "sumnjam","sumnjaš","sumnja","sumnjamo","sumnjate","sumnjaju"),

    ("nadati",   "nadam",  "nadaš",  "nada",  "nadamo", "nadate", "nadaju"),
    ("planirati","planiram","planiraš","planira","planiramo","planirate","planiraju"),
    ("namjeravati","namjeravam","namjeravaš","namjerava","namjeravamo","namjeravate","namjeravaju"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI KOMUNIKACIJE
    # ═══════════════════════════════════════════════════════════════════════
    ("šaputati", "šaputam","šaputaš","šaputa","šaputamo","šaputate","šaputaju"),
    ("vikati",   "vičem",  "vičeš",  "viče",  "vičemo", "vičete", "viču"),
    ("uzviknuti","uzviknem","uzvikneš","uzvikne","uzviknemo","uzviknete","uzviknu"),

    ("pričati",  "pričam", "pričaš", "priča", "pričamo","pričate", "pričaju"),
    ("razgovarati","razgovaram","razgovaraš","razgovara","razgovaramo","razgovarate","razgovaraju"),

    ("šutjeti",  "šutim",  "šutiš",  "šuti",  "šutimo", "šutite", "šute"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI MANIPULACIJE
    # ═══════════════════════════════════════════════════════════════════════
    ("uzeti",    "uzmem",  "uzmeš",  "uzme",  "uzmemo", "uzmete", "uzmu"),
    ("dati",     "dam",    "daš",    "da",    "damo",   "date",   "daju"),
    ("primiti",  "primim", "primiš", "primi", "primimo","primite","prime"),
    ("poslati",  "pošaljem","pošalješ","pošalje","pošaljemo","pošaljete","pošalju"),

    ("kupiti",   "kupim",  "kupiš",  "kupi",  "kupimo", "kupite", "kupe"),
    ("prodati",  "prodajem","prodaješ","prodaje","prodajemo","prodajete","prodaju"),
    ("krasti",   "kradem", "kradeš", "krade", "krademo","kradete","kradu"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI STANJA I POSTOJANJA
    # ═══════════════════════════════════════════════════════════════════════
    ("stajati",  "stojim", "stojiš", "stoji", "stojimo","stojite","stoje"),
    ("sjediti",  "sjedim", "sjediš", "sjedi", "sjedimo","sjedite","sjede"),
    ("ležati",   "ležim",  "ležiš",  "leži",  "ležimo", "ležite", "leže"),

    ("ostati",   "ostanem","ostaneš","ostane","ostanemo","ostanete","ostanu"),
    ("postojati","postojim","postojiš","postoji","postojimo","postojite","postoje"),

    # ═══════════════════════════════════════════════════════════════════════
    # GLAGOLI PROMJENE
    # ═══════════════════════════════════════════════════════════════════════
    ("postati",  "postanem","postaneš","postane","postanemo","postanete","postanu"),
    ("promijeniti","promijenim","promijeniš","promijeni","promijenimo","promijenite","promijene"),
    ("mijenjati","mijenjam","mijenjaš","mijenja","mijenjamo","mijenjate","mijenjaju"),

    ("rasti",    "rastem", "rasteš", "raste", "rastemo","rastete","rastu"),
    ("opadati",  "opadam", "opadaš", "opada", "opadamo","opadate","opadaju"),

    # ═══════════════════════════════════════════════════════════════════════
    # OSTALI ČESTI GLAGOLI
    # ═══════════════════════════════════════════════════════════════════════
    ("pomoći",   "pomognem","pomogneš","pomogne","pomognemo","pomognete","pomognu"),
    ("pomagati", "pomažem","pomažeš","pomaže","pomažemo","pomažete","pomažu"),

    ("raditi",   "radim",  "radiš",  "radi",  "radimo", "radite", "rade"),
    ("uraditi",  "uradim", "uradiš", "uradi", "uradimo","uradite","urade"),
    ("napraviti","napravim","napraviš","napravi","napravimo","napravite","naprave"),
    ("praviti",  "pravim", "praviš", "pravi", "pravimo","pravite","prave"),

    ("koristiti","koristim","koristiš","koristi","koristimo","koristite","koriste"),
    ("iskoristiti","iskoristim","iskoristiš","iskoristi","iskoristimo","iskoristite","iskoriste"),

    ("trebati",  "trebam", "trebaš", "treba", "trebamo","trebate","trebaju"),
    ("vrijediti","vrijedim","vrijediš","vrijedi","vrijedimo","vrijedite","vrijede"),

    ("izgledati","izgledam","izgledaš","izgleda","izgledamo","izgledate","izgledaju"),
    ("djelovati","djelujem","djeluješ","djeluje","djelujemo","djelujete","djeluju"),

    ("sjećati",   "sjećam", "sjećaš", "sjeća", "sjećamo","sjećate","sjećaju"),
    ("pamtiti",   "pamtim", "pamtiš", "pamti", "pamtimo","pamtite","pamte"),

    ("vjerovati", "vjerujem","vjeruješ","vjeruje","vjerujemo","vjerujete","vjeruju"),
    ("nadati",    "nadam", "nadaš",  "nada",  "nadamo", "nadate", "nadaju"),

    ("čekati",    "čekam", "čekaš",  "čeka",  "čekamo", "čekate", "čekaju"),
    ("čekati",    "čekam", "čekaš",  "čeka",  "čekamo", "čekate", "čekaju"),

    ("voljeti",   "volim", "voliš",  "voli",  "volimo", "volite", "vole"),
    ("mrziti",    "mrzim", "mrziš",  "mrzi",  "mrzimo", "mrzite", "mrze"),

    ("svidjeti",  "svidim", "svidiš", "svidi", "svidimo","svidite","svide"),

    ("umjeti",    "umijem","umiješ", "umije", "umijemo","umijete","umiju"),
    ("znati",     "znam",  "znaš",   "zna",   "znamo",  "znate",  "znaju"),
]


# ═══════════════════════════════════════════════════════════════════════════
# GENERIRANJE MAPE — oblik → (infinitiv, lice)
# ═══════════════════════════════════════════════════════════════════════════
GLAGOLI_MAPA: dict[str, tuple[str, str]] = {}

for _par in GLAGOLI_PARADIGME:
    _inf, _1sg, _2sg, _3sg, _1pl, _2pl, _3pl = _par
    for _oblik, _lice in (
        (_1sg, "1sg"), (_2sg, "2sg"), (_3sg, "3sg"),
        (_1pl, "1pl"), (_2pl, "2pl"), (_3pl, "3pl"),
    ):
        if _oblik and _oblik not in GLAGOLI_MAPA:
            GLAGOLI_MAPA[_oblik] = (_inf, _lice)

# ═══════════════════════════════════════════════════════════════════════════
# MODALI — glagoli koji zahtijevaju infinitiv u konstrukciji
# ═══════════════════════════════════════════════════════════════════════════
MODALI_1SG: frozenset = frozenset([
    "želim", "hoću", "mogu", "moram", "smijem", "trebam", "znam", "umijem",
    "počinjem", "prestajem", "nastavljam", "pokušavam", "uspijevam",
    "završavam", "započinjem", "namjeravam", "planiram", "moram",
])

MODALI_2SG: frozenset = frozenset([
    "želiš", "hoćeš", "možeš", "moraš", "smiješ", "trebaš", "znaš", "umiješ",
    "počinješ", "prestaješ", "nastavljaš", "pokušavaš", "uspijevaš",
    "završavaš", "započinješ", "namjeravaš", "planiraš",
])

MODALI_3SG: frozenset = frozenset([
    "želi", "hoće", "može", "mora", "smije", "treba", "zna", "umije",
    "počinje", "prestaje", "nastavlja", "pokušava", "uspijeva",
    "završava", "započinje", "namjerava", "planira",
])

MODALI_1PL: frozenset = frozenset([
    "želimo", "hoćemo", "možemo", "moramo", "smijemo", "trebamo", "znamo", "umijemo",
    "počinjemo", "prestajemo", "nastavljamo", "pokušavamo", "uspijevamo",
    "završavamo", "započinjemo", "namjeravamo", "planiramo",
])

MODALI_2PL: frozenset = frozenset([
    "želite", "hoćete", "možete", "morate", "smijete", "trebate", "znate", "umijete",
    "počinjete", "prestajete", "nastavljate", "pokušavate", "uspijevate",
    "završavate", "započinjete", "namjeravate", "planirate",
])

MODALI_3PL: frozenset = frozenset([
    "žele", "hoće", "mogu", "moraju", "smiju", "trebaju", "znaju", "umiju",
    "počinju", "prestaju", "nastavljaju", "pokušavaju", "uspijevaju",
    "završavaju", "započinju", "namjeravaju", "planiraju",
])

MODALI_LICA: dict[str, str] = {}
for _skup, _lice in (
    (MODALI_1SG, "1sg"),
    (MODALI_2SG, "2sg"),
    (MODALI_3SG, "3sg"),
    (MODALI_1PL, "1pl"),
    (MODALI_2PL, "2pl"),
    (MODALI_3PL, "3pl"),
):
    for _m in _skup:
        MODALI_LICA.setdefault(_m, _lice)


def dobij_glagol(oblik: str) -> tuple[str, str] | None:
    """Vraća (infinitiv, lice) ili None."""
    return GLAGOLI_MAPA.get(oblik.lower())


def dobij_modal_lice(oblik: str) -> str | None:
    """Vraća lice modala ili None."""
    return MODALI_LICA.get(oblik.lower())


def broj_glagola() -> int:
    return len({inf for inf, _ in GLAGOLI_MAPA.values()})


def broj_oblika() -> int:
    return len(GLAGOLI_MAPA)


if __name__ == "__main__":
    print(f"Glagola: {broj_glagola()}")
    print(f"Prezent oblika: {broj_oblika()}")
    print(f"Modala (lica): {len(MODALI_LICA)}")
    print()
    print("Primjeri:")
    for oblik in ("radim", "radiš", "radi", "radimo", "rade", "idem", "želim", "hoću"):
        info = dobij_glagol(oblik)
        ml = dobij_modal_lice(oblik)
        print(f"  {oblik!r}: glagol={info}, modal_lice={ml}")
