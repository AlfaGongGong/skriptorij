# ⚡ BOOKLYFI TURBO CHARGED

**Asinhroni AI Prevodilac i Lektor za EPUB/MOBI formate**

[![Status](https://img.shields.io/badge/Status-TURBO_CHARGED-3b82f6?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Platform](https://img.shields.io/badge/Platform-Termux%20%7C%20Linux%20%7C%20Windows-10b981?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Python](https://img.shields.io/badge/Python-3.10%2B-f59e0b?style=for-the-badge)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-a78bfa?style=for-the-badge)](LICENSE)

**BOOKLYFI TURBO CHARGED** je masivni, multi-modelarni AI sistem dizajniran za automatsko prevođenje, lektorisanje i formatiranje cijelih knjiga (EPUB i MOBI). Umjesto oslanjanja na jedan API koji može pasti ili udariti u *rate limit*, BOOKLYFI koristi **"Fleet Manager"** arhitekturu — rojeve API ključeva raspoređenih preko 8 različitih AI provajdera, uz kinematski 3D uvodni ekran koji rivalizes Matrix (1999) ali je moderan i web-nativan.

---

## ⚡ Ključne Funkcije

### 🧠 1. V8 Fleet Manager (8-Motorni Pogon)
Sistem upravlja višestrukim API ključevima u realnom vremenu. Ako jedan motor otkaže, sistem u milisekundi prebacuje zadatak na sljedeći dostupan motor bez prekida rada.

| Motor | Provajder |
|-------|-----------|
| `GEMINI` | Google |
| `GROQ` | Groq |
| `CEREBRAS` | Cerebras |
| `SAMBANOVA` | SambaNova |
| `MISTRAL` | Mistral AI |
| `COHERE` | Cohere |
| `OPENROUTER` | OpenRouter |
| `GITHUB` | GitHub Models |

- **Real-time health tracking** — svaki ključ prati se zasebno: dostupnost, cooldown timer, broj zahtjeva, greške
- **Rate-limit headeri** — parsira `X-RateLimit-*` headere, prikazuje minutne i dnevne kvote
- **Cooldown sistem** — ključevi koji dobiju 429 automatski se hlade i vraćaju u rotaciju

### 🛡️ 2. Auto-Heal Firewall & XML Karantin
- **Anti-Loop** — detektuje i uništava AI halucinacije (beskonačno ponavljanje)
- **XML Karantin** — sprečava prompt leaking (AI instrukcije u prijevodu)
- **Self-Correction** — oštećeni checkpointi se automatski obnavljaju

### 📖 3. Dinamički Glosar i Analiza Tona
Prije prevođenja, AI analizira početak knjige:
- Izvlači imena likova i njihov pol (gramatička dosljednost)
- Detektuje ton i žanr (prilagođen vokabular)

### 🔄 4. Live EPUB Preview
Svako završeno poglavlje generiše live `(LIVE)_Ime_Knjige.epub` koji se može odmah otvoriti u e-readeru.

### ⚡ 5. Pametni Checkpointi
Svaki blok se granularno spašava. Možete ugasiti proces i nastaviti tačno gdje ste stali.

### 🔊 6. TTS Filter Mode
Poseban mod koji generiše `.ttsfilter` fajl za Moon+ Reader i slične TTS čitače.

---

## 🎬 EMERGENCE — Kinematska Intro Animacija

BOOKLYFI uključuje spektakularnu **12-sekundnu intro animaciju** koja koristi Three.js i WebGL:

| Faza | Trajanje | Efekat |
|------|----------|--------|
| Digitalna kiša | 0–1 s | Plavi Matrix-style padajući simboli |
| Materijalizacija knjige | 1–3 s | 5000 čestica se skuplja u oblik knjige |
| Otapanje stranica | 3–5 s | Eksplozivno rasipanje čestica s trail efektom |
| Spiralni tok | 5–7 s | 3D helix, orbit, bokeh efekat |
| Emergencija loga | 7–9 s | Čestice morfuju u BOOKLYFI logo |
| Montaža teksta | 9–10 s | Slova se pojavljuju jedno po jedno |
| Kulminacija sjaja | 10–11 s | Bloom efekat na maksimumu |
| Nestajanje | 11–12 s | Fade u crno, UI se pojavljuje |

**Tehničke karakteristike:**
- Three.js r162 (WebGL 2 rendering)
- GPU-accelerated particle system (5000+ čestica)
- Smooth 60fps na modernim uređajima
- Mobilna verzija: 2200 čestica (optimizirano)
- Fallback za `prefers-reduced-motion` i starije preglednike
- Skip dugme pojavljuje se nakon 2 sekunde

---

## 🖥️ Web Interfejs

Flask Web UI sa BOOKLYFI dizajnom, pristupan iz bilo kojeg pretraživača.

### Ekrani i Paneli:
| Panel | Opis |
|-------|------|
| **Setup** | 2-koračni wizard — upload knjige + konfiguracija |
| **Dashboard** | Progress bar, ETA, statistika u realnom vremenu |
| **Fleet Pool** | Status svakog API ključa — dostupnost, cooldown, rate limiti |
| **Audit Log** | Detaljan dnevnik HTTP zahtjeva, prevoda i grešaka |
| **API Ključevi** | Dodaj/obriši ključeve bez ponovnog pokretanja |

### Status Semafor:
| Indikator | Značenje |
|-----------|----------|
| 🟢 RUNNING | Obrada u toku |
| ⏸️ PAUSED | Pauzirano |
| 🟡 IDLE | Čeka / standby |
| ❌ ERROR | Greška / zaustavljeno |

---

## 🛠️ Instalacija i Pokretanje

### Zahtjevi
- Python 3.10+
- `flask`, `requests`, `httpx`, `beautifulsoup4`, `lxml`, `tiktoken`
- Opcionalno: `mobi` (MOBI podrška)

### 1. Kloniranje
```bash
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij
pip install -r requirements.txt
```

### 2. Konfiguracija API Ključeva
Kreirajte `dev_api.json` u root folderu:
```json
{
    "GEMINI":     ["VAŠ_GEMINI_KLJUČ_1", "VAŠ_GEMINI_KLJUČ_2"],
    "GROQ":       ["VAŠ_GROQ_KLJUČ"],
    "CEREBRAS":   ["VAŠ_CEREBRAS_KLJUČ"],
    "SAMBANOVA":  ["VAŠ_SAMBA_KLJUČ"],
    "MISTRAL":    ["VAŠ_MISTRAL_KLJUČ"],
    "COHERE":     ["VAŠ_COHERE_KLJUČ"],
    "OPENROUTER": ["VAŠ_OPENROUTER_KLJUČ"],
    "GITHUB":     ["VAŠ_GITHUB_TOKEN"]
}
```

> ⚠️ **Napomena:** `dev_api.json` je već u `.gitignore` — nikad nemojte commitati stvarne ključeve!

### 3. Pokretanje
```bash
python main.py
```
Otvorite pretraživač na `http://localhost:8080`.

---

## 📂 Struktura Projekta

| Fajl / Folder | Opis |
|---------------|------|
| `main.py` | Ulazna tačka — Flask server, orkestrator |
| `app.py` | Flask factory, ruteri |
| `skriptorij.py` | V8 motor — chunking, AI pozivi, checkpoint sistem |
| `api_fleet.py` | Fleet Manager — tracking ključeva, cooldown, rate limiti |
| `intro_ui.py` | EMERGENCE intro animacija (Three.js, 12s) |
| `tts.py` | TTS filter mod za Moon+ Reader |
| `export_manager.py` | JSON/TXT izvještaji o prijevodu |
| `s.py` | Proxy i helper funkcije |
| `templates/index.html` | Glavna web stranica |
| `static/css/style.css` | BOOKLYFI dizajn sistem |
| `static/js/` | JavaScript moduli (app, fleet, UI) |
| `config/` | Konfiguracija i postavke |
| `api/` | Flask Blueprint rute |

---

## 🔒 .gitignore — Šta Staviti i Kako?

`.gitignore` fajl govori Gitu koje fajlove **nikada ne treba pratiti** (secrets, build artefakti, privremeni fajlovi).

### Naziv i lokacija
Fajl se **uvijek** naziva tačno: **`.gitignore`** (sa tačkom na početku, bez ekstenzije).  
Smjestite ga u **root (korijen) repozitorijuma** — isti folder gdje se nalazi `.git/` folder:

```
skriptorij/          ← root repozitorijuma
├── .git/
├── .gitignore       ← OVDJE, u root-u
├── main.py
└── ...
```

> Za specifičan podfolder možete kreirati i lokalni `.gitignore` u tom folderu — on vrijedi samo za taj folder.

### Sintaksa
```gitignore
# Komentar — ova linija se ignoruje

# Tačno ime fajla
secrets.json
dev_api.json

# Svi fajlovi s određenom ekstenzijom
*.log
*.pyc

# Cijeli folder (i sve što je unutra)
__pycache__/
node_modules/
dist/

# Fajl u specifičnom podfolderu
data/cache/

# Svaki fajl tog imena, bez obzira na lokaciju
**/.env

# Negacija — NE ignoruj ovaj fajl
!important.log
```

### Što UVIJEK staviti u .gitignore
```gitignore
# API ključevi i tajni podaci — OBAVEZNO
*.json          # ali oprezno — dodajte izuzetke za javne JSON fajlove
dev_api.json
proxies.json
.env
.env.*
secrets.*

# Python build artefakti
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/

# IDE i editor fajlovi
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db

# Logovi
*.log
logs/

# Privremeni fajlovi
*.tmp
*.temp
/tmp/
```

### Primjena na već commitane fajlove
Ako ste greškom commitali fajl koji treba biti ignorisan:
```bash
# Ukloni iz Git trackinga (fajl ostaje na disku)
git rm --cached ime_fajla.json

# Commitajte brisanje
git commit -m "Remove sensitive file from tracking"
```

> ⚠️ Ako ste commitali API ključeve ili lozinke, smatrajte ih kompromitovanima i odmah ih invalidujte/zamijenite, bez obzira na brisanje iz historije.

---

## 🔧 Troubleshooting

### "Svi motori nedostupni"
- Provjerite da li su API ključevi u `dev_api.json` validni
- Otvorite Fleet Pool panel — provjeri koji ključevi su na hlađenju
- Sačekajte da cooldown istekne (obično 60 sekundi nakon 429)
- Dodajte više ključeva za isti provajder

### Intro animacija se ne prikazuje
- Provjerite WebGL podršku: otvorite `chrome://gpu/` u Chromeu
- Stariji/slabiji uređaji automatski dobivaju CSS fallback
- Provjeri konzolu pretraživača za greške u učitavanju Three.js CDN-a

### Scroll ne radi
- Uvjerite se da intro overlay nije aktivan (preskočite ga ili sačekajte kraj)
- Scroll je automatski omogućen čim se main UI pojavi

### Rate limit / 429 greške
- Normalna pojava — sistem automatski prelazi na drugi motor
- Ključ se vraća u rotaciju nakon cooldown perioda

### Checkpoint greška
- Obrišite folder `data/_skr_ImeniKnjige/` za problematičnu knjigu
- Sistem će početi od početka

---

## ⚠️ Napomene

- Sistem koristi visoku kreativnost (temperatura) za književni prevod
- Povremene AI halucinacije moguće su; Auto-Heal Firewall ih detektuje u 99% slučajeva
- Za best results: koristite **QUAD_CORE** mod koji paralelno koristi sve dostupne motore

---

*Autor: [AlfaGongGong](https://github.com/AlfaGongGong)*  
*Dizajnirano za konzumiranje masivnih količina teksta. Ne čitajte loše prevode.*
