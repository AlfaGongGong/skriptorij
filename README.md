# Skriptorij (BooklyFi Turbo)

Alat za **prijevod, lekturu i stilizaciju knjiga (EPUB) s engleskog na bosanski/hrvatski/srpski**, uz web sučelje i flotu besplatnih AI provajdera. Napravljen je za rad s mobitela (Android/Termux + proot Ubuntu), ali radi i na običnom Linuxu.

Ulaz je EPUB (ili MOBI uz opcionalnu ovisnost), izlaz je stiliziran EPUB na ciljnom jeziku. Obrada ide po blokovima teksta s checkpointima (`.chk`), pa se prekinuti posao nastavlja tamo gdje je stao.

> Stanje: kod je u funkciji i s njim se radi. Dio ponašanja je označen kao **nepotvrđen u radu** u internim zapisima (`HANDOFF`); to se odnosi na nedavne izmjene (npr. čekanje reseta kvote, dedup po slijedu riječi), ne na osnovni tok.

---

## Što radi

- **Prijevod** po blokovima (chunking), s kontekstom prethodnog i sljedećeg bloka, glosarom imena i rječnikom zamjena.
- **Lektura i korektura** (zasebne uloge modela, vidi `config/model_roles.py`), uz zaštitu od prevelikih izmjena korektora.
- **Kapije kvalitete** prije upisa checkpointa: struktura (broj `<p>`, znamenke, imena, replike), engleski ostaci, halucinacije, odsječen tekst, rod pripovjedača, tipografija i navodnici.
- **Verifikator** (zadano uključen) koji označava i po potrebi ponovno prevodi sumnjive blokove; ručni pregled kroz `/revizija`.
- **Stilizator** (`epub/styler.py`) koji iz `.chk` datoteka gradi završni EPUB: naslovna, TOC, drop caps, ukrasi, tipografija, čišćenje duplikata i preklopa među blokovima.
- **Otpornost na kvote**: praćenje dnevnih limita po ključu, cooldown ključeva, prebacivanje na drugog provajdera, čekanje reseta kvote umjesto prekida.
- **Web sučelje** (Flask) s pogledima Rad, Kvaliteta, Knjiga i Alati, upravljanjem ključevima i monitorom flote.
- Pomoćno: audiobook/TTS (`tts.py`, `tools/audiobook_batch.py`), alati za reviziju EPUB-ova (`tools/`).

## Kako teče obrada (pojednostavljeno)

~~~
EPUB (EN)
  -> parser / chunking              core/chunking.py, epub/parser.py
  -> prijevod (V1 ili V2 radnici)   processing/pipeline.py, processing/workers.py
  -> lektor -> korektor             core/prompts.py, config/model_roles.py
  -> kapije + popravci              core/gate_provjere.py, core/strukturna_kapija.py,
                                    core/text_utils.py, core/validators/
  -> checkpoint .chk                _skr_<knjiga>/checkpoints/
  -> verifikator                    core/verifier.py, processing/verifier_hook.py
  -> styler spaja .chk u EPUB       epub/styler.py (ne gradi EPUB od EN izvora ako spajanje padne)
STYLED EPUB (HR/BS/SR)
~~~

Provajderi i modeli se ne hardkodiraju u kodu: izvor istine je `config/providers.json`, a model za ulogu bira `model_discovery` prema zahtjevima iz `config/model_roles.py`.

## Zahtjevi

- Python 3.10+ (razvijano na Pythonu 3 u proot Ubuntuu)
- Ovisnosti: `requirements.txt` (Flask, requests, beautifulsoup4, lxml, ebooklib, httpx, classla i dr.). Točne verzije: `requirements.lock.txt`.
- Barem jedan API ključ nekog od podržanih provajdera (vidi dolje).
- Neobavezno: `mobi` (MOBI ulaz), `classla`/`obeliks` (morfološka provjera; resursi u `data/classla_resources/` nisu u repou).

## Instalacija

~~~bash
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # po potrebi popuni
~~~

Na Androidu: Termux + `proot-distro` (Ubuntu). Zadani direktoriji pokušavaju koristiti `/storage/emulated/0/...` ako je dostupan, inače se koristi home.

## Konfiguracija

### API ključevi

Ključevi se čuvaju u `dev_api.json` u korijenu projekta (u `.gitignore`, **nikad ga ne commitaj**). Format: ime provajdera i lista ključeva.

~~~json
{
  "GEMINI": ["KLJUC_1", "KLJUC_2"],
  "GROQ": ["KLJUC_3"]
}
~~~

Ključeve možeš dodavati i iz web sučelja (`POST /api/keys/<provajder>`); nova flota se učitava bez restarta. Podržani provajderi (`config/providers.json`): GEMINI, GEMMA, GROQ, CEREBRAS, SAMBANOVA, MISTRAL, TOGETHER, COHERE, CHUTES, HUGGINGFACE, KLUSTER, FIREWORKS, GITHUB, NVIDIA, OPENROUTER.

Napomena: besplatni planovi imaju dnevni limit zahtjeva (RPD). Više ključeva istog projekta kod provajdera dijeli isti limit.

### Varijable okruženja

| Varijabla | Značenje |
|---|---|
| `SKRIPTORIJ_PORT` | port servera (zadano 8080) |
| `SKRIPTORIJ_INPUT_DIR` | ulazni direktorij knjiga (zadano `~/Skriptorij/data`) |
| `SKRIPTORIJ_OUTPUT_DIR` | izlazni direktorij |
| `SKRIPTORIJ_CONFIG` | putanja do `dev_api.json` |
| `BOOKLYFI_HOST` | adresa servera; `0.0.0.0` za pristup s drugog uređaja |
| `BOOKLYFI_TOKEN` | token za pristup izvan localhosta; ako nije zadan a host nije lokalni, `main.py` ga generira i ispiše u konzolu |
| `BOOKLYFI_STYLED_DIR` | direktorij za stilizirane EPUB-ove |
| `BOOKLYFI_KANON_DIR`, `BOOKLYFI_KANON_ZRCALO_DIR` | kanonske knjige i njihovo zrcalo |
| `BOOKLYFI_ORNAMENTS_DIR` | ukrasi za stilizator |
| `BOOKLYFI_VERIFIER`, `BOOKLYFI_VERIFIER_FIX` | verifikator i ponovni prijevod označenih blokova; `main.py` ih postavlja na `1` ako nisu zadane, `run.py` pokrenut sam ih ne postavlja |
| `BOOKLYFI_CEKAJ` | `0` isključuje čekanje reseta kvote (vraća zaustavljanje) |
| `BOOKLYFI_WORKER_REP` | `1` vraća stari rep workera (ponovno ocjenjivanje, retry, EN rescue nad kopijom koja ne ulazi u `.chk`); zadano isključen |
| `CLOUDFLARE_ACCOUNT_ID` | za Cloudflare provajdera (vidi `.env.example`) |

Postoje i druge `BOOKLYFI_*` varijable (modeli po ulozi, filtriranje datoteka itd.); popis: `grep -rhoE "BOOKLYFI_[A-Z_0-9]+" --include=*.py .`

## Pokretanje

Web sučelje:

~~~bash
BOOKLYFI_HOST=127.0.0.1 python3 main.py
# otvori http://127.0.0.1:8080
~~~

Za pristup s drugog uređaja u mreži postavi `BOOKLYFI_HOST=0.0.0.0`; token će biti ispisan u konzoli (`http://<IP>:8080/?token=...`).

`run.py` je batch dio obrade (automatski bira mod PREVOD, LEKTURA ili AUTO-RETRO prema stanju checkpointa); web sučelje ga pokreće preko `/api/start`.

## Korištenje (sučelje)

1. Učitaj EPUB (`/api/upload_book`) ili stavi datoteku u ulazni direktorij.
2. U pogledu **Rad** dodaj ključeve, odaberi knjigu i pokreni obradu; pratiš progres, flotu i logove.
3. **Kvaliteta**: ocjene blokova, označeni blokovi, verifikator.
4. **Knjiga**: pregled EPUB-a, ručna revizija, povijest.
5. **Alati**: stilizator, TTS filter, stručni alati, monitor.
6. `/revizija` je zaseban ekran za pregled i odluke o označenim blokovima; `/intro` je uvodni ekran.
7. Gotov EPUB se preuzima preko `/api/download/<ime.epub>` (traži samo po imenu datoteke u izlaznom, ulaznom i STYLED direktoriju).

### Odabrane API rute

| Ruta | Namjena |
|---|---|
| `GET /api/status` | stanje obrade |
| `POST /api/start`, `/control/<action>` | pokretanje i upravljanje obradom |
| `/api/keys`, `/api/keys/<provajder>` | pregled, dodavanje, brisanje, ping i obnova ključeva |
| `/api/fleet`, `/api/monitor/*` | flota provajdera i monitor |
| `/api/quality*`, `/api/qa_flags*` | ocjene i oznake kvalitete |
| `/api/review/*`, `/api/human_review` | ručna revizija blokova |
| `/api/style_epub` | stilizacija EPUB-a |
| `/api/names/*` | zamjena imena |
| `/api/download/<ime>`, `/api/export/<fmt>` | preuzimanje i izvoz |

Potpun popis: `grep -rhoE 'route\("[^"]+"' app.py api/routes/*.py`

## Struktura repozitorija

| Direktorij / datoteka | Sadržaj |
|---|---|
| `main.py`, `app.py`, `run.py` | ulazna točka servera, Flask aplikacija, batch obrada |
| `api/` | rute (blueprinti), preglednik datoteka, error handleri |
| `config/` | postavke, `providers.json`, uloge modela, logging |
| `core/` | engine, promptovi, kapije, validatori, glosar, rod pripovjedača, kvaliteta |
| `processing/` | pipeline, radnici, paralelizam, retro obrada, verifikator |
| `epub/` | parser, normalizator, styler, packager |
| `network/` | HTTP klijent, router provajdera, praćenje kvota, rate limiter, discovery modela |
| `api_fleet.py` | upravljanje flotom provajdera |
| `static/`, `templates/` | frontend (JS/CSS/HTML) |
| `tools/` | pomoćne skripte: audit EPUB-a, rebuild knjige, retro popravci |
| `tests/` | testovi (`tests/unit`, `tests/integration`, `tests/golden`) |
| `HANDOFF.md`, `KONTEKST.md`, `CLAUDE_LOG.md` | zapisi razvoja i pravila rada |

## Direktoriji s podacima

- Checkpointi po knjizi: `_skr_<knjiga>/checkpoints/` (`.chk` glavni, `.prevod.chk` sirovi prijevod). Središnja baza checkpointa je `CHECKPOINT_BASE_DIR` (`/storage/emulated/0/booklyfi_checkpoints` ako je dostupan, inače `<ulaz>/_checkpoints`).
- Stilizirani EPUB-ovi: `STYLED_DIR`.
- Logovi i zapisi dedupa: `.logs/` (u `.gitignore`).
- Cooldowni kvota: `quota_cooldowns.json` (u `.gitignore`).

## Otpornost na kvote i greške

- `network/quota_tracker.py` bilježi cooldown po ključu; kad su svi ključevi svih provajdera iscrpljeni, obrada ne upisuje markere "neprevedeno" nego ulazi u stanje čekanja i nastavlja isto poglavlje nakon reseta.
- Zapisi na disk su atomski (`utils/file_utils.atomic_write_json`).
- Sumnjivi blokovi (fallback prijevod, neprevedeno, kapija koja nije mogla odlučiti) idu u `human_review` umjesto da tiho prođu.
- Stilizator ne pravi EPUB od engleskog izvora kad spajanje `.chk` datoteka padne.

## Testovi

~~~bash
python3 -m pytest -q tests/unit
make test        # Makefile pretpostavlja venv/bin/python3
make golden
~~~

## Razvojni postupak

Projekt se razvija malim, provjerljivim koracima: jedna izmjena = jedna skripta s git snapshotom prije izmjene, `ast.parse` + `py_compile`, testom, commitom i automatskim vraćanjem (rollback) pri bilo kojoj grešci. Pravila (P1-P20) i trenutno stanje nalaze se u `KONTEKST.md` i `HANDOFF.md`.

## Poznata ograničenja

- Kvaliteta i brzina ovise o besplatnim limitima provajdera (RPD); duge knjige se obrađuju kroz više dana.
- `stil_ai.py` i dio ruta/blueprinta nisu povezani s glavnim tokom (kandidati za čišćenje).
- Antologije i knjige s više pripovjedača traže ručni pregled roda pripovjedača (`human_review`).
- Pragovi nekih kapija (npr. korektor, dedup) nisu kalibrirani na velikom uzorku.

## Sigurnost

- `dev_api.json`, `.env` i checkpointi su u `.gitignore`; ključeve nikad ne stavljaj u repo.
- Izvan localhosta pristup štiti `BOOKLYFI_TOKEN`.

## Licenca

Nije određena.
