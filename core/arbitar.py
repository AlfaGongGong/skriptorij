"""P2.5: arbitraza nalaza verifikatora (kriv_smisao).

Cista logika, bez mreze i bez AI poziva. AI poziv se ubacuje izvana.
Ovdje: predfilter, trazenje fragmenta u sirovom .chk, provjera zamjene,
prompt, parsiranje odgovora.
"""
import json
import re
from pathlib import Path

PRESUDE = ("stvarna_greska", "lazni_alarm", "nesigurno")

_PREDFILTER_RX = re.compile(
    r"(?:^|[.;:]\s*)(?:to[čc]no|ispravno)\s*[.!]?\s*$"
    r"|prihvatljiv|provjerit [ćc]u|sinonim|nije pogre[šs]n|je to[čc]no",
    re.IGNORECASE,
)


def predfilter(g):
    """(True, "") ako nalaz ide arbitru; (False, razlog) ako ga treba odbaciti bez AI poziva."""
    hr = (g.get("hr_fragment") or "").strip()
    obj = (g.get("objasnjenje") or "").strip()
    if not hr:
        return False, "prazan_hr_fragment"
    if obj and _PREDFILTER_RX.search(obj):
        return False, "verifikator_sam_opovrgava"
    return True, ""


def nadji_u_raw(raw, fragment):
    """(start, end) ako se fragment pojavljuje TOCNO jednom u sirovom tekstu
    (razmaci tolerantni, velika/mala slova se razlikuju, bez oznaka usred fragmenta), inace None."""
    toks = (fragment or "").split()
    if not toks:
        return None
    rx = re.compile(r"(?<!\w)" + r"\s+".join(re.escape(t) for t in toks) + r"(?!\w)")
    ms = list(rx.finditer(raw or ""))
    if len(ms) != 1:
        return None
    return ms[0].span()


def primijeni(raw, fragment, zamjena):
    """Vraca novi raw ili None ako fragment nije jednoznacno nadjen."""
    sp = nadji_u_raw(raw, fragment)
    if sp is None:
        return None
    return raw[: sp[0]] + zamjena + raw[sp[1]:]


def _plain(t):
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def kontekst_oko(plain_tekst, fragment, n=220):
    i = (plain_tekst or "").find((fragment or "").strip())
    if i < 0:
        return ""
    return plain_tekst[max(0, i - n): i + len(fragment) + n]


def rijecnik_knjige(chk_dir):
    """Skup rijeci (mala slova) iz svih .chk blokova knjige."""
    rj = set()
    for p in Path(chk_dir).glob("*.chk"):
        for w in re.findall(r"\w+", _plain(p.read_text("utf-8", "ignore")).lower()):
            rj.add(w)
    return rj


def nove_rijeci(zamjena, fragment, rijecnik):
    stare = set(re.findall(r"\w+", (fragment or "").lower()))
    return [w for w in re.findall(r"\w+", (zamjena or "").lower())
            if w not in rijecnik and w not in stare]


def provjeri_zamjenu(fragment, zamjena, rijecnik):
    """(True, "") ako je zamjena sigurna za automatsku primjenu."""
    f = (fragment or "").strip()
    z = (zamjena or "").strip()
    if not z:
        return False, "prazna_zamjena"
    if z == f:
        return False, "ista_kao_original"
    if re.search(r"[<>\n]", z):
        return False, "oznake_ili_novi_red"
    r = len(z) / max(1, len(f))
    if r < 0.4 or r > 2.5:
        return False, "duljina_%.1f" % r
    if rijecnik is not None:
        nr = nove_rijeci(z, f, rijecnik)
        if nr:
            return False, "nova_rijec:" + ",".join(nr[:4])
    return True, ""


def napravi_prompt(en, hr, obj, kontekst):
    return (
        "Ti si strogi urednik prijevoda s engleskog na hrvatski. Automatski verifikator je prijavio "
        "mogucu gresku smisla. Verifikator cesto griješi, zato presudi sam.\n\n"
        "EN fragment: %s\n" % (en or "(nije naveden)")
        + "HR fragment: %s\n" % hr
        + "Okolni HR tekst: %s\n" % kontekst
        + "Tvrdnja verifikatora: %s\n\n" % (obj or "(prazno)")
        + "Odgovori ISKLJUCIVO JSON-om, bez teksta oko njega:\n"
        '{"presuda": "stvarna_greska" | "lazni_alarm" | "nesigurno", "zamjena": "...", "razlog": "..."}\n'
        "Pravila: presuda je stvarna_greska samo ako HR fragment stvarno mijenja smisao ili je besmislen. "
        "Slobodniji ili idiomatski prijevod koji cuva smisao je lazni_alarm. "
        "Zamjena je novi tekst koji zamjenjuje TOCNO HR fragment (isti oblik, padez i interpunkcija, "
        "bez HTML-a, bez novih redova), samo za stvarna_greska, inace prazan string. "
        "Ne izmisljaj rijeci; koristi pravilne hrvatske rijeci. Ako nisi siguran, odgovori nesigurno."
    )


def parsiraj_odgovor(txt):
    """dict {presuda, zamjena, razlog} ili None."""
    m = re.search(r"\{.*\}", txt or "", flags=re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("presuda") not in PRESUDE:
        return None
    return {"presuda": d["presuda"],
            "zamjena": str(d.get("zamjena") or "").strip(),
            "razlog": str(d.get("razlog") or "").strip()}


# ── P2.5.2b: slijepa arbitraza (arbitar NE vidi tvrdnju verifikatora) ────────
SLIJEPE = ("ekvivalentno", "razlicito", "nesigurno")


def _json(txt):
    m = re.search(r"\{.*\}", txt or "", flags=re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) else None


def prompt_slijepo(en, hr, kontekst):
    return (
        "Ti si strogi, ali pravedan urednik prijevoda s engleskog na hrvatski.\n\n"
        "EN fragment: %s\nHR fragment (iz prijevoda): %s\nOkolni HR tekst: %s\n\n" % (en or "(nije naveden)", hr, kontekst)
        + "Zadatak: 1) kratko napisi sto EN fragment znaci u ovom kontekstu (moj_smisao). "
        "2) Presudi: \"ekvivalentno\" = HR prenosi isti smisao, makar slobodnije, idiomatski ili uz lokalnu prilagodbu "
        "(sleng, idiom, psovka prilagodjena hrvatskom); \"razlicito\" = HR mijenja ili gubi smisao, ili je besmisleno; "
        "\"nesigurno\" = ne mozes procijeniti bez vise konteksta.\n"
        "Odgovori ISKLJUCIVO JSON-om: {\"moj_smisao\": \"...\", \"presuda\": \"ekvivalentno\"|\"razlicito\"|\"nesigurno\", \"razlog\": \"...\"}"
    )


def parsiraj_slijepo(txt):
    d = _json(txt)
    if not d or d.get("presuda") not in SLIJEPE:
        return None
    return {"moj_smisao": str(d.get("moj_smisao") or "").strip(),
            "presuda": d["presuda"], "razlog": str(d.get("razlog") or "").strip()}


def prompt_zamjena(en, hr, kontekst, smisao):
    return (
        "EN fragment: %s\nZnacenje: %s\nHR fragment koji treba ispraviti: %s\nOkolni HR tekst: %s\n\n" % (en or "", smisao, hr, kontekst)
        + "Napisi MINIMALNU zamjenu koja zamjenjuje TOCNO HR fragment: isti padez, rod, broj i interpunkcija koji "
        "odgovaraju okolnom tekstu, bez HTML-a i novih redova, samo pravilne standardne hrvatske rijeci, bez izmisljenih. "
        "Odgovori ISKLJUCIVO JSON-om: {\"zamjena\": \"...\"}"
    )


def parsiraj_zamjena(txt):
    d = _json(txt)
    if not d:
        return None
    return {"zamjena": str(d.get("zamjena") or "").strip()}


def prompt_provjera(en, staro, novo):
    return (
        "EN: %s\nStari HR: %s\nNovi HR: %s\n\n" % (en or "", staro, novo)
        + "Je li NOVI HR vjerniji izvorniku od starog i je li gramaticki ispravan? Sadrzi li novi HR rijeci koje NISU "
        "pravilne standardne hrvatske rijeci (izmisljene, krivo tvorene)? "
        "Odgovori ISKLJUCIVO JSON-om: {\"vjernije\": true|false, \"izmisljene_rijeci\": [\"...\"]}"
    )


def parsiraj_provjera(txt):
    d = _json(txt)
    if not d or not isinstance(d.get("vjernije"), bool):
        return None
    iz = d.get("izmisljene_rijeci") or []
    return {"vjernije": d["vjernije"], "izmisljene": [str(x) for x in iz] if isinstance(iz, list) else []}
