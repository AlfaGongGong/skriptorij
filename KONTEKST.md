# BOOKLYFI — KONTEKST PROJEKTA v5

Generirano: 2026-10-27
Lokacija: /root/skriptorij/ (proot Ubuntu)
Server: python3 main.py -> Flask na http://127.0.0.1:8080

---

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


### P17 — Dijagnostika → STARO/NOVO → test → audit

**Za svaku izmjenu koda:**

1. **Dijagnostika prije STARO/NOVO** — `grep -n`, `sed -n`, Python `ast` ili `py_compile` na **stvarnom** kodu. Bez pretpostavki. Ako funkcija ne postoji ili ima više kopija, prvo to prikaži.
2. **STARO / NOVO** — jedan blok, jedna izmjena. Bez "usput sam popravio još ovo".
3. **Primijeni** — `ast.parse` + `py_compile` + `import`. Ako pukne, rollback odmah.
4. **Test na stvarnom ulazu** — ne na `mini_hatred.epub` (premali). Prava knjiga, pravi izlaz. Broji: `galley-rw`, `section`, `display:inline`, `dropcaps_added`, hash ulaz≠izlaz.
5. **`make audit` (medium)** — jedan mod, jedan EPUB. Ako FAIL raste → rollback.
6. **`make audit-diff`** — uporedi sa baseline. Novi FAIL = rollback. Rešeni FAIL = nastavi.

**Zašto:** `ast.parse` i `import` ne hvataju da fix nije u živoj funkciji (slučaj `_ukloni_sve` u mrtvoj kopiji), da fix ne piše output (slučaj `EpubStyler.stilizuj` šablona), ili da fix kvari izlaz (slučaj `_razdvoji_dijalog_p` koji je štetio naraciji). Samo audit kroz stvarni EPUB vidi razliku.

**Zabranjeno:**
- Reći "radi" na osnovu `ast.parse` ili `import` — bez testa na stvarnom izlazu
- Ostaviti fix u mrtvoj kopiji funkcije (provjeri `grep -n "def ime"` — koliko kopija)
- Popravljati preko greške — `git checkout`, pa ispočetka drugačije (P6)
- Mijenjati više od jedne stvari u bloku (P2)
- Testirati na `mini_hatred.epub` kao dokaz da radi (samo frontmatter, bez h1)

**Alati:**
- `make audit-quick` — poslije svake izmjene (~10s)
- `make audit` — prije commita (~2-5 min)
- `make audit-full` — prije veće izmjene (~15-30 min)
- `make audit-diff` — uporedi sa baseline
- `make baseline` — snimi trenutni audit kao baseline

**Kad audit pokaže novi FAIL:**
- Ako je fix uzrok → `git checkout <fajl>`, pa drugačije
- Ako je baseline bio nepotpun → ažuriraj baseline
- Ne ignorisati FAIL "zato što je mali" — svaki FAIL ima uzrok


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

---

## STRUKTURA PROJEKTA

```
/root/skriptorij/
├── main.py              # Flask server (port 8080, 127.0.0.1 default)
├── run.py               # Batch obrada, _auto_stilizuj
├── app.py               # 33 rute (kandidat za blueprinte — batch H)
├── api/routes/          # Flask blueprinti
├── core/                # Engine, prompts, quality, metadata, kalkovi, chunking
├── processing/          # Pipeline, workers, retro, parallel, rescue
├── epub/                # styler.py, normalizer.py, packager.py, parser.py, manager.py
├── network/             # http_client, provider_router, quota_tracker, rate_limiter
├── config/              # settings, ai_config, logger, model_roles
├── analysis/            # book_context, autor_analiza
├── utils/               # file_utils (atomic_write), logging, checkpoint_cleaner
├── data/                # kanon, rod_registri, glosar_pravila.json, kalkovi_karantena.db
├── templates/index.html
├── static/js/main.js    # 3867 redaka
├── static/css/style.css # 3487 redaka
├── tools/               # cistoca.sh, popravi_projekat.sh, pipeline_audit.py, audit_diff.py
├── tests/               # unit, integration, golden
└── Makefile
```

**venv:** `venv/bin/python3`

---

## PIPELINE

### Prevođenje/lektura

PREVODILAC → LEKTOR → KOREKTOR → VALIDATOR → GUARDIAN → POLISH → SCORER

Modovi: PREVOD (EN→HR) ili LEKTURA (HR→HR).

### Stilizacija (epub/styler.py)

```
.epub ulaz
  ↓
_spoji_chk_u_html
  - trazi _skr_<knjiga> po imenu (fuzzy match)
  - _skrati_overlap (suffix-prefix)
  - _je_duplikat (plain vs HTML 70%, HTML vs HTML 90%)
  - _spoji_blokove (razmak izmedju alfanum)
  - ako .chk bez <p>: konvertuj plain text u <p>
  ↓
_classify (odbacuje frontmatter)
  - kratki fajlovi bez h1 POGLAVLJE: copyright/marketing/navigation
  - ima h1 POGLAVLJE ili >5000c: propusta
  ↓
Po poglavlju:
  1. _ukloni_sve
  2. _normalizuj
  3. _dijalog
  4. _ukloni_duplikate_p
  5. _dodaj_vijenac
  6. _ocisti_fffc
  7. _dodaj_naslov
  8. _dodaj_dropcap
  ↓
Moon+ .replacement (ako postoji)
  - fuzzy match po tokenima
  - *X = prefix, X = cijela rijec
  - skip <head>, <h1-h3>
  ↓
_write(out, files) → izlazni .epub
```

**Izlaz:** `/storage/emulated/0/Books/MoonReader/STYLED/{autor}_{naslov}_PREVEDENO_STYLED.epub`

---

## PROVIDERI

**Kljucevi:** GEMINI=12, GEMMA=4, GROQ=6, MISTRAL=5, OPENROUTER=4, NVIDIA=1, CLOUDFLARE=1

**Modeli:**
- GEMINI: gemini-3.5-flash-lite, gemini-3.1-flash-lite
- GEMMA: gemma-4-26b-a4b-it
- GROQ: qwen/qwen3.8-27b
- MISTRAL: mistral-small-latest (1 RPM)
- OPENROUTER: thinkingmachines/inkling:free
- NVIDIA: nemotron-3.5-lightning

**PRIORITY:** GEMINI → GROQ → GEMMA → OPENROUTER → MISTRAL → CLOUDFLARE → NVIDIA

**Fallback:** kontekst → Gemma → Mistral

---

## MOON+ REPLACEMENT

Format: `<ime>.epub.replacement`, linija po pravilo:
```
X#->#Y              # cijela rijec
*X#->#Y             # prefix (mijenja Xov, Xova...)
\bX\b#->#Y          # regex
```

**Lokacija:** pored ulaznog EPUB-a, u STYLED/, ili fuzzy match po tokenima.

**Ne dira:** `<head>`, `<h1>`, `<h2>`, `<h3>`, `<script>`, `<style>`, atribute.

---

## MAKE TARGETI

| Target | Sta | Kad |
|---|---|---|
| make test | pytest tests/ | poslije izmjene |
| make golden | pytest tests/golden/ | poslije izmjene |
| make lint | pyflakes (informativno) | poslije izmjene |
| make audit-quick | staticka analiza + import (~10s) | poslije svake izmjene |
| make audit | + jedan mod na EPUB-u (~2-5 min) | prije commita |
| make audit-full | + sva 3 moda + idempotentnost | prije vece izmjene |
| make baseline | snimi trenutni audit kao baseline | prije vece izmjene |
| make audit-diff | uporedi sa baseline | poslije izmjene |

---

## STANJE — F0 ZAVRSENO (2026-10-27)

Svi audit FAIL-ovi reseni. Pipeline radi.

### F0 fixevi (17)

| # | Fix | Commit |
|---|---|---|
| F0.1 | _shared_images = [] (NameError) | f3507c8 |
| F0.2 | manager.py zove run_epub_styler | b5b73cd |
| F0.3 | Dropcaps — artefakt mini_hatred | — |
| F0.4 | Uklonjen mode (jedan mod) | 315acbc |
| F0.5 | Broj rijeci — artefakt | — |
| F0.6 | _skrati_overlap | 578f130 |
| F0.7 | _je_duplikat plain vs HTML | a705588 |
| F0.8 | _je_duplikat HTML vs HTML | 2005096 |
| F0.9 | _spoji_blokove | fe550c2 |
| F0.10 | _classify copyright filter prag | 985dcd2 |
| F0.11 | _dodaj_dropcap ≥60c + crtica | 026bf65 |
| F0.12 | _classify frontmatter skip po h1 | e021064 |
| F0.13 | .chk bez <p> → <p> | 3d8ff8f |
| F0.15 | * prefix mode + skip metapodataka | ff9674e |
| F0.16 | Workflow .replacement | f99f764 |
| F0.16b | Fuzzy match .replacement | 928ed53 |
| B | .replacement cleanup (394→282) | — |

### Test rezultati

| Knjiga | Poglavlja | Dropcaps | Duplikati |
|---|---|---|---|
| TWP | 77 | 73 | 0 |
| The Collective | 45 | 42 | 0 |
| A Death | 3 | 1 | 0 |

### Poznati bugovi (nisu F0)

- 3 poglavlja u TWP bez dropcapa — dio/epigraf, ispravno
- Bayazov, Bayazova ostaju — .replacement nema pravila
- analysis/cache/ se regenerise — nije problem

---

## PIPELINE BACKLOG (vraceno iz starog plana)

Sve stavke iz starih sekcija "A. Aktivna revizija", "B. Predlozi — kod i rad sistema", "C. UI predlozi", "D. UX predlozi", plus batch A-J iz 2026-10-26. Status provjeren na git logu i kodu.

### A. Revizija — bugovi (15 stavki)

| # | Stavka | Status | Fajl | Napomena |
|---|---|---|---|---|
| A#1 | 429 drzi semafor 120s | ✅ ZAVRSENO | network/http_client.py | sleep pre acquire |
| A#2 | Tri imena za qwen/gpt-oss | ⏳ OSTALO | config/ai_config.py | `gpt_oss`, `gpt-oss`, `qwen_chutes` — nije razrijeseno |
| A#3 | Dupli MODEL_MAP / GEMINI_BASE_URL | ⏳ DELIMICNO | config/ai_config.py | `MODEL_MAP = all_fallbacks()` samo jedan, ali heuristike za nove modele na 688 |
| A#4 | SKIP_TITLES "prolaznost zivota" | ✅ ZAVRSENO | epub/styler.py | v7 |
| A#5 | Dropcap gubi slovo u em/strong | ✅ ZAVRSENO | epub/styler.py | v5 |
| A#6 | _dodaj_naslov brise sve h1-h3 | ✅ ZAVRSENO | epub/styler.py | v7 |
| A#7 | XML escaping u NCX/TOC/NAV | ✅ ZAVRSENO | epub/styler.py | v5 |
| A#8 | _je_poglavlje folder/podniz | ✅ ZAVRSENO | epub/styler.py | v5 |
| A#9 | Gemma fallback dijagnostika | ✅ ZAVRSENO | network/provider_router.py | log pokazuje RPD |
| A#10 | Cloudflare grana ostala | ✅ ZATVORENO | network/http_client.py | funkcionalna |
| A#11 | NVIDIA/GROQ + thinkingConfig duplo | ✅ ZAVRSENO | network/http_client.py | Grupa 2 |
| A#12 | live_audit kao JSON | ✅ ZAVRSENO | api/routes/monitor.py, static/js/main.js | 3a-1, 3a-2, 3b |
| A#13 | Jitter sleep unutar semafora | ✅ ZATVORENO | network/http_client.py | dizajnerski kompromis |
| A#14 | Cache hash fix | ✅ ZAVRSENO | processing/pipeline.py | blok 1-3 |
| A#15 | Pola rata cache 318 .chk bez hash | ⏳ OSTALO | /storage/.../booklyfi_checkpoints | odluka A |

### B. Predlozi — kod i rad sistema (9 stavki)

| # | Stavka | Status | Napomena |
|---|---|---|---|
| B#1 | Jedan `providers.json` izvor istine | ⏳ OSTALO | umesto razbijenog MODEL_MAP + AI_MODEL_STRINGS |
| B#2 | Jedan HTTP klijent (httpx/aiohttp) | ⏳ OSTALO | blokirajuci api_call + async |
| B#3 | Stanje kvota na disk | ⏳ DELIMICNO | `quota_tracker.py:439` jos `open(w)` — nije atomic |
| B#4 | Kes odgovora po chunku (model + glosar u hash) | ⏳ OSTALO | trenutno samo chunk |
| B#5 | Pametnije grupiranje: batch SCORER/VALIDATOR/glosar | ⏳ OSTALO | chunk velicina po TPM-u |
| B#6 | Stilizator kao niz cistih faza | ⏳ DELIMICNO | F0 razdvojio neke faze, ali nije pun refaktor |
| B#7 | Dropcap slike kao zajednicki fajlovi | ⏳ OSTALO | trenutno base64 u svakom poglavlju |
| B#8 | Strukturirano logiranje (JSON) | ⏳ OSTALO | nivo, modul, provider, maskiran kljuc |
| B#9 | Golden-test s mini EPUB + pyflakes/ruff | ⏳ DELIMICNO | `make golden` postoji, `make audit-quick` pokriva pyflakes |

### C. UI predlozi (6 stavki) → prebaceno u "UI poboljsanja"

### D. UX predlozi (9 stavki) → prebaceno u "F — UX"

### Batch-evi 2026-10-26 (A-J)

| Batch | Stavka | Status | Napomena |
|---|---|---|---|
| A | Path traversal + bind 127.0.0.1 | ✅ ZAVRSENO | commit d226896, sve 4 rute + main.py |
| B1 | Atomski upis za api_keys | ✅ ZAVRSENO | commit bdb85ec, `atomic_write_json` |
| B2 | Atomski upis za quality_scores + lock | ✅ ZAVRSENO | commit 65f9386, `_QS_LOCK` |
| B3 | Atomski upis za quota_tracker | ⏳ DELIMICNO | `quota_tracker.py:439` jos `open(w)` |
| B4 | `_atomic_write` u `utils/file_utils.py` | ⏳ DELIMICNO | jos u `core/engine.py:213`, `file_utils` ima svoju |
| C | `except-pass` → logger | ✅ ZAVRSENO | commit 7643be2, 37 fajlova, 152→13 |
| C+ | Preostalih 13 `except-pass` | ⏳ OSTALO | 2 u `styler.py`, 2 u `engine.py`, 1 u `packager.py`, 1 u `workers.py`, 1 u `main.py`, 1 u `tts.py`, 1 u `system_logger.py`, 1 u `name_replacer.py`, 1 u `app.py`, 1 u `file_utils.py` |
| D-J | Frontend, mobilni, UX, a11y, refaktor | ⏳ OSTALO | vidi "OTVORENO — BATCH D–J" |

---

## OTVORENO — BATCH D–J

### D — Frontend performanse
- 7 setInterval, 3 zovu /api/status → jedan poller
- services/polling.js postoji ali se ne ucitava
- nema visibilitychange (baterija kad je tab skriven)
- sw.js cache-uje nepostojeci app.js

### E — Mobilni raspored
- viewport-fit=cover bez env(safe-area-inset)
- 100vh → 100dvh
- 8 tabova u jednom redu bez scroll-snap
- 53 dugmeta, samo 2 imaju min-height 44px

### F — UX
- 11 alert() → toast
- 4 confirm() → bottom sheet
- nedostaju loading stanja

### G — Pristupacnost
- 2 aria- atributa, nijedan :focus-visible
- nema prefers-reduced-motion
- 186 !important u CSS-u
- 32 innerHTML sa tekstom iz chunkova

### H — app.py → blueprints (visok rizik)
- 2098 redaka, 33 rute
- prije: make audit-full baseline
- poslije: make audit-full diff, rollback ako FAIL raste

### I — Duplirana stilizacija (visok rizik)
- 5 modula dira dropcap
- odabrati epub/styler.py kao vlasnika

### J — Odrzavanje
- testovi, 168 print() → logger
- # FIX komentari → CHANGELOG.md

**Preporuceni redoslijed:** D → E → F → G → J → H → I

---

## KLJUCNE FUNKCIJE U EPUB/STYLER.PY

Ne diraj bez testa na TWP i The Collective.

| Funkcija | Linija | Sta |
|---|---|---|
| _ukloni_sve | ~92 | unwrap section + galley-rw, brise booklyfi klase |
| _normalizuj | ~144 | div→p, h4-h6→h3, dedup AAutorska |
| _dijalog | ~200 | orphan navodnici 1-6, " → — |
| _ukloni_duplikate_p | ~219 | min-len prefix match |
| _skrati_overlap | nova | suffix prethodnog = prefix sljedeceg |
| _je_duplikat | nova | fuzzy 70%/90% |
| _spoji_blokove | nova | razmak izmedju alfanum |
| _dodaj_vijenac | ~282 | ornament iznad naslova |
| _dodaj_naslov | ~516/725 | split TOC naslov |
| _dodaj_dropcap | ~550 | prvi p ≥60c, slovo ili crtica |
| run_epub_styler | ~808 | glavna funkcija |
| _classify | nested | frontmatter skip, copyright filter |
| _spoji_chk_u_html | inline | .chk → HTML |

---

## NA STA OBRATITI PAZNJU

1. from __future__ — svi importi poslije. ast.parse ne hvata, samo compile() i import.
2. h1 = body.find("h1") — mora biti prije if h1: u _dodaj_dropcap.
3. _ukloni_duplikate_p — mora biti prije _dodaj_dropcap u petlji.
4. _razdvoji_dijalog_p — NIKAD vracati u petlju (steti naraciji).
5. .chk bez <p> — F0.13 konvertuje plain text u <p>.
6. run_epub_styler — samo jedan (808+).
7. mode — uklonjen. Samo stilizuj(options).
8. .replacement — *X prefix, X cijela rijec, \bX\b regex.
9. apply_to_html — skip <head>, <h1-h3>, <script>, <style>.
10. main.py — _host prije try: bloka.

---

KRAJ KONTEKSTA
