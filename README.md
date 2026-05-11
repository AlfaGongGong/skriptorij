# 📚 BOOKLYFI ⚡ TURBO V10

**AI-Powered Book Translation & Refinement Engine**

[![Version](https://img.shields.io/badge/Version-TURBO_V10-3b82f6?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Android-10b981?style=for-the-badge)](https://github.com/AlfaGongGong/skriptorij)
[![Python](https://img.shields.io/badge/Python-3.10%2B-f59e0b?style=for-the-badge)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-8b5cf6?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-0ea5e9?style=for-the-badge)](Dockerfile)

**BOOKLYFI TURBO V10** is a full-featured, multi-model AI engine that automatically translates, proofreads, and formats entire books in EPUB/MOBI format. Rather than relying on a single API that can fail or hit rate limits, BOOKLYFI runs a **Fleet Manager** — a pool of API keys spread across **14 AI providers**, with per-key semaphore locking, automatic cooldown rotation, provider-level Retry-After backoff, and adaptive pacing derived from observed RPM/TPM limits.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🧠 **Fleet Manager V10** | 14 AI providers in a single fleet — automatic key rotation, per-key semaphore, smart cooldown |
| ⏱️ **Adaptive provider pacing** | Runtime throttling for all providers from observed rate-limit headers + token usage (RPM/TPM aware) |
| 🧩 **Model-aware tuning** | Per-model/per-family generation tuning by role (translator/proofreader/validator/editor) with safe fallback |
| 🔍 **Live key ping** | Click the 🔍 button next to any key to instantly check its actual health status |
| 🔄 **3-pass AI pipeline** | TRANSLATOR → PROOFREADER → EDITOR — three independent AI passes per text block |
| 🎯 **Composite quality scorer** | Heuristic + AI scoring (25/75 weights), thresholds: 🌟 ≥8.5 · ✅ ≥6.5 · ⚠ ≥4.0 · 🔴 <4.0 |
    | 🛡️ **Auto-Heal Firewall** | Detects and eliminates AI hallucinations and prompt injection attempts in real time |
    | 📖 **Dynamic glossary** | Analyzes characters, tone, and genre before translation begins |
    | 🔄 **RETRO re-proofreading** | Reprocesses only blocks below a specified quality threshold — no full restart required |
    | 📊 **Quality Review panel** | Flags low-quality blocks, submits them for repair in one click, tracks progress live |
    | ⚡ **Smart checkpoints** | Granular per-block state persistence — resume exactly where processing stopped |
    | 🔊 **TTS Filter mode** | Generates `.ttsfilter` output for Moon+ Reader and other TTS applications |
    | 🌗 **Dark / Light theme** | Glassmorphism design, live switching without page reload |
    | 📱 **PWA support** | Add to mobile home screen, works offline via service worker |

    ---

    ## 🚀 Quick Start

    ### Prerequisites

    - **Python 3.10+**
    - **pip** package manager
    - At least one API key from one of the supported providers:

    | Provider | Link | Notes |
    |----------|------|-------|
    | 🔷 Google Gemini | [ai.google.dev](https://ai.google.dev) | Recommended — high quality, 1500 RPD free |
    | ⚡ Groq | [console.groq.com](https://console.groq.com) | Ultra-fast, 14,400 RPD free |
    | 🔬 Cerebras | [cloud.cerebras.ai](https://cloud.cerebras.ai) | Fastest inference, 14,400 RPD |
    | 🧠 SambaNova | [cloud.sambanova.ai](https://cloud.sambanova.ai) | High throughput, DeepSeek models |
    | 💫 Mistral | [console.mistral.ai](https://console.mistral.ai) | Multilingual specialist |
    | 🌐 Cohere | [dashboard.cohere.com](https://dashboard.cohere.com) | Strong for proofreading |
    | 🔀 OpenRouter | [openrouter.ai](https://openrouter.ai) | Access to hundreds of models |
    | 🐙 GitHub Models | [github.com/marketplace/models](https://github.com/marketplace/models) | Free with a GitHub account |
    | 🤝 Together AI | [api.together.xyz](https://api.together.xyz) | Llama and other open-source models |
    | 🎆 Fireworks AI | [fireworks.ai](https://fireworks.ai) | Fast inference for open-source models |
    | 🪣 Chutes AI | [chutes.ai](https://chutes.ai) | Free LLM endpoint |
    | 🤗 HuggingFace | [huggingface.co](https://huggingface.co) | Inference API / serverless |
    | 🔗 Kluster AI | [kluster.ai](https://kluster.ai) | OpenAI-compatible endpoint |
    | 🔷 Gemma (Together) | — | Google Gemma models via Together |

    ### Installation

    ```bash
    # 1. Clone the repository
    git clone https://github.com/AlfaGongGong/skriptorij.git
    cd skriptorij

    # 2. (Recommended) Create a virtual environment
    python3 -m venv venv
    source venv/bin/activate        # Linux / macOS / Termux
    # venv\Scripts\activate         # Windows

    # 3. Install dependencies
    pip install -r requirements.txt
    ```

    ### Configuration

    Create `dev_api.json` in the project root directory with your API keys:

    ```json
    {
    "GEMINI":      ["YOUR_GEMINI_KEY_1", "YOUR_GEMINI_KEY_2"],
    "GROQ":        ["YOUR_GROQ_KEY"],
    "CEREBRAS":    ["YOUR_CEREBRAS_KEY"],
    "SAMBANOVA":   ["YOUR_SAMBANOVA_KEY"],
    "MISTRAL":     ["YOUR_MISTRAL_KEY"],
    "COHERE":      ["YOUR_COHERE_KEY"],
    "OPENROUTER":  ["YOUR_OPENROUTER_KEY"],
    "GITHUB":      ["YOUR_GITHUB_TOKEN"],
    "TOGETHER":    ["YOUR_TOGETHER_KEY"],
    "FIREWORKS":   ["YOUR_FIREWORKS_KEY"],
    "CHUTES":      ["YOUR_CHUTES_KEY"],
    "HUGGINGFACE": ["YOUR_HF_TOKEN"],
    "KLUSTER":     ["YOUR_KLUSTER_KEY"]
    }
    ```

    > ⚠️ **Security:** `dev_api.json` is listed in `.gitignore` — **never commit real keys!**
    > Only one key from one provider is required for the application to run.

    ### Running

    ```bash
    python main.py
    ```

    Open your browser at **`http://localhost:8080`**. On Termux (Android), the browser opens automatically.

    ---

    ## 📂 Project Structure

    ```
    skriptorij/
    ├── main.py                      # Entry point — starts the Flask server
    ├── app.py                       # Flask application factory
    ├── run.py                       # Alternative launcher (for Termux and desktop)
    ├── api_fleet.py                 # Fleet Manager — key tracking, cooldown, RPM/RPD limits
    ├── tts.py                       # TTS filter mode for Moon+ Reader
    │
    ├── config/                      # 🔧 Application configuration
    │   ├── settings.py              # Shared state, env variables, paths
    │   └── logging_config.py        # Logging configuration
    │
    ├── api/                         # 🌐 Flask Blueprint routes
    │   ├── __init__.py              # Blueprint registration
    │   ├── middleware/              # Error handlers, CORS
    │   └── routes/
    │       ├── books.py             # Upload, listing, downloading books
    │       ├── processing.py        # Start, status, model selection
    │       ├── control.py           # Pause, resume, stop, reset
    │       ├── fleet.py             # Fleet status & key toggle
    │       ├── keys.py              # Key CRUD + ping (health check)
    │       ├── qualities.py         # Quality score review and update
    │       ├── quality.py           # Scoring API routes
    │       └── export.py            # JSON/TXT report export
    │
    ├── core/                        # ⚙️ Engine core
    │   ├── engine.py                # SkriptorijAllInOne — processing orchestration
    │   ├── quality.py               # Composite quality scorer (heuristic + AI)
    │   ├── text_utils.py            # Text cleanup, English detection, typography
    │   └── prompt_injector.py       # Dynamic glossary injection into prompts
    │
    ├── processing/                  # 🔄 Pipeline modules
    │   ├── pipeline.py              # 3-pass pipeline: TRANSLATOR → PROOFREADER → EDITOR
    │   ├── workers.py               # Async chunk workers (V1)
    │   ├── workers_v2.py            # Async chunk workers (V2, active)
    │   ├── parallel.py              # Parallel chapter processing
    │   ├── retro.py                 # RETRO re-proofreading of low-quality blocks
    │   └── rescue.py                # Recovery from raw AI responses
    │
    ├── network/                     # 🌍 Network layer
    │   ├── http_client.py           # HTTP POST with per-key semaphore and 429 handling
    │   ├── rate_limiter.py          # Per-key semaphore + provider backoff + adaptive runtime pacing
    │   ├── provider_urls.py         # URL map for all 14 providers
    │   ├── provider_router.py       # Routing by role (TRANSLATOR, PROOFREADER, etc.)
    │   └── urls.py                  # Legacy URL helpers
    │
    ├── analysis/                    # 📊 Book analysis
    │   └── book_context.py          # Dynamic glossary — character, tone, and genre analysis
    │
    ├── epub/                        # 📚 EPUB processing
    │   └── parser.py                # EPUB parsing, cleanup, and reconstruction
    │
    ├── utils/                       # 🛠️ Utility functions
    │   └── file_utils.py            # Safe filenames, path validation
    │
    ├── static/                      # 🎨 Frontend assets
    │   ├── css/
    │   │   └── style.css            # Main stylesheet (dark/light theme)
    │   ├── js/
    │   │   ├── main.js              # Application initialization
    │   │   ├── api-client.js        # HTTP client for all API calls
    │   │   ├── ui/
    │   │   │   ├── fleet.js         # Fleet pool display
    │   │   │   └── notifications.js # Toast notifications
    │   │   ├── services/
    │   │   │   ├── polling.js       # Real-time status polling
    │   │   │   ├── storage.js       # localStorage persistence
    │   │   │   └── theme.js         # Dark/light theme
    │   │   └── intro/               # 3D intro animation (Three.js)
    │   ├── manifest.json            # PWA manifest
    │   └── sw.js                    # Service worker (offline support)
    │
    ├── templates/
    │   ├── index.html               # Main UI (dashboard)
    │   └── intro.html               # Cinematic intro screen
    │
    ├── tests/                       # 🧪 Test suite
    │   ├── unit/
    │   │   └── test_validators.py   # Unit tests for validators
    │   └── integration/
    │       └── test_api_routes.py   # Integration tests for API routes
    │
    ├── Dockerfile                   # Docker image definition
    ├── docker-compose.yml           # Docker Compose configuration
    ├── requirements.txt             # Python dependencies
    ├── dev_api.json                 # ⚠️ Your API keys (in .gitignore — never commit!)
    └── .gitignore                   # Git ignore rules
    ```

    ### Architecture

    BOOKLYFI uses a **modular monolith** — a single deployable unit divided into clear, independent modules:

    ```
    Browser ──► Flask (app.py)
    │
    ├─► api/routes/       (HTTP layer — Flask Blueprints)
    ├─► config/settings   (Shared state and paths)
    ├─► core/             (Business logic)
    ├─► processing/       (Pipeline and workers)
    └─► network/          (HTTP client, adaptive rate limiter)
    │
    api_fleet.py ◄─── FleetManager singleton
    (Key rotation,         (register_active_fleet /
    cooldown, semaphore)   get_active_fleet)
    ```

    ---

    ## ⚙️ Configuration

    ### API Keys (`dev_api.json`)

    > ⚠️ **NEVER commit this file!** It is already listed in `.gitignore`.

    ```json
    {
    "GEMINI":      ["key1", "key2"],
    "GROQ":        ["key1", "key2", "key3"],
    "CEREBRAS":    ["key1"],
    "SAMBANOVA":   ["key1", "key2"],
    "MISTRAL":     ["key1"],
    "COHERE":      ["key1"],
    "OPENROUTER":  ["key1"],
    "GITHUB":      ["token1"],
    "TOGETHER":    ["key1"],
    "FIREWORKS":   ["key1"],
    "CHUTES":      ["key1"],
    "HUGGINGFACE": ["token1"],
    "KLUSTER":     ["key1"]
    }
    ```

    - **Multiple keys per provider** — Fleet Manager rotates them automatically
    - Keys can be added or removed **without a restart** via the API Keys panel in the UI
    - Click **🔍** next to a key to immediately verify whether it is valid (live ping)

    ### Environment Variables

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `SKRIPTORIJ_PORT` | `8080` | Flask server port |
    | `SKRIPTORIJ_CONFIG` | `dev_api.json` | Path to the key configuration file |
    | `PYTHONUNBUFFERED` | `1` | Real-time log output in Docker |
    | `BOOKLYFI_V2` | `1` | Enables workers_v2 (recommended) |

    ### Proxy Configuration (`proxies.json`)

    To route requests through a proxy:

    ```bash
    cp proxies.json.example proxies.json
    # Edit proxies.json with your proxy settings
    ```

    > `proxies.json` is listed in `.gitignore` to protect credentials.

    ---

    ## 📖 Usage Guide

    ### Step 1 — Upload a Book

    1. On the **Setup** screen, click **📁 Upload EPUB/MOBI** or drag and drop a file
    2. The book appears in the selection dropdown
    3. Previously used books are remembered automatically

    ### Step 2 — Select a Model

    - **AUTO** (recommended) — the engine auto-detects TRANSLATION or PROOFREADING mode
    - **GROQ / CEREBRAS / GEMINI** etc. — force a specific provider
    - **RETRO** — re-proofread only blocks below the specified quality threshold
    - **TTS** — filter mode for Moon+ Reader

    ### Step 3 — Start Processing

    1. Click **🚀 Start System**
    2. Monitor the **Dashboard** for real-time progress:
    - Progress bar with percentage
    - ETA (estimated time remaining)
    - Active engine indicator
    - Processed block counter

    ### Step 4 — Monitor Fleet Health

    The **🛡️ Fleet** panel shows the live status of each API key:

    | Indicator | Meaning |
    |-----------|---------|
    | 🟢 ACTIVE | Key is available and processing requests |
    | 🟡 COOLING DOWN | Key hit a rate limit — automatic cooldown in progress |
    | 🔴 ERROR | Key returned an error — verify its validity |
    | ⚫ DISABLED | Key manually disabled via toggle |

    > **New:** Click the **🔍** button next to a key in the **Expert** tab to immediately check the key's actual status via a direct API call.

    ### Step 5 — Quality Review

    The **🎯 Quality** panel displays the score for each translated block:

    | Label | Score | Action |
    |-------|-------|--------|
    | 🌟 Excellent | ≥ 8.5 | No action needed |
    | ✅ Good | 6.5 – 8.5 | Optional review |
    | ⚠ Needs retro | 4.0 – 6.5 | Click to flag |
    | 🔴 Critical | < 4.0 | Immediate re-proofreading |

    Click **🔧 Re-proofread flagged** to submit low-quality blocks to the RETRO pass.

    ### Step 6 — Export

    When processing completes:
    - **Download EPUB/MOBI** — the translated book
    - **Export JSON report** — detailed statistics (blocks, timing, errors)
    - **Export TXT report** — human-readable translation log

    ### Processing Controls

    | Button | Action |
    |--------|--------|
    | ⏸️ Pause | Suspends processing after the current block |
    | ▶️ Resume | Continues from the paused state |
    | ⏹️ Stop | Gracefully halts processing |
    | 🔄 Reset | Returns to the Setup screen (checkpoints are retained) |

    ---

    ## 🌐 API Endpoints

    ### Books

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/files` | List all available EPUB/MOBI books |
    | `POST` | `/api/upload_book` | Upload a new book |
    | `GET` | `/api/download` | Download the output file |
    | `GET` | `/api/epub_preview` | Live EPUB preview (chapter by chapter) |
    | `GET` | `/api/epub_text/<book>` | Raw EPUB text (for inspection) |

    ### Processing

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/status` | Full processing status + ETA |
    | `GET` | `/api/dev_models` | List of available AI models/providers |
    | `POST` | `/api/start` | Start processing (`{"book": "...", "model": "GROQ", "tool": "AUTO"}`) |

    ### Processing Control

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `POST` | `/control/pause` | Pause processing |
    | `POST` | `/control/resume` | Resume from pause |
    | `POST` | `/control/stop` | Stop processing |
    | `POST` | `/control/reset` | Reset to initial state |

    ### Fleet Management

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/fleet` | All providers and key statuses |
    | `POST` | `/api/fleet/toggle` | Toggle a key on/off (`{"provider": "GROQ", "key": "...abc"}`) |

    ### API Keys

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/keys` | List all providers and masked keys |
    | `POST` | `/api/keys/<provider>` | Add a key (`{"key": "your-api-key"}`) |
    | `DELETE` | `/api/keys/<provider>/<idx>` | Delete a key by index |
    | `POST` | `/api/keys/<provider>/<idx>/ping` | **Live health check** for a key — returns `{ok, latency_ms, status_code}` |

    ### Quality Scores

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/quality_scores` | All quality scores for the current book |
    | `PATCH` | `/api/quality_scores/<stem>` | Update a block's score |
    | `DELETE` | `/api/quality_scores/<stem>` | Delete a block's score |
    | `POST` | `/api/quality_scores/send_to_fix` | Submit a block for RETRO repair |
    | `POST` | `/api/fix/bad_blocks` | Reprocess blocks below the quality threshold |
    | `POST` | `/api/fix/marked_blocks` | Reprocess manually flagged blocks |

    ### Export

    | Method | Endpoint | Description |
    |--------|----------|-------------|
    | `GET` | `/api/export/json` | Download the JSON translation report |
    | `GET` | `/api/export/txt` | Download the TXT translation report |

    ---

    ## 🧪 Development

    ### Running Tests

    ```bash
    # Full test suite (39 tests)
    python3 -m pytest tests/ -v

    # Unit tests only
    python3 -m pytest tests/unit/ -v

    # Integration tests only
    python3 -m pytest tests/integration/ -v

    # Short output (errors only)
    python3 -m pytest tests/ -v --tb = short
    ```

    ### Syntax Check

    ```bash
    python3 -m py_compile main.py app.py api_fleet.py
    python3 -m py_compile api/routes/keys.py network/http_client.py
    ```

    ### Local Dev Server

    ```bash
    # Explicit port
    SKRIPTORIJ_PORT = 9000 python main.py

    # Disable workers_v2 (legacy mode)
    BOOKLYFI_V2 = 0 python main.py
    ```

    ---

    ## 🚢 Deployment

    ### Linux — systemd Service

    Create `/etc/systemd/system/booklyfi.service`:

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

    ### Docker (Recommended)

    ```bash
    # Build and start
    docker compose up -d

    # View logs
    docker compose logs -f

    # Stop
    docker compose down
    ```

    `docker-compose.yml` mounts:
    - `./data/` — persistent checkpoints and books
    - `./dev_api.json` — API keys (read-only)
    - `./proxies.json` — proxy configuration (read-only)

    ```bash
    # Manual build
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
    # Install Termux from F-Droid (not the Play Store!)
    pkg update && pkg install python git
    git clone https://github.com/AlfaGongGong/skriptorij.git
    cd skriptorij
    pip install -r requirements.txt
    python main.py
    # Browser opens automatically at http://localhost:8080
    ```

    > Or add to the home screen as a **PWA** — the web app runs like a native application.

    ---

    ## 🔧 Troubleshooting

    ### "No API keys" / All providers unavailable

    ```bash
    # Verify valid JSON
    python3 -m json.tool dev_api.json

    # Check the location
    ls -la dev_api.json  # must be in the project root directory
    ```

    - A single key from one provider is sufficient for the application to run
    - Keys can be added directly from the UI via the **API Keys** panel — active immediately
    - Click **🔍** next to a key to verify it is valid

    ### Rate Limit (429 Too Many Requests)

    - **This is expected** — Fleet Manager automatically switches to the next key
    - V10 no longer retries the same exhausted key (recursive retry eliminated)
    - `Retry-After` is used as provider-level backoff to prevent synchronized key bursts
    - Runtime pacing is updated from observed provider limits (RPM/TPM headers + usage tokens)
    - Add more keys per provider to increase throughput
    - Monitor cooldown timers in the **Fleet** panel

    ### Translation Quality Issues

    - Use AUTO mode — the engine decides between TRANSLATION and PROOFREADING automatically
    - The dynamic glossary analyzes the first ~2,000 tokens of the book
    - After translation, use **RETRO** to re-proofread low-quality blocks
    - Gemini and Mistral generally deliver the best literary quality

    ### UI Not Responding

    ```
    Ctrl + Shift + R   # Hard refresh (Chrome/Firefox)
    Cmd + Shift + R    # macOS
    ```

    - F12 → Console tab for JavaScript errors
    - Chrome/Brave are the recommended browsers

    ### Checkpoint Issues

    ```bash
    # Checkpoints are stored in data/_skr_<BookTitle>/
    ls data/

    # Restart from scratch (delete checkpoints)
    rm -rf data/_skr_BookTitle/
    ```

    ---

    ## 🤝 Contributing

    Contributions are welcome!

    1. **Fork** the repository
    2. **Create** a branch: `git checkout -b feature/new-feature`
    3. **Commit** your changes: `git commit -m 'feat: add new feature'`
    4. **Push**: `git push origin feature/new-feature`
    5. **Open** a Pull Request

    ### Commit Message Convention

    ```
    feat:     New feature
    fix:      Bug fix
    docs:     Documentation changes
    refactor: Code refactoring (no functional changes)
    test:     Adding or updating tests
    chore:    Maintenance (dependencies, CI, etc.)
    ```

    ---

    ## 📋 Roadmap

    - [x] 3-pass AI pipeline (TRANSLATOR → PROOFREADER → EDITOR)
- [x] Fleet Manager with 14 providers and automatic key rotation
- [x] Per-key asyncio semaphore (MAX_CONCURRENT=1 per key)
- [x] Provider-level Retry-After backoff (anti-burst protection across keys)
- [x] Adaptive provider pacing from observed runtime limits (RPM/TPM aware)
- [x] Model-aware generation tuning by role with fallback heuristics
- [x] Live ping/health check for each API key
    - [x] Composite quality scorer (heuristic + AI, 25/75 weights)
    - [x] RETRO re-proofreading for blocks below the quality threshold
    - [x] Real-time web dashboard (dark/light theme)
    - [x] Modular monolith (api/, core/, processing/, network/, config/)
    - [x] Docker + systemd deployment
    - [x] Smart checkpoints (granular per-block persistence)
    - [x] PWA support (manifest + service worker)
    - [x] Collapsible Fleet panel in the Expert tab
    - [ ] Native Android application (`.apk`)
    - [ ] Debian package (`.deb`) for Linux desktop
    - [ ] Cloud synchronization of books and checkpoints
    - [ ] Web-based EPUB editor for post-translation review

    ---

    ## 🔐 Security Notes

    - `dev_api.json` and `proxies.json` are in `.gitignore` — **never commit these files**
    - API keys are masked in the UI (only the last 6 characters are shown: `...abc123`)
    - All file paths are sanitized against directory traversal attacks
    - The application runs locally — data is sent only to the AI providers you use

    ---

    ## 📄 License

    MIT License — see the [LICENSE](LICENSE) file for details.

    ---

    ## 💬 Contact & Support

    - 🐛 **Bug reports:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
    - 💡 **Feature requests:** [GitHub Issues](https://github.com/AlfaGongGong/skriptorij/issues)
    - 👤 **Author:** [AlfaGongGong](https://github.com/AlfaGongGong)

    ---

    *Built with ❤️ for readers who don't wait for official translations.*
    *BOOKLYFI TURBO V10 — because great books shouldn't have language barriers.*
