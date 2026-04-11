# 🚀 SKRIPTORIJ V8 TURBO
**Asinhroni AI Prevodilac i Lektor za EPUB/MOBI formate**

![Status](https://img.shields.io/badge/Status-V8_Turbo-00f3ff?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Termux%20%7C%20Linux%20%7C%20Windows-10b981?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-f59e0b?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

**Skriptorij V8 Turbo** je masivni, multi-modelarni AI sistem dizajniran za automatsko prevođenje, lektorisanje i formatiranje cijelih knjiga (EPUB i MOBI). Umjesto oslanjanja na jedan API koji može pasti ili udariti u *rate limit*, Skriptorij koristi **"Fleet Manager"** arhitekturu — rojeve API ključeva raspoređenih preko 8 različitih AI provajdera.

---

## ⚡ Ključne Funkcije

### 🧠 1. V8 Fleet Manager (8-Motorni Pogon)
Sistem upravlja višestrukim API ključevima u realnom vremenu. Ako jedan motor otkaže, sistem u milisekundi prebacuje zadatak na sljedeći dostupan motor bez prekida rada.

* **Podržani motori:** `GEMINI`, `GROQ`, `CEREBRAS`, `SAMBANOVA`, `MISTRAL`, `COHERE`, `OPENROUTER`, `GITHUB`
* **Real-time health tracking:** Svaki ključ se prati zasebno — stanje dostupnosti, cooldown timer, broj zahtjeva, greške
* **Rate-limit headeri:** Sistem parsira `X-RateLimit-*` headere i prikazuje minutne i dnevne kvote po ključu
* **Cooldown sistem:** Ključevi koji dobiju 429 odgovor automatski se hlade i vraćaju u rotaciju

### 🛡️ 2. Auto-Heal Firewall & XML Karantin
* **Anti-Loop:** Detektuje i uništava AI halucinacije (beskonačno ponavljanje)
* **XML Karantin:** Ako AI pokušan ispljunuti instrukcije u prijevod (Prompt Leaking), blok se odbija
* **Self-Correction:** Oštećeni checkpointi se automatski obnavljaju

### 📖 3. Dinamički Glosar i Analiza Tona
Prije prevođenja, AI analizira početak knjige:
* Izvlači imena likova i njihov pol (gramatička dosljednost)
* Detektuje ton i žanr knjige (prilagođen vokabular)

### 🔄 4. Live EPUB Preview
Svako završeno poglavlje generiše live `(LIVE)_Ime_Knjige.epub` koji se može odmah otvoriti u e-readeru.

### ⚡ 5. Pametni Checkpointi
Svaki blok se granularno spašava. Možete ugasiti proces i nastaviti tačno gdje ste stali.

### 🔊 6. TTS Filter Mode
Poseban mod koji generiše `.ttsfilter` fajl za Moon+ Reader i slične TTS čitače.

---

## 🖥️ Web Interfejs (V8 UI)

Flask Web UI sa dark/neon temom, pristupan iz bilo kojeg pretraživača (mobilnog ili desktop).

### Ekrani i Paneli:
| Panel | Opis |
|-------|------|
| **Setup** | Upload EPUB/MOBI, odabir motora i načina rada |
| **Dashboard** | Progress bar, ETA, statistika obrade |
| **Fleet Pool** | Realtime status svakog API ključa — dostupnost, cooldown, rate limiti |
| **Audit Log** | Detaljan dnevnik HTTP zahtjeva, prevoda i grešaka |
| **API Ključevi** | Dodaj/obriši ključeve bez ponovnog pokretanja |

### Status Semafor:
| Boja | Značenje |
|------|----------|
| 🟢 Zelena | Obrada u toku / završeno uspješno |
| 🟡 Žuta | IDLE / pauza / upozorenje |
| 🔴 Crvena | Greška / zaustavljeno |
| 🟣 Ljubičasta | Pauzirano |

---

## 🛠️ Instalacija i Pokretanje

### Zahtjevi
- Python 3.10+
- pip paketi: `flask`, `requests`, `httpx`, `beautifulsoup4`, `lxml`, `tiktoken`
- Opcionalno: `mobi` (za MOBI podršku)

### 1. Kloniranje repozitorijuma
```bash
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij
pip install -r requirements.txt
```

### 2. Konfiguracija API Ključeva
Kreirajte `dev_api.json` u root folderu:
```json
{
    "GEMINI": ["TVOJ_GEMINI_KLJUC_1", "TVOJ_GEMINI_KLJUC_2"],
    "GROQ": ["TVOJ_GROQ_KLJUC"],
    "CEREBRAS": ["TVOJ_CEREBRAS_KLJUC"],
    "SAMBANOVA": ["TVOJ_SAMBA_KLJUC"],
    "MISTRAL": ["TVOJ_MISTRAL_KLJUC"],
    "COHERE": ["TVOJ_COHERE_KLJUC"],
    "OPENROUTER": ["TVOJ_OPENROUTER_KLJUC"],
    "GITHUB": ["TVOJ_GITHUB_TOKEN"]
}
```

**Napomena:** `dev_api.json` je u `.gitignore` — nikad nemojte commitati stvarne ključeve!

### 3. Pokretanje
```bash
python main.py
```
Otvorite pretraživač na `http://localhost:8080`. Na Termuxu se browser otvara automatski.

---

## 📂 Struktura Projekta

| Fajl | Opis |
|------|------|
| `main.py` | Flask server, API endpointi, orkestrator |
| `skriptorij.py` | V8 motor — chunking, AI pozivi, checkpoint sistem |
| `api_fleet.py` | Fleet Manager — tracking ključeva, cooldown, rate limiti |
| `intro_ui.py` | Kinematski Matrix→Quill uvodni ekran |
| `tts.py` | TTS filter mod za Moon+ Reader |
| `export_manager.py` | JSON/TXT izvještaji o prijevodu |
| `s.py` | Proxy i helper funkcije |
| `templates/index.html` | Glavna web stranica |
| `static/` | CSS i JavaScript fajlovi |

---

## 🔧 Troubleshooting

### "Svi motori nedostupni"
- Provjerite da li su svi API ključevi u `dev_api.json` validni
- Otvorite Fleet Pool panel i provjerite koji ključevi su na hlađenju
- Sačekajte da cooldown istekne (obično 60 sekundi nakon 429 odgovora)
- Dodajte više ključeva za isti provajder (rotacija ključeva)

### "Motor na hlađenju"
- Normalna pojava kad server vrati 429 (Too Many Requests)
- Sistem automatski prelazi na drugi dostupni motor
- Ključ se vraća u rotaciju nakon cooldown perioda

### Status semafor ostaje žut
- Žuta boja = IDLE stanje (sistem čeka)
- Pokreće prijevod → zelena
- Dođe greška → crvena

### Rate limit informacije ne prikazuju se
- Rate limit info se puni tek nakon prvog uspješnog API odgovora koji sadrži `X-RateLimit-*` headere
- Nije svaki provajder šalje ove headere (npr. Cerebras, SambaNova možda ne)

### Checkpoint greška
- Obrišite folder `data/_skr_ImeniKnjige/` za problematičnu knjigu
- Sistem će početi od početka

---

## ⚠️ Napomene

- Sistem koristi visoku kreativnost (temperatura) za književni prevod
- Povremene AI halucinacije su moguće; Auto-Heal Firewall ih uočava u 99% slučajeva
- Za best results: koristite **QUAD_CORE** mod koji paralelno koristi sve dostupne motore

---

*Autor: [AlfaGongGong](https://github.com/AlfaGongGong)*  
*Dizajnirano za konzumiranje masivnih količina teksta. Ne čitajte loše prevode.*
