# BOOKLYFI - KONTEKST PROJEKTA v4

Generirano: 2026-10-14
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: python3 main.py -> Flask na http://127.0.0.1:8080

---

## POSTULATI RADA (MORANJE)

1. Skripte za COPY-PASTE u terminal - JEDAN BLOK.
2. Sve dijagnostike u JEDNOM bloku.
3. Svi fixevi u JEDNOM bloku.
4. NE PRAVI nove fajlove - koristi postojece.
5. NE MALTETIRAJ sa 'posalji mi X' - uzmi sam kroz kod.
6. Za TESTIRANJE - mini test EPUB (1-2 poglavlja).
7. Postuj arhitekturu: logger, fail-safe, checkpoint, backup, _strip_everything.
8. Ako ne moze odjednom - MAX 2 bloka.
9. Novi fajlovi SAMO ako postojeci ne mogu.

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
