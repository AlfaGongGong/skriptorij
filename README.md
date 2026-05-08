

# 📚 BOOKLYFI ⚡ TURBO V10

**AI-Powered Book Translation & Refinement Engine**

[![Version](https://img.shields.io/badge/Version-TURBO_V10-3b82f6?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Android-10b981?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Python](https://img.shields.io/badge/Python-3.10%2B-f59e0b?style=for-the-badge)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-8b5cf6?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-0ea5e9?style=for-the-badge)](Dockerfile)

**BOOKLYFI TURBO V10** is a full-featured, multi-model AI engine that automatically translates, proofreads, and formats entire books in EPUB/MOBI format. Rather than relying on a single API that can fail or hit rate limits, BOOKLYFI runs a **Fleet Manager** — a pool of API keys spread across **14 AI providers**, with per-key semaphore locking, automatic cooldown rotation, and millisecond-level failover.

---

## ✨ Ključne funkcionalnosti

| Funkcionalnost | Opis |
|----------------|------|
| 🧠 **Fleet Manager V10** | 14 AI provajdera u jednoj floti — automatska rotacija ključeva, per-key semaphore, pametni cooldown |
| 🔍 **Live ping ključeva** | Klikni dugme 🔍 pored bilo kojeg ključa da odmah provjeriš njegovo stvarno zdravlje |
| 🔄 **3-pass AI pipeline** | PREVODILAC → LEKTOR → KOREKTOR — tri nezavisna AI prolaska za svaki blok teksta |
| 🎯 **Kompozitni quality scorer** | Heuristička + AI ocjena (25/75 ponderi), thresholds: 🌟 ≥8.5 · ✅ ≥6.5 · ⚠ ≥4.0 · 🔴 <4.0 |
| 🛡️ **Auto-Heal Firewall** | Otkriva i uništava AI halucinacije i prompt injection pokušaje u realnom vremenu |
| 📖 **Dinamički glosar** | Analizira likove, ton i žanr knjige prije nego što prijevod počne |
| 🔄 **RETRO re-lektura** | Ponovo obradi samo blokove ispod zadanog quality praga — bez restarta od nule |
| 📊 **Quality Review panel** | Označi loše blokove, pošalji ih na popravku jednim klikom, prati napredak uživo |
| ⚡ **Smart checkpointi** | Granularno snimanje po bloku — nastavi točno gdje si stao/la |
| 🔊 **TTS Filter mode** | Generiše `.ttsfilter` output za Moon+ Reader i ostale TTS aplikacije |
| 🌗 **Tamna / svijetla tema** | Glassmorphism dizajn, live switching bez reload-a |
| 📱 **PWA podrška** | Dodaj na početni ekran mobitela, radi i offline (service worker) |

---

## 🚀 Brzi start

### Preduvjeti

- **Python 3.10+**
- **pip** package manager
- Barem jedan API ključ od jednog od podržanih provajdera:

| Provajder | Link | Napomena |
|-----------|------|----------|
| 🔷 Google Gemini | [ai.google.dev](https://ai.google.dev) | Preporučen — visok kvalitet, 1500 RPD besplatno |
| ⚡ Groq | [console.groq.com](https://console.groq.com) | Ultra-brz, 14 400 RPD besplatno |
| 🔬 Cerebras | [cloud.cerebras.ai](https://cloud.cerebras.ai) | Najbrži inference, 14 400 RPD |
| 🧠 SambaNova | [cloud.sambanova.ai](https://cloud.sambanova.ai) | Visok throughput, DeepSeek modeli |
| 💫 Mistral | [console.mistral.ai](https://console.mistral.ai) | Višejezični specijalist |
| 🌐 Cohere | [dashboard.cohere.com](https://dashboard.cohere.com) | Jak za lekturu |
| 🔀 OpenRouter | [openrouter.ai](https://openrouter.ai) | Pristup stotinama modela |
| 🐙 GitHub Models | [github.com/marketplace/models](https://github.com/marketplace/models) | Besplatno s GitHub računom |
| 🤝 Together AI | [api.together.xyz](https://api.together.xyz) | Llama i ostali open-source modeli |
| 🎆 Fireworks AI | [fireworks.ai](https://fireworks.ai) | Brz inference za open-source modele |
| 🪣 Chutes AI | [chutes.ai](https://chutes.ai) | Besplatni LLM endpoint |
| 🤗 HuggingFace | [huggingface.co](https://huggingface.co) | Inference API / serverless |
| 🔗 Kluster AI | [kluster.ai](https://kluster.ai) | OpenAI-kompatibilni endpoint |
| 🔷 Gemma (Together) | — | Google Gemma modeli putem Together |

### Instalacija

```bash
# 1. Kloniraj repozitorij
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij

# 2. (Preporučeno) Kreiraj virtualno okruženje
python3 -m venv venv
source venv/bin/activate        # Linux / macOS / Termux
# venv\Scripts\activate         # Windows

# 3. Instaliraj ovisnosti
pip install -r requirements.txt
```

### Konfiguracija

Kreiraj `dev_api.json` u root direktoriju projekta sa svojim API ključevima:

```json
{
    "GEMINI":      ["TVOJ_GEMINI_KLJUC_1", "TVOJ_GEMINI_KLJUC_2"],
    "GROQ":        ["TVOJ_GROQ_KLJUC"],
    "CEREBRAS":    ["TVOJ_CEREBRAS_KLJUC"],
    "SAMBANOVA":   ["TVOJ_SAMBANOVA_KLJUC"],
    "MISTRAL":     ["TVOJ_MISTRAL_KLJUC"],
    "COHERE":      ["TVOJ_COHERE_KLJUC"],
    "OPENROUTER":  ["TVOJ_OPENROUTER_KLJUC"],
    "GITHUB":      ["TVOJ_GITHUB_TOKEN"],
    "TOGETHER":    ["TVOJ_TOGETHER_KLJUC"],
    "FIREWORKS":   ["TVOJ_FIREWORKS_KLJUC"],
    "CHUTES":      ["TVOJ_CHUTES_KLJUC"],
    "HUGGINGFACE": ["TVOJ_HF_TOKEN"],
    "KLUSTER":     ["TVOJ_KLUSTER_KLJUC"]
}
```

> ⚠️ **Sigurnost:** `dev_api.json` je u `.gitignore` — **nikad ne commituj stvarne ključeve!**  
> Potreban ti je samo jedan ključ od jednog provajdera da aplikacija radi.

### Pokretanje

```bash
python main.py
```

Otvori browser na **`http://localhost:8080`**. Na Termux-u (Android), browser se otvori automatski.

---

## 📂 Struktura projekta

```
skriptorij/
├── main.py                      # Entry point — pokreće Flask server
├── app.py                       # Flask application factory
├── run.py                       # Alternativni launcher (za Termux i desktop)
├── api_fleet.py                 # Fleet Manager — praćenje ključeva, cooldown, RPM/RPD limiti
├── tts.py                       # TTS filter mode za Moon+ Reader
│
├── config/                      # 🔧 Konfiguracija aplikacije
│   ├── settings.py              # Zajednički state, env varijable, putanje
│   └── logging_config.py        # Logging konfiguracija
│
├── api/                         # 🌐 Flask Blueprint rute
│   ├── __init__.py              # Blueprint registracija
│   ├── middleware/              # Error handleri, CORS
│   └── routes/
│       ├── books.py             # Upload, listanje, preuzimanje knjiga
│       ├── processing.py        # Pokretanje, status, odabir modela
│       ├── control.py           # Pauza, nastavak, stop, reset
│       ├── fleet.py             # Fleet status & toggle ključeva
│       ├── keys.py              # CRUD ključeva + ping (health check)
│       ├── qualities.py         # Quality score pregled i ažuriranje
│       ├── quality.py           # Scoring API rute
│       └── export.py            # JSON/TXT export izvještaja
│
├── core/                        # ⚙️ Jezgro engine-a
│   ├── engine.py                # SkriptorijAllInOne — orchestracija obrade
│   ├── quality.py               # Kompozitni quality scorer (heuristika + AI)
│   ├── text_utils.py            # Čišćenje teksta, detekcija engleskog, tipografija
│   └── prompt_injector.py       # Dinamičko ubacivanje glosara u prompte
│
├── processing/                  # 🔄 Pipeline moduli
│   ├── pipeline.py              # 3-pass pipeline: PREVODILAC → LEKTOR → KOREKTOR
│   ├── workers.py               # Async chunk workeri (V1)
│   ├── workers_v2.py            # Async chunk workeri (V2, aktivan)
│   ├── parallel.py              # Paralelna obrada poglavlja
│   ├── retro.py                 # RETRO re-lektura loših blokova
│   └── rescue.py                # Spašavanje iz sirovog AI odgovora
│
├── network/                     # 🌍 Mrežni sloj
│   ├── http_client.py           # HTTP POST s per-key semaphore i 429 handlingom
│   ├── rate_limiter.py          # Per-key asyncio semaphore (MAX_CONCURRENT=1)
│   ├── provider_urls.py         # URL mapa svih 14 provajdera
│   ├── provider_router.py       # Routing po ulozi (PREVODILAC, LEKTOR, itd.)
│   └── urls.py                  # Legacy URL helperi
│
├── analysis/                    # 📊 Analiza knjige
│   └── book_context.py          # Dinamički glosar — analiza likova, tona, žanra
│
├── epub/                        # 📚 EPUB obrada
│   └── parser.py                # Parsiranje, čišćenje i rekonstrukcija EPUB-a
│
├── utils/                       # 🛠️ Pomoćne funkcije
│   └── file_utils.py            # Sigurni nazivi fajlova, path validacija
│
├── static/                      # 🎨 Frontend resursi
│   ├── css/
│   │   └── style.css            # Glavni stylesheet (tamna/svijetla tema)
│   ├── js/
│   │   ├── main.js              # Inicijalizacija aplikacije
│   │   ├── api-client.js        # HTTP klijent za sve API pozive
│   │   ├── ui/
│   │   │   ├── fleet.js         # Prikaz Fleet poola
│   │   │   └── notifications.js # Toast notifikacije
│   │   ├── services/
│   │   │   ├── polling.js       # Real-time polling statusa
│   │   │   ├── storage.js       # localStorage perzistencija
│   │   │   └── theme.js         # Tamna/svijetla tema
│   │   └── intro/               # 3D intro animacija (Three.js)
│   ├── manifest.json            # PWA manifest
│   └── sw.js                    # Service worker (offline podrška)
│
├── templates/
│   ├── index.html               # Glavni UI (dashboard)
│   └── intro.html               # Cinematični intro ekran
│
├── tests/                       # 🧪 Test suite
│   ├── unit/
│   │   └── test_validators.py   # Unit testovi za validatore
│   └── integration/
│       └── test_api_routes.py   # Integracijski testovi API ruta
│
├── Dockerfile                   # Docker image definicija
├── docker-compose.yml           # Docker Compose konfiguracija
├── requirements.txt             # Python ovisnosti
├── dev_api.json                 # ⚠️ Tvoji API ključevi (u .gitignore — nikad ne commituj!)
└── .gitignore                   # Git ignore pravila
```

### Arhitektura

BOOKLYFI koristi **modularni monolit** — jedna deployable jedinica podijeljena u jasne, nezavisne module:

```
Browser ──► Flask (app.py)
              │
              ├─► api/routes/       (HTTP sloj — Flask Blueprinti)
              ├─► config/settings   (Zajednički state i putanje)
              ├─► core/             (Business logika)
              ├─► processing/       (Pipeline i workeri)
              └─► network/          (HTTP klijent, rate limiter)
                        │
              api_fleet.py ◄─── FleetManager singleton
              (Rotacija ključeva,       (register_active_fleet /
               cooldown, semaphore)      get_active_fleet)
```

---

## ⚙️ Konfiguracija

### API ključevi (`dev_api.json`)

> ⚠️ **NIKAD ne commituj ovaj fajl!** Već je u `.gitignore`.

```json
{
    "GEMINI":      ["kljuc1", "kljuc2"],
    "GROQ":        ["kljuc1", "kljuc2", "kljuc3"],
    "CEREBRAS":    ["kljuc1"],
    "SAMBANOVA":   ["kljuc1", "kljuc2"],
    "MISTRAL":     ["kljuc1"],
    "COHERE":      ["kljuc1"],
    "OPENROUTER":  ["kljuc1"],
    "GITHUB":      ["token1"],
    "TOGETHER":    ["kljuc1"],
    "FIREWORKS":   ["kljuc1"],
    "CHUTES":      ["kljuc1"],
    "HUGGINGFACE": ["token1"],
    "KLUSTER":     ["kljuc1"]
}
```

- **Više ključeva po provajderu** — Fleet Manager ih rotira automatski
- Ključevi se mogu dodavati/brisati **bez restarta** iz panela API ključevi u UI-u
- Klikni **🔍** pored ključa da odmah provjeriš je li ključ validan (live ping)

### Env varijable

| Varijabla | Default | Opis |
|-----------|---------|------|
| `SKRIPTORIJ_PORT` | `8080` | Port Flask servera |
| `SKRIPTORIJ_CONFIG` | `dev_api.json` | Putanja do konfiguracije ključeva |
| `PYTHONUNBUFFERED` | `1` | Real-time output logova u Dockeru |
| `BOOKLYFI_V2` | `1` | Aktivira workers_v2 (preporučeno) |

### Proxy konfiguracija (`proxies.json`)

Ako moraš rutirati zahtjeve kroz proxy:

```bash
cp proxies.json.example proxies.json
# Uredi proxies.json s tvojim proxy podešavanjima
```

> `proxies.json` je u `.gitignore` radi zaštite kredencijala.

---

## 📖 Vodič za korištenje

### Korak 1 — Upload knjige

1. Na **Setup** ekranu, klikni **📁 Upload EPUB/MOBI** ili prevuci i spusti fajl
2. Knjiga se pojavljuje u dropdown za odabir
3. Prethodno korištene knjige se automatski pamte

### Korak 2 — Odaberi model

- **AUTO** (preporučeno) — engine sam detektuje PREVOD ili LEKTURA mod
- **GROQ / CEREBRAS / GEMINI** itd. — prisili na specifičan provajder
- **RETRO** — ponovi lekturu samo za blokove ispod zadanog quality praga
- **TTS** — filter mode za Moon+ Reader

### Korak 3 — Pokretanje

1. Klikni **🚀 Pokreni Sistem**
2. Prati **Dashboard** za real-time napredak:
   - Traka napretka s postotkom
   - ETA (preostalo vrijeme)
   - Indikator aktivnog engine-a
   - Brojač obrađenih blokova

### Korak 4 — Praćenje zdravlja flote

Panel **🛡️ Flota** prikazuje live status svakog API ključa:

| Indikator | Značenje |
|-----------|---------|
| 🟢 AKTIVAN | Ključ dostupan i obrađuje zahtjeve |
| 🟡 HLADI SE | Ključ pogodio rate limit — automatski cooldown |
| 🔴 GREŠKA | Ključ vratio grešku — provjeri validnost |
| ⚫ ISKLJUČEN | Ključ ručno isključen toggle-om |

> **Novi:** Klikni **🔍** dugme pored ključa u tabu **Stručnjak** da odmah provjeriš stvarno stanje ključa direktnim API pozivom.

### Korak 5 — Quality Review

Panel **🎯 Kvalitet** prikazuje ocjenu svakog prevedenog bloka:

| Oznaka | Ocjena | Akcija |
|--------|--------|--------|
| 🌟 Odlično | ≥ 8.5 | Nema potrebe |
| ✅ Dobro | 6.5 – 8.5 | Opciona provjera |
| ⚠ Treba retro | 4.0 – 6.5 | Klikni za označavanje |
| 🔴 Kritično | < 4.0 | Hitna re-lektura |

Klikni **🔧 Relektura označenih** da pošalješ loše blokove na RETRO prolaz.

### Korak 6 — Export

Kad obrada završi:
- **Download EPUB/MOBI** — prevedena knjiga
- **Export JSON izvještaj** — detaljne statistike (blokovi, timing, greške)
- **Export TXT izvještaj** — čitljivi log prijevoda

### Kontrola obrade

| Dugme | Akcija |
|-------|--------|
| ⏸️ Pauza | Suspendira obradu nakon trenutnog bloka |
| ▶️ Nastavi | Nastavlja od pauze |
| ⏹️ Stop | Graceful zaustavljanje obrade |
| 🔄 Reset | Povratak na Setup ekran (zadržava checkpointe) |

---

## 🌐 API Endpoints

### Knjige

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/files` | Lista svih dostupnih EPUB/MOBI knjiga |
| `POST` | `/api/upload_book` | Upload nove knjige |
| `GET` | `/api/download` | Preuzimanje rezultantnog fajla |
| `GET` | `/api/epub_preview` | Live EPUB preview (poglavlje po poglavlje) |
| `GET` | `/api/epub_text/<book>` | Sirovi tekst EPUB-a (za pregled) |

### Obrada

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/status` | Puni status obrade + ETA |
| `GET` | `/api/dev_models` | Lista dostupnih AI modela/provajdera |
| `POST` | `/api/start` | Pokretanje (`{"book": "...", "model": "GROQ", "tool": "AUTO"}`) |

### Kontrola obrade

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/control/pause` | Pauziraj obradu |
| `POST` | `/control/resume` | Nastavi pauzu |
| `POST` | `/control/stop` | Zaustavi obradu |
| `POST` | `/control/reset` | Reset na početno stanje |

### Fleet upravljanje

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/fleet` | Svi provajderi i status ključeva |
| `POST` | `/api/fleet/toggle` | Toggle ključ on/off (`{"provider": "GROQ", "key": "...abc"}`) |

### API ključevi

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/keys` | Lista svih provajdera i maskiranih ključeva |
| `POST` | `/api/keys/<provider>` | Dodaj ključ (`{"key": "tvoj-api-kljuc"}`) |
| `DELETE` | `/api/keys/<provider>/<idx>` | Obriši ključ po indeksu |
| `POST` | `/api/keys/<provider>/<idx>/ping` | **Live health check** ključa — vraća `{ok, latency_ms, status_code}` |

### Quality Scores

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/quality_scores` | Sve ocjene kvalitete za trenutnu knjigu |
| `PATCH` | `/api/quality_scores/<stem>` | Ažuriraj ocjenu bloka |
| `DELETE` | `/api/quality_scores/<stem>` | Obriši ocjenu bloka |
| `POST` | `/api/quality_scores/send_to_fix` | Pošalji blok na RETRO popravku |
| `POST` | `/api/fix/bad_blocks` | Re-obrada loših blokova ispod praga |
| `POST` | `/api/fix/marked_blocks` | Re-obrada ručno označenih blokova |

### Export

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/api/export/json` | Preuzmi JSON izvještaj prijevoda |
| `GET` | `/api/export/txt` | Preuzmi TXT izvještaj prijevoda |

---

## 🧪 Razvoj

### Pokretanje testova

```bash
# Puni test suite (18 testova)
python3 -m pytest tests/ -v

# Samo unit testovi
python3 -m pytest tests/unit/ -v

# Samo integracijski testovi
python3 -m pytest tests/integration/ -v

# Kratki output (samo greške)
python3 -m pytest tests/ -v --tb=short
```

### Provjera sintakse

```bash
python3 -m py_compile main.py app.py api_fleet.py
python3 -m py_compile api/routes/keys.py network/http_client.py
```

### Lokalni dev server

```bash
# Eksplicitni port
SKRIPTORIJ_PORT=9000 python main.py

# Isključi workers_v2 (legacy mod)
BOOKLYFI_V2=0 python main.py
```

---

## 🚢 Deployment

### Linux — systemd servis

Kreiraj `/etc/systemd/system/booklyfi.service`:

```ini
[Unit]
Description=BOOKLYFI TURBO V10 — AI Book Translation Engine
After=network.target

[Service]
Type=simple
User=booklyfi
WorkingDirectory=/opt/booklyfi
Environment=SKRIPTORIJ_PORT=8080
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/booklyfi/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -s /bin/false booklyfi
sudo cp -r . /opt/booklyfi
sudo chown -R booklyfi:booklyfi /opt/booklyfi
sudo systemctl daemon-reload
sudo systemctl enable --now booklyfi
sudo journalctl -u booklyfi -f
```

### Docker (Preporučeno)

```bash
# Build i start
docker compose up -d

# Logovi
docker compose logs -f

# Stop
docker compose down
```

`docker-compose.yml` mountuje:
- `./data/` — perzistentni checkpointi i knjige
- `./dev_api.json` — API ključevi (read-only)
- `./proxies.json` — proxy konfiguracija (read-only)

```bash
# Manuelni build
docker build -t booklyfi .
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/dev_api.json:/app/dev_api.json:ro \
  --name booklyfi \
  booklyfi
```

### Android (Termux)

```bash
# Instaliraj Termux s F-Droid (ne Play Store!)
pkg update && pkg install python git
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij
pip install -r requirements.txt
python main.py
# Browser se otvori automatski na http://localhost:8080
```

> Ili dodaj na početni ekran kao **PWA** — webapp radi kao nativna aplikacija.

---

## 🔧 Rješavanje problema

### "Nema API ključeva" / Svi provajderi nedostupni

```bash
# Provjeri validan JSON
python3 -m json.tool dev_api.json

# Provjeri lokaciju
ls -la dev_api.json   # mora biti u root direktoriju projekta
```

- Barem jedan ključ od jednog provajdera je dovoljan
- Ključeve dodaj direktno iz UI-a u panelu **API ključevi** → odmah aktivno
- Klikni **🔍** pored ključa da provjeriš je li validan

### Rate limit (429 Too Many Requests)

- **Normalno je** — Fleet Manager automatski prebacuje na sljedeći ključ
- V10 više ne ponavlja isti iscrpljeni ključ (eliminiran recursive retry)
- Dodaj više ključeva po provajderu za veći throughput
- Prati cooldown tajmere u panelu **Flota**

### Problemi s kvalitetom prijevoda

- Koristi AUTO mod — engine sam odlučuje PREVOD ili LEKTURA
- Dinamički glosar analizira prvih ~2000 tokena knjige
- Nakon prijevoda, iskoristi **RETRO** za re-lekturu loših blokova
- Gemini i Mistral daju generalno best literary quality

### UI ne reagira

```
Ctrl + Shift + R   # Hard-refresh (Chrome/Firefox)
Cmd + Shift + R    # macOS
```

- F12 → Console tab za JavaScript greške
- Chrome/Brave preporučeni browseri

### Checkpoint problemi

```bash
# Checkpointi su u data/_skr_<NazivKnjige>/
ls data/

# Restart od nule (brisanje checkpointa)
rm -rf data/_skr_NazivKnjige/
```

---

## 🤝 Doprinos projektu

Doprinosi su dobrodošli!

1. **Fork** repozitorij
2. **Kreiraj** granu: `git checkout -b feature/nova-funkcija`
3. **Commit** promjene: `git commit -m 'feat: dodaj novu funkciju'`
4. **Push**: `git push origin feature/nova-funkcija`
5. **Otvori** Pull Request

### Konvencija commit poruka

```
feat:     Nova funkcionalnost
fix:      Ispravka buga
docs:     Promjene dokumentacije
refactor: Refaktorisanje koda (bez promjene funkcionalnosti)
test:     Dodavanje ili ažuriranje testova
chore:    Održavanje (ovisnosti, CI, itd.)
```

---

## 📋 Roadmap

- [x] 3-pass AI pipeline (PREVODILAC → LEKTOR → KOREKTOR)
- [x] Fleet Manager s 14 provajdera i automatskom rotacijom ključeva
- [x] Per-key asyncio semaphore (MAX_CONCURRENT=1 po ključu)
- [x] Live ping/health check za svaki API ključ
- [x] Kompozitni quality scorer (heuristika + AI, 25/75 ponder)
- [x] RETRO re-lektura za blokove ispod quality praga
- [x] Real-time web dashboard (tamna/svijetla tema)
- [x] Modularni monolith (api/, core/, processing/, network/, config/)
- [x] Docker + systemd deployment
- [x] Smart checkpointi (granularno snimanje po bloku)
- [x] PWA podrška (manifest + service worker)
- [x] Collapsible Fleet panel u Stručnjak tabu
- [ ] Nativna Android aplikacija (`.apk`)
- [ ] Debian paket (`.deb`) za Linux desktop
- [ ] Cloud sinhronizacija knjiga i checkpointa
- [ ] Web-based EPUB editor za post-translation review

---

## 🔐 Sigurnosne napomene

- `dev_api.json` i `proxies.json` su u `.gitignore` — **nikad ne commituj ove fajlove**
- API ključevi su maskirani u UI-u (prikazuje se samo zadnjih 6 znakova: `...abc123`)
- Svi putevi fajlova su sanitizirani protiv directory traversal napada
- Aplikacija radi lokalno — podaci idu samo na AI provajdere koje koristiš

---

## 📄 Licenca

MIT License — vidi [LICENSE](LICENSE) fajl za detalje.

---

## 💬 Kontakt i podrška

- 🐛 **Bugovi:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
- 💡 **Prijedlozi:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
- 👤 **Autor:** [AlfaGongGong](https://github.com/AlfaGongGong)

---

*Napravljeno s ❤️ za čitaoce koji ne čekaju zvanične prijevode.*  
*BOOKLYFI TURBO V10 — jer dobre knjige ne smiju imati jezičke prepreke.*

