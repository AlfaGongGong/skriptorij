# -*- coding: utf-8 -*-
"""processing/verifier_hook.py — P2.1 hook: shadow verifikator EN vs HR po bloku.

Ukljucen samo uz BOOKLYFI_VERIFIER=1. NE mijenja ocjenu bloka; rezultat ide u
quality_verifier.json ({"verifier": "ok"} | {"verifier": "flags", ...} |
{"verifier": "skip", ...}). Greska ovdje nikad ne smije srusiti pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def ukljucen() -> bool:
    return os.environ.get("BOOKLYFI_VERIFIER", "") == "1"


_BROJAC = 0


def _dozvoljen() -> bool:
    """BOOKLYFI_VERIFIER_MAX=N: najvise N verifikacija po procesu (probni run). 0/prazno = bez limita."""
    global _BROJAC
    try:
        mx = int(os.environ.get("BOOKLYFI_VERIFIER_MAX", "0") or 0)
    except ValueError:
        mx = 0
    if mx <= 0:
        return True
    with _LOCK:
        if _BROJAC >= mx:
            return False
        _BROJAC += 1
        return True


def sazetak(res: dict) -> dict:
    status = res.get("status", "")
    if status == "ok":
        return {"verifier": "ok"}
    if status == "greske":
        g = res.get("greske") or []
        return {"verifier": "flags", "n": len(g), "score": res.get("score"), "greske": g}
    return {"verifier": "skip", "status": status, "error": res.get("error", "")}


async def verifikuj_blok(self, finalno, original_chunk, stem_key, chunk_idx,
                         file_name, tip_bloka, glosar=None):
    if not ukljucen():
        return None
    if not isinstance(original_chunk, str) or not original_chunk.strip():
        return None
    if not isinstance(finalno, str) or not finalno.strip():
        return None
    if not _dozvoljen():
        return None
    try:
        from core.verifier import oznaka_bloka, provjeri_blok_async

        _zadnji = {}

        async def _fleet(prompt, sys_p):
            _r = await self._call_ai_engine(
                prompt, chunk_idx, uloga="VERIFIER", filename=file_name,
                sys_override=sys_p, tip_bloka=tip_bloka,
            )
            _zadnji["r"] = _r
            return _r

        res = await provjeri_blok_async(original_chunk, finalno, glosar or {}, fleet=_fleet)
        out = sazetak(res)
        if out.get("verifier") == "skip":
            _rr = _zadnji.get("r")
            _raw = _rr[0] if isinstance(_rr, (tuple, list)) and _rr else _rr
            _raw = _raw if isinstance(_raw, str) else ""
            out["raw_len"] = len(_raw)
            out["raw_tail"] = _raw[-160:]
        p = self.checkpoint_dir / "quality_verifier.json"
        with _LOCK:
            ex = {}
            if p.exists():
                try:
                    ex = json.loads(p.read_text("utf-8"))
                except Exception:
                    logger.exception("[P2.1] quality_verifier.json nečitljiv, počinjem iznova")
                    ex = {}
            ex[stem_key] = dict(out, oznaka=oznaka_bloka(res))
            self._atomic_write(p, json.dumps(ex, ensure_ascii=False, indent=2))
        if out["verifier"] == "flags":
            self.log(
                f"[{file_name}] Blok {chunk_idx}: 🔎 verifikator: {out['n']} sumnji "
                f"(score={out.get('score')})",
                "warning",
            )
        return out
    except Exception:
        logger.exception("[P2.1] verifier hook")
        return None


# P2.1 popravak: ponovni prijevod flagiranog bloka (BOOKLYFI_VERIFIER_FIX=1)
_verifikuj_blok_orig = verifikuj_blok


def _fix_ukljucen() -> bool:
    return os.environ.get("BOOKLYFI_VERIFIER_FIX", "") == "1"


def _greske_u_tekst(greske) -> str:
    red = []
    for g in greske or []:
        if g.get("tip") == "izostavljeno" or not g.get("hr_fragment"):
            red.append('- OBAVEZNO PREVEDI I UBACI (u prijevodu je nedostajalo): "%s" | problem: %s' % (
                g.get("en_fragment", ""), g.get("objasnjenje", "")))
        elif g.get("tip") == "dodano" or not g.get("en_fragment"):
            red.append('- UKLONI (u izvorniku ne postoji): "%s" | problem: %s' % (
                g.get("hr_fragment", ""), g.get("objasnjenje", "")))
        else:
            red.append('- izvornik: "%s" | tvoj raniji prijevod: "%s" | problem: %s' % (
                g.get("en_fragment", ""), g.get("hr_fragment", ""), g.get("objasnjenje", "")))
    return "\n".join(red)


def _upisi_zapis(self, stem_key, zapis):
    p = self.checkpoint_dir / "quality_verifier.json"
    with _LOCK:
        ex = {}
        if p.exists():
            try:
                ex = json.loads(p.read_text("utf-8"))
            except Exception:
                ex = {}
        ex[stem_key] = zapis
        self._atomic_write(p, json.dumps(ex, ensure_ascii=False, indent=2))


async def verifikuj_blok(self, finalno, original_chunk, stem_key, chunk_idx,
                         file_name, tip_bloka, glosar=None):
    out = await _verifikuj_blok_orig(self, finalno, original_chunk, stem_key,
                                     chunk_idx, file_name, tip_bloka, glosar)
    if not _fix_ukljucen() or not out or out.get("verifier") != "flags":
        return out
    try:
        import re as _re
        from core.text_utils import _smart_extract
        from core.verifier import _plain, oznaka_bloka, provjeri_blok_async

        p_chk = self.checkpoint_dir / (file_name + "_blok_" + str(chunk_idx) + ".chk")
        if not p_chk.exists():
            return out
        ozn_old = oznaka_bloka({"provjeren": True, "greske": out.get("greske"), "score": out.get("score")})
        score_old = out.get("score") or 0
        zapis = dict(out, oznaka=ozn_old)

        prompt = ("Engleski tekst za prevod:\n" + original_chunk +
                  "\n\nPrethodni prijevod ovog teksta imao je ove greske smisla. Prevedi CIJELI tekst ponovo "
                  "i ispravi ih (zadrzi HTML oznake i ostalo kao prije):\n" + _greske_u_tekst(out.get("greske")))
        r = await self._call_ai_engine(prompt, chunk_idx, uloga="PREVODILAC",
                                       filename=file_name, tip_bloka=tip_bloka)
        raw = r[0] if isinstance(r, (tuple, list)) and r else r
        if not isinstance(raw, str) or not raw.strip():
            _upisi_zapis(self, stem_key, dict(zapis, popravljen=False, razlog="nema_odgovora"))
            return out
        novo = _smart_extract(raw)
        lo, ln = len(_plain(original_chunk)), len(_plain(novo))
        if not novo.strip() or "NEPREVEDENO" in novo or not (0.75 * lo <= ln <= 1.6 * lo):
            _upisi_zapis(self, stem_key, dict(zapis, popravljen=False, razlog="sumnjiva_duljina %d/%d" % (ln, lo),
                                              raw_pocetak=raw[:200], raw_kraj=raw[-200:], raw_duljina=len(raw),
                                              curenje=bool(__import__("re").search(r"Let's|\" ->|\(Wait|\bwe need to\b", raw))))
            return out

        async def _fleet2(prompt2, sys_p):
            return await self._call_ai_engine(prompt2, chunk_idx, uloga="VERIFIER", filename=file_name,
                                              sys_override=sys_p, tip_bloka=tip_bloka)

        res2 = await provjeri_blok_async(original_chunk, novo, glosar or {}, fleet=_fleet2)
        out2 = sazetak(res2)
        ozn2 = oznaka_bloka(res2)
        score_new = res2.get("score") if isinstance(res2, dict) else None
        bolji = bool(res2.get("provjeren")) and (ozn2 == "ok" or (isinstance(score_new, (int, float)) and score_new > score_old))
        if not bolji:
            _upisi_zapis(self, stem_key, dict(zapis, popravljen=False, razlog="nije_bolji", pokusaj_score=score_new))
            return out

        stari = p_chk.read_text("utf-8", errors="ignore")
        m = _re.match(r"<!--\s*chunk_sha[^>]*-->\s*\n", stari)
        zaglavlje = m.group(0) if m else ""
        bk = self.checkpoint_dir / "verifier_prije"
        bk.mkdir(parents=True, exist_ok=True)
        (bk / (p_chk.name + ".txt")).write_text(stari, "utf-8")
        self._atomic_write(p_chk, zaglavlje + novo)
        _upisi_zapis(self, stem_key, dict(out2, oznaka=ozn2, oznaka_prije=ozn_old, score_prije=score_old,
                                          popravljen=True, novi_pocetak=_plain(novo)[:40]))
        self.log("[" + file_name + "] Blok " + str(chunk_idx) + ": verifikator popravio blok (" +
                 str(score_old) + " -> " + str(score_new) + ")", "tech")
        return out2
    except Exception:
        logger.exception("[P2.1] verifier fix")
        return out


# L49b: tockasti popravak (BOOKLYFI_VERIFIER_TOCKA=1, ili automatski uz BOOKLYFI_VERIFIER_FIX=1)
_verifikuj_blok_cijeli = verifikuj_blok


async def verifikuj_blok(self, finalno, original_chunk, stem_key, chunk_idx,
                         file_name, tip_bloka, glosar=None):
    out = await _verifikuj_blok_cijeli(self, finalno, original_chunk, stem_key,
                                       chunk_idx, file_name, tip_bloka, glosar)
    try:
        from processing import verifier_tocka as _vt
        if not _vt.ukljucena() or not out or out.get("verifier") != "flags":
            return out
        return await _vt.tocka_popravak(self, out, original_chunk, stem_key,
                                        chunk_idx, file_name, tip_bloka, glosar)
    except Exception:
        logger.exception("[L49b] tocka hook")
        return out
