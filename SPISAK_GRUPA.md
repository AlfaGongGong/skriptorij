# BOOKLYFI — SPISAK POPRAVKI GRUPISAN PO ZAJEDNIČKOM FIXU
# Datum: 2026-10-16
# Pravilo: grupe se rješavaju jedna po jedna, dijagnostika pa fix.

---

## GRUPA A — INTEGRITET PODATAKA (Kritično)
Sve što se tiče gubitka/dupliranja/iskrivljavanja teksta. Isti uzrok ili ista faza pipeline-a.

### A1. AI smeće u EPUB-u (Poglavlje 25) — reasoning dump
- **Simptom:** Tekst sadrži "Sentence 1: ... Draft: ... Refinement: ... Check: ..."
- **Uzrok:** Reasoning model vratio thought-process u glavni `text`.
- **Gde:** `processing/pipeline.py` — `_je_placeholder_lokalni`
- **Fix:** Dodati obrasce u placeholder detekciju (VEĆ URADJENO u 1.1)

### A2. Odsječen tekst na kraju chunka (Poglavlje 26→27)
- **Simptom:** Tekst se prekida usred rečenice, pa odmah ide "POGLAVLJE 27".
- **Uzrok:** Nepoznat — chunking seče, AI skraćuje, ili rescue ne radi.
- **Gde:** `core/chunking.py`, `processing/rescue.py`, `processing/pipeline.py`
- **Fix:** Dijagnostika prvo.

### A3. Poglavlja 44-52 izgubljena iz `Pola rata`
- **Simptom:** Backup ima 51 poglavlje, novi EPUB ima 43.
- **Uzrok:** `_je_poglavlje` odbacuje fajlove < 8000 bajtova.
- **Gde:** `epub/styler.py` — `_je_poglavlje`
- **Fix:** Smanjiti prag.

### A4. 23 dupla pasusa u `Pola rata`
- **Simptom:** Isti pasusi 2x u istom poglavlju.
- **Uzrok:** Pipeline duplira chunkove pri spajanju.
- **Gde:** `processing/pipeline.py` ili `core/chunking.py`
- **Fix:** Deduplikacija po hash-u pasusa.

**Zajednički pristup:** Sve se tiče **teksta u `.chk` fajlovima** ili **granica chunkova**. Dijagnostika: analizirati `.chk` fajlove, chunking, i `_je_poglavlje`. Fixevi mogu biti u različitim fajlovima ali ista faza pipeline-a.

---

## GRUPA B — MODELI I KONFIGURACIJA (Kritično)
Sve što se tiče izbora modela, kvota, i konfiguracije provajdera.

### B1. GROQ model 404
- **Simptom:** `[GROQ] HTTP 404 — model ne postoji`
- **Uzrok:** `MODEL_MAP["GROQ"] = "llama-3.3-70b-versatile"` (ne postoji)
- **Gde:** `config/ai_config.py`
- **Fix:** Vratiti na `qwen/qwen3.8-27b`

### B2. GEMMA se ne poziva (`get_active_model` vraća None)
- **Simptom:** `fleet.get_active_model("GEMMA")` → None
- **Uzrok:** Nepoznat.
- **Gde:** `api_fleet.py`, `config/ai_config.py`
- **Fix:** Dijagnostika.

### B3. NVIDIA `finish_reason=length`
- **Simptom:** NVIDIA vraća prazan odgovor.
- **Uzrok:** `max_tokens` premali za reasoning model.
- **Gde:** `network/http_client.py`
- **Fix:** Povećati `max_tokens`, forsirati `thinking: False`.

### B4. Modeli se hardkodiraju umesto discovery
- **Simptom:** `MODEL_MAP` zastareo.
- **Uzrok:** Ručno upisani modeli.
- **Gde:** `config/ai_config.py`, `network/model_discovery.py`
- **Fix:** Discovery pri startu povlači `GET /models`.

### B5. Raspodela opterećenja — GEMINI se prvi iscrpi
- **Simptom:** Svaka uloga počinje GEMINI.
- **Uzrok:** `PROVIDER_PRIORITY`
- **Gde:** `config/ai_config.py`
- **Fix:** Kratke zadatke → GROQ/GEMMA.

**Zajednički pristup:** Sve se tiče `config/ai_config.py` i `network/model_discovery.py`. Fixevi su izmene u konfiguraciji ili discovery logici.

---

## GRUPA C — UI I PRIKAZ (Visok/Srednji)
Sve što se tiče frontend prikaza i `/api/status`.

### C1. Kontekst panel ne radi (📖📄⚙⏱)
- **Simptom:** Prikazuje `—`.
- **Uzrok:** Dvostruka `/api/status` ruta (`app.py` + `processing.py`).
- **Gde:** `app.py`, `api/routes/processing.py`
- **Fix:** Ostaviti jednu rutu.

### C2. Sistemski dnevnik se ne prikazuje
- **Simptom:** `#audit-log` ostaje na "Sistem spreman".
- **Uzrok:** `live_audit` HTML string parsiran u JS-u — krhko.
- **Gde:** `static/js/main.js`
- **Fix:** JSON lista događaja umesto HTML stringa.

### C3. "Napredak obrade" — obrisan, treba vratiti
- **Simptom:** Nema stat-boxova.
- **Uzrok:** AI obrisao.
- **Gde:** `templates/index.html`
- **Fix:** Vratiti stat-boxove.

### C4. Fleet lista — obrisana iz UI-a
- **Simptom:** Nema prikaza providera.
- **Gde:** `static/js/main.js`, `static/js/ui/fleet.js`
- **Fix:** Vratiti prikaz.

### C5. API ključevi — neinformativni
- **Simptom:** Samo "Upiši API ključ".
- **Gde:** `templates/index.html`, `static/js/main.js`
- **Fix:** Prikazati masked ključ, status, broj poziva.

**Zajednički pristup:** Sve se tiče `templates/index.html`, `static/js/main.js`, `static/js/ui/fleet.js`, `app.py` (rute). Fixevi su izmene u HTML-u i JS-u.

---

## GRUPA D — EPUB STILIZACIJA (Visok/Srednji)
Sve što se tiče `styler.py` i izgleda EPUB-a.

### D1. Siva pozadina u EPUB-u
- **Uzrok:** Dupli CSS (`#F5F0E8` + `#f5e6c8`).
- **Gde:** `epub/styler.py`
- **Fix:** Forsirati `#FDF6E3`.

### D2. Dupli CSS u EPUB-u
- **Uzrok:** `styler.py` ne poziva `_strip_everything`.
- **Gde:** `epub/styler.py`
- **Fix:** Pozvati `_strip_everything` PRE svega.

### D3. Dropcap i TTS
- **Simptom:** TTS ne čita slovo.
- **Uzrok:** Svi načini skrivanja sklanjaju slovo iz TTS-a.
- **Gde:** `epub/styler.py` — `_dodaj_dropcap`
- **Fix:** `::first-letter` + `@font-face` — slovo ostaje u tekstu.

**Zajednički pristup:** Sve se tiče `epub/styler.py`. Fixevi su izmene u CSS-u ili dropcap logici.

---

## GRUPA E — GLOGAR I TTS FILTER (Srednji/Nizak)
Sve što se tiče glosara i TTS filtera.

### E1. Glosar spor (12 batcheva × 2 min = 25 min)
- **Uzrok:** GROQ model je reasoning.
- **Gde:** `core/glosar_ekstrakcija.py`, `config/ai_config.py`
- **Fix:** Gemma prva, GROQ sa `reasoning_effort: "none"`.

### E2. Glosar ne koristi sve ključeve
- **Uzrok:** Isto kao B2 — `get_active_model("GEMMA")` vraća None.
- **Gde:** `core/glosar_ekstrakcija.py`
- **Fix:** Fallback na `MODEL_MAP.get("GEMMA")`.

### E3. TTS filter ne radi
- **Uzrok:** Nepoznat.
- **Gde:** `tts.py`
- **Fix:** Dijagnostika.

**Zajednički pristup:** Sve se tiče glosara i TTS modula.

---

## GRUPA F — OTPORNOST (Nizak, za budućnost)
Sve što se tiče robusnosti sistema.

### F1. Circuit breaker po (provider, ključ, model)
### F2. `quota_tracker` na disk
### F3. `finish_reason=length` retry sa većim `max_tokens`

**Zajednički pristup:** Sve se tiče `network/quota_tracker.py`, `network/rate_limiter.py`, `network/http_client.py`.

---

## PREDLOŽENI REDOSLED RADA PO GRUPAMA

| # | Grupa | Fokus | Rizik | Trajanje |
|---|-------|-------|-------|----------|
| 1 | **A** | Integritet podataka | Nizak (dijagnostika prvo) | 30-60 min |
| 2 | **B** | Modeli i konfiguracija | Srednji (može pokvariti pozive) | 30-45 min |
| 3 | **D** | EPUB stilizacija | Nizak (izolovano) | 20-30 min |
| 4 | **C** | UI i prikaz | Srednji (frontend) | 30-45 min |
| 5 | **E** | Glosar i TTS | Nizak | 20 min |
| 6 | **F** | Otpornost | Nizak | 30 min |

---

## ZAŠTO OVAJ REDOSLED

1. **A prvo** — bez integriteta podataka, sve ostalo je uzalud. Ako tekst gubi rečenice, EPUB je neupotrebljiv.
2. **B drugo** — modeli su osnova pipeline-a. Ako GROQ vraća 404, ništa ne radi.
3. **D treće** — EPUB stilizacija je izolovana. Ne utiče na pipeline.
4. **C četvrto** — UI je za korisnika. Ne utiče na podatke.
5. **E peto** — glosar je pomoćni. Nije kritičan za obradu.
6. **F šesto** — otpornost je za budućnost. Sistem radi i bez toga.

---

## DIJAGNOSTIKA PO GRUPAMA

Za svaku grupu treba prikupiti:

**Grupa A:**
- `core/chunking.py`
- `processing/rescue.py`
- `processing/pipeline.py` (`_je_sumnjiv_gubitak_teksta`, `_chk_write`)
- `epub/styler.py` (`_je_poglavlje`)
- `.chk` fajlovi za Poglavlje 26/27
- Struktura EPUB-a `Pola rata` (sva poglavlja)

**Grupa B:**
- `config/ai_config.py`
- `api_fleet.py`
- `network/model_discovery.py`
- `network/http_client.py` (NVIDIA deo)
- Test: stvarni modeli na svakom provajderu

**Grupa C:**
- `templates/index.html`
- `static/js/main.js`
- `static/js/ui/fleet.js`
- `app.py` (ruta `/api/status`)
- `api/routes/processing.py` (ruta `/api/status`)

**Grupa D:**
- `epub/styler.py`
- `epub/normalizer.py`

**Grupa E:**
- `core/glosar_ekstrakcija.py`
- `tts.py`

**Grupa F:**
- `network/quota_tracker.py`
- `network/rate_limiter.py`
- `network/http_client.py`

---

## KRAJ SPISKA GRUPA
