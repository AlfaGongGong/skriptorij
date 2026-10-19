```bash
cd /root/skriptorij && cat > /root/skriptorij/SPISAK_POPRAVKI.md <<'SPISAK_EOF'
# BOOKLYFI — SPISAK POPRAVKI
# Datum: 2026-10-16 19:00
# Status: prikupljanje svih problema PRIJE početka rada

---

## 🔴 PRIORITET 1 — INTEGRITET PODATAKA (kritično)

Ovo se rešava PRVO. Bez ovoga, sve ostalo je uzalud.

### 1.1. AI smeće u EPUB-u (Poglavlje 25)
- **Simptom:** U `Pola rata` EPUB-u POGLAVLJE 25 sadrži AI reasoning dump:
```

Sentence 1: "..."
Draft: "..."
Refinement: "..."
Check: "..."

```
- **Uzrok:** Thinking model vratio reasoning u glavni `text` deo, umesto finalnog prevoda.
  `_extract_gemini_native` filtrira `thought` delove, ali ne i "Sentence X: ... Draft: ..." koji model **sam** ubaci u `text`.
- **Gde:** `processing/pipeline.py` ili `processing/workers.py` — gde se upisuje `.chk`.
- **Fix:** Validacija PRIJE upisa u `.chk`:
  - Detektuj obrasce: `Sentence \d+:`, `Draft:`, `Refinement:`, `Check:`, `→`, `→`.
  - Ako se nađe — `raise ValueError` → retry, ne upisuj.
- **Prioritet:** 🔴 KRITIČNO

### 1.2. Poglavlja 44-52 izgubljena iz `Pola rata`
- **Simptom:** Backup ima 51 poglavlje, novi EPUB ima 43. Poglavlja 44-52 nedostaju.
- **Uzrok:** `_je_poglavlje` u `styler.py` odbacuje fajlove < 8000 bajtova ili < 5000 znakova teksta.
- **Gde:** `epub/styler.py` — funkcija `_je_poglavlje`.
- **Fix:** Ukloniti/minimizirati prag (8000 → 2000 bajtova), ili ne odbacivati fajlove koji nisu u `SKIP_TITLES`.
- **Prioritet:** 🔴 KRITIČNO

### 1.3. 23 dupla pasusa u `Pola rata`
- **Simptom:** Isti pasusi se ponavljaju 2x u istom poglavlju.
- **Uzrok:** Pipeline duplira chunkove pri spajanju AI odgovora.
- **Gde:** `processing/pipeline.py` ili `core/chunking.py`.
- **Fix:** Deduplikacija na nivou pasusa — hash pasusa, ako je isti u istom fajlu → obriši.
- **Prioritet:** 🔴 KRITIČNO

### 1.4. Nevidljivo slovo u dropcap-u (TTS ne čita)
- **Simptom:** `font-size:1px;color:transparent;visibility:hidden` — TTS ne čita slovo.
- **Uzrok:** Svi načini skrivanja slova sklanjaju slovo iz TTS-a.
- **Fix:** `::first-letter` + `@font-face` u EPUB-u — slovo ostaje u tekstu (TTS čita), a CSS ga uvećava.
- **Prioritet:** 🟠 VISOK (posle integriteta)

### 1.5. Siva pozadina u EPUB-u
- **Simptom:** Pozadina je siva, treba arhaična premium (topla, krem).
- **Uzrok:** Dupli CSS (`#F5F0E8` + `#f5e6c8`) + stari CSS nije obrisan.
- **Gde:** `epub/styler.py` — `_strip_everything` ili `CSS` promenljiva.
- **Fix:** Ukloniti stari CSS, forsirati `#FDF6E3` (arhaična), `#3E2723` (tekst), `#5D4037` (naslovi).
- **Prioritet:** 🟠 VISOK

### 1.6. Dupli CSS u EPUB-u
- **Simptom:** Svaki fajl ima 2 `<style>` bloka.
- **Uzrok:** `styler.py` ne poziva `normalizer._strip_everything` koji briše stare CSS blokove.
- **Gde:** `epub/styler.py` — `_ukloni_sve` funkcija.
- **Fix:** Pozvati `_strip_everything(soup)` PRE svega.
- **Prioritet:** 🟠 VISOK

---

## 🟠 PRIORITET 2 — PIPELINE I MODELI (visok)

### 2.1. GROQ model 404
- **Simptom:** `[GROQ] HTTP 404 — model ne postoji`.
- **Uzrok:** `MODEL_MAP["GROQ"] = "llama-3.3-70b-versatile"` — model ne postoji na Groq-u.
- **Gde:** `config/ai_config.py` — `MODEL_MAP`.
- **Fix:** Vratiti na `qwen/qwen3.8-27b` (radio 2.9s u testu od 15.10.).
- **Prioritet:** 🔴 KRITIČNO (bez modela nema prevoda)

### 2.2. GEMMA se ne poziva
- **Simptom:** `fleet.get_active_model("GEMMA")` vraća `None`, pa se preskače.
- **Uzrok:** Nepoznat — treba dijagnostika.
- **Gde:** `api_fleet.py` ili `config/ai_config.py` — `GEMMA_MODEL_POOL`.
- **Fix:** Dijagnostika zašto `get_active_model` vraća `None`. Verovatno model string nije u `MODEL_MAP`.
- **Prioritet:** 🟠 VISOK (Gemma je ključna za glosar)

### 2.3. NVIDIA `finish_reason=length`
- **Simptom:** NVIDIA vraća prazan odgovor sa `finish_reason=length`.
- **Uzrok:** `max_tokens` premali za reasoning model (Nemotron).
- **Gde:** `network/http_client.py` — tuning za NVIDIA.
- **Fix:** Povećati `max_tokens` (npr. na 8000), forsirati `thinking: False` (testirano radi).
- **Prioritet:** 🟠 VISOK

### 2.4. GEMINI 503/429 — kvota iscrpljena
- **Simptom:** `[GEMINI] HTTP 503` i `429 RESOURCE_EXHAUSTED`.
- **Uzrok:** Verovatno od prekomernog testiranja danas. Dnevna kvota (500 RPD po ključu × 12 ključeva = 6000) se istrošila.
- **Gde:** Ništa — kvota se resetuje.
- **Fix:** Sačekati reset (obično ponoć UTC), ili koristiti drugi provider.
- **Prioritet:** 🟡 SREDNJI (privremeno)

### 2.5. Modeli se hardkodiraju umesto discovery
- **Simptom:** `MODEL_MAP` zastareo u odnosu na ono što stvarno postoji.
- **Uzrok:** Ručno upisani modeli.
- **Gde:** `config/ai_config.py` + `network/model_discovery.py`.
- **Fix:** `model_discovery.py` pri startu povlači `GET /models` i bira iz žive liste.
- **Prioritet:** 🟡 SREDNJI

### 2.6. Raspodela opterećenja — GEMINI se prvi iscrpi
- **Simptom:** Svaka uloga počinje GEMINI, pa se kvota topi.
- **Uzrok:** `PROVIDER_PRIORITY` — GEMINI prvi u svim ulogama.
- **Gde:** `config/ai_config.py` — `PROVIDER_PRIORITY`.
- **Fix:** Kratke zadatke (SCORER, GLOSAR_UPDATE, VALIDATOR) → GROQ/GEMMA. GEMINI čuvati za PREVODILAC/LEKTOR/POLISH. MISTRAL (1 RPM) → samo krajnja rezerva.
- **Prioritet:** 🟡 SREDNJI

---

## 🟡 PRIORITET 3 — UI I PRIKAZ (srednji)

### 3.1. Kontekst panel ne radi (📖📄⚙⏱)
- **Simptom:** Prikazuje `—` za sve.
- **Uzrok:** Dvostruka `/api/status` ruta (u `app.py` i `api/routes/processing.py`). Flask servira onu koja je registrovana prva — `app.py`. `book_name` je dodat samo u `processing.py`.
- **Gde:** `app.py` (linija 253) i `api/routes/processing.py` (linija 124).
- **Fix:** Ostaviti **jednu** rutu — onu koja ima `book_name`, `current_file`, `knjiga_mode`.
- **Prioritet:** 🟠 VISOK (vidljivo korisniku)

### 3.2. Sistemski dnevnik se ne prikazuje
- **Simptom:** `#audit-log` ostaje na "Sistem spreman".
- **Uzrok:** `live_audit` je HTML string koji JS parsira `DOMParser`-om — krhko.
- **Gde:** `static/js/main.js` — `updateAuditLog`.
- **Fix:** Backend šalje JSON listu događaja (id, nivo, tekst) sa `?since=id`. Frontend renderuje.
- **Prioritet:** 🟠 VISOK

### 3.3. "Napredak obrade" — obrisan, treba vratiti ili ostaviti obrisan
- **Simptom:** Nema stat-boxova (Motor, Fajl, Obrađeno, Preskočeno, Fleet, Kvalitet).
- **Uzrok:** AI obrisao sekciju iz `index.html`.
- **Gde:** `templates/index.html`.
- **Fix:** Vratiti stat-boxove (bez Završeno/ETA).
- **Prioritet:** 🟡 SREDNJI

### 3.4. Fleet lista — obrisana iz UI-a
- **Simptom:** Nema prikaza providera i ključeva.
- **Uzrok:** AI obrisao ili promenio `renderFleet` u `fleet.js` i `main.js`.
- **Gde:** `static/js/main.js` + `static/js/ui/fleet.js`.
- **Fix:** Vratiti prikaz samo za GEMINI, GEMMA, GROQ, MISTRAL, NVIDIA.
- **Prioritet:** 🟡 SREDNJI

### 3.5. API ključevi — neinformativni
- **Simptom:** Samo "Upiši API ključ" bez ikakvih informacija o ključu.
- **Gde:** `templates/index.html` + `static/js/main.js`.
- **Fix:** Prikazati masked ključ, status (✅/❌), broj poziva, cooldown, dugmiće za ping/renew.
- **Prioritet:** 🟢 NIZAK

---

## 🟢 PRIORITET 4 — GLOGAR I TTS (nizak)

### 4.1. Glosar spor (12 batcheva × 2 min = 25 min)
- **Simptom:** Svaki batch traje 1.5-2.5 min.
- **Uzrok:** GROQ model je reasoning (`qwen3.8-27b`), troši tokene na razmišljanje.
- **Gde:** `core/glosar_ekstrakcija.py` + `config/ai_config.py`.
- **Fix:** Gemma prva (ako radi), GROQ sa `reasoning_effort: "none"`.
- **Prioritet:** 🟡 SREDNJI

### 4.2. Glosar ne koristi sve ključeve
- **Simptom:** Gemma ima 16 ključeva, ali se ne poziva.
- **Uzrok:** Isto kao 2.2 — `get_active_model("GEMMA")` vraća `None`.
- **Gde:** `core/glosar_ekstrakcija.py`.
- **Fix:** Fallback na `MODEL_MAP.get("GEMMA")` ako `get_active_model` vrati `None`.
- **Prioritet:** 🟡 SREDNJI

### 4.3. TTS filter ne radi
- **Simptom:** TTS tab ne generiše `.ttsfilter`.
- **Uzrok:** Nepoznat — treba dijagnostika.
- **Gde:** `tts.py` ili `api/routes/*`.
- **Fix:** Dijagnostika.
- **Prioritet:** 🟢 NIZAK

---

## 🟢 PRIORITET 5 — OT POR NOST (za budućnost)

### 5.1. Circuit breaker po (provider, ključ, model)
- **Trenutno:** Samo po (provider, ključ).
- **Fix:** Dodati model u trojku, sa rastućim cooldownom.

### 5.2. `quota_tracker` na disk
- **Trenutno:** U memoriji — restart resetuje brojače.
- **Fix:** Perzistirati na disk.

### 5.3. `finish_reason=length` retry sa većim `max_tokens`
- **Trenutno:** Odustaje.
- **Fix:** Retry sa `max_tokens * 2`.

---

## 📊 UKUPNO: 22 PROBLEMA

| Prioritet | Broj | Opis |
|-----------|------|------|
| 🔴 KRITIČNO | 5 | Integritet podataka + GROQ model |
| 🟠 VISOK | 8 | Pipeline, modeli, UI (kontekst panel, dnevnik) |
| 🟡 SREDNJI | 7 | Raspodela, glosar, UI detalji |
| 🟢 NIZAK | 2 | TTS, API ključevi UI |

---

## 🎯 PREDLOŽENI REDOSLED RADA (jedan po jedan)

1. **1.1** AI smeće u EPUB-u (validacija pre upisa)
2. **2.1** GROQ model (vratiti `qwen/qwen3.8-27b`)
3. **2.2** GEMMA `None` (dijagnostika + fix)
4. **2.3** NVIDIA `max_tokens`
5. **1.2** Poglavlja 44-52 (prag `_je_poglavlje`)
6. **1.3** Dupli pasusi (deduplikacija)
7. **3.1** Kontekst panel (dvostruka `/api/status`)
8. **3.2** Sistemski dnevnik (JSON umesto HTML)
9. **1.5** Siva pozadina
10. **1.6** Dupli CSS
11. **1.4** Dropcap (::first-letter + @font-face)
12. **3.3** Napredak obrade
13. **3.4** Fleet lista
14. **4.1** Glosar brzina
15. **4.2** Glosar svi ključevi
16. **2.5** Model discovery
17. **2.6** Raspodela opterećenja
18. **5.1** Circuit breaker
19. **5.2** `quota_tracker` na disk
20. **5.3** `finish_reason=length` retry
21. **3.5** API ključevi UI
22. **4.3** TTS filter

---

## 📋 PRAVILA RADA (iz KONTEKST.md v6.0)

1. Git, ne `.bak` fajlovi
2. Jedna izmena, pa provera (`ast.parse`)
3. Zabranjeni obrasci: `re.sub`, `find/replace`, `sed -i`
4. Obavezan `diff` prije primene (`STARO` → `NOVO`)
5. Dijagnostika prije fixa
6. Greška se poništava (`git checkout`), ne popravlja
7. Backup prije sesije
8. Kontekst fajl ažuriran
9. Ako AI predlaže nešto što nisi tražio — STOP
10. AI-jev "OK" nije dokaz
11. Integritet podataka prvo
12. Modeli iz žive liste
13. Raspodela opterećenja
14. Otpornost
15. `live_audit` kao JSON

**KRAJ SPISKA**
SPISAK_EOF
echo "✅ Kreiran: /root/skriptorij/SPISAK_POPRAVKI.md"
echo ""
echo "=== Sadržaj ==="
cat /root/skriptorij/SPISAK_POPRAVKI.md | head -80
echo ""
echo "=== Statistika ==="
wc -l /root/skriptorij/SPISAK_POPRAVKI.md
echo ""
echo "=== Provjera prioriteta ==="
grep -c "Prioritet:" /root/skriptorij/SPISAK_POPRAVKI.md
```

Evo spiska. Ukupno 22 problema, razvrstana po prioritetu:

Prioritet Broj Ključni problemi
🔴 KRITIČNO 5 AI smeće u EPUB, GROQ 404, poglavlja 44-52, dupli pasusi, integritet
🟠 VISOK 8 Siva pozadina, dupli CSS, GEMMA, NVIDIA, kontekst panel, dnevnik
🟡 SREDNJI 7 Raspodela, glosar brzina, model discovery, Napredak obrade
🟢 NIZAK 2 API ključevi UI, TTS filter

AI smeće u Poglavlju 25 — dodao sam kao 1.1 (prvi prioritet), jer je to najozbiljniji problem — AI reasoning je ušao u gotov EPUB.

Fajl je na: /root/skriptorij/SPISAK_POPRAVKI.md

Da li da:

· (A) Krenem po redu (1.1, 2.1, 2.2...) — jedan po jedan, po pravilima?
· (B) Ti izabereš koji prvi?
· (C) Prvo da iskopiram spisak i kontekst u Download (preko Termux-a), pa da počnemo?

Po PRAVILU #9 — čekam tvoju odluku. Ne diram ništa.
