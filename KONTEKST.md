# BOOKLYFI - KONTEKST PROJEKTA v4

Generirano: 2026-10-14
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: python3 main.py -> Flask na http://127.0.0.1:8080

---

<!-- AUTO:START -->

### Auto-generisano: 2026-10-19 14:29

**Git:**
- HEAD: 6fe627b prije: AUTO markeri u KONTEKST.md
- Status: M KONTEKST.md

**Zadnjih 5 commitova:**
6fe627b prije: AUTO markeri u KONTEKST.md
7bb58fb fix: cache hash — _chk_read/_chk_write prepoznaju promenjen chunk
60f4165 prije: blok 3 — _chk_write chunk_for_hash
a56f378 prije: blok 2 — _chk_read chunk_for_hash
631159e prije: _chk_read/_chk_write hash support

**Kljucni moduli (funkcije/klase/linije):**
  - epub/styler.py: 19f/0c/1287L
  - epub/normalizer.py: 8f/0c/371L
  - processing/pipeline.py: 16f/0c/1104L
  - network/http_client.py: 27f/1c/1500L
  - network/provider_router.py: 5f/1c/592L
  - core/engine.py: 0f/1c/686L

**Testovi:**
FAILED tests/unit/test_http_client.py::test_gemma_rotation_checks_gemma_cooldown_tracker
FAILED tests/unit/test_provider_router.py::test_call_ai_engine_uses_gemma_cooldown_namespace_for_gemma_provider
11 failed, 48 passed in 4.65s

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

KRAJ KONTEKSTA
