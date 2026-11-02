# BOOKLYFI — KONTEKST PROJEKTA v6

Generirano: 2026-11-02
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: `BOOKLYFI_HOST=0.0.0.0 python3 main.py` → Flask na http://127.0.0.1:8080 i LAN IP
Git HEAD: cd9602b

---

## POSTULATI RADA (MORANJE)

### P1 — Git, ne `.bak` fajlovi
Prije svake izmene: `git add -A && git commit -m "prije: <opis>"`. Vraćanje: `git checkout -- <fajl>`.

### P2 — Jedna izmena, pa provera
Jedan blok = jedna izmena. Posle: `python3 -c "import ast; ast.parse(open('fajl.py').read())"` + `py_compile`. Ako ne prolazi — `git checkout`.

### P3 — Zabranjeni obrasci
NE `re.sub` za izmene Python koda. NE `st.find('\ndef ')`. NE `sed -i` bez prikaza. NE `find/replace`.

### P4 — Obavezan `diff` prije primene
AI prikaže STARO/NOVO, korisnik kaže "da" ili "ne". Bez toga AI ne dira ništa.

### P5 — Dijagnostika prije fixa
Prikazati stvarni sadržaj funkcije, `grep -n`, `sed -n`. Bez pretpostavki.

### P6 — Greška se poništava, ne popravlja
`git checkout`, pa ispočetka drugačije. Nikad "popravljati" preko greške.

### P7 — Backup prije AI sesije
`tar czf /storage/emulated/0/Download/skriptorij_$(date +%Y%m%d_%H%M%S).tar.gz .`

### P8 — Kontekst ažuriran prije sesije
Tačno šta je problem, šta je poslednja izmena radila, šta NE SME da se dira.

### P9 — AI ne dira van zahteva
Ako predlaže izmenu van zahteva — korisnik kaže "ne".

### P10 — AI-jev "OK" nije dokaz
"Sintaksa OK" ne znači da izmena radi. Korisnik pokrene i vidi.

### P11 — Integritet podataka prvo
Prije izmene: proveriti broj poglavlja, znakova, hash pasusa. Obrada mora glasno pasti ako se ne slaže.

### P12 — Modeli se ne hardkodiraju
`model_discovery.py` pri startu povlači `GET /models`. `MODEL_MAP` samo fallback.

### P13 — Raspodela opterećenja
Kratki (SCORER, GLOSAR_UPDATE, VALIDATOR) → GROQ/GEMMA. GEMINI → PREVODILAC, LEKTOR, POLISH. MISTRAL (1 RPM) → krajnja rezerva.

### P14 — Otpornost
Circuit breaker po (provider, ključ, model). `quota_tracker` na disk. `finish_reason=length` → retry. NVIDIA `thinking: False`. GEMMA `None` → dijagnostika.

### P15 — `live_audit` kao JSON
Backend šalje listu JSON događaja sa `?since=id`. Frontend ne parsira HTML.

### P16 — Output sa `clear` + `tee` u fajl
Svaki blok: `clear` + `{ ... } 2>&1 | tee .logs/ime_$TS.log` + `bash tools/out.sh "$LOG"`.
NIKAD /tmp. Log u `.logs/` (Termux).

### P17 — Dijagnostika → STARO/NOVO → test → audit
1. Dijagnostika (`grep -n`, `sed -n`, ast)
2. STARO/NOVO, jedna izmena
3. `ast.parse` + `py_compile` + `import`
4. Test na stvarnom ulazu
5. `make audit-quick` (10s), `make audit` (2-5 min), `make audit-full` (15-30 min)
6. `make audit-diff` — uporedi baseline

### P18 — REPO GUARD
Svaka skripta koja dira git na početku:
```bash
cd /root/skriptorij
if [ ! -d .git ]; then echo FAIL; exit 1; fi
REPO=$(git rev-parse --show-toplevel 2>/dev/null)
if [ "$REPO" != "/root/skriptorij" ]; then echo FAIL; exit 1; fi
```

---


### P19 — Overdiagnose sindrom (zabranjeno)

Dijagnostika služi da se **nešto popravi**, ne da se razume sve. Svaki krug dijagnostike je krug izgubljenog vremena korisnika.

**Pravila:**

1. **Planiraj pre skripte.** Prije nego napišeš dijagnostičku skriptu, napiši u glavi:
   - Šta tačno tražim? (1-2 hipoteze, ne 5)
   - Koje 3-5 komandi mi daju odgovor?
   - Šta ću s podacima? (koji fix, ako hipoteza prođe)
   
   Ako ne znaš odgovor na sva tri — ne piši skriptu, pitaj korisnika.

2. **Maksimalno 2 prolaza dijagnostike.** Prvi prolaz: prikupi podatke. Drugi prolaz: popravi. Treći prolaz — **ne postoji**. Ako ni posle 2 prolaza ne znaš uzrok, priznaj: "ne znam, evo 2 hipoteze, biraj".

3. **Jedna skripta, sve odgovore.** Ne "prvo prikaži X, pa u sledećoj poruci Y". Jedna skripta, svi `grep`/`sed`/`cat` koji su ti potrebni. Ako skripta padne na grešci (npr. `_chk_path` potpis), popravi skriptu i pusti opet — ne šalji 3 skripte.

4. **Direktno pitanje = direktan odgovor.** Ako korisnik pita "šta je u ovom chk" — odgovor je `cat <fajl>` i 3 rečenice objašnjenja. Ne "pusti skriptu da vidimo". Ako znaš odgovor iz konteksta (npr. `[[NEPREVEDENO]]` marker + score 1.0 = `_quality_scores[stem] = 1.0` u pipeline), reci odmah.

5. **Ne ponavljaj dijagnostiku.** Ako si već video da je `_je_odsjecen_html` = True za `</p><`, ne traži opet. Ako si već video da `_CACHE_ACCEPT_SCORE = 7.5`, ne traži opet. Podaci ostaju u kontekstu.

6. **Ne šalji dijagnostiku kad možeš da popraviš.** Ako uzrok znaš iz prethodnog output-a (npr. `AttributeError: main_loop` — jer metoda ne postoji), fix ide odmah, ne "prvo da vidimo tačan potpis".

7. **Ako skripta padne na grešci u sebi (ne u kodu projekta)** — popravi skriptu, pusti opet, ne pitaj. Npr. `IndentationError` u mojoj Python skripti → popravim i pustim. Npr. `SyntaxError: unterminated string` → popravim i pustim.

8. **Kad nešto ne radi iz prve, ne pravi 3 kruga.** Prvi fix → test → ako ne radi, drugi fix (drugačiji pristup, ne "popravljam preko greške"). Treći krug znači da ne razumeš uzrok — pitaj korisnika jednom rečenicom, ne dijagnostikuj opet.

**Primer ispravno:**
> Korisnik: "404 na pregled tabu."
> AI: "Uzrok: review_list prikazuje blokove iz Unbound (last_book), review_chunk traži samo u aktivnoj knjizi. Fix: fallback po svim _skr_*." → skripta sa STARO/NOVO.

**Primer pogrešno:**
> Korisnik: "404 na pregled tabu."
> AI: "Pusti skriptu da vidimo koji endpoint vraća 404." → 5 fajlova, 30 linija.
> AI: "Sad pusti drugu skriptu da vidimo šta UI zove." → još 20 linija.
> AI: "Sad pusti treću..." → korisnik izgubi živce.

**Cilj:** 80% slučajeva → fix iz prve, bez dijagnostike. 20% → jedna dijagnostička skripta, pa fix.

---

## STRUKTURA PROJEKTA

```
/root/skriptorij/
├── main.py              # Flask server (port 8080)
├── run.py               # Batch obrada, _auto_stilizuj, main_loop, start_skriptorij_from_master
├── app.py               # 33 rute (legacy, još u upotrebi)
├── api/routes/          # Flask blueprinti (processing, books, qualities, monitor)
├── core/                # Engine, prompts, quality, metadata, kalkovi, chunking
│   ├── metrics.py       # accuracy_shadow, check_accuracy (T3.1b)
│   ├── text_utils.py    # _smart_extract, _je_odsjecen_html, _post_process_tipografija
│   ├── prompts.py       # PREVODILAC, LEKTOR, KOREKTOR, SCORER templates
│   └── quality.py       # _scoruj_kvalitetu, _izracunaj_heuristicki_score
├── processing/          # Pipeline, workers, retro, parallel, rescue
│   ├── pipeline.py      # Glavni tok, _quality_scoring, _primijeni_kalkove_i_validator
│   └── retro.py         # retroaktivna_relektura_v10
├── epub/                # styler.py, normalizer.py, packager.py, parser.py, manager.py
├── network/             # http_client, provider_router, quota_tracker, rate_limiter
├── config/              # settings, ai_config, logger, model_roles
├── analysis/            # book_context, autor_analiza
├── data/                # kanon, rod_registri, glosar_pravila.json, kalkovi_karantena.db
├── templates/index.html
├── static/js/main.js    # 3867 redaka
├── static/css/style.css # 3487 redaka
├── tools/               # cistoca.sh, pipeline_audit.py, audit_diff.py, out.sh
└── tests/
```

**venv:** `venv/bin/python3`

---

## PIPELINE

### Prevođenje/lektura
`PREVODILAC → LEKTOR → KOREKTOR → VALIDATOR → GUARDIAN → POLISH → SCORER`
Modovi: PREVOD (EN→HR) ili LEKTURA (HR→HR).

### Stilizacija (`epub/styler.py`)
```
.epub ulaz → _spoji_chk_u_html → _classify (odbacuje frontmatter)
  ↓ Po poglavlju:
  1. _ukloni_sve → 2. _normalizuj → 3. _dijalog → 4. _ukloni_duplikate_p
  5. _dodaj_vijenac → 6. _ocisti_fffc → 7. _dodaj_naslov → 8. _dodaj_dropcap
  ↓ Moon+ .replacement (ako postoji)
  ↓ _write(out, files)
```

**Izlaz:** `/storage/emulated/0/Books/MoonReader/STYLED/{autor}_{naslov}_PREVEDENO_STYLED.epub`

---

## PROVIDERI

**Kljucevi:** GEMINI=12, GEMMA=4, GROQ=6, MISTRAL=5, OPENROUTER=4, NVIDIA=1, CLOUDFLARE=1

**Modeli:**
- GEMINI: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`
- GEMMA: `gemma-4-26b-a4b-it`
- GROQ: `qwen/qwen3.8-27b`
- MISTRAL: `mistral-small-latest` (1 RPM)
- OPENROUTER: `thinkingmachines/inkling:free`
- NVIDIA: `nemotron-3.5-lightning`

**PRIORITY:** GEMINI → GROQ → GEMMA → OPENROUTER → MISTRAL → CLOUDFLARE → NVIDIA
**Fallback:** kontekst → Gemma → Mistral

**Quota/cooldown reset:** fajlovi u `quota_cooldowns.json`, `api_state.json`, `dev_api.json`, `data/quota_state.json`. Reset preko skripte `.logs/quota_full_backup_*` (backup pa nule). Restart Flask posle.

---

## STANJE 2026-11-02 — TWOC 98%

### Prevod TWOC (`The Wisdom of Crowds`)
| Metrika | Rezultat |
|---|---|
| Checkpointi | 452/459 finalnih `.chk`, 7 `.prevod.chk` |
| Markeri `[[NEPREVEDENO]]` u `.chk` | 0 |
| Odsječen HTML | 0 |
| Leak `{„korektura` | 0 |
| „ u atributima | 0 |
| Bayaz / Bajaz | 71 / 0 |
| Score histogram | ≤1.0: 7, <6: 1, 6-8: 27, 8-9: 289, ≥9: 135 |
| Prosečna ocena | 8.63 |
| accuracy_derived popunjen | 452/452 |
| EPUB | 4.4 MB, 77 XHTML dijelova |

**Ostaje:**
- **4 fajla u EPUB-u sa `[[NEPREVEDENO]]`** — `part0170.html`, `nav.xhtml` + 2 još. Uzrok: `.prevod.chk` odsječen usred taga, PREVODILAC fallback ne pokriva.
- **4 fajla bez checkpointa** — `part0170.html`, `part0246.html` (≥150 reči)
- **1 blok sa score < 6.0** (0.2%)

### Scorer problem (ključno)
- **8.3 i 9.8 su čista heuristika, NE AI ocena** — izvedeni AI = heur u 289/452 slučajeva, što znači scorer **ne vraća ništa** za ~85% blokova
- **6.3 = blokovi gde scorer radi** ali vraća konstantno 5.6 (kvantizacija iz rubrike)
- **Rubrika `QUALITY_SCORER_SYS`** kažnjava `tipograf 5-6 = navodnici umj. crtice` — a PREVODILAC prompt traži `„…”` kao pravilo. Kontradikcija.
- **Kvantizacija:** `kompozitni = heur * 0.25 + ai * 0.75`; kad AI nedostupan → `kompozitni = heur`. Heuristika vraća samo 8.3 ili 9.8.
- **Retro troši quotu bez efekta:** `_RETRO_QA_THRESHOLD = 9.5` gotovo sve šalje na retry, ali ocena se ne menja (kvantizacija).

**Skripta `booklyfi_twoc_rubrika.sh` NIJE puštena** — treba da popravi rubriku + prikaže heuristiku + `_QUALITY_RESCUE_THRESHOLD`.

---

## COMMITOVANI FIXEVI (STABILNO, NE DIRATI BEZ STARO/NOVO)

| Commit | Fix |
|---|---|
| `dac2726` | T4/leak-C: few-shot cleanup + filter protiv `{„korektura` |
| `63063fe` | replacements — prefix ne-slov + nested placeholder restore |
| `ba32c80` | T3.1b: `final = min(llm, accuracy_derived)` |
| `81912bc` | `_post_process_tipografija` ne kvari HTML atribute |
| `bd1db93` | Guard na 3 mesta (cache, prekinut, kalkovi) |
| `9578b18` | T1: kanon u promptu + few-shot filter |
| `c74125b` | PREVODILAC fallback kad LEKTOR padne |
| `cd9602b` | run.py retro grana inline (main_loop AttributeError) |

### Detalji fixeva
- **Wrapper (T4/leak):** `_smart_extract` skida `{"korektura":` i `{„korektura:` prefiks i kad `json.loads` padne (odsječen odgovor, tipografski navodnici).
- **Escape (T4/leak):** `_agresivno_cisti` čisti `\"` unutar HTML tagova (ne van — za dijalog).
- **Guard (T4/leak):** `_je_odsjecen_html` (usred taga, `<p` bez `</p>`, `{` bez `}`). 3 mesta: cache, prekinut, posle kalkova.
- **Replacements:** prefix sa ne-slovom (`*„#->#—`), nested placeholder (`<style>` unutar `<head>`).
- **T3.1b:** `accuracy_shadow` računa `accuracy_derived` = `10 - kazne (leak -5, kraj_u_tagu -3, ratio_nizak -3, p_gubitak -2, en_ostaci -3, imena_nedostaju -2, brojevi_razlika -2)`. Pipeline uzima `min(llm, accuracy)`.
- **T1:** `kanon_injekcija` u promptu, `few_shot_global` filtrira Bajaz parove.
- **B (`_retry_s_feedbackom`):** čuva HTML i dužinu, ne vraća plain.
- **run.py retro:** inline loop umesto nepostojećeg `engine.main_loop`.

---

## SLEDEĆI KORACI (prioritet)

1. **Pusti `booklyfi_twoc_rubrika.sh`** — popravi rubriku (`„…”` ispravan), prikaži heuristiku, `_QUALITY_RESCUE_THRESHOLD`.
2. **4 fajla NEPREVEDENO u EPUB-u** — dijagnostika `neprevedeno_diag.sh`, fix PREVODILAC fallback ili bisekcija.
3. **Reset kvota** — skripta za `quota_cooldowns.json`, `api_state.json`, `data/quota_state.json`.
4. **Ponovno ocenjivanje** (kad quota) — samo scorer pozivi, bez novog prevoda.
5. **ASCII `"` u 431 blok** — dijalog ili legit citat? Fix u `_post_process_tipografija` ako treba.
6. **`Adua`** — 79 EN / 37 HR, dodaj u kanon + `.replacement`.
7. **5 promoviranih blokova score 6.0** — ručna lektura ili retro.

**Cilj:** "izdavački dobar" prevod bez human audita (ili minimalni, 2-5% flagged blokova). Trenutno ~88-90% za čitanje.

---

## NE DIRATI

- `_FROZEN_TWOC/` — stari zamrznuti EPUB
- Commitovane fajlove iz tabele gore bez STARO/NOVO
- `data/few_shot_abercombie.json` — očišćen u T1
- `data/kalkovi_karantena.db` — checkout pre svakog commita
- `epub/styler.py`, `network/*` — stabilni

---

## PUTANJE

- Repo: `/root/skriptorij`
- Checkpointi TWOC: `/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints/`
- EPUB izlaz: `/storage/emulated/0/Books/MoonReader/STYLED/`
- Kanon: `/storage/emulated/0/Books/MoonReader/kanon/The_Wisdom_of_Crowds.json`
- EN original: `/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub`
- Logovi: `.logs/` (gitignore)
- Backup: `/storage/emulated/0/Download/skriptorij_*.tar.gz`

## AKTIVNI PROCESI

- Flask: `BOOKLYFI_HOST=0.0.0.0 python3 main.py` (port 8080, LAN IP `192.168.178.40`)
- Restart: `pkill -f "python.*main.py"; BOOKLYFI_HOST=0.0.0.0 nohup venv/bin/python3 main.py > .logs/flask.log 2>&1 & disown`
- Provera: `curl -sS -m 3 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/`

## KONTEKST ZA CLAUDE-a

Cilj: "izdavački dobar" prevod bez human audita (ili minimalni 2-5% flagged).
TWOC je 98% gotov ali:
- 4 fajla NEPREVEDENO (blokira čitanje)
- Scorer ocene nisu realne za 289 blokova (fallback heuristika)
- Rubrika kažnjava `„…”` (protivno prompt pravilu)
- Retro troši quotu bez poboljšanja

Redosled: rubrika → 4 fajla fix → reset quota → ponovno ocenjivanje → ASCII navodnici → Adua → 5 promoviranih.

**Ne diraj stabilno. Dijagnostika pre STARO/NOVO. Jedna izmena po bloku.**

KRAJ KONTEKSTA
