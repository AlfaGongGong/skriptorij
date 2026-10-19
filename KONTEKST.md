# BOOKLYFI - KONTEKST PROJEKTA v4

Generirano: 2026-10-14
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: python3 main.py -> Flask na http://127.0.0.1:8080

---

<!-- AUTO:START -->

### Auto-generisano: 2026-10-19 17:47

**Git:**
- HEAD: e9f1379 feat: Gemma fallback lanac — kontekst → Mistral (bez OpenRoutera)
- Status: M KONTEKST.md
 M data/rod_registri/The_Trouble_With_Peace.json

**Zadnjih 5 commitova:**
e9f1379 feat: Gemma fallback lanac — kontekst → Mistral (bez OpenRoutera)
aa2f20d feat: Gemini fallback lanac — kontekst → Gemma → Mistral (bez OpenRoutera)
1e33599 fix: QA score poruka dobija file_name + prevodilac_provider
7627dfa fix: GEMMA pool odvojen od GEMINI (samo kad ima vlastite kljuceve)
8008f48 fix: UI audit log — sacuvaj selekciju + povezi dugme 'Na kraj'

**Kljucni moduli (funkcije/klase/linije):**
  - epub/styler.py: 19f/0c/1287L
  - epub/normalizer.py: 8f/0c/371L
  - processing/pipeline.py: 16f/0c/1106L
  - network/http_client.py: 27f/1c/1515L
  - network/provider_router.py: 5f/1c/592L
  - core/engine.py: 0f/1c/686L

**Testovi:**
FAILED tests/unit/test_http_client.py::test_gemma_rotation_checks_gemma_cooldown_tracker
FAILED tests/unit/test_provider_router.py::test_call_ai_engine_uses_gemma_cooldown_namespace_for_gemma_provider
11 failed, 48 passed in 3.47s

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

KRAJ KONTEKSTA
