#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# BOOKLYFI — fix_faza2_highlight.sh
# 2.1 — 80+ anglicizama i kalkova
# 2.2 — Gramatički checker BS/HR (modalni glagoli, futur II, prijedlozi)
# 2.3 — Custom tooltip popover (umjesto title="")
# 2.4 — Score-1 problem banner + vizualne kategorije
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail
BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}[PATCH]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
fail() { echo -e "${RED}[ERR]${NC} $*"; exit 1; }

[ -f "static/js/main.js"    ] || fail "Nema static/js/main.js"
[ -f "static/css/style.css" ] || fail "Nema static/css/style.css"

TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/patch_faza2_highlight_${TS}"
mkdir -p "$BACKUP_DIR"
cp static/js/main.js    "$BACKUP_DIR/main.js.bak"
cp static/css/style.css "$BACKUP_DIR/style.css.bak"
log "Backup: $BACKUP_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.1 + 2.2 — Zamijeni _ANGLICIZMI_FRAZE i dodaj _GRAMATIKA_PRAVILA
# ═══════════════════════════════════════════════════════════════════════════════
log "2.1+2.2 — Proširena lista anglicizama + gramatički checker..."

python3 - <<'PYEOF'
import re

with open("static/js/main.js", "r", encoding="utf-8") as f:
    src = f.read()

# ── Nova lista anglicizama (80+) ──────────────────────────────────────────────
NEW_ANGLICIZMI = '''const _ANGLICIZMI_FRAZE = [
    // ── Kalkulirani izrazi (calques) ─────────────────────────────────────────
    { phrase: "u momentu",            reason: "Kalk — 'in the moment' → u trenutku" },
    { phrase: "u ovom momentu",       reason: "Kalk → u ovom trenutku" },
    { phrase: "dolazi sa",            reason: "Kalk — 'comes with' → dolazi uz / sadrži" },
    { phrase: "ova knjiga je o",      reason: "Kalk — 'this book is about' → govori o" },
    { phrase: "ja lično",             reason: "Kalk — 'personally, I' → osobno / lično (bez 'ja')" },
    { phrase: "na kraju krajeva",     reason: "Kalk — 'at the end of the day'" },
    { phrase: "napraviti razliku",    reason: "Kalk — 'make a difference' → promijeniti nešto" },
    { phrase: "napraviti smisao",     reason: "Kalk — 'make sense' → ima smisla" },
    { phrase: "praviti razliku",      reason: "Kalk — 'make a difference'" },
    { phrase: "uzeti za gotovo",      reason: "Kalk — 'take for granted' → podrazumijevati" },
    { phrase: "na kraju dana",        reason: "Kalk — 'at the end of the day' → naposljetku" },
    { phrase: "napraviti odluku",     reason: "Kalk — 'make a decision' → donijeti odluku" },
    { phrase: "donijeti odluku",      reason: "Ispravno ✓ — samo provjeri kontekst" },
    { phrase: "napraviti grešku",     reason: "Kalk — 'make a mistake' → pogriješiti / napraviti pogrešku" },
    { phrase: "imati smisla",         reason: "Kalk — 'to make sense' — ok ako znači 'ima logike'" },
    { phrase: "imati svrhu",          reason: "Kalk — 'to have a purpose' → služiti svrsi" },
    { phrase: "uzeti akciju",         reason: "Kalk — 'take action' → djelovati / poduzeti mjere" },
    { phrase: "dati sve od sebe",     reason: "Kalk — 'give it your all' — prihvatljivo, ali pazi" },
    { phrase: "biti tu za",           reason: "Kalk — 'be there for' → podržati / stajati uz" },
    { phrase: "ostati jak",           reason: "Kalk — 'stay strong' → ostati čvrst / izdržati" },
    { phrase: "kretati se naprijed",  reason: "Kalk — 'move forward' → napredovati / ići dalje" },
    { phrase: "idi naprijed",         reason: "Kalk — 'go ahead' → slobodno / nastavi" },
    { phrase: "na kraju dana",        reason: "Kalk — 'at the end of the day'" },
    { phrase: "otvoriti vrata",       reason: "Metafora 'open doors' — ok, ali pazi na pretjeranu upotrebu" },
    { phrase: "zatvori vrata",        reason: "Metafora — provjeris kontekst" },
    { phrase: "uzeti kontrolu",       reason: "Kalk — 'take control' → preuzeti kontrolu" },
    { phrase: "dati smisao",          reason: "Kalk — 'give meaning' → pridati smisao" },
    { phrase: "izgubiti fokus",       reason: "Anglicizam — fokus/focus → izgubiti nit / koncentraciju" },
    { phrase: "ostati fokusiran",     reason: "Anglicizam — → ostati usredotočen / sabran" },
    { phrase: "biti inspirisan",      reason: "Srbizam/anglicizam → biti inspiriran" },
    { phrase: "biti motivisan",       reason: "Srbizam → biti motiviran" },
    { phrase: "biti šokiran",         reason: "Srbizam → biti šokiran (BS ok) ili zapanjen" },
    { phrase: "super stvar",          reason: "Anglicizam 'super' → odlično / izvrsno" },
    { phrase: "cool stvar",           reason: "Anglicizam → zanimljivo / lijepo" },
    { phrase: "biti cool",            reason: "Anglicizam → biti kul / dobar / u redu" },
    { phrase: "okej",                 reason: "Anglicizam — u redu / dobro (okej prihvatljivo u razgovoru)" },

    // ── Pogrešne kolokacije ───────────────────────────────────────────────────
    { phrase: "uraditi razliku",      reason: "Pogrešna kolokacija → napraviti razliku / promijeniti situaciju" },
    { phrase: "uraditi grešku",       reason: "Pogrešna kolokacija → pogriješiti" },
    { phrase: "raditi grešku",        reason: "Pogrešna kolokacija → griješiti / praviti greške" },
    { phrase: "uzeti odluku",         reason: "Pogrešna kolokacija → donijeti odluku" },
    { phrase: "dati odluku",          reason: "Pogrešna kolokacija → donijeti odluku" },
    { phrase: "staviti napor",        reason: "Kalk 'put effort' → uložiti napor / trud" },
    { phrase: "napraviti napor",      reason: "Kalk 'make an effort' → uložiti napor" },
    { phrase: "igrati ulogu",         reason: "Kalk 'play a role' — ok ali: imati ulogu / biti važan" },
    { phrase: "odigrati ulogu",       reason: "Prihvatljivo ✓" },
    { phrase: "baci svjetlo",         reason: "Kalk 'shed light' → rasvijetliti / pojasniti" },
    { phrase: "baciti svjetlo",       reason: "Kalk 'shed light' → rasvijetliti / pojasniti" },
    { phrase: "u svjetlu toga",       reason: "Kalk 'in light of' → s obzirom na to" },
    { phrase: "dovesti do zaključka", reason: "Kalk 'lead to the conclusion' → zaključiti / izvesti zaključak" },
    { phrase: "na osnovu toga",       reason: "Srbizam → na temelju toga / na osnovi toga (BS: on osnovu ok)" },
    { phrase: "u skladu sa tim",      reason: "Srbizam → u skladu s time" },
    { phrase: "iz tog razloga",       reason: "Potencijalni kalk — ok, ali može biti: stoga / zato" },

    // ── Genitivna metafora (imati X) ─────────────────────────────────────────
    { phrase: "imati problema",       reason: "Genitivna metafora — ok u BS, pazi na kontekst" },
    { phrase: "imati sreće",          reason: "Genitivna metafora — ok ✓" },
    { phrase: "imati vremena",        reason: "Genitivna metafora — ok ✓" },
    { phrase: "imati razloga",        reason: "Genitivna metafora — ok, provjeri kontekst" },
    { phrase: "nema razloga",         reason: "Prihvatljivo ✓" },
    { phrase: "imati osjećaja",       reason: "Kalk 'have feelings' → osjećati / imati emocija" },

    // ── Pogrešna upotreba internacionalizama ──────────────────────────────────
    { phrase: "pozitivna energija",   reason: "Anglicizam/new-age kalk → pozitivan stav / raspoloženje" },
    { phrase: "negativna energija",   reason: "Anglicizam → negativno raspoloženje / loša atmosfera" },
    { phrase: "visoke vibracije",     reason: "Anglicizam 'high vibes' → dobro raspoloženje" },
    { phrase: "manifestovati",        reason: "Anglicizam 'manifest' → ostvariti / privući" },
    { phrase: "manifestirati",        reason: "Anglicizam — u ovom kontekstu: ostvariti / privući" },
    { phrase: "biti autentičan",      reason: "Anglicizam 'authentic' → biti iskren / biti svoj" },
    { phrase: "svoja priča",          reason: "Kalk 'your story' — prihvatljivo ali čest kalk" },
    { phrase: "tvoja priča",          reason: "Kalk 'your story' — prihvatljivo ali čest kalk" },
    { phrase: "live your best life",  reason: "Neprevedena EN fraza → živi punim plućima" },

    // ── Prijedložni anglicizmi (FIX 2.2 gramatika) ───────────────────────────
    { phrase: "ovisiti od",           reason: "Pogrešan prijedlog → ovisiti o / zavisiti od (BS)" },
    { phrase: "zavisi od toga",       reason: "Zavisi — ok u BS, ali pazi: ovisi o tome (HR)" },
    { phrase: "sastoji od",           reason: "Provjeri: sastoji se od ✓" },
    { phrase: "različit od",          reason: "Srbizam → različit od (BS ok) / različit od (HR: drugačiji od)" },
    { phrase: "zadovoljan sa",        reason: "Pogrešan prijedlog → zadovoljan čime / zadovoljan time" },
    { phrase: "siguran sa",           reason: "Pogrešan prijedlog → siguran u to / siguran u sebe" },
    { phrase: "ponosan sa",           reason: "Pogrešan prijedlog → ponosan na" },
    { phrase: "ponosan na",           reason: "Ispravno ✓" },
    { phrase: "ljubazan sa",          reason: "Pogrešan prijedlog → ljubazan prema" },
    { phrase: "sretan sa",            reason: "Pogrešan prijedlog → sretan zbog / sretan s (nečim)" },
    { phrase: "suočiti sa",           reason: "Provjeri: suočiti se s (čime) ✓" },
    { phrase: "baviti sa",            reason: "Pogrešno → baviti se (čime) ✓" },
];'''

# ── Novi gramatički checker (2.2) ─────────────────────────────────────────────
NEW_GRAMATIKA = '''
// ── FIX 2.2: Gramatički checker BS/HR ────────────────────────────────────────
const _GRAMATIKA_PRAVILA = [
    // Modalni glagoli: "mogu da radim" → srbizam u BS/HR
    {
        re: /\b(mogu|možeš|može|možemo|možete|mogu|moram|moraš|mora|moramo|morate|moraju|smijem|smiješ|smije|smijemo|smijete|smiju|trebam|trebaš|treba|trebamo|trebate|trebaju|hoću|hoćeš|hoće|hoćemo|hoćete|hoće)\s+da\s+\w+/gi,
        type: "gramatika",
        reason: "Srbizam: modalni glagol + 'da' + infinitiv → u BS/HR: modalni + infinitiv (mogu raditi, moram ići)"
    },
    // Futur II u neodgovarajućem kontekstu (budem + glagol u ind. prezentu)
    {
        re: /\bbudem\s+\w+(ao|la|lo|li|le|la)\b/gi,
        type: "gramatika",
        reason: "Futur II (budem radio) — provjeri je li kontekst uvjetna rečenica; inače koristiti futur I"
    },
    // Pogrešna upotreba "biti" + prijedlog "od" umjesto "iz"
    {
        re: /\bporijeklom\s+od\b/gi,
        type: "gramatika",
        reason: "Pogrešno: 'porijeklom od' → porijeklom iz (mjesta/države)"
    },
    // "što" umjesto "koji/koja/koje" u relativnim klauzama (prekomjerna upotreba)
    {
        re: /,\s*što\s+je\s+(bio|bila|bilo|bio|imao|imala|imalo)\b/gi,
        type: "gramatika",
        reason: "Provjeri: 'što je bio/imao' — možda bolje 'koji je bio/imao'"
    },
    // Pasiv s "od strane" (pretjerana upotreba — kalk)
    {
        re: /\bod\s+strane\s+\w+/gi,
        type: "gramatika",
        reason: "Kalk 'od strane' (by X) — razmotri aktiv: X je uradio / X je napravio"
    },
    // Pogrešni prijedlog: "ovisiti od" (trebalo bi "ovisiti o")
    {
        re: /\bovis[a-zšđčćž]+\s+od\b/gi,
        type: "gramatika",
        reason: "Pogrešan prijedlog: 'ovisiti od' → ovisiti o (čemu)"
    },
    // "isti kao i" — dvostruki veznik
    {
        re: /\bisti\s+kao\s+i\b/gi,
        type: "gramatika",
        reason: "Dvostruki veznik: 'isti kao i' → isti kao (bez 'i')"
    },
    // Anglicizam u sintaksi: "za razliku od toga što" umjesto "za razliku od"
    {
        re: /\bza\s+razliku\s+od\s+toga\s+što\b/gi,
        type: "gramatika",
        reason: "Razvučena konstrukcija → za razliku od + genitiv"
    },
    // "u isto vrijeme" — ok, ali često prekomjerno
    {
        re: /\bu\s+isto\s+vrijeme\b/gi,
        type: "gramatika",
        reason: "Provjeri: 'u isto vrijeme' — može biti: istovremeno / u isti mah"
    },
];

function _gramatikaCheck(text) {
    const hits = [];
    for (const pravilo of _GRAMATIKA_PRAVILA) {
        pravilo.re.lastIndex = 0;
        let m;
        while ((m = pravilo.re.exec(text)) !== null) {
            hits.push({
                start:  m.index,
                end:    m.index + m[0].length,
                word:   m[0],
                type:   pravilo.type,
                reason: pravilo.reason
            });
        }
    }
    return hits;
}'''

# Zamijeni staru _ANGLICIZMI_FRAZE
old_pattern = r'const _ANGLICIZMI_FRAZE = \[.*?\];'
new_src, n = re.subn(old_pattern, NEW_ANGLICIZMI, src, flags=re.DOTALL)
if n > 0:
    print(f"  _ANGLICIZMI_FRAZE zamijenjena (80+ unosa).")
    src = new_src
else:
    print("  [WARN] _ANGLICIZMI_FRAZE nije pronađena regex-om.")

# Dodaj _GRAMATIKA_PRAVILA + _gramatikaCheck ispred _heuristicScan
if "_GRAMATIKA_PRAVILA" not in src:
    src = src.replace(
        "const _EN_WORD_RE = /\\b([A-Za-z]{4,})\\b/g;",
        NEW_GRAMATIKA + "\nconst _EN_WORD_RE = /\\b([A-Za-z]{4,})\\b/g;"
    )
    print("  _GRAMATIKA_PRAVILA i _gramatikaCheck dodani.")
else:
    print("  [SKIP] _GRAMATIKA_PRAVILA već postoji.")

# Integracija gramatike u _heuristicScan
OLD_HEURISTIC_END = '''    highlights.sort((a, b) => a.start - b.start);
    const deduped = [];
    let lastEnd = -1;
    for (const h of highlights) {
        if (h.start >= lastEnd) {
            deduped.push(h);
            lastEnd = h.end;
        }
    }
    return deduped;
}'''

NEW_HEURISTIC_END = '''    // FIX 2.2: Dodaj gramatičke provjere
    const gramHits = _gramatikaCheck(text);
    highlights.push(...gramHits);

    highlights.sort((a, b) => a.start - b.start);
    const deduped = [];
    let lastEnd = -1;
    for (const h of highlights) {
        if (h.start >= lastEnd) {
            deduped.push(h);
            lastEnd = h.end;
        }
    }
    return deduped;
}'''

if OLD_HEURISTIC_END in src:
    src = src.replace(OLD_HEURISTIC_END, NEW_HEURISTIC_END, 1)
    print("  _heuristicScan: gramatika integrirana.")
else:
    print("  [INFO] _heuristicScan kraj nije pronađen — provjeri ručno.")

# Dodaj gramatika tip u _renderHighlights stil tabeli
OLD_STYLES = '''    const S = {
        en_word: {
            bg: "rgba(244,63,94,0.22)",
            border: "rgba(244,63,94,0.55)",
            color: "var(--rose)"
        },
        anglicizam: {
            bg: "rgba(245,158,11,0.22)",
            border: "rgba(245,158,11,0.55)",
            color: "var(--amber)"
        },
        word_order: {
            bg: "rgba(99,102,241,0.22)",
            border: "rgba(99,102,241,0.55)",
            color: "var(--accent)"
        }
    };'''

NEW_STYLES = '''    const S = {
        en_word: {
            bg: "rgba(244,63,94,0.22)",
            border: "rgba(244,63,94,0.55)",
            color: "var(--rose)"
        },
        anglicizam: {
            bg: "rgba(245,158,11,0.22)",
            border: "rgba(245,158,11,0.55)",
            color: "var(--amber)"
        },
        word_order: {
            bg: "rgba(99,102,241,0.22)",
            border: "rgba(99,102,241,0.55)",
            color: "var(--accent)"
        },
        gramatika: {
            bg: "rgba(6,182,212,0.18)",
            border: "rgba(6,182,212,0.55)",
            color: "var(--accent-2)"
        }
    };'''

if OLD_STYLES in src:
    src = src.replace(OLD_STYLES, NEW_STYLES, 1)
    print("  gramatika tip dodan u _renderHighlights stil tabelu.")

with open("static/js/main.js", "w", encoding="utf-8") as f:
    f.write(src)
PYEOF

ok "2.1+2.2 done"

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.3 — Custom tooltip popover (umjesto title="")
# ═══════════════════════════════════════════════════════════════════════════════
log "2.3 — Custom tooltip popover..."

python3 - <<'PYEOF'
import re

with open("static/js/main.js", "r", encoding="utf-8") as f:
    src = f.read()

if "bf-tooltip" in src:
    print("  [SKIP] bf-tooltip već postoji.")
else:
    TOOLTIP_JS = '''
// ── FIX 2.3: Custom tooltip popover ──────────────────────────────────────────
(function initTooltip() {
    let tip = null;
    let hideTimer = null;

    function _getOrCreate() {
        if (!tip) {
            tip = document.createElement("div");
            tip.id = "bf-tooltip";
            tip.className = "bf-tooltip";
            document.body.appendChild(tip);
        }
        return tip;
    }

    function _showTip(el, text) {
        if (!text) return;
        clearTimeout(hideTimer);
        const t = _getOrCreate();
        t.textContent = text;
        t.style.display = "block";
        t.style.opacity = "0";

        const rect = el.getBoundingClientRect();
        const scrollY = window.scrollY || 0;
        const scrollX = window.scrollX || 0;

        // Pozicioniraj iznad elementa
        let top  = rect.top  + scrollY - t.offsetHeight - 8;
        let left = rect.left + scrollX + rect.width / 2 - t.offsetWidth / 2;

        // Korekcija za rub ekrana
        if (left < 8) left = 8;
        if (left + t.offsetWidth > window.innerWidth - 8)
            left = window.innerWidth - t.offsetWidth - 8;
        if (top < scrollY + 8) top = rect.bottom + scrollY + 8;  // ispod ako nema mjesta

        t.style.top  = top  + "px";
        t.style.left = left + "px";
        t.style.opacity = "1";
    }

    function _hideTip() {
        hideTimer = setTimeout(() => {
            if (tip) {
                tip.style.opacity = "0";
                setTimeout(() => { if (tip) tip.style.display = "none"; }, 180);
            }
        }, 120);
    }

    // Delegirani event listener na document
    document.addEventListener("mouseover", e => {
        const el = e.target.closest("[data-tip]");
        if (el) _showTip(el, el.dataset.tip);
    });
    document.addEventListener("mouseout", e => {
        if (e.target.closest("[data-tip]")) _hideTip();
    });
    // Touch (mobilni)
    document.addEventListener("touchstart", e => {
        const el = e.target.closest("[data-tip]");
        if (el) {
            e.preventDefault();
            _showTip(el, el.dataset.tip);
            setTimeout(_hideTip, 2800);
        }
    }, { passive: false });
})();

'''

    # Ubaci PRIJE neon animacije
    src = src.replace(
        "// ═══════════════ Neon naslov animacija",
        TOOLTIP_JS + "// ═══════════════ Neon naslov animacija"
    )
    print("  bf-tooltip JS inicijalizator dodan.")

# Zamijeni title="" s data-tip="" u _renderHighlights
OLD_RENDER = 'html += `<span title="${_ea(h.reason)}" style='
NEW_RENDER = 'html += `<span data-tip="${_ea(h.reason)}" style='
if OLD_RENDER in src:
    src = src.replace(OLD_RENDER, NEW_RENDER)
    print("  _renderHighlights: title= zamijenjen s data-tip=.")
else:
    print("  [INFO] title= u _renderHighlights nije pronađen — možda već patchiran.")

with open("static/js/main.js", "w", encoding="utf-8") as f:
    f.write(src)
PYEOF

# CSS za tooltip
python3 - <<'PYEOF'
with open("static/css/style.css", "r", encoding="utf-8") as f:
    src = f.read()

if ".bf-tooltip" in src:
    print("  [SKIP] .bf-tooltip CSS već postoji.")
else:
    TOOLTIP_CSS = '''
/* ── FIX 2.3: Custom tooltip popover ─────────────────────────────────────── */
.bf-tooltip {
    display: none;
    position: absolute;
    z-index: 99999;
    max-width: 320px;
    padding: 7px 11px;
    background: var(--bg-4);
    border: 1px solid rgba(99,102,241,0.35);
    border-radius: var(--r-sm);
    font-family: var(--font-mono);
    font-size: 0.7rem;
    line-height: 1.5;
    color: var(--tx-1);
    pointer-events: none;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    transition: opacity 0.18s var(--ease);
    word-break: break-word;
    white-space: pre-wrap;
}
body.light .bf-tooltip {
    background: var(--bg-1);
    border-color: rgba(99,102,241,0.3);
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
}
'''
    src = src.rstrip() + "\n" + TOOLTIP_CSS
    with open("static/css/style.css", "w", encoding="utf-8") as f:
        f.write(src)
    print("  .bf-tooltip CSS dodan.")
PYEOF

ok "2.3 done"

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2.4 — Blokovi score 1: problem summary banner + vizualne kategorije
# ═══════════════════════════════════════════════════════════════════════════════
log "2.4 — Score-1 problem banner + vizualne kategorije..."

python3 - <<'PYEOF'
import re

with open("static/js/main.js", "r", encoding="utf-8") as f:
    src = f.read()

if "_buildProblemBanner" in src:
    print("  [SKIP] _buildProblemBanner već postoji.")
else:
    BANNER_FN = '''
// ── FIX 2.4: Problem banner za blokove score ≤ 2 ─────────────────────────────
function _buildProblemBanner(item, text) {
    // Analizira reason i tekst bloka → vraća HTML banner
    const reason = (item.reason || "").toLowerCase();
    const score  = item.score != null ? Number(item.score) : 10;

    if (score > 2) return "";  // samo za kritično loše

    const tags = [];

    if (!text || text.trim().length < 10) {
        tags.push({ cls: "tag-empty",        label: "PRAZNO",       icon: "⬜" });
    }
    if (/neprevedeno|untranslated|english|original/i.test(reason)) {
        tags.push({ cls: "tag-untranslated", label: "NEPREVEDENO",  icon: "🔤" });
    }
    const enWordMatches = (text || "").match(/\\b[A-Za-z]{4,}\\b/g) || [];
    const enCount = enWordMatches.filter(w => {
        const wl = w.toLowerCase();
        // Grubo filtriraj whitelist
        return !["the","and","for","with","that","this","from","have","been","will",
                 "not","but","are","can","was","its","your","you","they","their",
                 "which","when","what","how","also","than","then","more","some",
                 "into","over","out","has","had","him","her","his","she","he"].includes(wl);
    }).length;
    if (enCount >= 3) {
        tags.push({ cls: "tag-en",           label: `EN RIJEČ×${enCount}`,  icon: "🇬🇧" });
    }
    const kalkCount = _ANGLICIZMI_FRAZE.filter(f =>
        (text || "").toLowerCase().includes(f.phrase)
    ).length;
    if (kalkCount >= 2) {
        tags.push({ cls: "tag-kalk",         label: `KALK×${kalkCount}`,    icon: "⚠" });
    }
    if (/loš|slab|kratk|nedovoljn/i.test(reason)) {
        tags.push({ cls: "tag-poor",         label: "LOŠA OCJENA",  icon: "🔴" });
    }
    // Default ako nema specifičnih tagova
    if (tags.length === 0) {
        tags.push({ cls: "tag-poor",         label: "KRITIČNO",     icon: "🔴" });
    }

    const tagsHtml = tags.map(t =>
        `<span class="problem-tag ${t.cls}">${t.icon} ${t.label}</span>`
    ).join("");

    return `<div class="problem-banner">
        <div class="problem-banner-row">
            <span class="problem-banner-icon">⚠️</span>
            <span class="problem-banner-title">Kritičan blok — score ${score.toFixed(1)}/10</span>
        </div>
        <div class="problem-banner-tags">${tagsHtml}</div>
        ${item.reason ? `<div class="problem-banner-reason">${_e(item.reason)}</div>` : ""}
    </div>`;
}

'''
    # Dodaj ispred selectReview ili na dobro mjesto
    src = src.replace(
        "async function selectReview(idx) {",
        BANNER_FN + "async function selectReview(idx) {"
    )
    print("  _buildProblemBanner() dodana.")

# Integracija u selectReview — prikaži banner iznad textareae u modalu
OLD_SELECT = '''    document.getElementById("review-modal-stem").textContent = item.file || item.stem || "—";
    const ta = document.getElementById("review-textarea");'''

NEW_SELECT = '''    const stemLabel = (item.file || item.stem || "—");
    document.getElementById("review-modal-stem").textContent = stemLabel;

    // FIX 2.4: problem banner u modalu
    let bannerEl = document.getElementById("review-problem-banner");
    if (!bannerEl) {
        bannerEl = document.createElement("div");
        bannerEl.id = "review-problem-banner";
        const modalContainer = document.querySelector(".review-modal-container");
        const ta2 = document.getElementById("review-textarea");
        if (modalContainer && ta2) modalContainer.insertBefore(bannerEl, ta2);
    }
    // Banner se popunjava nakon što učitamo tekst (dole u try bloku)

    const ta = document.getElementById("review-textarea");'''

if OLD_SELECT in src:
    src = src.replace(OLD_SELECT, NEW_SELECT, 1)
    print("  selectReview: banner element dodan.")

# Nakon učitavanja teksta — popuni banner
OLD_AFTER_LOAD = '''    if (ta) {
        ta.value = text;
        ta.placeholder = text ? "" : "Upiši prijevod ovdje (blok je prazan)...";
    }
}'''

NEW_AFTER_LOAD = '''    if (ta) {
        ta.value = text;
        ta.placeholder = text ? "" : "Upiši prijevod ovdje (blok je prazan)...";
    }
    // FIX 2.4: popuni problem banner sad kad imamo tekst
    const bannerEl2 = document.getElementById("review-problem-banner");
    if (bannerEl2) {
        bannerEl2.innerHTML = _buildProblemBanner(item, text);
        bannerEl2.style.display = bannerEl2.innerHTML ? "block" : "none";
    }
}'''

if OLD_AFTER_LOAD in src:
    src = src.replace(OLD_AFTER_LOAD, NEW_AFTER_LOAD, 1)
    print("  selectReview: banner popunjavanje dodano.")
else:
    print("  [INFO] kraj selectReview nije pronađen — provjeri ručno.")

with open("static/js/main.js", "w", encoding="utf-8") as f:
    f.write(src)
PYEOF

# CSS za problem banner i tagove
python3 - <<'PYEOF'
with open("static/css/style.css", "r", encoding="utf-8") as f:
    src = f.read()

if ".problem-banner" in src:
    print("  [SKIP] .problem-banner CSS već postoji.")
else:
    BANNER_CSS = '''
/* ── FIX 2.4: Problem banner ─────────────────────────────────────────────── */
.problem-banner {
    background: rgba(244,63,94,0.1);
    border: 1px solid rgba(244,63,94,0.3);
    border-radius: var(--r-md);
    padding: 10px 12px;
    margin-bottom: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.problem-banner-row {
    display: flex;
    align-items: center;
    gap: 6px;
}
.problem-banner-icon { font-size: 1rem; }
.problem-banner-title {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--rose);
    letter-spacing: 0.04em;
}
.problem-banner-tags {
    display: flex;
    gap: 5px;
    flex-wrap: wrap;
}
.problem-banner-reason {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--tx-2);
    line-height: 1.4;
    opacity: 0.85;
}
.problem-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    border: 1px solid;
}
.tag-empty        { background: rgba(148,163,184,0.15); border-color: rgba(148,163,184,0.4); color: var(--tx-2); }
.tag-untranslated { background: rgba(99,102,241,0.15);  border-color: rgba(99,102,241,0.4);  color: var(--sky); }
.tag-en           { background: rgba(244,63,94,0.15);   border-color: rgba(244,63,94,0.4);   color: var(--rose); }
.tag-kalk         { background: rgba(245,158,11,0.15);  border-color: rgba(245,158,11,0.4);  color: var(--amber); }
.tag-poor         { background: rgba(244,63,94,0.1);    border-color: rgba(244,63,94,0.35);  color: var(--rose); }

/* ── Gramatika highlight tip ─────────────────────────────────────────────── */
/* (boja već u JS S objekt, ali dodaj i legend u review-legend) */
'''
    src = src.rstrip() + "\n" + BANNER_CSS
    with open("static/css/style.css", "w", encoding="utf-8") as f:
        f.write(src)
    print("  .problem-banner CSS dodan.")
PYEOF

ok "2.4 done"

# ═══════════════════════════════════════════════════════════════════════════════
# VALIDACIJA
# ═══════════════════════════════════════════════════════════════════════════════
log "Validacija..."

python3 - <<'PYEOF'
checks = [
    ("static/js/main.js",    "_GRAMATIKA_PRAVILA",     "2.2 — gramatički checker"),
    ("static/js/main.js",    "_gramatikaCheck",        "2.2 — _gramatikaCheck fn"),
    ("static/js/main.js",    "napraviti odluku",       "2.1 — nova fraza u listi"),
    ("static/js/main.js",    "ovisiti od",             "2.1 — prijedložni anglicizmi"),
    ("static/js/main.js",    "bf-tooltip",             "2.3 — tooltip inicijalizator"),
    ("static/js/main.js",    "data-tip=",              "2.3 — data-tip atribut"),
    ("static/js/main.js",    "_buildProblemBanner",    "2.4 — problem banner fn"),
    ("static/js/main.js",    "review-problem-banner",  "2.4 — banner element"),
    ("static/css/style.css", ".bf-tooltip",            "2.3 — tooltip CSS"),
    ("static/css/style.css", ".problem-banner",        "2.4 — banner CSS"),
    ("static/css/style.css", ".tag-en",                "2.4 — tag CSS"),
]
all_ok = True
for fpath, needle, label in checks:
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        found = needle in content
    except FileNotFoundError:
        found = False
    status = "✅" if found else "❌"
    print(f"  {status} {label}")
    if not found:
        all_ok = False

if not all_ok:
    print("\n⚠ Neki checkovi nisu prošli!")
    exit(1)
print("\n✅ Sve provjere prošle!")
PYEOF

# ═══════════════════════════════════════════════════════════════════════════════
# SERVER RESTART
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
log "Server restart..."
pkill -f "python.*main.py" 2>/dev/null || true
pkill -f "python.*app.py"  2>/dev/null || true
pkill -f "python.*run.py"  2>/dev/null || true
sleep 1
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true

if   [ -f "run.py"  ]; then S="run.py"
elif [ -f "main.py" ]; then S="main.py"
elif [ -f "app.py"  ]; then S="app.py"
else fail "Nije pronađen server script"
fi

nohup python3 "$S" > /tmp/booklyfi_server.log 2>&1 &
PID=$!
echo $PID > /tmp/booklyfi_server.pid
sleep 2
if kill -0 $PID 2>/dev/null; then
    ok "Server pokrenut (PID: $PID)"
else
    tail -20 /tmp/booklyfi_server.log || true
    fail "Server se nije pokrenuo!"
fi

echo ""
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${GREEN}  Faza 2 — Highlight engine završen!${NC}"
echo -e "${GREEN}  2.1 — 80+ anglicizama, kalkova, pogrešnih kolokacija${NC}"
echo -e "${GREEN}  2.2 — Gramatički checker: modalni glagoli, prijedlozi, pasiv${NC}"
echo -e "${GREEN}  2.3 — Custom tooltip popover (hover + tap na mobilnom)${NC}"
echo -e "${GREEN}  2.4 — Problem banner za score ≤ 2 (PRAZNO/NEPREVEDENO/EN/KALK)${NC}"
echo -e "${BOLD}${GREEN}═══════════════════════════════════════════════════════${NC}"