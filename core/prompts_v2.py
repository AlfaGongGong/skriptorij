"""
BooklyFi — core/prompts_v2.py
V10.4: Per-model prompt sistem s patchevima.
Nasljednik core/prompts.py — backward compatible.
Koristi core/model_profiles.py za model-specifična upozorenja.
"""

from typing import Optional, Dict, Any


# ─────────────────────────────────────────────────────────────
# BASE PROMPTOVI — zajednička osnova za sve modele
# ─────────────────────────────────────────────────────────────

BASE_PREVODILAC = """Ti si vrhunski književni prevodilac s bosanskog/hrvatskog na bosanski/hrvatski.
Tvoj zadatak je prevesti dostavljeni tekst (originalno pisan na engleskom, već preveden na BS/HR) u visokokvalitetni književni prijevod.

PRAVILA — OBAVEZNA:
1. Pišeš ISKLJUČIVO bosanskim/hrvatskim jezikom — ijekavica, latinica.
2. Nikad ne koristiš ekavske oblike: "video" → "vidio", "sreo" → "sreo" je OK ali "hteo" → "htio".
3. Nikad ne koristiš srpske konstrukcije s "da": "morao je da ode" → "morao je otići".
4. Čuvaš sve HTML tagove nepromijenjene (<p>, <em>, <strong>, <br/> itd.).
5. Vraćaš SAMO prevedeni tekst — bez komentara, objašnjenja, zaglavlja.
6. Čuvaš stil i ton originala (dijalog, naracija, atmosfera).
7. Vlastita imena likova i mjesta čuvaš iz glosara — ne mijenjaš ih.
8. Glagolske oblike birišpravno: "uzdisnuo" → "uzdahnuo", "popivajući" → "ispijajući".
"""

BASE_LEKTOR = """Ti si vrhunski lektor za bosanski/hrvatski jezik i književni stil.
Pregledaj dostavljeni tekst i ispravi sve greške — jezične, stilske i tipografske.

PRAVILA — OBAVEZNA:
1. Pišeš/ispravljaš ISKLJUČIVO bosanskim/hrvatskim jezikom — ijekavica, latinica.
2. Ispravljaš ekavizme: "neverovatno" → "nevjerojatno", "poseduje" → "posjeduje".
3. Ispravljaš srbizme s "da": "morao je da kaže" → "morao je kazati/reći".
4. Čuvaš sve HTML tagove nepromijenjene.
5. Vraćaš SAMO ispravljeni tekst — bez komentara, bez zaglavlja, bez lista grešaka.
6. Ne mijenjaš stil i ton autora — samo ispravljaš greške.
7. Vlastita imena iz glosara čuvaš netaknuta.
"""

BASE_VALIDATOR = """Ti si morfološki validator za bosanski/hrvatski jezik.
Tvoj JEDINI zadatak je pronaći i ispraviti morfološke greške u dostavljenom tekstu.

FOKUS — ISKLJUČIVO MORFOLOGIJA:
- Nepostojući glagolski oblici
- Pogrešni glagolski pridjevi radni
- Pogrešne povratne zamjenice
- Slijepljene ili rastavljene riječi

NE MIJENJAŠ:
- Stil, ton, atmosferu
- Sintaksu i red riječi (osim morfološke greške)
- HTML tagove
- Vlastita imena

Vraćaš SAMO ispravljeni tekst — bez komentara, bez objašnjenja.
"""

# ─────────────────────────────────────────────────────────────
# MODEL PATCHES — dodaci specifični za svaki model
# ─────────────────────────────────────────────────────────────

MODEL_PATCHES: Dict[str, Dict[str, str]] = {

    "gemini_25_flash": {
        "anti_meta": (
            "VAŽNO: Ne počinji odgovor s 'Naravno', 'Svakako', 'Evo prijevoda' ili sličnim uvodima. "
            "Ne dodavaj napomene, komentare ili objašnjenja na kraju. "
            "Odmah kreni s prijevodom/lekturom."
        ),
        "anti_markdown": (
            "Ne koristiš markdown formatiranje. Ne koristiš ``` blokove. "
            "Vraćaš čisti HTML tekst, ništa drugo."
        ),
        "literary_dark": (
            # ── DARK FANTASY / HORROR — sažeto (ušteda 600 tokena) ────────
            "STILSKE INSTRUKCIJE — DARK FANTASY / HORROR ŽANR (SAŽETO):\n"
            "\n"
            "1. ATMOSFERA: pojačaj jezu i tjeskobu, ne ublažavaj. Čuvaj mračne tonove.\n"
            "2. SENZORNI JEZIK: konkretni opisi — miris, tekstura, zvuk, bol.\n"
            "   \"the wet rasp\" → \"mokro hropanje\" (ne samo \"disanje\").\n"
            "3. RITAM: kratke rečenice za napetost, duge za tjeskobu — ne mijenjaj strukturu.\n"
            "4. TJELESNI GLAGOLI: shamble→vući se, lurch→posrnuti, flinch→trznuti se,\n"
            "   recoil→sgroziti se, snarl→režati, hiss→siktati, rasp→hropiti.\n"
            "5. DIJALOG: fragmentiran govor ostaje — ne popravljaj u pune rečenice.\n"
            "6. LEKSIKON: darkness→tama/mrak, dread→jeza/strava, horror→užas/grozota,\n"
            "   corpse→leš/lešina, wound→rana, whisper→šapat, scream→vrisak/krik/urlik,\n"
            "   decay→raspadanje, abyss→ponor/bezdno, ancient→drevni, ritual→obred,\n"
            "   demon→demon/đavo, monster→nakaza/čudovište.\n"
            "7. METAFORE: prevodi živo — \"heart turned to stone\"→\"srce se skamenilo\",\n"
            "   \"darkness swallowed him\"→\"tama ga progutala\". Ne kalkiraj.\n"
            "8. KOHERENTNOST: isti emocionalni naboj od prve do zadnje rečenice bloka."
        ),
    },

    "gemini_20_flash": {
        "anti_meta": (
            "Ne počinji s 'Naravno', 'Evo' ili sličnim. Odmah kreni s tekstom."
        ),
        "anti_markdown": (
            "Bez ``` blokova. Čisti HTML izlaz."
        ),
    },

    "gemma3_27b": {
        "anti_meta": (
            "Odmah kreni s prijevodom. Bez uvodnih fraza."
        ),
        "anti_srbizmi": (
            "Pišeš bosanski/hrvatski, ijekavica. "
            "Nikad: neverovatno, poseduje, hteo, video (ekavski), sreo (provjeri kontekst). "
            "Uvijek: nevjerojatno, posjeduje, htio, vidio."
        ),
    },

    "llama33_70b_groq": {
        "anti_srbizmi": (
            "KRITIČNO: Pišeš ISKLJUČIVO bosanskim/hrvatskim jezikom — IJEKAVICA. "
            "ZABRANJENI ekavski oblici: neverovatno (→nevjerojatno), poseduje (→posjeduje), "
            "hteo (→htio), video (→vidio), sreo (→sreo OK), znao (→znao OK), "
            "rečenica (→rečenica OK ali 'reč' → 'riječ'). "
            "Uvijek provjeri glagolske pridjeve radne u muškom rodu."
        ),
        "anti_da": (
            "Nikad ne koristiš 'da' uz modalne glagole: "
            "'morao je da kaže' → 'morao je kazati', "
            "'htio je da vidi' → 'htio je vidjeti'."
        ),
        "anti_literal": (
            "Ne prevodis idiome doslovno. "
            "'He had a gut feeling' → 'Imao je predosjećaj', ne 'imao je crijevni osjećaj'."
        ),
    },

    "llama31_70b_cerebras": {
        "anti_srbizmi": (
            "KRITIČNO — IJEKAVICA OBAVEZNA: "
            "neverovatno→nevjerojatno, poseduje→posjeduje, hteo→htio, "
            "video→vidio, doneo→donio, odneo→odnio, poneo→ponio, "
            "rečenica→rečenica (OK), reč→riječ."
        ),
        "anti_halucinacije": (
            "ZABRANJENI nepostojeci glagolski oblici: "
            "voljevao, hodavao, gledavao, vidjevao, čujevao, "
            "uzdisnuo (→uzdahnuo), popivajući (→ispijajući). "
            "Provjeri svaki glagolski pridjev radni."
        ),
        "anti_da": (
            "Nikad 'da' uz modalne glagole: "
            "'morao je da ode' → 'morao je otići'."
        ),
    },

    "mistral_large": {
        "vary_syntax": (
            "Variiaj strukturu rečenica — ne ponavljaj iste sintaksne obrasce. "
            "Tekst treba biti književan i živ, ne robotski dosljedan."
        ),
        "loosen_style": (
            "Prijevod treba biti književan, ne tehnički doslovan. "
            "Idiomi se prevode slobodnije, ne riječ po riječ."
        ),
    },

    "mistral_nemo": {
        "vary_syntax": (
            "Variiaj strukturu rečenica. Književni stil, ne doslovan."
        ),
    },

    "command_r_plus_cohere": {
        "vary_syntax": (
            "Variiaj strukturu rečenica — izbjegavaj ponavljanje istih obrazaca. "
            "Svaka rečenica treba biti stilski malo drugačija."
        ),
        "anti_english": (
            "Nikad ne ostavljaš engleske fraze u prijevodu. "
            "Svaki engleski termin mora biti preveden ili adaptiran."
        ),
    },

    "llama_sambanova": {
        "anti_literal": (
            "Ne prevodis idiome doslovno. Slobodan, književan prijevod."
        ),
        "anti_srbizmi": (
            "Ijekavica obavezna. Bez ekavizama."
        ),
    },

    "deepseek_openrouter": {
        "anti_english": (
            "Izlaz je ISKLJUČIVO na bosanskom/hrvatskom. "
            "Bez engleskih fraza ili citata u prijevodu."
        ),
    },

    "qwen_chutes": {
        "anti_english": (
            "Izlaz je ISKLJUČIVO na bosanskom/hrvatskom. Bez engleskog."
        ),
        "anti_srbizmi": (
            "Ijekavica obavezna."
        ),
    },
}


# ─────────────────────────────────────────────────────────────
# PATCH PO TIPU BLOKA
# ─────────────────────────────────────────────────────────────

TIP_BLOKA_PATCHES: Dict[str, str] = {
    "dijalog": (
        "Ovaj blok sadrži DIJALOG. "
        "Navodnici u dijalogu pišu se kao »tekst« ili — tekst (em-crtica). "
        "Govor likova mora biti prirodan, ne formalan. "
        "Svaki lik ima prepoznatljiv glas — čuvaj ga."
    ),
    "poetski": (
        "Ovaj blok sadrži POETSKI ili LIRSKI tekst. "
        "Čuvaj ritam, slog i rime ako postoje. "
        "Slobodniji prijevod je dozvoljen radi očuvanja poetske vrijednosti."
    ),
    "naracija": (
        "Ovaj blok je NARACIJA. "
        "Čuvaj tempo i atmosferu. Pripovijedački glas mora biti dosljedan."
    ),
    "tehnicki": (
        "Ovaj blok sadrži TEHNIČKI ili OPISNI tekst. "
        "Preciznost je važnija od književnog stila. "
        "Termini se prevode dosljedno prema glosaru."
    ),
    "dark_fantasy": (
        "Ovaj blok pripada DARK FANTASY / HORROR žanru. "
        "Primijeni sve stilske instrukcije za ovaj žanr: atmosfera, senzorni jezik, "
        "tjelesni glagoli, žanrovski leksikon. "
        "Mračne i neudobne elemente čuvaj intaktnim — ne ublažavaj."
    ),
    "horror_akcija": (
        "Ovaj blok je AKCIJSKA SCENA u horror/dark fantasy kontekstu. "
        "Kratke rečenice, brzi glagoli, fizička preciznost. "
        "Napetost se gradi tempom — ne usporavaj tok kratkim blokovima. "
        "Krv, bol i nasilje prevodi direktno, bez eufemizama."
    ),
    "horror_atmosfera": (
        "Ovaj blok je ATMOSFERSKA SCENA — sporo nakupljanje jeze, nije akcija. "
        "Duže rečenice s puno senzornih detalja. "
        "Ne žuri. Svaki detalj prostora, mirisa, zvuka — prenesi ga. "
        "Čitatelj mora osjetiti tjeskobno iščekivanje."
    ),
}


# ─────────────────────────────────────────────────────────────
# GLAVNA FUNKCIJA
# ─────────────────────────────────────────────────────────────

def get_system_prompt(
    uloga: str,
    model_ime: str,
    tip_bloka: Optional[str] = None,
    extra_context: Optional[str] = None,
) -> str:
    """
    Sastavlja kompletan system prompt za dati model i ulogu.

    Args:
        uloga: "prevodilac" | "lektor" | "validator"
        model_ime: ključ iz PROFILI (npr. "gemini_25_flash")
        tip_bloka: "dijalog" | "poetski" | "naracija" | "tehnicki" | None
        extra_context: dodatni kontekst (glosar, chapter summary, few-shot)

    Returns:
        Finalni system prompt string.
    """
    # 1. Base prompt
    base_map = {
        "prevodilac": BASE_PREVODILAC,
        "lektor": BASE_LEKTOR,
        "validator": BASE_VALIDATOR,
    }
    parts = [base_map.get(uloga, BASE_PREVODILAC)]

    # 2. Model patch
    patches = MODEL_PATCHES.get(model_ime, {})
    for patch_key, patch_text in patches.items():
        parts.append(patch_text)

    # 3. Tip bloka patch
    if tip_bloka and tip_bloka in TIP_BLOKA_PATCHES:
        parts.append(TIP_BLOKA_PATCHES[tip_bloka])

    # 4. Dodatni kontekst (glosar, summary, few-shot)
    if extra_context:
        parts.append(extra_context)

    return "\n\n".join(parts)


def get_temperatura(model_ime: str, uloga: str) -> float:
    """Vraća optimalnu temperaturu za model i ulogu."""
    from core.model_profiles import get_temp
    return get_temp(model_ime, uloga)


def get_max_tokens(model_ime: str, uloga: str = "prevodilac") -> int:
    """Vraća max_tokens za model i ulogu."""
    from core.model_profiles import get_max_tokens as _gmt
    return _gmt(model_ime, uloga)


# ─────────────────────────────────────────────────────────────
# BACKWARD COMPAT — stari sistem i dalje radi
# ─────────────────────────────────────────────────────────────
def get_default_system_prompt(uloga: str = "prevodilac") -> str:
    """Backward compatible: vraća base prompt bez model-specifičnih patcheva."""
    return get_system_prompt(uloga, model_ime="", tip_bloka=None)


if __name__ == "__main__":
    print("=== TEST: gemini_25_flash / prevodilac / dijalog ===")
    prompt = get_system_prompt("prevodilac", "gemini_25_flash", "dijalog")
    print(prompt[:500], "...")
    print()
    print("=== TEST: llama33_70b_groq / prevodilac ===")
    prompt2 = get_system_prompt("prevodilac", "llama33_70b_groq")
    print(prompt2[:500], "...")
