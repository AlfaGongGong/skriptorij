# BOOKLYFI - KONTEKST PROJEKTA v4

Generirano: 2026-10-14
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: python3 main.py -> Flask na http://127.0.0.1:8080

---

<!-- AUTO:START -->

### Auto-generisano: 2026-10-25 17:45

**Git:**
- HEAD: 3b7972d prije: KONTEKST update

**Status:**
M .logs/KONTEKST_174520.log

**Zadnjih 5 commitova:**
3b7972d prije: KONTEKST update
0e4439b prije: KONTEKST.md update (P17, P18, FAZA 7)
b90e36c chore: BATCH A-2 — SIM105 contextlib.suppress (57), UP035/C401 partial; 12 ostalo za ručno
6f58379 chore: BATCH A — ruff autofix (I001, UP, SIM, RET, C401, B007, PIE810)
08bdad3 fix(ui): selectBadBlocks čita data-score (qh-cell je prazan div, textContent je bio 10)

<!-- AUTO:END -->

## POSTULATI RADA (MORANJE)

### P1 — Git, ne `.bak` fajlovi
- Prije svake izmene: `git add -A && git commit -m "prije: <opis>"`
- Ako izmena ne valja: `git checkout -- <fajl>` (vraća sve iz zadnjeg commita)
- Nikad ne koristiti `.bak` fajlove kao primarni mehanizam za vraćanje
- `.bak` fajlovi su ignorisani u `.gitignore`

### P2 — Jedna izmena, pa provera
- U jednom bloku TAČNO JEDNA izmena
- Posle izmene: `python3 -c "import ast; ast.parse(open('fajl.py').read())"`
- Ako ne prolazi — odmah `git checkout`, bez rasprave
- Nikad više od jedne izmene u jednom bloku

### P3 — Zabranjeni obrasci
- NE koristiti `re.sub` za izmene Python koda
- NE koristiti `st.find('\ndef ')` za pronalaženje kraja funkcije
- NE koristiti `sed -i` bez prikaza rezultata prije upisa
- NE koristiti `find/replace` bilo koje vrste

### P4 — Obavezan `diff` prije primene
- AI mora prije izmene prikazati:

      STARO: <tačan red>
      NOVO: <tačan red>

- Korisnik kaže "da" ili "ne". Bez toga AI ne dira ništa.

### P5 — Dijagnostika prije fixa
- Prikazati: tačan sadržaj funkcije, šta trenutno radi, šta treba da radi
- Ako ne može — nema pravo da menja

### P6 — Greška se poništava, ne popravlja
- Kad AI pogreši: `git checkout`, pa ispočetka drugačije
- Nikad ne "popravljati" preko greške — to pravi novu grešku

### P7 — Backup prije svake AI sesije
- `tar czf /storage/emulated/0/Download/skriptorij_$(date +%Y%m%d_%H%M%S).tar.gz .`
- Sigurnosna kopija cijelog projekta, ne pojedinačnih fajlova

### P8 — Kontekst ažuriran prije svake sesije
- Prije AI: napiši tačno šta je problem (jedna rečenica), šta je posljednja izmena koja je radila, šta NE SME da se dira

### P9 — Ako AI predlaže nešto što nisi tražio — STOP
- AI ne sme da dira ništa što nije u zahtevu
- Ako predlaže izmenu van zahteva — korisnik kaže "ne"

### P10 — AI-jev "OK" nije dokaz
- "Sintaksa OK" ne znači da je izmena ispravna
- Korisnik pokrene i vidi

### P11 — Integritet podataka prvo
- Prije izmene: proveriti broj poglavlja, znakova, hash pasusa
- Izvor naspram izlaza
- Obrada mora glasno pasti ako se ne slaže

### P12 — Modeli se ne hardkodiraju
- `model_discovery.py` pri startu povlači `GET /models`
- Bira iz žive liste, ne iz statičke mape
- `MODEL_MAP` se koristi samo kao fallback

### P13 — Raspodela opterećenja
- Kratki zadaci (SCORER, GLOSAR_UPDATE, VALIDATOR) → GROQ/GEMMA
- GEMINI → PREVODILAC, LEKTOR, POLISH (dugi promptovi)
- MISTRAL (1 RPM) → samo krajnja rezerva

### P14 — Otpornost
- Circuit breaker po (provider, ključ, model) sa rastućim cooldownom
- `quota_tracker` na disk (restart ne resetuje brojače)
- `finish_reason=length` → retry sa većim `max_tokens`
- NVIDIA dobija `thinking: False`
- GEMMA `None` → prvo dijagnostika, pa fix

### P15 — `live_audit` kao JSON, ne HTML string
- Backend šalje listu JSON događaja (id, nivo, tekst) sa `?since=id`
- Frontend ne parsira HTML nazad

### P16 — Output sa `clear` + `tee` u fajl
- Svaki blok počinje sa `clear` — prazan ekran, ništa staro ne sme da smeta
- Sve komande pišu u `/tmp/blok_$(date +%H%M%S).log` kroz `{ ... } 2>&1 | tee "$LOG"`
- Na kraju bloka: `echo "Log: $LOG"` — korisnik zna gde je
- Ako se izgubi početak: `cat $(ls -t /tmp/blok_*.log | head -1)` — vraća ceo blok iz fajla
- Cilj: korisnik uvek dobije čist, kompletan output od nule, bez traženja početka u starom terminalu

---

### P17 — LOG PUTANJA (Termux)

Nikad ne koristiti /tmp/ za logove — nije writable u Termux-u.

Uvek pre skripte:

    mkdir -p .logs
    TS=$(date +%H%M%S)
    LOG=.logs/ime_$TS.log
    exec > >(tee $LOG) 2>&1

Na kraju skripte: echo Log: $LOG

Log fajlovi su u .logs/ (gitignore).

### P18 — REPO GUARD

Svaka skripta koja dira git mora na pocetku imati:

    cd /root/skriptorij
    if [ ! -d .git ]; then echo FAIL: nema .git; exit 1; fi
    REPO=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL: repo je $REPO; exit 1; fi

Bez ovoga skripta ne sme da se izvrsi.


---

## STRUKTURA PROJEKTA
 /root/skriptorij/
main.py              -> Flask server (port 8080)
run.py               -> Batch obrada
stil_ai.py           -> Stilizacija EPUB-a (legacy, ostaje za pipeline)
epub/styler.py       -> NOVI STYLER (uniformni format, standalone + pipeline)
epub/normalizer.py   -> _strip_everything, _normalize_html
api/routes/          -> Flask endpointi (processing, qualities, keys, fleet, books, export, renewal, control, monitor)
core/                -> Engine, prompts, quality, metadata, kalkovi, chunking
processing/          -> Pipeline, workers, retro
epub/                -> Normalizer, styler, parser, packager
network/             -> HTTP, router, quota, rate limiter
config/              -> settings, ai_config, logger
analysis/            -> book_context, autor_analiza
templates/index.html -> UI
static/css/style.css -> Stilovi
static/js/main.js    -> Frontend
 
---

## PIPELINE

PREVODILAC -> LEKTOR -> KOREKTOR -> VALIDATOR -> GUARDIAN -> POLISH -> SCORER

Modovi: PREVOD (EN) ili LEKTURA (HR)

Kalkovi: 621 lista (94 DA, 261 ekavizam, 118 dinamicki, 43 dijalog, 51 pleonazam, 56 glagol)

---

## PROVIDERI

Kljucevi: GEMINI=12, GEMMA=16, GROQ=6, MISTRAL=5, OPENROUTER=4, NVIDIA=1, CLOUDFLARE=1

Modeli:
- GEMINI: gemini-3.5-flash-lite (primarni), gemini-3.1-flash-lite (fallback)
- GEMMA: gemma-4-26b-a4b-it
- GROQ: qwen/qwen3.8-27b (OTPM limit 1000!)
- MISTRAL: mistral-small-latest (1 RPM!)
- OPENROUTER: thinkingmachines/inkling:free
- NVIDIA: nemotron-3.5-lightning

PROVIDER_PRIORITY (nakon fixa):
- GEMINI, GROQ, GEMMA, OPENROUTER, MISTRAL, CLOUDFLARE, NVIDIA

---

## STILIZACIJA (epub/styler.py)

Tok stilizuj():
1. Ucitaj EPUB (files dict)
2. Nadji OPF, spine, manifest
3. Detektuj STVARNA poglavlja (_je_poglavlje)
   - Filtrira: uvod, o autoru, impresum, sadrzaj, copyright, posveta, zahvala
   - Min 8000 bajtova, min 5000 znakova teksta
   - Preskace fname: cover, titlepage, toc, nav, impressum, about
   - Preskace title: uvod, predgovor, o autoru, o knjizi, impresum, sadrzaj
4. Za svako poglavlje:
   - _ukloni_sve (brisi style, link, ornament, dropcap, klase, span-ove)
   - Vrati skriveno slovo iz spana u tekst (fix AAutorska)
   - _normalizuj (div->p, h4-h6->h3, font->unwrap, deduplikacija)
   - _dijalog (DIJALOG_TIPOGRAFIJA)
   - _dodaj_vijenac (ornament iznad naslova)
   - _dodaj_naslov (POGLAVLJE N)
   - _dodaj_dropcap (4em PNG, 3+ reda, prvo slovo nevidljivo)
5. Booklyfi stranice (naslovna + impresum) - dodaju se u OPF
6. Obrisi SVE HTML koji NISU poglavlja (osim booklyfi_*, cover)
7. Obrisi SVE TOC/NCX
8. Generisi NOVI toc.ncx + toc.xhtml (samo POGLAVLJE N)
9. Azuriraj OPF (manifest + spine)
10. Snimi EPUB

Idempotentnost: _ukloni_sve() PRIJE svega (brise stilove, klase, ornamente, dropcape, vraca skriveno slovo u tekst)

---

## BOOKLYFI STRANICE (nove)

epub/styler.py dodaje:
- booklyfi_001_naslovna.xhtml — naslovna stranica (Booklyfi izdanje, naslov, autor, potpis)
- booklyfi_002_impresum.xhtml — impresum (metadata, o izdanju, autorska prava, tehnicki podaci)
- booklyfi_toc.xhtml — TOC (sadrzaj sa POGLAVLJE N)

Redoslijed u EPUB-u:
1. Naslovna
2. Impresum
3. TOC
4. POGLAVLJE 1
5. POGLAVLJE 2
...

---

## UI (redizajn 2026-10-12)

Struktura: Header + Setup panel (wizard 2 koraka) + Dashboard + 8 tabova.

Tabovi: Kvalitet, Historija, Pregled, Revizija, Strucnjak, TTS, Stil, Monitor.

Fajlovi:
- templates/index.html
- static/css/style.css
- static/js/main.js
- static/js/heatmap.js
- static/js/ui/fleet.js

---

## POZNATI PROBLEMI

Aktivni:
1. Upload zone u Stil/TTS - klik ne otvara file picker (fix u toku)
2. Kontekst panel - book_name prazan (fix u toku)

Nedavno rijeseno (2026-10-14):
- epub/styler.py kompletan rewrite — uniformni format za sve knjige
- Booklyfi stranice (naslovna + impresum)
- max_words=250 u core/chunking.py (manji chunkovi, Gemini ne blokira)
- _naslov_element cita <title> iz <head> (originalni naslovi)
- Dropcap deduplikacija (uklanja stare img/span prije dodavanja)
- Ornament deduplikacija
- Skriveno slovo se vraca u tekst prije brisanja (fix AAutorska)
- Svi HTML fajlovi koji NISU poglavlja se brisu (uvod, impresum, copyright)
- TOC i NCX se regenerisu — samo POGLAVLJE N
- PROVIDER_PRIORITY: GEMINI #1, GROQ #2, GEMMA #3
- MODEL_MAP: NVIDIA nemotron-3.5-lightning, OPENROUTER thinkingmachines/inkling:free
- Anti-refusal u http_client.py (_build_gemini_native_payload)
- Uklonjen cross-provider cooldown (GEMINI<->GEMMA)
- app.py: logger definiran, review Sacuvaj/Obrisi radi, pct izracun
- run.py: podrska za dict/float format quality_scores
- processing/pipeline.py: merge quality_scores.json (ne prepisuje)
- static/js/main.js: _currentReviewStem, sacuvajTrenutniChunk, obrisiTrenutniChunk, auto-stil disabled
- utils/logging.py: MAX_AUDIT_LINES=500
- SambaNova uklonjen (mrtvi kljucevi, UUID format nije API kljuc)

Starije (2026-10-12 i prije):
- Dropcap stroga pravila, nevidljivo slovo za TTS
- _strip_everything idempotentnost
- Base64 -> pravi put za slike
- mode: booklyfi u /api/style_epub
- core/metadata.py BooklyFi Metadata Standard v1.0
- Migracija 10 starih + rekonstrukcija 2 pokvarene knjige
- UI redizajn: header, tabovi, log agregacija, heatmap
- Model pool: gemini-3.5-flash-lite + gemini-3.1-flash-lite

---

## GRUPNA RE-STILIZACIJA (2026-10-14)

25 EPUB-ova u STYLED/ re-stilizovano sa novim epub/styler.py:
- Backuptovi u /storage/emulated/0/Download/STYLED_backup_YYYYMMDD_HHMMSS/
- Svi dobili: naslovna, impresum, TOC, POGLAVLJE N, vijenac, dropcap
- Bez front/back matter (uvod, impresum, copyright, posveta)
- Uniformni format za sve

---

## ŠTA JE OSTALO — radni plan (revizija 2026-10-19)

Status svih tačaka iz tehničke revizije. Detalji u git logu (od `6fe627b` naovamo).

### A. Aktivna revizija (bugovi i nedostaci)

| # | Tačka | Status | Fajl |
|---|---|---|---|
| 1 | 429 drži semafor 120s | ✅ rešeno (sleep pre acquire) | network/http_client.py |
| 2 | Tri imena za isti model (qwen/gpt-oss) | ❌ nije adresirano | config/ai_config.py |
| 3 | Dupli MODEL_MAP / GEMINI_BASE_URL | ❌ nije adresirano | config/ai_config.py |
| 4 | SKIP_TITLES "prolaznost života" | ✅ rešeno (v7) | epub/styler.py |
| 5 | Dropcap gubi slovo u em/strong | ✅ rešeno (v5) | epub/styler.py |
| 6 | _dodaj_naslov briše sve h1-h3 | ✅ rešeno (v7) | epub/styler.py |
| 7 | XML escaping u NCX/TOC/NAV | ✅ rešeno (v5) | epub/styler.py |
| 8 | _je_poglavlje folder/podniz | ✅ rešeno (v5) | epub/styler.py |
| 9 | Gemma fallback dijagnostika | ✅ rešeno (log jasno pokazuje RPD) | network/provider_router.py |
| 10 | Cloudflare grana ostala | ✅ zatvoreno (funkcionalna, nije u prioritetu) | network/http_client.py |
| 11 | NVIDIA/GROQ + thinkingConfig duplo | ✅ rešeno (Grupa 2, 10 deletions) | network/http_client.py |
| 12 | live_audit kao JSON, ne HTML | ✅ rešeno (3a-1, 3a-2, 3b) | api/routes/monitor.py, static/js/main.js |
| 13 | Jitter sleep unutar semafora | ✅ zatvoreno (dizajnerski kompromis, 2s) | network/http_client.py |
| 14 | Cache hash fix | ✅ rešeno (blok 1-3) | processing/pipeline.py |
| 15 | Pola rata cache (318 .chk bez hash) | ⏳ odluka A (ostaje) | /storage/.../booklyfi_checkpoints |

### B. Predlozi — kod i rad sistema

- [ ] Jedan `providers.json` izvor istine (umesto razbijenog MODEL_MAP + AI_MODEL_STRINGS)
- [ ] Jedan HTTP klijent (`httpx`/`aiohttp`) umesto blokirajući `api_call` + async
- [ ] Stanje kvota na disk (verifikovati da restart ne resetuje brojače)
- [ ] Keš odgovora po chunku — dodati model + glosar u hash (trenutno samo chunk)
- [ ] Pametnije grupiranje: batch SCORER/VALIDATOR/glosar, chunk veličina po TPM-u
- [ ] Stilizator kao niz čistih faza (parsiranje, klasifikacija, transformacija, OPF)
- [ ] Dropcap slike kao zajednički fajlovi u EPUB (ne base64 u svakom poglavlju)
- [ ] Strukturirano logiranje (JSON događaji: nivo, modul, provider, maskiran ključ)
- [ ] Golden-test s mini EPUB + `pyflakes`/`ruff` prije svakog pokretanja

### C. Predlozi — UI

- [ ] Dnevnik kao JSON događaji s `?since=id`, umesto HTML stringa (povezano s A#12)
- [ ] Razmotriti SSE umesto pollinga (manje baterije, bolja reaktivnost)
- [ ] Donja traka s 3-4 glavna taba umesto 8 (Obrada, Kvalitet, Revizija, Više)
- [ ] Jedna glavna kartica statusa: faza, poglavlje X/Y, ETA, trenutni provider
- [ ] Kvote vizualno: trake po provideru (zeleno/žuto/crveno), oznaka kad zapne
- [ ] Intro s three.js — prikazati samo prvi put, poštovati `prefers-reduced-motion`, lijeno učitavanje

### D. Predlozi — UX

- [ ] Poruke umesto sirovih logova ("GEMINI kvota iscrpljena, prebacujem na GROQ")
- [ ] Filter u dnevniku "samo upozorenja i greške"
- [ ] Obavijest kad je gotovo (service worker `sw.js` već postoji)
- [ ] Wake Lock da ekran ne zaspi tokom obrade
- [ ] Obrada preživljava osvježavanje stranice, dugme "Nastavi od checkpointa" uvijek vidljivo
- [ ] Revizija: original i prijevod jedno uz drugo, diff po riječima, akcije prihvati/odbaci/regeneriraj
- [ ] Klik na heatmap vodi direktno na taj blok
- [ ] Pregled prije pune obrade: iframe preview (naslovna, prvo poglavlje, plan TOC-a)
- [ ] Dugme "Provjeri ključeve" s kvačicama po provideru (logika u `test_complete_v4.py`)

### E. Redosled rada (grupisanje po fajlovima)

**Grupa 1:** `config/ai_config.py` — tačke A#2, A#3 (~30 min)
**Grupa 2:** `network/http_client.py` — tačke A#10, A#11, A#13 (~25 min)
**Grupa 3a:** `api/routes/monitor.py` — tačka A#12 backend JSON (~60 min)
**Grupa 3b:** `static/js/main.js` — tačka A#12 frontend parsiranje (~30 min)
**Grupa 4+:** arhitektonske promjene (B) posle A revizije, jedna po jedna, sa golden-testom

**Preporučeni sledeći:** Grupa 1, prvo #3 (duplikati), pa #2 (tri imena za model).

---

## FAZA 2 (2026-10-19) — razdvajanje pool-ova + fallback lanac

### Šta je urađeno

1. **GEMMA pool odvojen od GEMINI** (`api_fleet.py`, commit `7627dfa`)
   - Prije: `GEMMA = GEMINI ∪ GEMMA` (~20 ključeva, deljeni)
   - Poslije: `GEMMA = samo GEMMA` (8 ključeva), backward compat ako GEMMA prazan
   - Razlog: dva odvojena servisa, svaki sa svojim limitima

2. **QA score poruka dobija kontekst** (`processing/pipeline.py`, commit `1e33599`)
   - Prije: `⚠️ Blok 3 [naracija]: score=5.2 — ...`
   - Poslije: `⚠️ [001.xhtml] Blok 3 [naracija]: score=5.2 (prevodilac: GEMINI) — ...`
   - Razlog: bez `file_name` i prevodioca, score je bez konteksta

3. **Gemini fallback lanac: kontekst → Gemma → Mistral** (`network/http_client.py`, commit `aa2f20d`)
   - Prije: kontekst → OpenRouter Nemotron → odustani
   - Poslije: kontekst → Gemma → Mistral → odustani
   - Razlog: Gemma je odvojen pool (radi), OpenRouter nije adekvatan

4. **Gemma fallback lanac: kontekst → Mistral** (`network/http_client.py`, commit `e9f1379`)
   - Prije: kontekst → OpenRouter Nemotron → odustani
   - Poslije: kontekst → Mistral → odustani
   - Sinhronizovano sa Gemini lancem

### Rezultat

- OpenRouter više nije u aktivnom lancu (definicija ostaje, nigde se ne poziva)
- Gemma ima odvojene ključeve — može da radi kad Gemini padne
- QA score poruke imaju dovoljno konteksta za dijagnostiku

### Šta je ostalo

- **`_posalji_na_openrouter`** — mrtav kod, čeka odluku da li obrisati
- **Nepotrebne/ponovljene poruke u logu** — treba primere iz UI (screenshot ili tekst)
- **Gemma ključevi** — 4 od 8 se preklapaju sa GEMINI (korisnik ih duplo stavio)

---

---

## FAZA 3 (2026-10-20) — jedan scorer + deterministicke metrike

### Sta je uradjeno

1. **Base64/truncated `.chk` fix** (`processing/pipeline.py`, commit `71124bf`)
   - Prije: `_chk_read` prihvatao `.chk` sa 53 chars umesto 2000+ izvora (base64 dropcap video kao tekst)
   - Poslije: odbija ako izvor > 500c a `.chk` < 50% izvora, ili < 20 chars
   - Rezultat: 22 nepotpuna bloka iz Pola_rata se re-obradjuju umesto da budu kesirana

2. **F2 — jedan scorer, jedan izvor** (`processing/pipeline.py`, commit `52a1161`)
   - Prije: V2 put pisao heuristicki score (`ocijeni_kvalitet`), V1 put pisao AI score u `quality_scores.json`
   - Poslije: V2 put uvek poziva `_quality_scoring` (AI scorer), heuristicki ostaje samo za retry odluku unutar V2
   - Rezultat: `quality_scores.json` ima konzistentan izvor (AI score)

3. **`core/metrics.py` — deterministicki brojaci** (novi fajl, commit `b388528`)
   - `compute_metrics(text, source)` vraca: `ekavizmi_per_1000`, `en_ostaci_per_1000`, `duplikati`, `ratio_source_target`, `tipografija_greske`, `reci_ukupno`
   - Bez AI poziva, uporedivo izmedju knjiga i kroz vreme
   - 18/18 testova (`tests/benchmarks/test_metrics.py`)

4. **F3a — metrike se racunaju paralelno** (`processing/pipeline.py`, commit `013c9c6`)
   - `_quality_scoring` sada pise i `quality_metrics.json` (odvojen od `quality_scores.json`)
   - `quality_scores.json` ostaje nepromenjen — citaci ne vide razliku

5. **`_navodnici_greske` — parnost po tipu** (`core/metrics.py`, commit `c116f08`)
   - Prije: mesao ASCII `"` i njemacki `„"` u isti zbir → `part0090` davao 15 laznih gresaka
   - Poslije: ASCII `"` paran, `„..."` mora biti par, `«»`, `''` odvojeno
   - Rezultat: `part0090` = 1 stvarna greska (chunk boundary), bilo 15

### Brzi fixevi istog dana (povezani)

| Commit | Fajl | Sta |
|---|---|---|
| `3fbea77` | `processing/pipeline.py` | `stvarno_prevedeno` sync u `shared_stats` (UI prikaz) |
| `7b1a5c1` | `network/http_client.py` | Ispis `prelazim na Mistral` prefiks `[GEMINI->GEMMA]` |
| `f22be6a` | `utils/logging.py` | `add_audit` dedupe — ista poruka u 2s → 1 zapis sa `(xN)` |
| `a53d518` | `core/quality.py` + `pipeline.py` | Cache accept 7.5, retry target 9.2 (realno dostizno) |
| `91646eb` | `config/ai_config.py` | MISTRAL `preferred=[]` (1 RPM ne moze biti preferred) |
| `7690c21` | `config/ai_config.py` | PROFILES uskladjeni sa PRIORITY |
| `53f4293` | `config/ai_config.py` | Gemma na kraj prioriteta u svih 10 uloga |
| `f498d21` | `network/model_discovery.py` | GEMINI filter — uklonjen `gemma-4` |
| `562b626` | `network/model_discovery.py` | NVIDIA vracen u `_MODELS_ENDPOINTS` |
| `71bb6fe` | `app.py` | Discovery pri startu servera |
| `31c774b` | `network/model_discovery.py` | Ispravni URL-evi za GROQ/OPENROUTER |
| `d8c6760` | `network/http_client.py` | Uklonjen `_posalji_na_openrouter` + Gemma 503 agregacija |

### Reseno iz FAZA 2 "Sta je ostalo"

- **`_posalji_na_openrouter`** — uklonjen u `d8c6760`
- **Nepotrebne/ponovljene poruke** — `add_audit` dedupe (`f22be6a`)
- **Gemma kljucevi overlap** — uklonjen ranije (GEMINI 12 / GEMMA 4, 0 overlap)

### U toku (FAZA 3 nedovrseno)

- **F3b** — `quality_class` iz metrika (`OK` / `REVIEW` / `REJECT`)
- **F3c** — UI prikaz metrika umesto samo score-a

### Otvoreno (za buduce faze)

- **EKAVIZMI `[149]`** (`\breci\b`) — hvata i ijekavski "reci" (lazni pozitiv). U `core/kalkovi/ekavizmi.py`, treba suziti na infinitiv.
- **`ocijeni_kvalitet`** — jos u `WorkersV2` kao interni hint za retry, moze se ukloniti kad F3b bude gotov
- **`_qa_ai_ocjena`** — sinhroni AI scorer, ostaje samo za retry feedback
- **Skala zasícena** — 75% blokova na 9.8. Metrike su prvi korak; potpuni redizajn tek sledi.

---

---

## FAZA 4 (2026-10-22) — cleanup, discovery, refaktor, fallback

### Sta je uradjeno (20+ commitova, 84/84 testova)

**Fallback i otpornost:**
- `e827ba3` — 503 UNAVAILABLE (Google high demand) — 5s backoff, rotacija modela
- `3b82859` + `9a82738` — 429: RPM 60s vs RPD do ponoci (streak 3x), retryDelay iz body
- `e827ba3` — URLError retry (24% u dijagnostici)
- `a4597c9` — GEMINI_TIMEOUT 45→20s, global 30s u petlji, _async_http_post 45→20
- `9a82738` — fallback 2 kruga (30s/60s pauze) + treci GEMINI + ALL_FAILED marker

**Discovery i modeli:**
- `9cb1c8a` — discovery filter (audio/vision/reasoning/non-HR odbaceni)
- `56eb4fe` — dinamički izbor modela po ulozi (`config/model_roles.py` + `enrich_models_with_metrics`)
- `9c44f01` — Blok 2: 6 provider-level profila + aliasi

**Cleanup i refaktor:**
- `6b65936` — provider_router namespace po prov_upper (GEMINI/GEMMA razdvojeni)
- `e4eb8e0` — 4 test fixa (api_fleet UnboundLocal, pool modeli, gemma pool)
- `e3d9982` — A#3 hardkodovani URL-ovi
- `c881162` — obrisan metrics.js duplikat (F3d pokriva metrike)
- `f88a4bc` — .fq-* trake vracene

**Replacements:**
- `542a8c3` — Moon+ replacement parser + CLI (post-polish EPUB)
- Testirano na A Little Hatred: 266 pravila, 175 aktivirano, 4335 zamjena

### Baseline

**Testovi:** 84 passed, 0 failed (bio 11 failed, 48 passed)

### Kljucni testovi danas

- `gemini-3.5-flash-lite`: 12s po pozivu (stabilno)
- `gemini-3.1-flash-lite`: 30-47s (high demand, mrtav danas)
- `gemini-flash-lite-latest`: 75s (high demand)
- `gemini-3.8-flash`: 7.79s ali 20 RPD
- **GROQ qwen3.8-27b: 2.4s, 500+ RPD**
- **NVIDIA nemotron-3-ultra-550b: 9.4s**

### Otvoreno

- **GEMMA discovery** — nema endpoint, `fetch_models("GEMMA")` vraca `[]`
- **Blok 3** — prompts.py patchevi po provajderu
- **Blok 4** — workers.py provider umjesto model_ime
- **Blok 5** — ai_config.py AI_MODEL_STRINGS fallback
- **GEMMA/MISTRAL/NVIDIA dedup** — previse modela poslije filtera
- **`gemini-flash-lite-latest`** — testirati sutra kad Google odmori
- **3 sumnjiva pravila** u replacement fajlu (`Uffrith→Afriθ`, `Meadow→medou`, `Oxelu→Okse`)

---

---

## FAZA 5 (2026-10-23) — retryDelay fix, GEMMA discovery, mode detection, replacements_learn

### Sta je uradjeno danas (14 commitova)

**Kriticni fixevi (blokirali produkciju):**

| Commit | Fajl | Sta |
|---|---|---|
| `b7ac191` | `api_fleet.py` | **retryDelay > 3600s bez RPD oznake = RPM 60s** (sprecena 10h blokada) |
| `5317aee` | `api_fleet.py` | f-string `.0fs` → `.0f}s` (invalid format specifier) |
| `7f1cf6c` | `api_fleet.py` | RPD detekcija — samo eksplicitno (`rpd`/`daily`/`per day`), nikad streak heuristika |
| `7a11c48` | `run.py`, `core/engine.py` | Mode detection — filename heuristika (`PREVEDENO` → LEKTURA), `_detect_language` vraca LEKTURA/PREVOD |

**GEMMA discovery (bio mrtav od pocetka):**

| Commit | Fajl | Sta |
|---|---|---|
| `b8ea8be` | `model_discovery.py` | `pageSize=50` → `pageSize=1000` (vraca 60 modela, 2 gemma) |
| `8974e9d` | `model_discovery.py` | GEMMA grana **pre** `_MODELS_ENDPOINTS` provere (GEMMA nema endpoint u mapi) |

**Replacements / Faza 3:**

| Commit | Fajl | Sta |
|---|---|---|
| `4a39e8c` | `tools/replacements_learn_cli.py` | CLI za analizu Moon+ replacement fajlova |
| `73b60f1` | `core/replacements_learn.py` | Learning iz fires — glosar + anti-pattern kandidati |
| `d25aa0a` | `core/replacements_learn.py` | No-op filter (search == replace) |

**Cleanup iz FAZE 4 (dodatno):**

| Commit | Fajl | Sta |
|---|---|---|
| `fd68c6a` | `checkpoint_cleaner.py` | `_ocisti_json_wrapper` cisti escape u HTML-u (`class=„X"` → `class="X"`) |
| `6093652` | `checkpoint_cleaner.py` | `_ocisti_json_wrapper` hvata `chunk_sha` pre JSON provere |
| `b48037f` | `http_client.py` | `_extract_gemini_native` filtrira `<thinking>`, thinking tagove (qwen/llama), channel thought blokove |

### Baseline

**Testovi:** 84 passed, 0 failed

### Mode detection — kako sad radi

1. `book_analysis.json` u checkpoint folderu cuva `knjiga_mode` (`PREVOD` ili `LEKTURA`)
2. `_odredi_strategiju` (run.py) cita:
   - Prvo `book_analysis.json` — ako postoji `saved_mode`, koristi ga
   - **Override:** ako `saved_mode == PREVOD` ali filename sadrzi `PREVEDENO` → vrati LEKTURA
   - Ako nema `saved_mode` — filename heuristika, pa `_detect_knjiga_mode`
3. `_detect_language` (engine.py) sada vraca `LEKTURA`/`PREVOD` (ne `HR`/`EN`)
4. `pipeline.py:782` — `if knjiga_mode == "LEKTURA"` sada radi (pre nije, jer je bilo `"HR"`)

### GEMMA discovery — kako sad radi

- `_fetch_gemini_native_models(api_key, provider_filter="GEMMA")` vraca 2 modela
- `_fetch_gemini_native_models(api_key, provider_filter="GEMINI")` vraca 18 modela
- `fetch_models("GEMMA")` vraca 2 modela (gemma-4-31b-it, gemma-4-26b-a4b-it)
- **Nije "nije resivo"** — sa `pageSize=1000` Google API vraca 60 modela ukupno

### retryDelay — kako sad radi

- Google `retryDelay: "36564s"` (10h) → ako **nema** `rpd`/`daily`/`per day` u `message` → **RPM 60s**
- Google `retryDelay: "36564s"` (10h) → ako **ima** `daily` u `message` → **RPD 36564s** (10h)
- Google `retryDelay: "60s"` → **RPM 60s** (bez provere, ispod 1h)
- Bez `retryDelay` — kao pre (`_is_explicit_rpd` provera)

### The_Trouble_With_Peace — stanje

**Input:** `/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_-_The_Trouble_With_Peace_PREVEDENO_STYLED.epub`

**Output:**
- `_FIXED.epub` — replacement + escape fix (XML 0/82)
- `_FINAL.epub` — stilizovan (78 chapters, 73 dropcaps, NCX 78 navPoints, XML 0/80)

**Replacement:** `/storage/emulated/0/Download/The_Trouble_With_Peace_replacement.txt` (auto-generisan, 131 pravila, ~5000 zamena)

**Checkpoint folders:**
- `_skr_The_Trouble_With_Peace` — 447 `.chk`, 448 scores, `book_analysis.json: LEKTURA`
- `_skr_PREVEDENO_The_Trouble_With_Peace` — 299 `.chk`, 132 scores

### Otvoreno (posle FAZA 5)

**Blok 4** — `workers.py` provider umesto `model_ime` (reverse lookup) — 45 min
**Blok 5** — `ai_config.py` `AI_MODEL_STRINGS` fallback po provajderu — 30 min
**Testovi discovery** — za `pageSize=1000` i GEMMA granu — 30 min
**`part0066.html`** — JSON wrapper u `pipeline.py` (bug od pre) — 1h
**3 sumnjiva pravila** u replacement fajlu (`Uffrith→Afriθ`, `Meadow→medou`, `Oxelu→Okse`)
**`GEMINI_BASE_URL`** (Cloudflare) mrtav u `provider_urls.py`
**Sve B/C/D** iz ranijih faza — ne-blokirajuce

### Kljucne lekcije danas

1. **`pageSize=1000`** je bio skriveni bug — GEMMA discovery je bio "mrtav" jer Google vraca 18 modela sa `pageSize=50`, a 60 sa `pageSize=1000`. **Nije "nije resivo" — bila je pogresna pretpostavka.**
2. **12h blokada kljuceva** — `retryDelay: 36564s` se prihvatao direktno. Google ne razlikuje RPM od RPD u tekstu. **Fix:** ako > 3600s i nema `daily`/`rpd` — RPM 60s.
3. **Mode mismatch** — `book_analysis.json` je imao `PREVOD` za HR knjigu. Pipeline je pokusavao PREVODILAC na HR tekstu. Model je vracao "vec je HR", scorer davao 3. **Fix:** filename heuristika + `_detect_language` vraca LEKTURA/PREVOD.

---

---

## FAZA 6 (2026-10-24) — alati za cistocu projekta

### Sta je dodato

**`tools/cistoca.sh`** — read-only skeniranje projekta (ili `--fix` sa backup-om).
Sekcije: pokvareno (sintaksa, importi, ruff, JSON, shellcheck, mypy, testovi),
ne koristi se (vulture, orfani, deptry, zakomentirano), duplo (pylint, AST,
md5), smece, sigurnost (bandit, tajne), kvalitet (debug, print, TODO, imena
modela, radon, stil, format), struktura (gitignore, requirements, README).
Rezultat: `cistoca_izvjestaj.txt`. Nista ne menja bez `--fix`.
Sa `--fix`: backup u `.cistoca/backup_TIMESTAMP.tar.gz`, karantina u
`.cistoca/karantina_TIMESTAMP/`, automatski rollback ako sintaksa pukne.

**`tools/popravi_projekat.sh`** — automatske popravke:
1. Karantina `.bak*`, `.corrupt*`, `_RECOVERED`, praznih fajlova (60 fajlova)
2. Brise `__pycache__/` (17 foldera)
3. `pyproject.toml` sa `testpaths=["tests"]` (resava INTERNALERROR pri collectu)
4. JSON — odbacuje visak iza prvog JSON objekta
5. F821 — dodaje `import X` za stdlib nedostajuce (`os`, `re`, ...)
6. F401 — brise neiskoristene importe (cuva re-export u `__init__.py`)
7. Ruff sigurne autopopravke + format
8. Tajne u kodu — chmod 600, dodaje u `.gitignore`, upozorava za rotaciju
9. `.env.example` iz `.env` (bez vrednosti)
10. `requirements.txt` — dodaje zavisnosti, `requirements.lock.txt` iz `pip freeze`
11. `README.md` kostur ako ne postoji
12. `RUCNO_ZA_POPRAVITI.md` — 30 mesta sa kontekstom koda

Sigurnost: backup pre svega, automatski rollback ako sintaksa ili F821 puknu.

### Rezultat na projektu (2026-10-24)

- **128 fajlova promenjeno**, ~8967 insertions, ~4735 deletions (ruff format + F401)
- **60 fajlova u karantinu**: `.bak_*`, `.corrupt*`, `_RECOVERED`, prazni
- **1 fajl obrisan iz koda**: `core/dynamic_few_shot.py` (orfan, nema referenci)
- **3 fajla sa tajnama** chmod 600: `api_state.json`, `dev_api.json`, `quota_cooldowns.json`
- **requirements.txt** +3: `Werkzeug>=3.1.8`, `mobi>=0.4.1`, `httpx>=0.28.1`
- **Testovi posle: svi prolaze** (94 unit/integration + 8 golden)
- F821 (nedefinisana imena): 23 → 19 (4 resena automatski, 19 u RUCNO_ZA_POPRAVITI.md)

### Napomene

- Oba skripta pretpostavljaju venv u `venv/` (koriste `venv/bin/python`)
- `--bez-instalacije` preskace `pip install` alata
- `--dir /put/do/projekta` radi nad drugim projektom
- `pyproject.toml` automatski `testpaths=["tests"]` — resava INTERNALERROR

### Otvoreno

- `RUCNO_ZA_POPRAVITI.md` — 30 mesta sa kontekstom koda, treba ljudska odluka
- `classla` u `requirements.txt` — nije instaliran paket, ali se uvozi (mozda treba `pip install classla`)
- `skriptorij` u `requirements.txt` — self-import, ignorisi

---

---

## FAZA 7 (2026-10-25) — UI selekcija, Ruff, P17/P18

### Uradjeno

UI selekcija:
- f0a96c7 — selekcija bar u Kvalitet tabu
- 03d0295 — inline onclick, SW v4, bump verzije
- d45623e — qh-cell umesto qs-block-pill
- 08bdad3 — data-score umesto textContent
- Backfill 20 NEPREVEDENO markera na score 1.0

Ruff:
- 6f58379 (BATCH A) — I001, UP, SIM, RET, C401, B007, PIE810 (36 nalaza)
- b90e36c (BATCH A-2) — SIM105 contextlib.suppress (57 nalaza)

Pravila:
- P17 — log u .logs/
- P18 — repo guard pre git operacija

### Trenutni baseline

- Testovi: 102 passed
- Ruff baseline (F,E9,B,PLE,PIE): 160 nalaza
  - S110 x124 (fail-safe pattern, ne diramo)
  - F401 x31 (unused imports, auto-fix)
  - B905 x3 (zip strict, rucno)
  - F811 x1, B007 x1
- Commit: b90e36c

### Otvoreno — prioritet

BATCH P (pipeline fix):
- P1 — _je_placeholder_lokalni prepoznaj NEPREVEDENO marker
- P2 — process_chunk_with_retry upisi marker + score 1.0
- P3 — workers.py res is None upisi marker, skip QA

BATCH HIGIJENA:
- A-3 — I001, F401, SIM105, B007, F811 auto-fix
- A-4 — UP035 (10), B905 (3) rucno
- A-5 — pyproject.toml ignore S110
- B — test_complete_v4 u tools/, .env.example, pin requirements, orfani
- D — git rm cached tajne, Bandit B605/B602

BATCH F (KONTEKST planirano):
- Blok 4 — workers.py provider umesto model_ime
- Blok 5 — ai_config.py AI_MODEL_STRINGS fallback
- A2 — tri imena za isti model
- EKAVIZMI — suziti \breci\b
- part0066.html — JSON wrapper

---

KRAJ KONTEKSTA
