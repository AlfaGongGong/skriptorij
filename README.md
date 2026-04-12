# 📚 BOOKLYFI TURBO CHARGED ⚡

**AI-Powered Book Translation & Refinement Engine**

[![Status](https://img.shields.io/badge/Status-TURBO_CHARGED-3b82f6?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Android-10b981?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Python](https://img.shields.io/badge/Python-3.10%2B-f59e0b?style=for-the-badge)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-8b5cf6?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-0ea5e9?style=for-the-badge)](Dockerfile)

**BOOKLYFI TURBO CHARGED** is a massive, multi-model AI system designed to automatically translate, proofread, and format entire books in EPUB and MOBI formats. Instead of relying on a single API that can fail or hit rate limits, BOOKLYFI uses a **Fleet Manager** architecture — swarms of API keys distributed across 8 different AI providers, with automatic failover in milliseconds.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🧠 **V8 Fleet Manager** | 8-engine AI fleet with automatic key rotation and cooldown management |
| 🛡️ **Auto-Heal Firewall** | Detects and destroys AI hallucinations and prompt injection attempts |
| 📖 **Dynamic Glossary** | Analyzes characters, tone, and genre before translation begins |
| 🔄 **Live EPUB Preview** | Each completed chapter updates a live EPUB you can open immediately |
| ⚡ **Smart Checkpoints** | Granular per-block saves — resume exactly where you left off |
| 🔊 **TTS Filter Mode** | Generates `.ttsfilter` output for Moon+ Reader and other TTS apps |
| 🎨 **Modern Web UI** | Real-time dashboard with dark/light themes, glassmorphism design |
| 🌐 **Multi-Provider** | Gemini, Groq, Cerebras, SambaNova, Mistral, Cohere, OpenRouter, GitHub |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **pip** package manager
- At least one API key from a supported provider:
  - [Google Gemini](https://ai.google.dev) — recommended, high quality
  - [Groq](https://console.groq.com) — fast, generous free tier
  - [Cerebras](https://cloud.cerebras.ai) — ultra-fast inference
  - [SambaNova](https://cloud.sambanova.ai) — high throughput
  - [Mistral](https://console.mistral.ai) — multilingual specialist
  - [Cohere](https://dashboard.cohere.com) — strong text generation
  - [OpenRouter](https://openrouter.ai) — access to hundreds of models
  - [GitHub Models](https://github.com/marketplace/models) — free with GitHub account

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij

# 2. (Optional but recommended) Create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux / macOS / Termux
# venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### Configuration

Create `dev_api.json` in the project root with your API keys:

```json
{
    "GEMINI": ["YOUR_GEMINI_KEY_1", "YOUR_GEMINI_KEY_2"],
    "GROQ": ["YOUR_GROQ_KEY"],
    "CEREBRAS": ["YOUR_CEREBRAS_KEY"],
    "SAMBANOVA": ["YOUR_SAMBANOVA_KEY"],
    "MISTRAL": ["YOUR_MISTRAL_KEY"],
    "COHERE": ["YOUR_COHERE_KEY"],
    "OPENROUTER": ["YOUR_OPENROUTER_KEY"],
    "GITHUB": ["YOUR_GITHUB_TOKEN"]
}
```

> ⚠️ **Security:** `dev_api.json` is in `.gitignore` — **never commit real API keys!**
> You only need keys for the providers you plan to use. Even a single key works.

### Run the Application

```bash
python main.py
```

Open your browser at **`http://localhost:8080`**. On Termux (Android), the browser opens automatically.

---

## 📂 Project Structure

```
skriptorij/
├── main.py                      # Entry point — starts Flask server
├── app.py                       # Flask application factory
├── skriptorij.py                # V8 translation engine (chunking, AI calls, checkpoints)
├── api_fleet.py                 # Fleet Manager — key tracking, cooldown, rate limits
├── intro_ui.py                  # Cinematic intro screen (3D page-flip animation)
├── tts.py                       # TTS filter mode for Moon+ Reader
├── export_manager.py            # JSON/TXT translation report generator
├── s.py                         # Proxy and helper utilities
│
├── config/                      # 🔧 Application configuration
│   ├── __init__.py
│   ├── settings.py              # Shared state, env vars, paths
│   └── logging_config.py        # Logging setup
│
├── api/                         # 🌐 Flask Blueprint routes
│   ├── __init__.py              # Blueprint registration
│   ├── middleware/              # Error handlers, CORS, etc.
│   └── routes/
│       ├── books.py             # Book upload, listing, download
│       ├── processing.py        # Start, status, model selection
│       ├── control.py           # Pause, resume, stop, reset
│       ├── fleet.py             # Fleet pool status & key toggle
│       ├── keys.py              # API key CRUD (add/delete)
│       └── export.py            # JSON/TXT report export
│
├── core/                        # ⚙️ Core engine modules
│   ├── engine/                  # Translation pipeline steps
│   ├── fleet/                   # Fleet management logic
│   └── models/                  # Data models
│
├── utils/                       # 🛠️ Utility functions
│   ├── __init__.py
│   └── file_utils.py            # Secure filename, path validation
│
├── static/                      # 🎨 Frontend assets
│   ├── css/
│   │   └── style.css            # Main stylesheet (dark/light themes)
│   ├── js/
│   │   ├── main.js              # App initialization
│   │   ├── app.js               # Core app logic
│   │   ├── api-client.js        # API communication layer
│   │   ├── ui/
│   │   │   ├── fleet.js         # Fleet pool UI rendering
│   │   │   └── notifications.js # Toast notifications
│   │   ├── services/
│   │   │   ├── polling.js       # Real-time status polling
│   │   │   ├── storage.js       # localStorage persistence
│   │   │   └── theme.js         # Dark/light theme toggle
│   │   └── utils/
│   │       ├── constants.js     # App-wide constants
│   │       ├── formatters.js    # Number/time formatters
│   │       └── validators.js    # Input validators
│   ├── img/                     # Images and icons
│   ├── manifest.json            # PWA manifest
│   └── sw.js                    # Service worker (offline support)
│
├── templates/
│   └── index.html               # Main HTML template
│
├── tests/                       # 🧪 Test suite
│   ├── unit/
│   │   └── test_validators.py   # Unit tests for validators
│   └── integration/
│       └── test_api_routes.py   # Integration tests for API routes
│
├── Dockerfile                   # Docker image definition
├── docker-compose.yml           # Docker Compose setup
├── requirements.txt             # Python dependencies
├── proxies.json.example         # Proxy configuration template
├── dev_api.json                 # ⚠️ Your API keys (in .gitignore — never commit!)
└── .gitignore                   # Git ignore rules
```

### Architecture Overview

BOOKLYFI uses a **modular monolith** architecture — a single deployable unit split into clear, independent modules:

```
Browser ──► Flask (app.py)
              │
              ├─► api/routes/      (HTTP layer — Blueprints)
              ├─► config/          (Shared state & settings)
              ├─► core/            (Business logic)
              └─► utils/           (Shared utilities)
                      │
              skriptorij.py ──► api_fleet.py
              (Translation          (Key rotation
               pipeline)             & health)
```

---

## ⚙️ Configuration

### API Keys (`dev_api.json`)

> ⚠️ **NEVER commit this file!** It is already in `.gitignore`.

```json
{
    "GEMINI": ["key1", "key2"],
    "GROQ": ["key1", "key2", "key3"],
    "CEREBRAS": ["key1"],
    "SAMBANOVA": ["key1", "key2"],
    "MISTRAL": ["key1"],
    "COHERE": ["key1"],
    "OPENROUTER": ["key1"],
    "GITHUB": ["token1"]
}
```

- **Multiple keys per provider** — the Fleet Manager rotates them automatically
- Keys can be added/removed live from the **API Keys** panel in the UI without restarting
- The special key `V8_TURBO` activates all providers simultaneously in a round-robin rotation

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SKRIPTORIJ_PORT` | `8080` | Port the Flask server listens on |
| `SKRIPTORIJ_CONFIG` | `dev_api.json` | Path to API keys config file |
| `PYTHONUNBUFFERED` | `1` | Ensures real-time log output in Docker |

### Proxy Configuration (`proxies.json`)

If you need to route requests through a proxy, copy the example and fill in your credentials:

```bash
cp proxies.json.example proxies.json
# Edit proxies.json with your proxy settings
```

> `proxies.json` is in `.gitignore` to protect credentials.

---

## 📖 Usage Guide

### Step 1 — Upload a Book

1. On the **Setup** screen, click **📁 Upload EPUB/MOBI** or drag and drop your file
2. The book appears in the book selector dropdown
3. Previously used books are remembered automatically

### Step 2 — Configure Processing

1. **Select Model:**
   - `V8_TURBO` — Uses all available providers in parallel (recommended)
   - Individual provider names for single-engine mode
2. **Select Mode:**
   - `PREVOD` — Full AI translation with glossary and tone analysis
   - `TTS` — TTS filter mode for Moon+ Reader

### Step 3 — Start the Engine

1. Click **🚀 Pokreni Sistem**
2. Watch the **Dashboard** for real-time progress:
   - Progress bar with percentage
   - ETA (estimated time remaining)
   - Active engine indicator
   - Chunks processed counter

### Step 4 — Monitor Fleet Health

The **🛡️ Fleet Pool** panel shows every API key's live status:

| Indicator | Meaning |
|-----------|---------|
| 🟢 ACTIVE | Key is available and processing requests |
| 🟡 COOLING | Key hit rate limit — automatic cooldown in progress |
| 🔴 ERROR | Key returned an error — check validity |
| ⚫ DISABLED | Key manually disabled via toggle |

### Step 5 — Export Results

When processing completes:
- **Download EPUB/MOBI** — the translated book file
- **Export JSON Report** — detailed statistics (chunks, timing, errors)
- **Export TXT Report** — human-readable translation log

### Controlling Processing

| Button | Action |
|--------|--------|
| ⏸️ Pause | Suspends processing after the current chunk |
| ▶️ Resume | Continues from where it was paused |
| ⏹️ Stop | Gracefully stops processing |
| 🔄 Reset | Returns to Setup screen (keeps checkpoints) |

---

## 🌐 API Endpoints

### Books

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/books` | List all available EPUB/MOBI books |
| `POST` | `/api/upload_book` | Upload a new EPUB/MOBI file |
| `GET` | `/api/download/<filename>` | Download a processed result file |

### Processing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Get full processing status + ETA |
| `GET` | `/api/dev_models` | List available AI models/providers |
| `POST` | `/api/start` | Start processing (`{"book": "name.epub", "model": "V8_TURBO", "mode": "PREVOD"}`) |

### Processing Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/control/pause` | Pause processing |
| `POST` | `/control/resume` | Resume paused processing |
| `POST` | `/control/stop` | Stop processing completely |
| `POST` | `/control/reset` | Reset to initial state |

### Fleet Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/fleet` | Get fleet health summary (all providers + keys) |
| `POST` | `/api/fleet/toggle` | Toggle a key on/off (`{"provider": "GROQ", "key": "...abc123"}`) |

### API Key Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/keys` | List all providers and masked keys (`...abc123`) |
| `POST` | `/api/keys/<provider>` | Add a key (`{"key": "your-api-key"}`) |
| `DELETE` | `/api/keys/<provider>/<index>` | Delete key at index |

### Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/export/json` | Download JSON translation report |
| `GET` | `/api/export/txt` | Download TXT translation report |

---

## 🧪 Development

### Running Tests

```bash
# Run the full test suite
python3 -m pytest tests/ -v

# Run only unit tests
python3 -m pytest tests/unit/ -v

# Run only integration tests
python3 -m pytest tests/integration/ -v

# Run with coverage report
python3 -m pytest tests/ -v --tb=short
```

### Code Style

The project follows standard Python conventions:

```bash
# Check syntax
python3 -m py_compile main.py app.py skriptorij.py

# Format with black (if installed)
black .

# Lint with flake8 (if installed)
flake8 . --max-line-length=100
```

### Local Development Server

```bash
# Development mode with auto-reload (Flask debug)
FLASK_ENV=development python main.py

# Or set port explicitly
SKRIPTORIJ_PORT=9000 python main.py
```

### Project Dependencies

```
flask==3.1.3          # Web framework
httpx==0.27.0         # Async HTTP client for API calls
beautifulsoup4==4.12.3 # HTML/XML parsing for EPUB
lxml==5.1.0           # Fast XML/HTML parser
requests==2.33.0      # HTTP library
tiktoken==0.6.0       # Token counting for AI models
```

---

## 🚢 Deployment

### Linux — systemd Service

Create `/etc/systemd/system/booklyfi.service`:

```ini
[Unit]
Description=BOOKLYFI TURBO CHARGED — AI Book Translation Engine
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
# Install and start the service
sudo useradd -r -s /bin/false booklyfi
sudo cp -r . /opt/booklyfi
sudo chown -R booklyfi:booklyfi /opt/booklyfi
sudo systemctl daemon-reload
sudo systemctl enable booklyfi
sudo systemctl start booklyfi

# Check status
sudo systemctl status booklyfi
sudo journalctl -u booklyfi -f
```

### Docker (Recommended)

```bash
# Build and start with Docker Compose
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The included `docker-compose.yml` mounts:
- `./data/` — persistent book storage and checkpoints
- `./dev_api.json` — API keys (read-only mount)
- `./proxies.json` — proxy config (read-only mount)

```bash
# Build only (no compose)
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
# Install Termux from F-Droid (not Play Store)
pkg update && pkg install python git
git clone https://github.com/AlfaGongGong/skriptorij.git
cd skriptorij
pip install -r requirements.txt
python main.py
# Browser opens automatically at http://localhost:8080
```

### Android App (Future Roadmap)

A native Android `.apk` / `.aab` build is planned. The current web UI is fully responsive and works well as a PWA (Progressive Web App) — add to home screen from your mobile browser for an app-like experience.

### Linux Desktop Package (`.deb`)

A Debian package for easy installation on Ubuntu/Debian systems is on the roadmap. The `systemd` setup above provides equivalent functionality in the meantime.

---

## 🔧 Troubleshooting

### "No API keys configured" / All engines unavailable

```bash
# Verify the file exists and has valid JSON
python3 -m json.tool dev_api.json

# Check the file is in the correct location
ls -la dev_api.json
```

- Ensure `dev_api.json` is in the project root directory
- Keys must be non-empty strings in an array format
- You need at least one valid key from any supported provider

### Rate Limit Hit (429 Too Many Requests)

- **This is normal** — the Fleet Manager handles it automatically
- The key enters cooldown and the next available key takes over
- Add more keys per provider to increase throughput
- Check the **Fleet Pool** panel to see cooldown timers

### Translation Quality Issues

- Use `V8_TURBO` mode (all providers in parallel) for best quality
- The Dynamic Glossary analyzes the first ~2000 tokens before starting
- Lektor AI (step 3 in the pipeline) refines literary style
- For genre-specific books, Mistral often performs better

### Scrolling / UI Not Responding

```bash
# Hard-refresh the browser
Ctrl + Shift + R   # Chrome/Firefox
Cmd + Shift + R    # macOS
```

- Open browser DevTools (F12) → Console tab for JavaScript errors
- Clear browser cache and reload
- Try a different browser (Chrome/Brave recommended)

### Checkpoint / Resume Issues

```bash
# Checkpoints are stored in data/_skr_<BookName>/
ls data/

# To restart a book from scratch, delete its checkpoint folder:
rm -rf data/_skr_YourBookName/
```

- The system automatically resumes from the last saved checkpoint on restart
- If a checkpoint is corrupted, the auto-heal system attempts recovery

### Docker: Container Won't Start

```bash
# Check logs
docker compose logs booklyfi

# Common cause: dev_api.json missing
ls dev_api.json  # Must exist before running docker compose up
```

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Commit** your changes: `git commit -m 'feat: add amazing feature'`
4. **Push** to the branch: `git push origin feature/amazing-feature`
5. **Open** a Pull Request

### Commit Message Convention

```
feat:     New feature
fix:      Bug fix
docs:     Documentation changes
refactor: Code restructuring (no feature change)
test:     Adding or updating tests
chore:    Maintenance (deps, CI, etc.)
```

---

## 📋 Roadmap

- [x] Core V8 translation pipeline (5-step: translate → validate → proofread → correct → typograph)
- [x] Multi-provider Fleet Manager with automatic key rotation
- [x] Real-time web dashboard with dark/light themes
- [x] Modular architecture (api/, core/, config/, utils/)
- [x] Docker + systemd deployment
- [x] Smart checkpoints (granular per-block resume)
- [x] PWA support (manifest + service worker)
- [ ] Native Android app (`.apk`)
- [ ] Debian package (`.deb`) for Linux desktop
- [ ] Cloud synchronization of books and checkpoints
- [ ] Advanced quality metrics and translation scoring
- [ ] Web-based EPUB editor for post-translation review

---

## 🔐 Security Notes

- `dev_api.json` and `proxies.json` are in `.gitignore` — **never** commit these files
- API keys are masked in the UI (only last 6 characters shown: `...abc123`)
- All file paths are sanitized against directory traversal attacks
- The app runs locally — no data is sent to external servers except your AI API calls

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

## 💬 Support

- 🐛 **Bug Reports:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
- 💡 **Feature Requests:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
- 👤 **Author:** [AlfaGongGong](https://github.com/AlfaGongGong)

---

*Made with ❤️ for readers who refuse to wait for official translations.*  
*BOOKLYFI TURBO CHARGED — because good books shouldn't have language barriers.*
