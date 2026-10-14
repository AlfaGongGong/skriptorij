# config/ai_config.py

"""Central AI configuration shared across routing, quota, and model layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

# RPD limiti (free tier, maj 2026):
#   gemini-3.5-flash:      10 RPM / 20 RPD  — primarni, stabilan
#   gemini-3.1-flash-lite: 15 RPM / 500 RPD — visok RPD fallback
#   gemini-2.5-flash-lite: 15 RPM / 20 RPD
#   gemini-2.5-flash:      10 RPM / 20 RPD
GOOGLE_MODEL_POOL = [
    # Primarni: gemini-3.5-flash-lite — najnoviji free-tier model
    # Test 2026-10-10: daje najbolji književni prijevod (aorist, bolji red riječi)
    # 15 RPM / 500 RPD po ključu × 12 ključeva = 180 RPM / 6000 RPD
    {"model": "gemini-3.5-flash-lite", "rpm": 15, "rpd": 500},
    # Fallback: gemini-3.1-flash-lite — stabilan, isti limiti
    {"model": "gemini-3.1-flash-lite", "rpm": 15, "rpd": 500},
]

GEMMA_MODEL_POOL = [
    {"model": "gemma-4-26b-a4b-it", "rpm": 15, "rpd": 1500},
    {"model": "gemma-4-31b-it", "rpm": 15, "rpd": 1500},
]

# GEMMA je nositelj (#1) za sve Google uloge — 1500 RPD/ključ.
# GEMINI je fallback (#2).
PROVIDER_PRIORITY = {
    "PREVODILAC":       ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "MISTRAL", "CLOUDFLARE", "NVIDIA"],
    "LEKTOR":           ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "MISTRAL", "CLOUDFLARE", "NVIDIA"],
    "KOREKTOR":         ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "MISTRAL", "CLOUDFLARE", "NVIDIA"],
    "VALIDATOR":        ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "MISTRAL", "CLOUDFLARE", "NVIDIA"],
    "GUARDIAN":         ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "CLOUDFLARE", "NVIDIA"],
    "POLISH":           ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "MISTRAL", "CLOUDFLARE", "NVIDIA"],
    "ANALIZA":          ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "CLOUDFLARE", "NVIDIA"],
    "CHAPTER_SUMMARY":  ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "CLOUDFLARE"],
    "GLOSAR_UPDATE":    ["GEMINI", "GROQ", "GEMMA", "OPENROUTER", "CLOUDFLARE"],
    "SCORER":           ["GEMINI", "GROQ", "GEMMA", "CLOUDFLARE", "OPENROUTER"],
}

AI_MODEL_STRINGS = {
    "gemini_25_flash": "gemini-3.5-flash-lite",
    # Backward-compatible alias: the old gemini_20_flash profile now targets
    # the stable replacement model after gemini-2.0-flash deprecation.
    "gemini_20_flash": "gemini-3.5-flash-lite",
    "gemini_3_flash": "gemini-3.5-flash-lite",    # gemini-3.0-flash ne postoji; koristi 3.5-flash
    "gemini_31_flash_lite": "gemini-3.1-flash-lite",
    "gemini_25_flash_lite": "gemini-2.5-flash-lite",
    "gemma4_26b": "gemma-4-26b-a4b-it",
    "gemma4_31b": "gemma-4-31b-it",
    "gemma3_27b": "gemma-3-27b-it",
    "llama33_70b_groq": "openai/gpt-oss-120b",
    "llama31_70b_cerebras": "llama-3.1-70b",
    "mistral_large": "mistral-large-latest",
    "mistral_nemo": "open-mistral-nemo",
    "command_r_plus_cohere": "command-r-plus",
    "llama_sambanova": "Meta-Llama-3.1-70B-Instruct",
    "deepseek_openrouter": "deepseek/deepseek-v4-flash:free",
    "qwen_chutes": "Qwen/Qwen2.5-72B-Instruct",
}

MODEL_MAP = {
    "CEREBRAS": "llama-4-scout-17b-16e-instruct",
    "SAMBANOVA": "Meta-Llama-3.3-70B-Instruct",
    "MISTRAL": "mistral-small-latest",
    "TOGETHER": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "GROQ": "qwen/qwen3.8-27b",
    "GEMINI": GOOGLE_MODEL_POOL[0]["model"],
    "OPENROUTER": "thinkingmachines/inkling:free",
    "COHERE": "command-r-plus-08-2024",
    "CHUTES": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "HUGGINGFACE": "meta-llama/Llama-3.3-70B-Instruct",
    "KLUSTER": "klusterai/Meta-Llama-3.3-70B-Instruct-Turbo",
    "FIREWORKS": "accounts/fireworks/models/llama-v3p3-70b-instruct",
    "GEMMA": GEMMA_MODEL_POOL[0]["model"],
    "GITHUB": "openai/gpt-4.1",
    "CLOUDFLARE": "@cf/meta/llama-3.1-8b-instruct-fp8",
    "NVIDIA": "nvidia/nemotron-3.5-lightning",

}

MORFO_VALIDATOR_MODEL = "gemini-3.1-flash-lite"

GEMINI_BASE_URL = "https://booklyfi.jasenkobozinovic.workers.dev"
GEMINI_DIRECT_BASE_URL = "https://generativelanguage.googleapis.com"


def get_gemini_url(model: str) -> str:
    # FIX: direktno na Google API, zaobiđi Cloudflare worker (timeout/404)
    return f"{GEMINI_DIRECT_BASE_URL}/v1beta/models/{model}:generateContent"


def get_gemini_direct_url(model: str) -> str:
    return f"{GEMINI_DIRECT_BASE_URL}/v1beta/models/{model}:generateContent"


def get_google_model_for_key(key_index: int) -> dict:
    """Return the pooled Google model assigned to a key index via modulo rotation."""
    return GOOGLE_MODEL_POOL[key_index % len(GOOGLE_MODEL_POOL)]


def get_next_google_model(current_model: str) -> dict:
    """Return the next Google model in the pool, or the first one if not found."""
    for i, model in enumerate(GOOGLE_MODEL_POOL):
        if model["model"] == current_model:
            return GOOGLE_MODEL_POOL[(i + 1) % len(GOOGLE_MODEL_POOL)]
    return GOOGLE_MODEL_POOL[0]


def get_model_api_string(profile_name: str, fallback: str = "") -> str:
    return AI_MODEL_STRINGS.get(profile_name, fallback)


@dataclass
class ProviderProfile:
    name: str  # uppercase ime ("GEMINI", "GROQ" ...)
    rpm_hard: int  # stvarni API limit
    rpm_safe: int  # naša granica (koristimo ovo)
    rpd_hard: int  # dnevni hard limit (0 = nepoznat/visok)
    rpd_safe: int  # naša dnevna granica
    tpm_hard: int  # token/min limit (0 = nebitan)
    min_gap_s: float  # min razmak između poziva JEDNOG ključa
    cooldown_429_s: float  # kratki cooldown na RPM 429 (ne kvota!)
    supports_system_role: bool  # prihvata {"role":"system"}?
    preferred_roles: List[str]  # uloge u kojima je odličan
    avoid_roles: List[str]  # uloge za koje je loš
    quality_tier: int  # 1=top, 2=solid, 3=ok, 4=fallback
    notes: str = ""

    @property
    def min_gap_for_key(self) -> float:
        """Minimalni razmak između poziva s jednog ključa (sigurni RPM limit)."""
        if self.rpm_safe <= 0:
            return 10.0
        return 60.0 / self.rpm_safe

    @property
    def daily_budget_per_key(self) -> int:
        """Sigurni dnevni budžet po ključu."""
        return self.rpd_safe


# ─────────────────────────────────────────────────────────────────────────────
# PROFILI — građeni iz stvarnih free-tier dokumentacija (maj 2026)
# ─────────────────────────────────────────────────────────────────────────────

PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    # ── GEMINI ──────────────────────────────────────────────────────────────
    # Free tier (dashboard 22.05.2026 + deprecation stranica):
    #   gemini-3.5-flash      — 10 RPM / 500 RPD  — STABLE, nema shutdown  ← PRIMARNI
    #   gemini-3.1-flash-lite — 15 RPM / 500 RPD  — STABLE, shutdown maj 2027
    #   gemini-2.5-flash      — 10 RPM / 1500 RPD — deprecated okt 2026 (fallback)
    #   gemini-2.5-flash-lite — 15 RPM / 1500 RPD — deprecated okt 2026 (fallback)
    #   gemini-2.0-flash      — DEPRECATED, shutdown 1. JUNA 2026 — NE KORISTITI!
    #
    # rpm_hard=10 jer je primarni 3.5-flash limitiran na 10 RPM
    # Sa 8 ključeva × 500 RPD = 4000 RPD/dan na stable modelima
    # Google šalje "quota" i "resource exhausted" za SVE 429 — i RPM i dnevne
    "GEMINI": ProviderProfile(
        name="GEMINI",
        rpm_hard=10,
        rpm_safe=8,  # 80% od 10 RPM po ključu (3.5-flash primarni)
        rpd_hard=500,
        rpd_safe=425,  # 85% od 500 RPD po ključu (stable modeli)
        tpm_hard=1_000_000,
        min_gap_s=7.5,  # 60s / 8 rpm_safe = 7.5s razmak između poziva jednog ključa
        cooldown_429_s=15.0,  # 15s cooldown po ključu nakon RPM 429
        supports_system_role=True,
        preferred_roles=["LEKTOR", "POLISH", "SCORER", "ANALIZA"],
        avoid_roles=[],  # radi sve
        quality_tier=1,
        notes="Primarni: 3.5-flash (stable, nema shutdown). 8 ključeva × 500 RPD = 4000 RPD/dan. 2.5 fallback do okt 2026.",
    ),
    # ── GROQ ────────────────────────────────────────────────────────────────
    # Free tier (STARI podaci za llama-3.3-70b-versatile — model ugašen 17.06.2026):
    # TODO: provjeriti stvarni RPM/RPD za openai/gpt-oss-120b na console.groq.com
    # llama-3.1-8b-instant = 30 RPM / 14400 RPD (sekundarni model)
    # Pažnja: RPD je nizak na primarnom modelu (1000/dan po ključu)
    # Ključevi: 5 komada → 5000 RPD ukupno — ne rasipati na scorer/validator
    "GROQ": ProviderProfile(
        name="GROQ",
        rpm_hard=30,
        rpm_safe=12,  # FIX #4: per-key limit (uklonjen iz global RPM)
        rpd_hard=1000,
        rpd_safe=850,
        tpm_hard=6000,  # FIX: qwen3.8-27b free tier ~6k TPM (bilo 15k, previse)
        min_gap_s=2.5,  # 60/24 = 2.5s
        cooldown_429_s=10.0,  # FIX: Groq šalje Retry-After (2-10s) pa se profil rijetko koristi.
                               # 65s je bilo predugo — drži ključ zaključan kad Groq nema header.
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=["SCORER"],  # RPD previše vrijedan za scorer
        quality_tier=2,
        notes="Brz. 5 ključeva. RPD je usko grlo — čuvati za prevod/korektor.",
    ),
    # ── SAMBANOVA ───────────────────────────────────────────────────────────
    # Free tier: Meta-Llama-3.3-70B = 10 RPM / 10000 RPD / 4096 TPM
    # TPM je JAKO nizak (4096) — dugi promptovi momentalno gaze limit.
    # Pravo usko grlo je TPM, ne RPD (RPD=10000 se nikad ne dostiže).
    # 429 u praksi = TPM prekoračenje (~65-70% rejection rate bez throttle).
    # Realni kapacitet: ~133-200 uspješnih poziva/dan po ključu (TPM limiti).
    # Ključevi: 3 aktivna (402 su blacklistirani) → ~600 korisnih poziva/dan ukupno
    # Pažnja: skratiti promptove na max ~800 tokena za SambaNova
    "SAMBANOVA": ProviderProfile(
        name="SAMBANOVA",
        rpm_hard=10,
        rpm_safe=8,
        rpd_hard=10_000,
        rpd_safe=400,   # Realno po ključu — TPM limit čini RPD irrelevantnim
        tpm_hard=4_096,  # KRITIČNO nizak! Ovo je pravo usko grlo.
        min_gap_s=7.5,  # 60/8 = 7.5s
        cooldown_429_s=75.0,  # TPM 429 treba čekati cijeli 60s prozor + buffer
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=["ANALIZA", "SCORER"],  # dugi outputi + TPM problem
        quality_tier=2,
        notes="TPM=4096 je pravo usko grlo (ne RPD). Max ~800 tokena po promptu. 3 aktivna ključa.",
    ),
    # ── COHERE ──────────────────────────────────────────────────────────────
    # Free tier: command-r-plus = 20 RPM / 1000 RPD (trial key)
    # API v2 format — drugačiji od OpenAI (provider_urls.py već ima ispravku)
    # Ključevi: 5 komada → 5000 RPD
    # Odličan za BS/HR lekturu — command-r modeli su trenirani na europskim jezicima
    "COHERE": ProviderProfile(
        name="COHERE",
        rpm_hard=20,
        rpm_safe=16,
        rpd_hard=1_000,
        rpd_safe=850,
        tpm_hard=0,  # nije ograničen na free tier
        min_gap_s=3.75,  # 60/16
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["LEKTOR", "POLISH"],
        avoid_roles=["PREVODILAC"],  # sporiji od Groq/Cerebras za prevod
        quality_tier=2,
        notes="Odličan za lekturu/polish. V2 API format.",
    ),
    # ── OPENROUTER ──────────────────────────────────────────────────────────
    # Free tier: :free modeli — limiti variraju po modelu (~20 RPM / 200 RPD)
    # RPD je JAKO nizak na free modelima — čuvati za fallback
    # Ključevi: 5 komada → 1000 RPD ukupno
    # Koristi deepseek/qwen free modele — nepredvidiv kvalitet
    "OPENROUTER": ProviderProfile(
        name="OPENROUTER",
        rpm_hard=20,
        rpm_safe=15,
        rpd_hard=200,
        rpd_safe=180,
        tpm_hard=200_000,
        min_gap_s=4.0,
        cooldown_429_s=60.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER", "LEKTOR", "KOREKTOR"],
        quality_tier=2,
        notes="Nemotron 3 Ultra preko OpenRoutera. Samo fallback za prohibited content (nasilne scene).",
    ),
    # ── GITHUB MODELS ───────────────────────────────────────────────────────
    # Free tier: gpt-4o = 10 RPM / 50 RPD (JAKO nizak!)
    # gpt-4o-mini = 15 RPM / 150 RPD
    # Microsoft throttluje agresivno — čak i ping može trošiti kvotu
    # Ključevi: 5 komada → 250 RPD ukupno (gpt-4o) — koristiti pametno
    "GITHUB": ProviderProfile(
        name="GITHUB",
        rpm_hard=10,
        rpm_safe=8,
        rpd_hard=50,  # gpt-4o — izuzetno nizak
        rpd_safe=42,
        tpm_hard=0,
        min_gap_s=7.5,
        cooldown_429_s=70.0,
        supports_system_role=True,
        preferred_roles=["SCORER", "ANALIZA"],  # gpt-4o je dobar scorer ali čuva RPD
        avoid_roles=["PREVODILAC", "KOREKTOR"],  # RPD prenizak za bulk
        quality_tier=1,  # kvalitet je top ali limitiran
        notes="gpt-4o. KRITIČNO nizak RPD (50/dan po ključu). Samo za scorer/analizu.",
    ),
    # ── CLOUDFLARE WORKERS AI ────────────────────────────────────────────────
    # Dodano 21.09.2026. GLM-4.7-Flash: 131K kontekst, 100+ jezika. Budžet je
    # 10.000 "Neurons"/dan DIJELJENO preko svih modela na accountu — nije
    # čist RPM/RPD broj kao kod drugih, pa su brojevi ispod konzervativna
    # procjena dok se ne potvrdi stvaran trošak po zahtjevu. Podesi kad
    # imamo stvarne podatke iz quota_trackera.
    "CLOUDFLARE": ProviderProfile(
        name="CLOUDFLARE",
        rpm_hard=20,
        rpm_safe=15,
        rpd_hard=0,  # Neuron-based, ne RPD — vidi napomenu iznad
        rpd_safe=0,
        tpm_hard=0,
        min_gap_s=3.0,
        cooldown_429_s=60.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "LEKTOR"],
        avoid_roles=[],
        quality_tier=2,  # neprovjereno za BCS — pratiti quality scores
        notes="GLM-4.7-Flash. Neuron budžet dijeljen — brojevi konzervativni dok se ne potvrde.",
    ),
    # ── NVIDIA NIM ────────────────────────────────────────────────────────────
    # Dodano 21.09.2026. Nemotron 3 familija. Free tier je od 2025. čist
    # rate limit (~40 RPM), bez kartice, bez kredita koji ističu.
    "NVIDIA": ProviderProfile(
        name="NVIDIA",
        rpm_hard=40,
        rpm_safe=32,
        rpd_hard=0,
        rpd_safe=0,
        tpm_hard=0,
        min_gap_s=1.5,
        cooldown_429_s=60.0,
        supports_system_role=True,
        preferred_roles=["KOREKTOR", "VALIDATOR", "ANALIZA"],
        avoid_roles=[],
        quality_tier=2,  # neprovjereno za BCS — pratiti quality scores
        notes="Nemotron 3. ~40 RPM potvrđeno (sep 2026). Model string provjeriti kroz discovery.",
    ),
    # ── KLUSTER ─────────────────────────────────────────────────────────────
    # Free tier: llama-3.3-70b = ~15 RPM / neograničen RPD (po dokumentaciji)
    # Relativno novi provajder — stabilnost varira
    # Ključevi: 5 komada
    "KLUSTER": ProviderProfile(
        name="KLUSTER",
        rpm_hard=15,
        rpm_safe=12,
        rpd_hard=0,  # neograničen (po dokumentaciji)
        rpd_safe=5_000,  # konzervativna gornja granica
        tpm_hard=0,
        min_gap_s=5.0,
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=[],
        quality_tier=3,
        notes="Neograničen RPD. Kvalitet solidan. Dobar za bulk prevod.",
    ),
    # ── CHUTES ──────────────────────────────────────────────────────────────
    # Free tier: deepseek-r1-distill, qwen modeli
    # Limiti nisu javno dokumentirani — konzervativne pretpostavke
    # Ključevi: 5 komada
    "CHUTES": ProviderProfile(
        name="CHUTES",
        rpm_hard=10,
        rpm_safe=8,
        rpd_hard=0,
        rpd_safe=3_000,
        tpm_hard=0,
        min_gap_s=7.5,
        cooldown_429_s=70.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER", "ANALIZA"],
        quality_tier=3,
        notes="DeepSeek/Qwen modeli. Limiti nedokumentirani — konzervativno.",
    ),
    # ── HUGGINGFACE ─────────────────────────────────────────────────────────
    # HF Inference API (router): llama-3.3-70b
    # Free tier limiti su strogi i nepredvidivi (queue based)
    # Ključevi: 3 komada — najmanje od svih
    "HUGGINGFACE": ProviderProfile(
        name="HUGGINGFACE",
        rpm_hard=10,
        rpm_safe=7,
        rpd_hard=0,
        rpd_safe=2_000,
        tpm_hard=0,
        min_gap_s=8.6,  # 60/7
        cooldown_429_s=90.0,  # HF često treba dulje da se oporavi
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER", "ANALIZA", "LEKTOR"],
        quality_tier=4,
        notes="Samo 3 ključa. Queue-based, latencija nepredvidiva. Zadnji fallback.",
    ),
    # ── MISTRAL ─────────────────────────────────────────────────────────────
    # Free tier (La Plateforme): 1 ključ — POZOR!
    # mistral-small-latest = 1 RPM (!) na free tier — gotovo neupotrebljiv bulk
    # Čuvati isključivo za kvalitetne one-off pozive (scorer, posebni slučajevi)
    "MISTRAL": ProviderProfile(
        name="MISTRAL",
        rpm_hard=1,  # free tier je 1 RPM!
        rpm_safe=1,
        rpd_hard=0,
        rpd_safe=200,  # pretpostavljamo konzervativno
        tpm_hard=0,
        min_gap_s=62.0,  # 60s + buffer — praktično jedan poziv u minuti
        cooldown_429_s=120.0,
        supports_system_role=True,
        preferred_roles=["SCORER"],  # samo za posebne slučajeve
        avoid_roles=["PREVODILAC", "KOREKTOR", "LEKTOR"],  # prenizak RPM
        quality_tier=2,
        notes="SAMO 1 KLJUČ i 1 RPM na free tier! Koristiti samo za scorer/posebne slučajeve.",
    ),
    # ── CEREBRAS ────────────────────────────────────────────────────────────
    # Free tier: llama-3.3-70b = 30 RPM / 10000 RPD / 131K TPM (procjena)
    # Izuzetno brzak (kompajlovani silikon). Preferiran za PREVODILAC/KOREKTOR.
    "CEREBRAS": ProviderProfile(
        name="CEREBRAS",
        rpm_hard=30,
        rpm_safe=24,  # 80% od 30
        rpd_hard=10_000,
        rpd_safe=8_500,
        tpm_hard=131_072,
        min_gap_s=2.5,  # 60/24
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=["SCORER"],
        quality_tier=2,
        notes="Kompajlovani silikon — najbrži inferens. Dobar za PREVODILAC/KOREKTOR.",
    ),
    # ── TOGETHER ────────────────────────────────────────────────────────────
    # Free tier: 60 RPM / 60 RPD (konzervativno) — rate limiti variraju po modelu
    "TOGETHER": ProviderProfile(
        name="TOGETHER",
        rpm_hard=60,
        rpm_safe=16,  # konzervativno — modeli imaju različite limite
        rpd_hard=0,
        rpd_safe=2_000,
        tpm_hard=0,
        min_gap_s=3.75,  # 60/16
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER"],
        quality_tier=3,
        notes="Različiti modeli s različitim limitima. Konzervativni RPM.",
    ),
    # ── FIREWORKS ───────────────────────────────────────────────────────────
    # Free tier: 60 RPM / varijabilno RPD
    "FIREWORKS": ProviderProfile(
        name="FIREWORKS",
        rpm_hard=60,
        rpm_safe=16,
        rpd_hard=0,
        rpd_safe=2_000,
        tpm_hard=0,
        min_gap_s=3.75,
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER"],
        quality_tier=3,
        notes="Slično Together.ai — varijabilni rate limiti po modelu.",
    ),
    # ── GEMMA ───────────────────────────────────────────────────────────────
    # Gemma 4 modeli na Google Gemini native endpointu (isti API kao Gemini).
    # gemma-4-26b-a4b-it = 15 RPM / 1500 RPD po ključu (dashboard 22.05.2026)
    # gemma-4-31b-it = 15 RPM / 1500 RPD po ključu
    # Koristi GEMINI ključeve. Format: native (contents/systemInstruction).
    # Gemma NE podržava system role — merge u user poruku.
    "GEMMA": ProviderProfile(
        name="GEMMA",
        rpm_hard=15,
        rpm_safe=12,  # 80% od 15 RPM
        rpd_hard=1500,
        rpd_safe=1275,  # 85% od 1500
        tpm_hard=250_000,
        min_gap_s=5.0,  # 60/12 = 5.0s
        cooldown_429_s=15.0,  # isto kao Gemini — Google API
        supports_system_role=False,  # Gemma nema system role
        preferred_roles=["LEKTOR", "POLISH"],
        avoid_roles=["SCORER"],
        quality_tier=2,
        notes="Gemma 4 na Gemini native endpointu. Koristi GEMINI ključeve. 15 RPM / 1500 RPD.",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNKCIJE — koriste se iz api_fleet.py, rate_limiter.py i router-a
# ─────────────────────────────────────────────────────────────────────────────


def get_profile(provider: str) -> ProviderProfile | None:
    """Vraća profil za provajdera ili None ako nije poznat."""
    return PROVIDER_PROFILES.get(provider.upper())


def get_rpm_safe(provider: str) -> int:
    """Sigurni RPM limit za provajdera."""
    p = get_profile(provider)
    return p.rpm_safe if p else 15


def get_rpd_safe(provider: str) -> int:
    """Sigurni dnevni limit za provajdera (0 = neograničen)."""
    p = get_profile(provider)
    return p.rpd_safe if p else 1000


def get_min_gap(provider: str) -> float:
    """Minimalni razmak između poziva jednog ključa (sekunde)."""
    p = get_profile(provider)
    return p.min_gap_s if p else 5.0




# FIX #1: prva get_tpm_safe obrisana (dupla definicija)
def get_cooldown_429(provider: str) -> float:
    """Kratki cooldown na RPM 429 (ne dnevna kvota)."""
    p = get_profile(provider)
    return p.cooldown_429_s if p else 65.0


def is_preferred_for_role(provider: str, role: str) -> bool:
    p = get_profile(provider)
    return role.upper() in [r.upper() for r in (p.preferred_roles if p else [])]


def should_avoid_for_role(provider: str, role: str) -> bool:
    p = get_profile(provider)
    return role.upper() in [r.upper() for r in (p.avoid_roles if p else [])]


def get_quality_tier(provider: str) -> int:
    p = get_profile(provider)
    return p.quality_tier if p else 4


def effective_rpm_with_keys(provider: str, num_keys: int) -> int:
    """
    Ukupni efektivni RPM flote za provajdera s N ključeva.
    Korisno za logging i debug.
    """
    p = get_profile(provider)
    if not p:
        return 0
    return p.rpm_safe * num_keys


def effective_rpd_with_keys(provider: str, num_keys: int) -> int:
    """
    Ukupni efektivni dnevni kapacitet flote.
    """
    p = get_profile(provider)
    if not p:
        return 0
    if p.rpd_safe == 0:
        return 0  # neograničen
    return p.rpd_safe * num_keys


def print_fleet_capacity(fleet_keys: dict[str, list]) -> None:
    """
    Debug: ispiši kapacitet svake provajder flote.
    Primjer: print_fleet_capacity({"GEMINI": [...6 ključeva...], "GROQ": [...5...]})
    """
    print("\n=== FLEET KAPACITET ===")
    total_rpm = 0
    for prov, keys in sorted(fleet_keys.items()):
        n = len(keys)
        p = get_profile(prov)
        if not p:
            print(f"  {prov:<14} {n} ključ(a) — profil nije definiran")
            continue
        rpm_total = p.rpm_safe * n
        rpd_total = p.rpd_safe * n if p.rpd_safe else 0
        rpd_str = f"{rpd_total:,}/dan" if rpd_total else "neograničen/dan"
        total_rpm += rpm_total
        preferred = ", ".join(p.preferred_roles) or "sve"
        avoid = ", ".join(p.avoid_roles) or "—"
        print(
            f"  {prov:<14} {n} ključ(a) | "
            f"~{rpm_total:>3} RPM | {rpd_str:<18} | "
            f"tier={p.quality_tier} | OK za: {preferred:<30} | izbjegavaj: {avoid}"
        )
        if p.notes:
            print(f"  {'':14}   ⚠️  {p.notes}")
    print(f"\n  UKUPNO: ~{total_rpm} RPM efektivnih (svi ključevi)")
    print("=" * 60)


# ============================================================================
# FIX sve_fix: NVIDIA + CLOUDFLARE provideri + TPM safe mape
# ============================================================================

# TPM sigurnosne granice po provideru (tokens per minute).
# Vrijednosti su konzervativne — discovery može vratiti niže, ali ovo je
# donja granica koju rate_limiter NIKAD ne spušta ispod.
PROVIDER_TPM_SAFE = {
    "GEMINI":     250000,
    "GEMMA":      250000,
    "GROQ":       12000,      # FIX: bilo 6400 — output chunk ~7000 tok
    "CEREBRAS":   15000,
    "SAMBANOVA":  20000,
    "MISTRAL":    500000,
    "COHERE":     100000,
    "OPENROUTER": 20000,
    "GITHUB":     15000,
    "NVIDIA":     40000,      # NVIDIA NIM free tier ~40k TPM
    "CLOUDFLARE": 30000,      # Workers AI free tier
    "TOGETHER":   20000,
    "FIREWORKS":  20000,
    "CHUTES":     20000,
    "HUGGINGFACE":15000,
    "KLUSTER":    20000,
}


def get_tpm_safe(provider: str) -> float:
    """FIX #1: TPM sigurnosna granica (80% od tpm_hard iz profila).
    Vraća 0.0 ako profil nema TPM limit (gate isključen).
    Dinamički discovery iz response headera prepisuje ovo kad stigne."""
    p = get_profile(provider)
    if not p or getattr(p, "tpm_hard", 0) <= 0:
        return 0.0
    return float(p.tpm_hard * 0.8)


# NVIDIA NIM — modeli (integrate.api.nvidia.com)
# FINALNA LISTA nakon testova 2026-09-25 (vidjeti snapshot)
#
# Testovi pokazali:
#   ✅ RADI:  riva-v2, nemotron-3-ultra-550b, gemma-4-31b, laguna-xs-2.1
#   ❌ LOŠE:  mistral-nemotron (vraća RUSKI), riva-v1.1 (vraća ARAPSKI)
#   ⚠️  404:   nvidia/llama-3.1-nemotron-70b (traži aktivaciju na build.nvidia.com)
#   ⚠️  Gone:  meta/llama-3.1-70b-instruct (410 — uklonjen s NIM-a)
NVIDIA_MODEL_POOL = []  # FIX: svi modeli 404

# CLOUDFLARE Workers AI — modeli (@cf/ prefiks)
# Cloudflare Workers AI — modeli (test 2026-09-26)
# Pobjednik: llama-3.3-70b-instruct-fp8-fast (1.29s, odličan BS prijevod)
# Backup: llama-4-scout-17b (1.75s, solidan)
CLOUDFLARE_MODEL_POOL = [
    # Primarni: Llama 3.3 70B FP8 Fast — najbrži, najkvalitetniji
    #   EN: "The old warrior drew his sword slowly."
    #   BS: "Stari ratnik polako je izvukao mač."  ← identično Gemini
    {"model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "rpm": 30, "rpd": 10000},
    # Backup: Llama 4 Scout 17B — noviji, malo sporiji
    {"model": "@cf/meta/llama-4-scout-17b-16e-instruct", "rpm": 30, "rpd": 10000},
    # Qwen 2.5 Coder 32B — jak multilingual
    {"model": "@cf/qwen/qwen2.5-coder-32b-instruct", "rpm": 30, "rpd": 10000},
]
