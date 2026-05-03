"""
processing/pipeline.py — v2.0 (Granularni checkpoint sistem)

IZMJENE vs v1.0:
  - Svaki međukorak (sirovi prijevod, lektor) sada ima vlastiti .chk fajl.
  - LEKTURA mod: sprema lektorisani blok u  <blok>.lektura.chk
  - PREVOD  mod: sprema sirovi prijevod u    <blok>.prevod.chk
                 sprema lektorisani finalni u <blok>.chk  (kao i ranije)
  - Kod checkpointa čita koji korak već postoji i nastavlja od tačno tog mjesta.
  - Dodan _chk_read / _chk_write kao interni helper — jedan atomičan poziv.
  - Svi ostali dijelovi (quality scoring, human_review.json, rescue) ostaju netaknuti.
"""

import gc
import asyncio
import re
import json
from bs4 import BeautifulSoup
from core.text_utils import (
    _smart_extract,
    _agresivno_cisti,
    _detektuj_en_ostatke,
    _detektuj_halucinaciju,
    _post_process_tipografija,
    _automatska_korekcija,
    _HR_DIACRITICALS,
    detektuj_tip_bloka,
)
from processing.rescue import _spasi_od_sirovog


# ── Privatni checkpoint helperi ───────────────────────────────────────────────

def _chk_path(self, file_name: str, chunk_idx: int, suffix: str = "") -> object:
    """
    Vraća Path za checkpoint fajl.

    suffix="" → finalni blok  (<file>_blok_<i>.chk)
    suffix="prevod" → sirovi prijevod (<file>_blok_<i>.prevod.chk)
    suffix="lektura" → lektorisani u LEKTURA modu (<file>_blok_<i>.lektura.chk)
    """
    if suffix:
        return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.{suffix}.chk"
    return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"


def _chk_read(self, file_name: str, chunk_idx: int, suffix: str = "") -> str | None:
    """
    Čita checkpoint fajl ako postoji i sadrži validan sadržaj.
    Vraća tekst ili None.
    """
    from utils.checkpoint_cleaner import _je_placeholder, _ocisti_json_wrapper
    p = _chk_path(self, file_name, chunk_idx, suffix)
    if not p.exists():
        return None
    try:
        tekst = p.read_text("utf-8", errors="ignore")
        tekst = _ocisti_json_wrapper(tekst)
        if len(tekst) > 10 and not _je_placeholder(tekst):
            return tekst
    except Exception:
        pass
    return None


def _chk_write(self, file_name: str, chunk_idx: int, sadrzaj: str, suffix: str = "") -> None:
    """Atomično piše checkpoint fajl."""
    p = _chk_path(self, file_name, chunk_idx, suffix)
    self._atomic_write(p, sadrzaj)


# ─────────────────────────────────────────────────────────────────────────────


def _strip_ai_json(text: str) -> str:
    """Strip ```json ... ``` ili ``` ... ``` wrappers iz AI odgovora."""
    if not text:
        return text
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"?```\s*$", "", t)
    return t.strip()


def _je_placeholder_lokalni(tekst: str) -> bool:
    """Lokalna verzija placeholder provjere bez importa."""
    _PLACEHOLDERS = {
        "", "n/a", "none", "null", "undefined",
        "placeholder", "[prijevod]", "[translation]", "[tekst]", "[text]",
    }
    cist = tekst.strip().lower()
    return cist in _PLACEHOLDERS or len(cist) < 5


# ─────────────────────────────────────────────────────────────────────────────
# GLAVNI PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

async def process_chunk_with_ai(self, chunk, prev_ctx, next_ctx, chunk_idx, file_name):
    """
    Obrađuje jedan HTML chunk kroz AI pipeline.

    Checkpoint logika:
      LEKTURA:
        1. Provjeri .lektura.chk  → gotovo, vrati cached
        2. Pokreni AI lekturu
        3. Spremi .lektura.chk + finalni .chk

      PREVOD:
        1. Provjeri finalni .chk  → gotovo (oba koraka), vrati cached
        2. Provjeri .prevod.chk  → sirovi prijevod je gotov, preskoči na lektor
        3. Pokreni prevodilac, spremi .prevod.chk
        4. Pokreni lektor, spremi finalni .chk
    """
    force_reprocess = getattr(self, "_force_reprocess", False)

    # ── Zajednička provjera finalnog cache-a (vrijedi za oba moda) ─────────
    if not force_reprocess:
        cached_final = _chk_read(self, file_name, chunk_idx)
        if cached_final and _detektuj_en_ostatke(cached_final) < 0.08:
            from core.quality import _QUALITY_RESCUE_THRESHOLD
            qs = self.shared_stats.get("quality_scores", {})
            stem_key = f"{file_name}_blok_{chunk_idx}"
            cached_score = qs.get(stem_key, None)

            if cached_score is None or cached_score >= _QUALITY_RESCUE_THRESHOLD:
                score_info = f"score={cached_score:.1f}" if cached_score else "score=?"
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Učitan iz cache-a ({score_info}).",
                    "tech",
                )
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return cached_final, "DATABASE"
            else:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ♻️ Cache ignorisan "
                    f"(score={cached_score:.1f} < {_QUALITY_RESCUE_THRESHOLD}) — ponovo obrađujem.",
                    "warning",
                )

    # ── Zajednički setup ────────────────────────────────────────────────────
    knjiga_mode = getattr(self, "knjiga_mode", None)
    if knjiga_mode is None:
        knjiga_mode = self._detect_language(chunk)

    rel_glosar  = self._extract_relevant_glossary(chunk)
    tip_bloka   = detektuj_tip_bloka(chunk)
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)

    # ══════════════════════════════════════════════════════════════════════════
    # LEKTURA mod — HR tekst, samo lektorisanje
    # ══════════════════════════════════════════════════════════════════════════
    if knjiga_mode == "LEKTURA":

        # Korak 1: Provjeri da li je lektura već završena (nastavak nakon prekida)
        if not force_reprocess:
            cached_lek = _chk_read(self, file_name, chunk_idx, "lektura")
            if cached_lek:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Lektura učitana iz cache-a.",
                    "tech",
                )
                # Osiguraj i finalni .chk (ako je nestao)
                if not _chk_path(self, file_name, chunk_idx).exists():
                    _chk_write(self, file_name, chunk_idx, cached_lek)
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return cached_lek, "DATABASE/LEKTURA"

        # Korak 2: Automatska korekcija + AI lektor
        sirovo = _automatska_korekcija(chunk)

        lek_sys = self._get_lektor_prompt(
            prev_kraj=prev_ctx,
            glosar_injekcija=rel_glosar,
            chapter_summary=chapter_summary,
            tip_bloka=tip_bloka,
        )
        p_lek = (
            f"IZVORNI TEKST (već na bosanskom/hrvatskom):\n{sirovo}\n\n"
            f"Lektoriraj tekst: ispravi interpunkciju, em-crtice u dijalogu, "
            f"stilske greške. NE PREVODI — tekst je već na HR/BS jeziku."
        )

        raw_l, prov_l = await self._call_ai_engine(
            p_lek,
            chunk_idx,
            uloga="LEKTOR",
            filename=file_name,
            sys_override=lek_sys,
            tip_bloka=tip_bloka,
        )

        # Korak 3: Prihvati ili fallback na original
        if raw_l:
            finalno = _smart_extract(raw_l)
            if not finalno or _je_placeholder_lokalni(finalno):
                finalno = sirovo
        else:
            finalno = sirovo
            prov_l  = "AUTO-HR"

        cist_priv = _agresivno_cisti(finalno)
        if not cist_priv or len(cist_priv.strip()) < 30:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Čišćenje dalo prazno – čuvam original.",
                "warning",
            )
            finalno = chunk
        else:
            finalno = _post_process_tipografija(cist_priv)

        # Korak 4: Spremi .lektura.chk i finalni .chk
        _chk_write(self, file_name, chunk_idx, finalno, "lektura")
        _chk_write(self, file_name, chunk_idx, finalno)

        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        gc.collect()
        self.log(f"[{file_name}] Blok {chunk_idx}: ✍️ HR lektura ({prov_l})", "tech")

        await _quality_scoring(self, finalno, None, chunk_idx, file_name,
                                tip_bloka, f"LEKTURA/{prov_l}",
                                tip_ocjenjivanja="lektura")
        return finalno, f"LEKTURA/{prov_l}"

    # ══════════════════════════════════════════════════════════════════════════
    # PREVOD mod — EN→HR prijevod + lektura
    # ══════════════════════════════════════════════════════════════════════════

    # Korak 1: Provjeri da li je sirovi prijevod već gotov (nastavi od lektora)
    sirovo_cached = None
    if not force_reprocess:
        sirovo_cached = _chk_read(self, file_name, chunk_idx, "prevod")
        if sirovo_cached:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ♻️ Sirovi prijevod iz cache-a — nastavljam od lektora.",
                "tech",
            )

    # Korak 2: Prevodilac (samo ako nema cache-a)
    if sirovo_cached:
        sirovo = sirovo_cached
        prov1  = "DATABASE/PREVOD"
    else:
        fusion_sys = self._get_prevodilac_prompt(
            glosar_chunk=rel_glosar, prev_kraj=prev_ctx, tip_bloka=tip_bloka
        )
        p_fusion = f"Engleski tekst za prevod:\n{chunk}"
        raw_fusion, prov1 = await self._call_ai_engine(
            p_fusion,
            chunk_idx,
            uloga="PREVODILAC",
            filename=file_name,
            sys_override=fusion_sys,
            tip_bloka=tip_bloka,
        )
        if not raw_fusion:
            self.chunk_skips += 1
            return None, "N/A"

        sirovo = _agresivno_cisti(raw_fusion)

        # Spremi sirovi prijevod odmah — štiti od gubitka ako lektor failuje
        _chk_write(self, file_name, chunk_idx, sirovo, "prevod")

    # Korak 3: Lektor
    lek_sys = self._get_lektor_prompt(
        prev_kraj=prev_ctx,
        glosar_injekcija=rel_glosar,
        chapter_summary=chapter_summary,
        tip_bloka=tip_bloka,
    )
    p_lek = (
        f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
        f"SIROVI PRIJEVOD:\n{sirovo}\n\n"
        f"Profesionalno lektoriraj na bosanski/hrvatski."
    )
    raw_l, prov2 = await self._call_ai_engine(
        p_lek,
        chunk_idx,
        uloga="LEKTOR",
        filename=file_name,
        sys_override=lek_sys,
        tip_bloka=tip_bloka,
    )
    finalno = _smart_extract(raw_l) if raw_l else sirovo
    if not finalno:
        finalno = sirovo

    # Korak 4: Rescue ako ima previše engleskog
    if _detektuj_en_ostatke(finalno) > 0.15:
        spas, _ = await _spasi_od_sirovog(
            self, sirovo, chunk, chunk_idx, file_name,
            prev_ctx, rel_glosar, "en>15%", tip_bloka,
        )
        if spas:
            finalno = spas

    if _detektuj_halucinaciju(chunk, finalno):
        self.log(f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju", "warning")

    finalno = _post_process_tipografija(_agresivno_cisti(finalno))

    # Korak 5: Spremi finalni .chk i očisti međukorak .prevod.chk
    _chk_write(self, file_name, chunk_idx, finalno)
    try:
        _chk_path(self, file_name, chunk_idx, "prevod").unlink(missing_ok=True)
    except Exception:
        pass  # Ne prekidaj tok ako brisanje ne uspije

    self.global_done_chunks += 1
    self.stvarno_prevedeno_u_sesiji += 1

    await _quality_scoring(self, finalno, chunk, chunk_idx, file_name,
                            tip_bloka, f"{prov1}→{prov2}",
                            tip_ocjenjivanja="prevod")

    aud = (
        f"📦 Blok {chunk_idx} [{tip_bloka}] | {prov1}→{prov2} | "
        f"EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:50]}… → "
        f"HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:50]}…"
    )
    self.log("", "accordion", en_text=aud)
    return finalno, f"{prov1}→{prov2}"


# ─────────────────────────────────────────────────────────────────────────────
# QUALITY SCORING — Izdvojen helper da se ne ponavlja kod
# ─────────────────────────────────────────────────────────────────────────────

async def _quality_scoring(
    self, finalno: str, original_chunk, chunk_idx: int,
    file_name: str, tip_bloka: str, prov_label: str,
    tip_ocjenjivanja: str = "opci"
) -> None:
    """
    Računa quality score za blok i ažurira shared_stats.
    Nikad ne prekida tok — sve greške su tihe.
    """
    # ── Paratekst provjera ────────────────────────────────────────────────
    # Fajlovi koji nisu knjizevni tekst ne ocjenjuju se po knjizevnim kriterijima.
    # Dobijaju neutralnu ocjenu 8.5 i ne trose API pozive.
    _PARATEKST_KLJUCNE_RIJECI = (
        "halftitle", "title", "otherbyauthor", "alsoby", "seriespage",
        "copyright", "dedication", "contents", "toc", "colophon",
        "frontmatter", "backmatter", "epigraph", "acknowledgment",
        "aboutauthor", "cover", "insert",
    )
    _fn_lower = file_name.lower().replace("_", "").replace("-", "")
    _je_paratekst = any(kw in _fn_lower for kw in _PARATEKST_KLJUCNE_RIJECI)

    if _je_paratekst:
        # Paratekst: fiksna neutralna ocjena, bez AI poziva
        _para_score = 8.5
        if not hasattr(self, "_quality_scores"):
            self._quality_scores = {}
        _stem = f"{file_name}_blok_{chunk_idx}"
        self._quality_scores[_stem] = {
            "score":   _para_score,
            "tip":     tip_bloka,
            "prov":    "PARATEKST",
            "preview": "(paratekst — nije knjizevni prijevod)",
        }
        if "quality_scores" not in self.shared_stats:
            self.shared_stats["quality_scores"] = {}
        self.shared_stats["quality_scores"][_stem] = _para_score
        self.log(f"[{file_name}] Blok {chunk_idx}: paratekst → ocjena {_para_score}", "tech")
        return

    try:
        from core.quality import _scoruj_kvalitetu

        # ISPRAVNO: engine_fn = self._call_ai_engine (callable, ne string teksta)
        score = await _scoruj_kvalitetu(
            finalno,
            self._call_ai_engine,
            chunk_idx,
            file_name,
            self_obj=self,
            tip_ocjenjivanja=tip_ocjenjivanja,
        )
        score_float = float(max(1.0, min(10.0, score)))

        if not hasattr(self, "_quality_scores"):
            self._quality_scores = {}

        stem_key = f"{file_name}_blok_{chunk_idx}"
        preview  = BeautifulSoup(finalno, "html.parser").get_text()[:80]

        self._quality_scores[stem_key] = {
            "score":   score_float,
            "tip":     tip_bloka,
            "prov":    prov_label,
            "preview": preview,
        }
        if "quality_scores" not in self.shared_stats:
            self.shared_stats["quality_scores"] = {}
        self.shared_stats["quality_scores"][stem_key] = score_float

        if score_float < 6.5:
            self.log(
                f"⚠️ Blok {chunk_idx} [{tip_bloka}]: score={score_float:.1f} — "
                f"{preview[:60]}…",
                "warning",
            )
            hr_path = self.checkpoint_dir / "human_review.json"
            try:
                hr_data = json.loads(_strip_ai_json(hr_path.read_text("utf-8"))) \
                          if hr_path.exists() else []
                if not any(item.get("stem") == stem_key for item in hr_data):
                    hr_data.append({
                        "stem":    stem_key,
                        "score":   score_float,
                        "tip":     tip_bloka,
                        "preview": preview,
                    })
                    self._atomic_write(
                        hr_path,
                        json.dumps(hr_data, ensure_ascii=False, indent=2),
                    )
            except Exception:
                pass

        done = self.global_done_chunks
        if done > 0 and done % 10 == 0:
            gc.collect()
            try:
                qs_path = self.checkpoint_dir / "quality_scores.json"
                qs_path.write_text(
                    json.dumps(
                        self.shared_stats["quality_scores"],
                        ensure_ascii=False, indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass

    except Exception:
        pass


async def process_chunk_with_retry(
    self, chunk, prev_ctx, next_ctx, chunk_idx, file_name, max_retries=3
):
    """Obrađuje chunk sa ponavljanjem ako ne uspije."""
    for attempt in range(max_retries):
        result, engine = await process_chunk_with_ai(
            self, chunk, prev_ctx, next_ctx, chunk_idx, file_name
        )
        if result is not None:
            return result, engine
        self.log(
            f"⚠️ Blok {chunk_idx} nije obrađen (pokušaj {attempt + 1}/{max_retries})",
            "warning",
        )
        if attempt < max_retries - 1:
            await asyncio.sleep(2)
            self.log("🔄 Pokušavam sa drugim modelom...", "info")
    self.log(
        f"❌ Blok {chunk_idx} nije obrađen ni nakon {max_retries} pokušaja — koristim original",
        "error",
    )
    return chunk, "ORIGINAL-FALLBACK"