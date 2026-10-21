# HANDOFF — Claude zadaci za Booklyfi

Ovaj dokument je namijenjen Claude-u za izolovane zadatke na projektu Booklyfi. Claude NE treba ceo repo — treba mu brief za konkretan zadatak, lista zabranjenih fajlova, i primjer ulaza/izlaza.

## Opšti kontekst projekta

Booklyfi je Python/Flask pipeline za prevođenje i lekturu EPUB knjiga. Radi u `/root/skriptorij/`, server na `http://127.0.0.1:8080`. Ključni moduli:

- `epub/styler.py` — stilizacija EPUB-a (naslovna, impresum, TOC, dropcap, vijenac)
- `processing/pipeline.py` — PREVODILAC → LEKTOR → KOREKTOR → VALIDATOR → GUARDIAN → POLISH → SCORER
- `network/http_client.py` — HTTP pozivi ka 8+ AI provajdera
- `core/quality.py` — AI scorer kvaliteta (1–10, zasićen)
- `core/metrics.py` — deterministički brojači (6 metrika, 18/18 testova)
- `core/kalkovi/` — ekavizmi, pleonazmi, dijalog, glagoli (621 lista)

Detalji u `/root/skriptorij/KONTEKST.md`.

## Pravila (P1–P16)

- P1: Git, ne `.bak`. Prije izmene commit.
- P2: Jedna izmena, pa `ast.parse` / pytest.
- P3: Bez `re.sub` za izmenu Python koda, bez `sed -i`, bez find/replace.
- P4: `STARO:` / `NOVO:` diff prije primjene, korisnik kaže „da".
- P9: Ne diraj ništa van zadatka.
- P12: Modeli se ne hardkodiraju — koristi `model_discovery` ili `ai_config`.
- P15: `live_audit` kao JSON, ne HTML string.

**Puna pravila:** `/root/skriptorij/KONTEKST.md`, sekcija „POSTULATI RADA".

## Zabranjeni fajlovi (Claude ih NE dira)

- `epub/styler.py`
- `processing/pipeline.py`
- `network/http_client.py`
- `network/provider_router.py`
- `config/ai_config.py`
- `core/quality.py`
- `api_fleet.py`
- `core/engine.py`

Ako zadatak zahteva izmenu ovih — vrati „OVO NE DIRAM, potreban je kontekst sesije" i stani.

## OBAVEZNO — CLAUDE_LOG.md poslije svakog zadatka

Poslije svakog zavrsenog zadatka, azuriraj `/root/skriptorij/CLAUDE_LOG.md`.
Ovaj fajl je jedina memorija izmedju Claude acc — kad korisnik potrosi limit
i predje na novi acc, salvije samo ovaj fajl + KONTEKST.md i nastavljas
kao da si isti acc. NE preskaci ovo.

Format (append-only, ne brisi staro, dodaj novo na vrh ispod zaglavlja):

```
## [YYYY-MM-DD HH:MM] Zadatak: <kratki naziv>
- Status: ZAVRSEN | DJELIMICNO | BLOKIRAN
- Fajlovi kreirani: <pune putanje>
- Fajlovi izmijenjeni: <pune putanje>
- Testovi: <broj prosli>/<broj ukupno>, npr. 8/8
- Commit: <hash ako je korisnik commitovao>
- Sljedeci korak: <1 recenica>
- Napomene: <opciono — sta nije uradjeno, gdje zapelo>
```

Ako je zadatak DJELIMICNO ili BLOKIRAN — obavezno napisi u "Napomene"
tacno gdje si stao (fajl, linija, greska). Sljedeci acc mora moci nastaviti
bez pitanja.

Ako je zadatak ZAVRSEN — "Sljedeci korak" je konkretan (npr. "Iteracija 2 iz
HANDOFF.md").

Ne cekaj da te korisnik pita — azuriraj log prije nego vratis odgovor.

## Kako koristiti ovaj dokument

Za svaku iteraciju kopiraj brief u Claude sesiju. Claude:

1. Pročita `/root/skriptorij/KONTEKST.md` i ovaj dokument
2. Pročita samo fajlove iz brief-a
3. Napravi izmenu po pravilima P1–P16
4. Vrati rezultat po šablonu (na kraju dokumenta)

---

## Iteracija 1 — F3b + EKAVIZMI

### Zadatak 1.1 — `core/quality_class.py` (novi fajl)

**Kontekst:** FAZA 3 je u toku. Determinističke metrike su gotove (`core/metrics.py`, `compute_metrics`), 18/18 testova prolazi. Treba kategorička ocjena (OK/REVIEW/REJECT) da bi pipeline mogao odlučiti šta dalje sa blokom, umesto subjektivnog score-a 1–10 (zasićen — 75% blokova na 9.8).

**Fajl:** `core/quality_class.py` (novi)

**Pročitaj prije:** `core/metrics.py`, `KONTEKST.md` sekcija „FAZA 3".

**API:**

```
def classify_quality(metrics: dict, thresholds: dict | None = None) -> str
    Vraća "OK" | "REVIEW" | "REJECT"
```

**Podrazumevane granice:**

```
DEFAULT_THRESHOLDS = {
    "ekavizmi_per_1000_ok": 1.0,
    "ekavizmi_per_1000_review": 3.0,
    "en_ostaci_per_1000_ok": 5.0,
    "en_ostaci_per_1000_review": 20.0,
    "duplikati_ok": 0,
    "duplikati_review": 2,
    "tipografija_ok": 3,
    "tipografija_review": 10,
    "ratio_ok_min": 0.8,
    "ratio_ok_max": 1.2,
    "ratio_review_min": 0.5,
    "ratio_review_max": 2.0,
}
```

**Logika:**
- Sve metrike u „ok" granicama → `"OK"`
- Bilo koja u „review" granicama → `"REVIEW"`
- Bilo koja van „review" → `"REJECT"`
- Nedostajući ključevi → tretiraj kao 0 (osim `ratio_source_target` — ako `None`, preskoči ratio)
- `reci_ukupno` se ne koristi za klasifikaciju

**Primer:**

```
metrics = {
    "ekavizmi_per_1000": 0.5,
    "en_ostaci_per_1000": 2.0,
    "duplikati": 0,
    "ratio_source_target": 1.05,
    "tipografija_greske": 1,
    "reci_ukupno": 1500,
}
classify_quality(metrics)  # → "OK"
metrics["ekavizmi_per_1000"] = 5.0
classify_quality(metrics)  # → "REJECT"
```

**Test:** `tests/unit/test_quality_class.py` (novi). Pokriva:
1. `test_ok` — sve u granicama → OK
2. `test_review_ekavizmi` — ekavizmi između ok/review → REVIEW
3. `test_review_duplikati` — duplikati 1 → REVIEW
4. `test_reject_ekavizmi` — ekavizmi > review → REJECT
5. `test_reject_tipografija` — tipografija > review → REJECT
6. `test_prazan_metrics` — `{}` → OK
7. `test_ratio_none` — ratio `None` → preskoči u odluci
8. `test_custom_thresholds` — prosljeđene granice mijenjaju odluku

Ako `tests/unit/` ne postoji, napravi `tests/unit/__init__.py` (prazan).

### Zadatak 1.2 — `core/kalkovi/ekavizmi.py` — suziti `\breci\b`

**Kontekst:** U `core/kalkovi/ekavizmi.py` postoji lista `[149]` sa `\breci\b` koja hvata **ijekavski** „reci" (imperativ: „reci mi") kao lažni ekavizam. Treba suziti na infinitiv.

**Fajl:** `core/kalkovi/ekavizmi.py` (postojeći)

**Pročitaj prije:** `core/kalkovi/ekavizmi.py`, `core/kalkovi/__init__.py`.

**Šta treba:**
- Nađi listu `[149]` sa `\breci\b`
- Suziti na kontekst gde je „reci" infinitiv a ne imperativ

**Predlog logike:**
- „reci" na početku rečenice, bez „da" prije → imperativ (IJEKAVSKI, NE ekavizam)
- „reci" posle „da", „ću", „ćeš", „hoću", „mogu" → infinitiv (EKAVIZAM)
- „reći" → uvek ekavizam
- „reci" u drugim kontekstima → vidi postojeći test

**Test:** `tests/unit/test_ekavizmi.py` (ako postoji, dopuni; ako ne, napravi). Pokriva:
1. „Rekao mi je da reci istinu" → nije ekavizam (imperativ)
2. „Rekao mi je da reći istinu" → jeste ekavizam
3. „Reci mi šta misliš" → nije ekavizam (imperativ na početku)
4. „On će reci istinu" → jeste ekavizam (infinitiv)

### ŠTA NE SMEŠ (oba zadatka)

- Ne diraj: `core/metrics.py`, `epub/styler.py`, `processing/pipeline.py`, `network/http_client.py`, `config/ai_config.py`, `core/quality.py`
- Ne pokreći Flask, ne pozivaj AI API, ne pravi commit

---

## Iteracija 2 — F3c-JS + C5-JS

### Zadatak 2.1 — `static/js/metrics.js` (novi)

UI prikaz metrika pored score-a. Čist JS, bez zavisnosti.

**API koji troši:** `GET /api/monitor/metrics?stem=<stem>`.

**Renderuje:** panel sa 6 metrika + badge za `quality_class` (zeleno OK, žuto REVIEW, crveno REJECT).

### Zadatak 2.2 — `static/js/fleet.js` — vizualne trake kvota

Dopuni postojeći sa trakama po provajderu (zeleno/žuto/crveno), oznaka kad zapne.

**Pročitaj prije:** `static/js/fleet.js`, `api/routes/fleet.py`.

---

## Iteracija 3 — C3 + C4

### Zadatak 3.1 — 3-4 taba umesto 8

Grupiši: Obrada, Kvalitet, Revizija, Više.

**Pročitaj prije:** `templates/index.html`, `static/js/main.js`.

### Zadatak 3.2 — jedna kartica statusa

Spoji fazu, poglavlje X/Y, ETA, trenutni provider u jednu karticu na vrhu.

**Pročitaj prije:** `api/routes/monitor.py`, `static/js/main.js`.

---

## Iteracija 4 — D2 + D4

### Zadatak 4.1 — filter „samo upozorenja i greške"

Dugme u dnevniku, lokalno u JS, ne dira backend.

**Pročitaj prije:** `static/js/main.js` (live_audit dio).

### Zadatak 4.2 — Wake Lock

`navigator.wakeLock.request('screen')` kad obrada krene, release kad završi.

**Pročitaj prije:** `static/js/main.js` (start obrade).

---

## Iteracija 5 — D3 + D7

### Zadatak 5.1 — obavijest kad je gotovo

`Notification API` + postojeći `sw.js`.

**Pročitaj prije:** `static/sw.js`, `static/js/main.js`.

### Zadatak 5.2 — klik na heatmap → blok

Klik vodi na blok (scroll + highlight).

**Pročitaj prije:** `static/js/heatmap.js`, `static/css/style.css`.

---

## Iteracija 6 — C6 + B9

### Zadatak 6.1 — three.js intro (samo prvi put)

Lagana animacija, `prefers-reduced-motion`, lijeno učitavanje.

**Pročitaj prije:** `templates/index.html`.

### Zadatak 6.2 — `tests/golden/` + `Makefile`

Golden-test sa mini EPUB + `pyflakes`/`ruff` hook.

**Pročitaj prije:** `tests/`, `requirements.txt` (ili `pyproject.toml`).

---

## Šablon za rezultat (Claude vraća)

1. **Fajlovi:** pune putanje novih/izmenjenih
2. **Test:** pytest output (zadnjih 30 linija), ili „nema testova za JS"
3. **Ako pao:** šta si probao
4. **Ako menjao spec:** gdje i zašto
5. **Ne šalji kod u odgovoru** — samo putanje, rezultat, izveštaj
