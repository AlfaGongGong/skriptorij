# -*- coding: utf-8 -*-
"""processing/verifier_tocka.py — L49b: tockasti popravak greske smisla.

Drugi pokusaj kad popravak CIJELOG bloka ne uspije (model vrati samo 200-260 zn
umjesto bloka od ~2500). Za svaku gresku (kriv_smisao, negacija, broj, ime,
ostalo) koja ima i EN i HR fragment trazi se nova HR rjecenica/fragment.
Zamjena se radi samo ako se HR fragment u .chk pojavljuje TOCNO jednom i nema
HTML oznaka; zatim se cijeli blok ponovno verificira i zapis se pise samo ako
je gresaka manje nego prije. Greska ovdje nikad ne smije srusiti pipeline.
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

TIPOVI_TOCKA = ("kriv_smisao", "negacija", "broj", "ime", "ostalo")
MAX_PO_BLOKU = 4

SYS_PROMPT = (
    "Ti ispravljas JEDAN fragment hrvatskog prijevoda. Dobit ces engleski fragment, "
    "hrvatski fragment, problem koji je prijavio verifikator i okolni hrvatski tekst "
    "(samo za gramatiku; fragment je u njemu oznacen s [[ ]]).\n"
    "Ako je hrvatski fragment zapravo vjeran engleskom (verifikator moze pogrijesiti), "
    'vrati {"hr": ""}.\n'
    "Inace vrati ISPRAVLJEN fragment koji ga zamjenjuje: isti dio teksta, gramaticki "
    "uklopljen u okolni tekst (padez, rod, broj), bez HTML oznaka, bez novih redova, "
    "bez objasnjenja i bez razmisljanja naglas.\n"
    'Odgovor je ISKLJUCIVO jedan JSON objekt: {"hr": "..."}'
)

_ZAGLAVLJE = re.compile(r"<!--\s*chunk_sha[^>]*-->\s*\n")
_FENCE = re.compile(r"```(?:json|JSON)?")
_OMOTAC = re.compile(r"</?(?:out|output|json)\s*>", re.I)


def ukljucena() -> bool:
    v = os.environ.get("BOOKLYFI_VERIFIER_TOCKA", "")
    if v != "":
        return v == "1"
    return os.environ.get("BOOKLYFI_VERIFIER_FIX", "") == "1"


def podijeli(chk: str) -> tuple:
    """.chk -> (zaglavlje, tijelo)."""
    m = _ZAGLAVLJE.match(chk)
    return (m.group(0), chk[m.end():]) if m else ("", chk)


def kandidati(greske, maks: int = MAX_PO_BLOKU) -> list:
    out, vidjeno = [], set()
    for g in greske or []:
        if not isinstance(g, dict) or g.get("tip") not in TIPOVI_TOCKA:
            continue
        en = str(g.get("en_fragment") or "").strip()
        hr = str(g.get("hr_fragment") or "").strip()
        if not en or not hr or hr in vidjeno:
            continue
        vidjeno.add(hr)
        out.append({"tip": g.get("tip"), "en": en, "hr": hr,
                    "objasnjenje": str(g.get("objasnjenje") or "")})
        if len(out) >= maks:
            break
    return out


def _bez_tagova(t: str) -> str:
    return re.sub(r"<[^>]*>", "", t)


def _varijante(stari: str) -> list:
    v = [stari]
    esc = _html.escape(stari, quote=False)
    if esc != stari:
        v.append(esc)
    return v


def provjeri_fragment(tijelo: str, stari: str) -> str:
    """'' ako se fragment smije mijenjati, inace razlog."""
    if not stari or not stari.strip():
        return "prazan_fragment"
    if "<" in stari or ">" in stari:
        return "html_u_fragmentu"
    for v in _varijante(stari):
        n = tijelo.count(v)
        if n == 1:
            return ""
        if n > 1:
            return "vise_pojava"
    return "nema_pojave"


def kontekst(tijelo: str, stari: str, n: int = 90) -> str:
    for v in _varijante(stari):
        i = tijelo.find(v)
        if i >= 0:
            pre = _bez_tagova(tijelo[max(0, i - n * 3):i])[-n:]
            post = _bez_tagova(tijelo[i + len(v):i + len(v) + n * 3])[:n]
            return _html.unescape(pre + "[[" + v + "]]" + post)
    return ""


def napravi_prompt(k: dict, ctx: str) -> str:
    return ("ENGLESKI FRAGMENT: " + k["en"] + "\n"
            "HRVATSKI FRAGMENT: " + k["hr"] + "\n"
            "PROBLEM (tip " + str(k.get("tip")) + "): " + k.get("objasnjenje", "") + "\n"
            "OKOLNI HR TEKST: " + ctx + "\n\n"
            'Vrati JSON {"hr": "..."}.')


def parse_odgovor(raw):
    """-> str (novi fragment, '' = vec ispravno) ili None (neupotrebljiv odgovor)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    t = _FENCE.sub("", _OMOTAC.sub("", raw)).strip()
    cand = [t]
    a, b = t.find("{"), t.rfind("}")
    if 0 <= a < b:
        cand.append(t[a:b + 1])
    for c in cand:
        try:
            o = json.loads(c)
        except ValueError:
            continue
        if isinstance(o, dict) and isinstance(o.get("hr"), str):
            return o["hr"].strip()
    return None


def primijeni_zamjenu(tijelo: str, stari: str, novi) -> tuple:
    """-> (novo_tijelo | None, razlog)."""
    razlog = provjeri_fragment(tijelo, stari)
    if razlog:
        return None, razlog
    if not isinstance(novi, str) or not novi.strip():
        return None, "prazan_novi"
    if "<" in novi or ">" in novi:
        return None, "html_u_novom"
    if "\n" in novi or "\r" in novi:
        return None, "novi_red"
    if "NEPREVEDENO" in novi or "[[" in novi:
        return None, "marker"
    if novi == stari:
        return None, "isto"
    ls, ln = len(stari), len(novi)
    if not (0.4 * ls <= ln <= 2.5 * ls):
        return None, "duljina %d/%d" % (ln, ls)
    for v in _varijante(stari):
        if tijelo.count(v) == 1:
            nov_v = _html.escape(novi, quote=False) if (v != stari or "&" in novi) else novi
            return tijelo.replace(v, nov_v, 1), ""
    return None, "nema_pojave"


def _spoji_zapis(self, stem_key, osnova, **kw):
    from processing.verifier_hook import _LOCK
    p = self.checkpoint_dir / "quality_verifier.json"
    with _LOCK:
        ex = {}
        if p.exists():
            try:
                ex = json.loads(p.read_text("utf-8"))
            except Exception:
                ex = {}
        baza = dict(osnova) if osnova is not None else dict(ex.get(stem_key, {}))
        baza.update(kw)
        ex[stem_key] = baza
        self._atomic_write(p, json.dumps(ex, ensure_ascii=False, indent=2))


async def tocka_popravak(self, out, original_chunk, stem_key, chunk_idx,
                         file_name, tip_bloka, glosar=None):
    """-> novi sazetak (uspjeh) ili isti `out`. Nikad ne baca."""
    try:
        from core.verifier import oznaka_bloka, provjeri_blok_async
        from processing.verifier_hook import sazetak

        p_chk = self.checkpoint_dir / (file_name + "_blok_" + str(chunk_idx) + ".chk")
        if not p_chk.exists():
            return out
        stari_chk = p_chk.read_text("utf-8", errors="ignore")
        zagl, tijelo = podijeli(stari_chk)
        kand = kandidati(out.get("greske"))
        if not kand:
            return out

        izmjene, preskoceno, vec_ok = [], [], 0
        novo_tijelo = tijelo
        for k in kand:
            razlog = provjeri_fragment(novo_tijelo, k["hr"])
            if razlog:
                preskoceno.append([k["hr"][:40], razlog])
                continue
            r = await self._call_ai_engine(
                napravi_prompt(k, kontekst(novo_tijelo, k["hr"])), chunk_idx,
                uloga="VERIFIER", filename=file_name, sys_override=SYS_PROMPT,
                tip_bloka=tip_bloka)
            raw = r[0] if isinstance(r, (tuple, list)) and r else r
            hr_novi = parse_odgovor(raw)
            if hr_novi is None:
                preskoceno.append([k["hr"][:40], "neispravan_odgovor"])
                continue
            if hr_novi == "":
                vec_ok += 1
                continue
            nt, razlog = primijeni_zamjenu(novo_tijelo, k["hr"], hr_novi)
            if nt is None:
                preskoceno.append([k["hr"][:40], razlog])
                continue
            novo_tijelo = nt
            izmjene.append({"tip": k["tip"], "prije": k["hr"], "poslije": hr_novi})

        if not izmjene:
            _spoji_zapis(self, stem_key, None, tocka={
                "popravljeno": 0, "vec_ispravno": vec_ok, "preskoceno": preskoceno})
            return out

        novo_chk = zagl + novo_tijelo

        async def _fleet(prompt, sys_p):
            return await self._call_ai_engine(
                prompt, chunk_idx, uloga="VERIFIER", filename=file_name,
                sys_override=sys_p, tip_bloka=tip_bloka)

        res2 = await provjeri_blok_async(original_chunk, novo_chk, glosar or {}, fleet=_fleet)
        n_old = len(out.get("greske") or [])
        n_new = len(res2.get("greske") or []) if res2.get("provjeren") else None
        ozn_old = oznaka_bloka({"provjeren": True, "greske": out.get("greske"),
                                "score": out.get("score")})
        if n_new is None or n_new >= n_old:
            _spoji_zapis(self, stem_key, None, tocka={
                "popravljeno": 0, "razlog": "nije_bolji", "n_prije": n_old, "n_poslije": n_new,
                "pokusano": izmjene, "vec_ispravno": vec_ok, "preskoceno": preskoceno})
            return out

        from core.popravak_kapija import prihvatljiv as _prih_kapija  # G34
        _ok_g, _raz_g = _prih_kapija(original_chunk, novo_tijelo, tijelo, glosar)
        if not _ok_g:
            self.log("[" + file_name + "] Blok " + str(chunk_idx) + ": tockasti popravak odbijen kapijom: "
                     + "; ".join(_raz_g)[:200], "warning")
            _spoji_zapis(self, stem_key, None, tocka={
                "popravljeno": 0, "razlog": "kapija: " + "; ".join(_raz_g)[:200],
                "pokusano": izmjene, "vec_ispravno": vec_ok, "preskoceno": preskoceno})
            return out
        bk = self.checkpoint_dir / "verifier_prije"
        bk.mkdir(parents=True, exist_ok=True)
        bk_f = bk / (p_chk.name + ".tocka.txt")
        if not bk_f.exists():
            bk_f.write_text(stari_chk, "utf-8")
        self._atomic_write(p_chk, novo_chk)
        out2 = sazetak(res2)
        ozn2 = oznaka_bloka(res2)
        _spoji_zapis(self, dict(out2, oznaka=ozn2, oznaka_prije=ozn_old,
                                score_prije=out.get("score")), stem_key if False else None) \
            if False else _spoji_zapis(
                self, stem_key, dict(out2, oznaka=ozn2, oznaka_prije=ozn_old,
                                     score_prije=out.get("score")),
                tocka={"popravljeno": len(izmjene), "n_prije": n_old, "n_poslije": n_new,
                       "izmjene": izmjene, "vec_ispravno": vec_ok, "preskoceno": preskoceno})
        self.log("[" + file_name + "] Blok " + str(chunk_idx) + ": tockasti popravak "
                 + str(len(izmjene)) + " (" + str(n_old) + " -> " + str(n_new) + " gresaka)", "tech")
        return out2
    except Exception:
        logger.exception("[L49b] tocka_popravak")
        return out
