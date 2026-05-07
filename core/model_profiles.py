"""
BooklyFi — core/model_profiles.py
V10.4: Empirijski određeni profili svih AI modela u fleeti.
Svaki profil definira snage, slabosti, optimalne temperature
i anti-patterne karakteristične za taj model.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ModelProfile:
    ime: str                          # interni identifikator
    provider: str                     # gemini / groq / cerebras / mistral / cohere / sambanova / openrouter / chutes
    api_model_string: str             # stvarni string za API poziv
    rpm_limit: int                    # requests per minute (free tier)
    rpd_limit: int                    # requests per day (free tier, 0 = neograničeno)
    snage: List[str]                  # empirijski utvrđene snage
    slabosti: List[str]               # empirijski utvrđene slabosti
    anti_patterne: List[str]          # regex patterne karakteristični za ovaj model
    preferred_roles: List[str]        # uloge za koje je model najprikladniji
    blacklisted_roles: List[str]      # uloge za koje se model ne koristi
    temp_prevodilac: float = 0.75     # optimalna temperatura za prijevod
    temp_lektor: float = 0.65         # optimalna temperatura za lekturu
    temp_validator: float = 0.30      # optimalna temperatura za morfološku validaciju
    max_tokens_chunk: int = 2048      # max output tokena za chunk prijevod
    max_tokens_validator: int = 1024  # max output tokena za validator prolaz
    notes: str = ""                   # slobodne napomene


# ─────────────────────────────────────────────────────────────
# PROFILI — definirani empirijski iz QA analize
# ─────────────────────────────────────────────────────────────

PROFILI: Dict[str, ModelProfile] = {

    "gemini_25_flash": ModelProfile(
        ime="gemini_25_flash",
        provider="gemini",
        api_model_string="gemini-2.5-flash-preview-05-20",
        rpm_limit=10,
        rpd_limit=500,
        snage=[
            "književni stil",
            "BS/HR morfologija",
            "dugi kontekst",
            "razumijevanje idioma",
            "dijalog",
        ],
        slabosti=[
            "meta-komentari ('Naravno, evo prijevoda:')",
            "markdown blokovi u izlazu (``` ```)",
            "ponekad predugi odgovori",
            "povremeni anglicizmi u tehničkim tekstovima",
        ],
        anti_patterne=[
            r"^Naravno[,!]?\s",
            r"^Evo\s(prijevoda|mog|rezultata)",
            r"^Svakako[,!]?\s",
            r"```[\w]*\n",
            r"\n```",
            r"^\*\*Prijevod\*\*",
            r"^\*\*Napomena\*\*",
            r"Nadam se da",
            r"Slobodno pitajte",
        ],
        preferred_roles=["prevodilac", "lektor", "validator", "chapter_summary"],
        blacklisted_roles=[],
        temp_prevodilac=0.72,
        temp_lektor=0.65,
        temp_validator=0.30,
        max_tokens_chunk=2048,
        notes="Primarni model za kvalitetne prolaze. Sklon meta-komentarima — anti_meta patch obavezan.",
    ),

    "gemini_20_flash": ModelProfile(
        ime="gemini_20_flash",
        provider="gemini",
        api_model_string="gemini-2.0-flash",
        rpm_limit=15,
        rpd_limit=1500,
        snage=[
            "brz",
            "pouzdan",
            "dobar BS/HR",
            "stabilan izlaz",
        ],
        slabosti=[
            "meta-komentari (manje nego 2.5)",
            "ponekad formalan ton",
            "markdown u izlazu",
        ],
        anti_patterne=[
            r"^Naravno[,!]?\s",
            r"^Evo\s(prijevoda|mog|rezultata)",
            r"```[\w]*\n",
            r"\n```",
            r"Nadam se da",
        ],
        preferred_roles=["prevodilac", "lektor", "chapter_summary"],
        blacklisted_roles=[],
        temp_prevodilac=0.75,
        temp_lektor=0.68,
        temp_validator=0.35,
        max_tokens_chunk=2048,
        notes="Pouzdana alternativa za gemini_25_flash kada je rpm limit dostignut.",
    ),

    "gemma3_27b": ModelProfile(
        ime="gemma3_27b",
        provider="gemini",
        api_model_string="gemma-3-27b-it",
        rpm_limit=30,
        rpd_limit=14400,
        snage=[
            "visoki rpm limit",
            "dobar za kratke blokove",
            "stabilan izlaz",
        ],
        slabosti=[
            "slabiji književni stil od 2.5/2.0",
            "povremeni srbizmi",
            "formalan",
        ],
        anti_patterne=[
            r"^Naravno[,!]?\s",
            r"```[\w]*\n",
            r"\n```",
        ],
        preferred_roles=["lektor", "prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.78,
        temp_lektor=0.70,
        temp_validator=0.40,
        max_tokens_chunk=1800,
        notes="Koristiti kada su Gemini flash modeli na limitu. Nije za validator — slabija morfološka preciznost.",
    ),

    "llama33_70b_groq": ModelProfile(
        ime="llama33_70b_groq",
        provider="groq",
        api_model_string="llama-3.3-70b-versatile",
        rpm_limit=30,
        rpd_limit=14400,
        snage=[
            "iznimno brz",
            "visoki rpm limit",
            "dobar za masovnu obradu",
        ],
        slabosti=[
            "sistematski srbizmi/ekavizmi (srpski korpus dominira)",
            "morfološke halucinacije (uzdisnuo, popivajući)",
            "doslovan prijevod idioma",
            "gubi kontekst na dužim blokovima",
        ],
        anti_patterne=[
            r"\bneverovatno?\b",
            r"\bposeduje\b",
            r"\bposedujem\b",
            r"\bvideo\b(?!\s+\w+\s+\w)",   # ekavski "video" umjesto "vidio"
            r"\bsreo\b",
            r"\bneo\b",
            r"\bpeo\b",
            r"^Naravno[,!]?\s",
        ],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.65,
        temp_lektor=0.60,
        temp_validator=0.30,
        max_tokens_chunk=1800,
        notes="OBAVEZAN anti_srbizmi patch u promptu. Kalkovi engine hvata većinu, ali prompt patch smanjuje učestalost.",
    ),

    "llama31_70b_cerebras": ModelProfile(
        ime="llama31_70b_cerebras",
        provider="cerebras",
        api_model_string="llama-3.1-70b",
        rpm_limit=30,
        rpd_limit=0,
        snage=[
            "najbrži od svih",
            "neograničeni rpd",
            "dobar za paralelnu obradu",
        ],
        slabosti=[
            "jaki srbizmi/ekavizmi",
            "morfološke halucinacije — najgori od svih",
            "ponekad reže rečenice",
            "doslovan prijevod",
        ],
        anti_patterne=[
            r"\bneverovatno?\b",
            r"\bposeduje\b",
            r"\bvideo\b",
            r"\bsreo\b",
            r"\bhteo\b",
            r"\bznao\b",
            r"\bvoljevao\b",
            r"\bhodavao\b",
            r"\bgledavao\b",
        ],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary", "lektor"],
        temp_prevodilac=0.65,
        temp_lektor=0.60,
        temp_validator=0.30,
        max_tokens_chunk=1600,
        notes="Koristiti samo za volume obradu. Kalkovi engine + morfo_validator OBAVEZNI nakon ovog modela.",
    ),

    "mistral_large": ModelProfile(
        ime="mistral_large",
        provider="mistral",
        api_model_string="mistral-large-latest",
        rpm_limit=10,
        rpd_limit=0,
        snage=[
            "precizan",
            "dosljedan izlaz",
            "dobar HTML preservation",
            "nema meta-komentara",
        ],
        slabosti=[
            "formalan ton",
            "monoton — ponavlja sintaksne obrasce",
            "ponekad previše bukvalan",
        ],
        anti_patterne=[
            r"^Voilà[,!]?\s",
            r"^Bien sûr",
        ],
        preferred_roles=["lektor", "prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.80,
        temp_lektor=0.72,
        temp_validator=0.35,
        max_tokens_chunk=2048,
        notes="Dobar lektor. Treba vary_syntax patch jer je monoton.",
    ),

    "mistral_nemo": ModelProfile(
        ime="mistral_nemo",
        provider="mistral",
        api_model_string="open-mistral-nemo",
        rpm_limit=10,
        rpd_limit=0,
        snage=[
            "brz",
            "precizan za kratke blokove",
        ],
        slabosti=[
            "formalan",
            "slabiji od mistral_large",
            "monoton",
        ],
        anti_patterne=[],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.78,
        temp_lektor=0.70,
        temp_validator=0.35,
        max_tokens_chunk=1800,
        notes="Backup za mistral_large.",
    ),

    "command_r_plus_cohere": ModelProfile(
        ime="command_r_plus_cohere",
        provider="cohere",
        api_model_string="command-r-plus",
        rpm_limit=10,
        rpd_limit=1000,
        snage=[
            "dosljedan",
            "dobar za naraciju",
            "stabilan izlaz",
        ],
        slabosti=[
            "monoton — ponavlja sintaksne obrasce",
            "povremeni anglicizmi",
            "sporiji",
        ],
        anti_patterne=[
            r"^Certainly[,!]?\s",
            r"^Of course[,!]?\s",
        ],
        preferred_roles=["prevodilac", "lektor"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.78,
        temp_lektor=0.70,
        temp_validator=0.35,
        max_tokens_chunk=2048,
        notes="Treba vary_syntax patch. Solidan backup model.",
    ),

    "llama_sambanova": ModelProfile(
        ime="llama_sambanova",
        provider="sambanova",
        api_model_string="Meta-Llama-3.1-70B-Instruct",
        rpm_limit=10,
        rpd_limit=0,
        snage=[
            "brz",
            "besplatan",
        ],
        slabosti=[
            "doslovan prijevod idioma",
            "srbizmi",
            "ponekad miješa jezike",
        ],
        anti_patterne=[
            r"\bneverovatno?\b",
            r"\bposeduje\b",
        ],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.70,
        temp_lektor=0.65,
        temp_validator=0.35,
        max_tokens_chunk=1800,
        notes="Anti_literal patch obavezan.",
    ),

    "deepseek_openrouter": ModelProfile(
        ime="deepseek_openrouter",
        provider="openrouter",
        api_model_string="deepseek/deepseek-chat",
        rpm_limit=10,
        rpd_limit=0,
        snage=[
            "dobar za tehnički tekst",
            "precizan",
        ],
        slabosti=[
            "ponekad engleski fraze u izlazu",
            "formalan",
        ],
        anti_patterne=[
            r"^Sure[,!]?\s",
            r"^Here('s| is)\s",
        ],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.75,
        temp_lektor=0.68,
        temp_validator=0.35,
        max_tokens_chunk=2048,
        notes="Koristiti za tehničku SF literaturu.",
    ),

    "qwen_chutes": ModelProfile(
        ime="qwen_chutes",
        provider="chutes",
        api_model_string="Qwen/Qwen2.5-72B-Instruct",
        rpm_limit=10,
        rpd_limit=0,
        snage=[
            "dobar za dugi kontekst",
            "besplatan",
            "stabilan",
        ],
        slabosti=[
            "ponekad engleski u izlazu",
            "srbizmi",
        ],
        anti_patterne=[
            r"^Sure[,!]?\s",
            r"^Here('s| is)\s",
            r"\bneverovatno?\b",
        ],
        preferred_roles=["prevodilac"],
        blacklisted_roles=["validator", "chapter_summary"],
        temp_prevodilac=0.75,
        temp_lektor=0.68,
        temp_validator=0.35,
        max_tokens_chunk=2048,
        notes="Backup za volume obradu.",
    ),
}


# ─────────────────────────────────────────────────────────────
# POMOĆNE FUNKCIJE
# ─────────────────────────────────────────────────────────────

def get_profil(ime: str) -> Optional[ModelProfile]:
    """Vraća ModelProfile za dati identifikator. None ako nije pronađen."""
    return PROFILI.get(ime)


def get_profili_za_ulogu(uloga: str) -> List[ModelProfile]:
    """Vraća sve profile koji podržavaju danu ulogu (nisu blacklisted)."""
    return [
        p for p in PROFILI.values()
        if uloga in p.preferred_roles
        and uloga not in p.blacklisted_roles
    ]


def get_anti_patterne(ime: str) -> List[str]:
    """Vraća listu regex anti-patterna za dati model."""
    p = PROFILI.get(ime)
    return p.anti_patterne if p else []


def get_temp(ime: str, uloga: str) -> float:
    """Vraća optimalnu temperaturu za dati model i ulogu."""
    p = PROFILI.get(ime)
    if not p:
        return 0.75
    mapping = {
        "prevodilac": p.temp_prevodilac,
        "lektor": p.temp_lektor,
        "validator": p.temp_validator,
    }
    return mapping.get(uloga, p.temp_prevodilac)


def get_max_tokens(ime: str, uloga: str = "prevodilac") -> int:
    """Vraća max_tokens za dati model i ulogu."""
    p = PROFILI.get(ime)
    if not p:
        return 2048
    if uloga == "validator":
        return p.max_tokens_validator
    return p.max_tokens_chunk


if __name__ == "__main__":
    print(f"Učitano profila: {len(PROFILI)}")
    for ime, p in PROFILI.items():
        print(f"  {ime:30s} provider={p.provider:12s} rpm={p.rpm_limit:4d} temp_prev={p.temp_prevodilac}")
