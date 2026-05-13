# network/provider_profiles.py
#
# CENTRALNI PER-PROVIDER PROFILI — jedino mjesto gdje su limiti i karakteristike
# svakog provajdera definirani. Koriste se u:
#   api_fleet.py      → _DEFAULT_RPM, _DEFAULT_DAILY_QUOTA, _PROVIDER_MIN_GAP
#   rate_limiter.py   → _PROVIDER_MIN_GAP, _RPM_THROTTLE_MULTIPLIER
#   provider_router_v2.py → routing prioriteti i sposobnosti
#
# Svaki profil je građen iz stvarnih limita free-tier planova (maj 2026).
# Sve vrijednosti su konzervativne — bolje sporije nego banned.
#
# ─── LEGENDA ────────────────────────────────────────────────────────────────
# rpm_hard     : stvarni API limit (zahtjevi/minuta) — NIKAD ne prekoračiti
# rpm_safe     : naša gornja granica (80% od hard) — s marginom sigurnosti
# rpd_hard     : dnevni limit zahtjeva (requests per day)
# rpd_safe     : naša gornja granica (85% od hard)
# tpm_hard     : token limit po minuti (0 = nepoznat/nije bitan)
# min_gap_s    : minimalni razmak između poziva s JEDNOG KLJUČA (sekunde)
#                Izračun: 60s / rpm_safe — ne treba provider lock
# cooldown_429 : kratki cooldown pri RPM 429 (sekunde) — NE dnevna kvota
# supports_system_role : da li model prihvata {"role":"system"} poruke
# preferred_roles      : liste u kojima je provajder odličan
# avoid_roles          : uloge za koje je loš (ne koristiti ako ima alternative)
# quality_tier         : 1=top, 2=solid, 3=ok, 4=fallback (za routing prioritet)
# notes        : kratka napomena (bitno za debugging)
# ────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass, field
from typing import List


@dataclass
class ProviderProfile:
    name: str                       # uppercase ime ("GEMINI", "GROQ" ...)
    rpm_hard: int                   # stvarni API limit
    rpm_safe: int                   # naša granica (koristimo ovo)
    rpd_hard: int                   # dnevni hard limit (0 = nepoznat/visok)
    rpd_safe: int                   # naša dnevna granica
    tpm_hard: int                   # token/min limit (0 = nebitan)
    min_gap_s: float                # min razmak između poziva JEDNOG ključa
    cooldown_429_s: float           # kratki cooldown na RPM 429 (ne kvota!)
    supports_system_role: bool      # prihvata {"role":"system"}?
    preferred_roles: List[str]      # uloge u kojima je odličan
    avoid_roles: List[str]          # uloge za koje je loš
    quality_tier: int               # 1=top, 2=solid, 3=ok, 4=fallback
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
    # Free tier: gemini-2.0-flash = 15 RPM / 1500 RPD / 1M TPM
    # gemini-2.5-flash-lite = 10 RPM / 500 RPD
    # Ključevi: 6 komada → efektivni kapacitet: 90 RPM / 9000 RPD (svih 6 zajedno)
    # Pažnja: TPM limit (1M/min) može biti usko grlo na dugim tekstovima
    # Google šalje "quota" i "resource exhausted" za SVE 429 — i RPM i dnevne
    "GEMINI": ProviderProfile(
        name="GEMINI",
        rpm_hard=15,
        rpm_safe=12,           # 80% od 15 — s marginom
        rpd_hard=1500,
        rpd_safe=1275,         # 85% od 1500
        tpm_hard=1_000_000,
        min_gap_s=5.0,         # 60/12 = 5s po ključu
        cooldown_429_s=65.0,   # malo više od 60s RPM window-a
        supports_system_role=True,
        preferred_roles=["LEKTOR", "POLISH", "SCORER", "ANALIZA"],
        avoid_roles=[],        # radi sve
        quality_tier=1,
        notes="Najbolji kvalitet. 6 ključeva. TPM usko grlo na dugim promptovima.",
    ),

    # ── GROQ ────────────────────────────────────────────────────────────────
    # Free tier: llama-3.3-70b-versatile = 30 RPM / 1000 RPD / 131K TPM
    # llama-3.1-8b-instant = 30 RPM / 14400 RPD (sekundarni model)
    # Pažnja: RPD je nizak na primarnom modelu (1000/dan po ključu)
    # Ključevi: 5 komada → 5000 RPD ukupno — ne rasipati na scorer/validator
    "GROQ": ProviderProfile(
        name="GROQ",
        rpm_hard=30,
        rpm_safe=24,
        rpd_hard=1000,
        rpd_safe=850,
        tpm_hard=131_072,
        min_gap_s=2.5,         # 60/24 = 2.5s
        cooldown_429_s=65.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=["SCORER"],  # RPD previše vrijedan za scorer
        quality_tier=2,
        notes="Brz. 5 ključeva. RPD je usko grlo — čuvati za prevod/korektor.",
    ),

    # ── SAMBANOVA ───────────────────────────────────────────────────────────
    # Free tier: Meta-Llama-3.3-70B = 10 RPM / 10000 RPD / 4096 TPM
    # TPM je JAKO nizak (4096) — dugi promptovi momentalno gaze limit
    # Ključevi: 6 komada → 60 RPM / 60000 RPD (odlično)
    # Pažnja: skratiti system prompt na maksimum 1500 tokena za Sambanova
    "SAMBANOVA": ProviderProfile(
        name="SAMBANOVA",
        rpm_hard=10,
        rpm_safe=8,
        rpd_hard=10_000,
        rpd_safe=8_500,
        tpm_hard=4_096,        # KRITIČNO nizak!
        min_gap_s=7.5,         # 60/8 = 7.5s
        cooldown_429_s=70.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC", "KOREKTOR"],
        avoid_roles=["ANALIZA", "SCORER"],  # dugi outputi + TPM problem
        quality_tier=2,
        notes="Visok RPD ali KRITIČNO nizak TPM (4096). Koristiti kratke promptove!",
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
        tpm_hard=0,            # nije ograničen na free tier
        min_gap_s=3.75,        # 60/16
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
        rpd_safe=170,
        tpm_hard=0,
        min_gap_s=4.0,
        cooldown_429_s=70.0,
        supports_system_role=True,
        preferred_roles=["PREVODILAC"],
        avoid_roles=["SCORER", "ANALIZA"],
        quality_tier=3,
        notes="Fallback. RPD izuzetno nizak po ključu (200). Čuvati za krajnji slučaj.",
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
        rpd_hard=50,           # gpt-4o — izuzetno nizak
        rpd_safe=42,
        tpm_hard=0,
        min_gap_s=7.5,
        cooldown_429_s=70.0,
        supports_system_role=True,
        preferred_roles=["SCORER", "ANALIZA"],  # gpt-4o je dobar scorer ali čuva RPD
        avoid_roles=["PREVODILAC", "KOREKTOR"],  # RPD prenizak za bulk
        quality_tier=1,        # kvalitet je top ali limitiran
        notes="gpt-4o. KRITIČNO nizak RPD (50/dan po ključu). Samo za scorer/analizu.",
    ),

    # ── KLUSTER ─────────────────────────────────────────────────────────────
    # Free tier: llama-3.3-70b = ~15 RPM / neograničen RPD (po dokumentaciji)
    # Relativno novi provajder — stabilnost varira
    # Ključevi: 5 komada
    "KLUSTER": ProviderProfile(
        name="KLUSTER",
        rpm_hard=15,
        rpm_safe=12,
        rpd_hard=0,            # neograničen (po dokumentaciji)
        rpd_safe=5_000,        # konzervativna gornja granica
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
        min_gap_s=8.6,         # 60/7
        cooldown_429_s=90.0,   # HF često treba dulje da se oporavi
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
        rpm_hard=1,            # free tier je 1 RPM!
        rpm_safe=1,
        rpd_hard=0,
        rpd_safe=200,          # pretpostavljamo konzervativno
        tpm_hard=0,
        min_gap_s=62.0,        # 60s + buffer — praktično jedan poziv u minuti
        cooldown_429_s=120.0,
        supports_system_role=True,
        preferred_roles=["SCORER"],   # samo za posebne slučajeve
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
        rpm_safe=24,           # 80% od 30
        rpd_hard=10_000,
        rpd_safe=8_500,
        tpm_hard=131_072,
        min_gap_s=2.5,         # 60/24
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
        rpm_safe=16,           # konzervativno — modeli imaju različite limite
        rpd_hard=0,
        rpd_safe=2_000,
        tpm_hard=0,
        min_gap_s=3.75,        # 60/16
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
