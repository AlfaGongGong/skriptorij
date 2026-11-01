"""
processing/pipeline.py — v3.1 (Bugfix uvezivanja workers_v2)

IZMJENE vs v3.0:
  - Ispravljen potpis obradi_chunk_v2 — prima self + argumente (ne samo chunk)
  - Dodan _norm_score fallback za slučaj da quality nije float
  - _init_book_context: morfo_validator se inicijalizira iz fleet-a, ne iz gemini_api_key
  - process_chunk_with_retry: ispravan async poziv _obradi_chunk_v2
  - Dodat USE_WORKERS_V2 env fallback na "1" (aktivan po defaultu)
  - Korak 7: Nezavisni scorer — bilježenje prevoditelja za quality_scorer_v2
"""

import logging
logger = logging.getLogger(__name__)
import asyncio
import gc
import json
import os as _os
import re
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

import threading as _threading
_QS_LOCK = _threading.Lock()
from utils.file_utils import atomic_write_json

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
import contextlib

from core.quality import _CACHE_ACCEPT_SCORE
from core.text_utils import (
    _agresivno_cisti,
    _automatska_korekcija,
    _detektuj_en_ostatke,
    _detektuj_halucinaciju,
    _je_ai_anotacija,
    _post_process_tipografija,
    _smart_extract,
    detektuj_tip_bloka,
)
from processing.rescue import _spasi_od_sirovog

# ── Korak 2, 3, 4 integracije ──────────────────────────────────────────────
try:
    from core.kalkovi.engine import kalkovi_engine

    _KALKOVI_OK = True
except ImportError:
    kalkovi_engine = None
    _KALKOVI_OK = False

try:
    from core.validators.morfo_validator import MorfoValidator

    _MORFO_OK = True
except ImportError:
    MorfoValidator = None
    _MORFO_OK = False

try:
    from analysis.book_context import BookContext

    _BOOK_CTX_OK = True
except ImportError:
    BookContext = None
    _BOOK_CTX_OK = False

try:
    from core.prompt_injector import PromptInjector

    _INJECTOR_OK = True
except ImportError:
    PromptInjector = None
    _INJECTOR_OK = False

# ── Workers integracija ─────────────────────────────────────────────────────
USE_WORKERS_V2: bool = _os.environ.get("BOOKLYFI_V2", "1").strip() == "1"

try:
    from processing.workers import WorkerV2

    _V2_DOSTUPAN = True
except ImportError:
    WorkerV2 = None
    _V2_DOSTUPAN = False
    USE_WORKERS_V2 = False

# Korak 7 — Nezavisni scorer (odvojeni try, nema veze s WorkerV2)
try:
    from core.quality import zabilježi_prevoditelja as _zabilježi_prev

    _SCORER_V2_OK = True
except ImportError:
    _zabilježi_prev = None
    _SCORER_V2_OK = False
# ── Samoučeći sistem V1.0 ──────────────────────────────────────────────────
try:
    from core.few_shot_global import dodaj_odlican_prevod, formatiraj_za_prompt

    _FEW_SHOT_OK = True
except ImportError:
    dodaj_odlican_prevod = None
    formatiraj_za_prompt = None
    _FEW_SHOT_OK = False

try:
    from core.skip_oracle import moze_skipovati_korektor

    _SKIP_ORACLE_OK = True
except ImportError:
    moze_skipovati_korektor = None
    _SKIP_ORACLE_OK = False


# ── Karantena detektor (singleton, lazy init) ────────────────────────────────
_karantena_detektor = None


def _get_karantena_detektor():
    """Vraća singleton DinamickiDetektor, inicijaliziran pri prvom pozivu."""
    global _karantena_detektor
    if _karantena_detektor is None:
        try:
            from core.kalkovi.dinamicki_detektor import DinamickiDetektor

            _karantena_detektor = DinamickiDetektor()
        except Exception:
            _karantena_detektor = False  # sentinel: ne pokušavaj ponovo
    return _karantena_detektor if _karantena_detektor is not False else None


# ── Rod detektor (singleton, lazy init) ──────────────────────────────────────
_rod_detektor_pipeline = None


def _get_rod_detektor():
    """Vraća DIJELJENI RodDetektor singleton (isti objekt kao u workers.py)."""
    global _rod_detektor_pipeline
    if _rod_detektor_pipeline is None:
        try:
            from core.kalkovi.rod_detektor import rod_detektor as _shared_rod_detektor

            _rod_detektor_pipeline = _shared_rod_detektor
        except Exception:
            _rod_detektor_pipeline = False
    return _rod_detektor_pipeline if _rod_detektor_pipeline is not False else None


# ── Privatni checkpoint helperi ───────────────────────────────────────────────

_CHUNK_SHA_RX = re.compile(
    r"^<!--\s*chunk_sha:(?P<v2>v2:(?P<mh>[a-f0-9]+):(?P<gh>[a-f0-9]+):)?(?P<h>[a-f0-9]+)\s*-->\s*\n?"
)


def _hash_glosar(glosar) -> str:
    """2026-10-24 B4b: hash glosara za keš validaciju.
    Vraca "" ako je glosar prazan (konzistentno, ne None).
    """
    import hashlib as _hl
    import json as _json

    if not glosar:
        return ""
    try:
        if isinstance(glosar, dict):
            canonical = _json.dumps(
                glosar, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        elif isinstance(glosar, (list, tuple)):
            canonical = _json.dumps(
                list(glosar), sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        else:
            canonical = str(glosar)
        return _hl.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return ""


def _chk_path(self, file_name: str, chunk_idx: int, suffix: str = "") -> object:
    if suffix:
        return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.{suffix}.chk"
    return self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"


def _next_ctx_blok(next_ctx: str) -> str:
    if not next_ctx or next_ctx in ("Sljedeći blok postoji.", "Ovo je zadnji blok poglavlja."):
        return ""
    return f"\n\nKONTEKST (ne prevodi): sljedeći blok počinje s ...{next_ctx[:250]}..."


def _chk_read(
    self,
    file_name: str,
    chunk_idx: int,
    suffix: str = "",
    chunk_for_hash: str | None = None,
    model_hash: str | None = None,
    glosar_hash: str | None = None,
) -> str | None:
    import hashlib as _hashlib

    from utils.checkpoint_cleaner import _je_placeholder, _ocisti_json_wrapper

    p = _chk_path(self, file_name, chunk_idx, suffix)
    if not p.exists():
        return None
    try:
        tekst = p.read_text("utf-8", errors="ignore")
        m = _CHUNK_SHA_RX.match(tekst)
        if m:
            # 2026-10-24 B4a: v2 format (model + glosar + chunk), v1 (samo chunk)
            stored = m.group("h")
            is_v2 = m.group("v2") is not None
            tekst = tekst[m.end() :]
            if chunk_for_hash is not None:
                if is_v2 and (model_hash is not None or glosar_hash is not None):
                    stored_mh = m.group("mh") or ""
                    stored_gh = m.group("gh") or ""
                    _mh_expected = (model_hash or "")[:16]
                    _gh_expected = (glosar_hash or "")[:16]
                    if (model_hash is not None and stored_mh != _mh_expected) or (
                        glosar_hash is not None and stored_gh != _gh_expected
                    ):
                        return None
                expected = _hashlib.sha256(chunk_for_hash.encode("utf-8")).hexdigest()[
                    :16
                ]
                if stored != expected:
                    return None

        # FIX 2026-10-26: Ukloni SVE preostale chunk_sha markere (mogu biti
        # u sredini/kraju teksta od prethodnih lektura koje su pisale u HTML).
        import re as _re_csr
        _prije = len(tekst)
        tekst = _re_csr.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", tekst)
        if len(tekst) < _prije:
            # Marker je bio u sredini — očisti i JSON wrapper ako treba
            tekst = _ocisti_json_wrapper(tekst)

        tekst = _ocisti_json_wrapper(tekst)
        if len(tekst) <= 10 or _je_placeholder(tekst):
            return None

        # ── NEW: sanity — .chk ne smije biti drasticno kraci od izvornog chunka
        # Stiti od nepotpunih .chk (base64 nedovrsen, tekst izgubljen).
        if chunk_for_hash is not None:
            try:
                from bs4 import BeautifulSoup as _BS

                _text_chk = _BS(tekst, "html.parser").get_text(" ", strip=True)
                _text_src = _BS(chunk_for_hash, "html.parser").get_text(" ", strip=True)
                if len(_text_src) > 500 and len(_text_chk) < len(_text_src) * 0.5:
                    with contextlib.suppress(Exception):
                        self.log(
                            f"[{file_name}] Blok {chunk_idx}"
                            f"{'.' + suffix if suffix else ''}: "
                            f"⚠️ .chk nepotpun ({len(_text_chk)}c vs {len(_text_src)}c izvor) "
                            f"— re-obradjujem",
                            "warning",
                        )
                    return None
                if len(_text_chk) < 20:
                    return None
            except Exception:
                logger.exception("[C1_http] pipeline.py:261 Exception")

        return tekst
    except Exception:
        logger.exception("[C1_kriticno] pipeline.py:265 Exception")
    return None


def _chk_write(
    self,
    file_name: str,
    chunk_idx: int,
    sadrzaj: str,
    suffix: str = "",
    chunk_for_hash: str | None = None,
    model_hash: str | None = None,
    glosar_hash: str | None = None,
) -> None:
    import hashlib as _hashlib

    p = _chk_path(self, file_name, chunk_idx, suffix)

    # FIX 2026-10-26: Očisti SVE postojeće chunk_sha markere iz sadržaja
    # prije dodavanja novog. Sprječava akumulaciju markera kroz lekturu:
    # _chk_read ukloni prvi, ostali ostaju u res, pa u HTML, pa u sljedeći .chk...
    import re as _re_cs
    sadrzaj = _re_cs.sub(r"<!--\s*chunk_sha[^>]*-->\s*\n?", "", sadrzaj)

    if chunk_for_hash is not None:
        sha = _hashlib.sha256(chunk_for_hash.encode("utf-8")).hexdigest()[:16]
        if model_hash is not None or glosar_hash is not None:
            _mh = (model_hash or "")[:16]
            _gh = (glosar_hash or "")[:16]
            sadrzaj = (
                "<!-- chunk_sha:v2:" + _mh + ":" + _gh + ":" + sha + " -->\n" + sadrzaj
            )
        else:
            sadrzaj = "<!-- chunk_sha:" + sha + " -->\n" + sadrzaj
    self._atomic_write(p, sadrzaj)


def _strip_ai_json(text: str) -> str:
    if not text:
        return text
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*?", "", t, flags=re.IGNORECASE)
    t = re.sub(r"```\s*$", "", t)
    return t.strip()


def _je_placeholder_lokalni(tekst: str) -> bool:
    if not tekst or not tekst.strip():
        return True
    cist = re.sub(r"<[^>]+>", "", tekst).strip().lower()
    if len(cist) < 15:
        return True
    _exact = {
        "lektorisani tekst ovdje",
        "korigirani tekst ovdje",
        "molim te, pošalji tekst za obradu. čekam ga.",
        "pošalji tekst za obradu.",
        "čekam ga.",
        "[prijevod]",
        "[translation]",
        "[tekst]",
        "[text]",
        "placeholder",
        "[prijevod ovdje]",
        "[lektura ovdje]",
    }
    if cist in _exact:
        return True
    # 2026-10-25: NEPREVEDENO marker iz fallback-a (retry iscrpljen)
    if "[[neprevedeno" in cist or "[[manual:" in cist:
        return True
    _contains = [
        "molim te, pošalji tekst",
        "čekam ga",
        "pošalji tekst za obradu",
        "naravno, evo lektoriranog",
        "naravno, evo prijevoda",
        "evo lektoriranog teksta:",
        "evo prijevoda:",
        "evo korigiranog teksta:",
        "svakako, evo",
        "kao što ste tražili",
        "kao što si tražio",
        "u traženom json formatu",
        "u traženom formatu",
        "kada dobijem sadržaj",
        "kad dobijem sadržaj",
    ]
    if len(cist) < 400:
        for fraza in _contains:
            if fraza in cist:
                return True
    # FIX: hvata formalni i neformalni registar zahtjeva za tekstom
    # (npr. "Molim vas da pošaljete tekst..."), bez obzira na duzinu —
    # ova fraza se prakticno nikad ne pojavljuje u stvarnom tekstu knjige.
    if re.search(r"molim (te|vas)[^.!?\n]{0,80}pošalj\w*[^.!?\n]{0,20}tekst", cist):
        return True
    # Odbaci anotacijski format (AI vratio listu izmjena umjesto teksta)
    if _je_ai_anotacija(tekst):
        return True
    return False


def _norm_score(v) -> float:
    if isinstance(v, dict):
        return float(v.get("score", 0.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


_MIN_ORIG_LEN_FOR_LOSS_CHECK = 120
_MIN_CAND_LEN_FOR_LOSS_CHECK = 20
# PREVODILAC može biti kraći od EN (kompresija), ali sve ispod 62% je često
# signal da su ispali odlomci.
_MIN_TRANSLATION_RATIO = 0.62
# LEKTOR/KOREKTOR ne bi smjeli značajno skraćivati sadržaj.
_MIN_LEKTOR_RATIO = 0.80


def _plain_len(tekst: str) -> int:
    try:
        return len(BeautifulSoup(tekst or "", "html.parser").get_text(" ", strip=True))
    except Exception:
        return len((tekst or "").strip())


def _je_sumnjiv_gubitak_teksta(
    original: str, kandidat: str, uloga: str = "LEKTOR"
) -> bool:
    """
    FIX 2026-10-26: Poredi PLAIN vs PLAIN, ne RAW vs PLAIN.

    Prije: poredio len(original) (HTML sa tagovima, 3007 raw) sa
    len(kandidat) (plain text, 1499). Tagovi u originalu napuhavaju
    broj → lažni "gubitak 51%".

    Sad: oba se svode na plain tekst pa se poredi. Stvarni gubitak
    (kad lektura odseče deo teksta) se i dalje detektuje, ali HTML
    tagovi ne prave lažni signal.
    """
    if not original or not kandidat:
        return False
    orig_len = _plain_len(original)
    cand_len = _plain_len(kandidat)
    if (
        orig_len < _MIN_ORIG_LEN_FOR_LOSS_CHECK
        or cand_len < _MIN_CAND_LEN_FOR_LOSS_CHECK
    ):
        return False
    ratio = cand_len / max(1, orig_len)
    if uloga == "PREVODILAC":
        return ratio < _MIN_TRANSLATION_RATIO
    return ratio < _MIN_LEKTOR_RATIO


def _je_prekinut_tekst(original: str, finalno: str) -> bool:
    """
    FIX 1.7: Provjerava da li se tekst prekida usred rečenice.
    Ako original završava pravom interpunkcijom, a finalno ne,
    i finalno završava slovom ili crticom — tekst je prekinut.
    """
    orig_clean = re.sub(r"<[^>]+>", "", original).strip()
    final_clean = re.sub(r"<[^>]+>", "", finalno).strip()

    if not orig_clean or not final_clean:
        return False

    # Ako original završava pravom interpunkcijom (tačka, uzvik, pitanje, navodnik)
    if orig_clean[-1] in '.!?"”…':
        # A ako finalno završava sa slovom ili crticom (nema interpunkcije)
        if final_clean[-1].isalpha() or final_clean[-1] in "-—–":
            return True
    return False


# ── Korak 5: Helper za kalkove + validator ──────────────────────────────────


def _primijeni_kalkove_i_validator(
    self, finalno: str, file_name: str, chunk_idx: int
) -> str:
    """
    Primjenjuje kalkovi engine (Korak 2) i morfo validator (Korak 3).
    Fail-safe: ako bilo što ne uspije, vraća originalni tekst.
    """
    import logging
    import re as _re_lore

    # Korak 0.9: HTML atributi cleanup („ → " u atributima)
    try:
        from utils.checkpoint_cleaner import _ocisti_escape as _ocisti_attrs
        finalno = _ocisti_attrs(finalno)
    except Exception as _e:
        logging.debug(f"[pipeline] HTML atributi cleanup greška: {_e}")

    # Korak 1.5: Lore enforcement — zameni zabranjene varijante sa kanonskim
    try:
        kanon = {}
        if hasattr(self, "book_path"):
            from pathlib import Path as _P
            _knjiga_id = _P(self.book_path).stem
            _kanon_path = _P("/root/skriptorij/data/kanon/knjige") / (_knjiga_id + ".json")
            if _kanon_path.exists():
                import json as _json_lore
                _data = _json_lore.loads(_kanon_path.read_text(encoding="utf-8"))
                kanon = _data.get("termini", {})

        if kanon:
            zamenjeno = 0
            for _en, _info in kanon.items():
                _hr = _info.get("hr", _en)
                _forbidden = _info.get("odbacene_varijante", [])
                for _bad in _forbidden:
                    if not _bad or _bad.lower() == _hr.lower():
                        continue
                    _pattern = _re_lore.compile(
                        r"\b" + _re_lore.escape(_bad) + r"\b",
                        _re_lore.IGNORECASE,
                    )
                    _new, _n = _pattern.subn(_hr, finalno)
                    if _n > 0:
                        finalno = _new
                        zamenjeno += _n
            if zamenjeno > 0:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: Lore enforcement — {zamenjeno} zamena",
                    "tech",
                )
    except Exception as _lore_err:
        logging.debug(f"[pipeline] Lore enforcement greška: {_lore_err}")

    # Korak 2: Kalkovi engine
    if _KALKOVI_OK and kalkovi_engine is not None:
        try:
            glosar = {}
            if hasattr(self, "book_context") and self.book_context:
                glosar = getattr(self.book_context, "glosar", {})
            blok_id = f"{file_name}_blok_{chunk_idx}"
            finalno_k, _ = kalkovi_engine.primijeni(
                finalno, glosar=glosar, blok_id=blok_id
            )
            if finalno_k and len(finalno_k.strip()) > 10:
                finalno = finalno_k
        except Exception as e:
            logging.warning(f"[pipeline] Kalkovi engine greška (blok {chunk_idx}): {e}")

    # Korak 3: Morfo validator
    validator = getattr(self, "morfo_validator", None)
    if validator and len(finalno.strip()) > 50:
        try:
            finalno = validator.validiraj(
                finalno, knjiga_id=file_name, chunk_id=chunk_idx
            )
        except Exception as e:
            logging.warning(
                f"[pipeline] Morfo validator greška (blok {chunk_idx}): {e}"
            )

    # Korak 11a: Karantena detektor — pasivno bilježenje kandidiata
    detektor = _get_karantena_detektor()
    if detektor is not None and finalno:
        try:
            knjiga_str = ""
            bp = getattr(self, "book_path", None)
            if bp:
                from pathlib import Path as _Path

                knjiga_str = _Path(bp).stem
            quality_score = 0.0
            qs = getattr(self, "shared_stats", {})
            if qs and isinstance(qs, dict):
                scores = qs.get("quality_scores", {})
                if isinstance(scores, dict) and scores:
                    vals = [v for v in scores.values() if isinstance(v, (int, float))]
                    if vals:
                        quality_score = sum(vals) / len(vals)
            detektor.analiziraj(
                original="",  # originalni EN tekst nije dostupan na ovoj tački pipeline-a
                prijevod=finalno,
                knjiga=knjiga_str,
                chunk_idx=chunk_idx,
                quality_score=quality_score,
            )
        except Exception as e:
            logging.debug(
                f"[pipeline] Karantena detektor greška (blok {chunk_idx}): {e}"
            )

    # Korak 11a-fix: da_konjugator — "modal + da + glagol" → "modal + infinitiv"
    # FIX 2026-09-25: Gemma/GPT-OSS vraćaju "želim da radim" umjesto "želim raditi".
    # Konjugator pretvara SAMO kad su modal i glagol ista lica (subjekt isti).
    try:
        from core.kalkovi.da_konjugator import konjuguj as _da_konjuguj

        if finalno:
            finalno_dk, n_dk = _da_konjuguj(finalno, agresivno=False)
            if n_dk > 0 and finalno_dk and len(finalno_dk.strip()) > 10:
                finalno = finalno_dk
                logging.info(
                    f"[pipeline] da_konjugator: blok {chunk_idx} → {n_dk} konjugacija"
                )
    except Exception as e:
        logging.debug(f"[pipeline] da_konjugator greška (blok {chunk_idx}): {e}")

    # Korak 11b: Rod detektor — aktivna korekcija miješanja roda
    rod_det = _get_rod_detektor()
    if rod_det is not None and finalno:
        try:
            knjiga_id_rod = ""
            bp = getattr(self, "book_path", None)
            if bp:
                from pathlib import Path as _PathR

                knjiga_id_rod = _PathR(bp).stem
            elif hasattr(self, "clean_book_name"):
                knjiga_id_rod = self.clean_book_name

            glosar_rod = {}
            bc = getattr(self, "book_context", None)
            if bc:
                raw_g = getattr(bc, "_glosar", {})
                glosar_rod = {
                    ime: entry.get("rod", "auto")
                    for ime, entry in raw_g.items()
                    if isinstance(entry, dict) and entry.get("rod") in ("M", "Ž")
                }

            finalno_r, n_rod = rod_det.primijeni(
                finalno, knjiga_id=knjiga_id_rod, glosar_rod=glosar_rod
            )
            if n_rod and finalno_r and len(finalno_r.strip()) > 10:
                finalno = finalno_r
                logging.info(
                    f"[pipeline] Rod korekcija: blok {chunk_idx} → {n_rod} zamjena"
                )
        except Exception as e:
            logging.debug(f"[pipeline] Rod detektor greška (blok {chunk_idx}): {e}")

    return finalno


def _init_book_context(self, knjiga_id: str):
    """
    Inicijalizira BookContext i PromptInjector za datu knjigu (Korak 4).
    Pozvati jednom na početku obrade knjige.
    """
    import logging

    if getattr(self, "book_context", None) is not None:
        return  # već inicijalizirano

    if _BOOK_CTX_OK and BookContext is not None:
        self.book_context = BookContext(knjiga_id=knjiga_id)
    else:
        self.book_context = None

    if _INJECTOR_OK and PromptInjector is not None and self.book_context:
        self.prompt_injector = PromptInjector(book_context=self.book_context)
    else:
        self.prompt_injector = None

    # ─── ANALIZA AUTOROVOG STILA ───
    # Analizira prvih 30K znakova EPUB-a i sprema profil u book_context.
    # Profil se automatski ubacuje u PREVODILAC prompt (core/prompts.py).
    if self.book_context is not None:
        try:
            from core.autor_analiza import analiziraj_knjigu

            _epub = getattr(self, "book_path", None)
            if _epub and Path(_epub).exists():
                _profil = analiziraj_knjigu(str(_epub))
                if _profil and not _profil.get("greska"):
                    self.book_context.postavi_autor_stil_profil(_profil)
                    logging.info(
                        f"[autor-analiza] Stil: {_profil.get('stil', '?')} | "
                        f"Ton: {_profil.get('ton', '?')} | "
                        f"Tempo: {'brz' if _profil.get('brz_tempo') else 'spor'} | "
                        f"Dijalog: {int(_profil.get('omjer_dijaloga', 0) * 100)}%"
                    )
                else:
                    logging.warning(f"[autor-analiza] Analiza neuspješna: {_profil}")
            else:
                logging.warning(f"[autor-analiza] Nema book_path: {_epub}")
        except Exception as _e:
            logging.warning(f"[autor-analiza] Greška: {_e}")

    # MorfoValidator — uzima ključ iz fleet managera ako je dostupan
    if _MORFO_OK and MorfoValidator is not None:
        try:
            fleet = getattr(self, "fleet", None)
            api_key = None
            if fleet:
                key_state = fleet.get_best_key("GEMINI")
                if key_state:
                    api_key = key_state.key if hasattr(key_state, "key") else None
            # Fallback na direktni atribut
            if not api_key:
                api_key = getattr(self, "gemini_api_key", None)

            self.morfo_validator = MorfoValidator(
                api_key=api_key,
                skip_ai=(api_key is None),
            )
            self.morfo_validator.set_engine(self)
        except Exception as e:
            logging.warning(f"[pipeline] MorfoValidator init greška: {e}")
            self.morfo_validator = None
    else:
        self.morfo_validator = None

    logging.info(
        f"[pipeline] BookContext={'OK' if self.book_context else 'N/A'} | "
        f"MorfoValidator={'OK' if getattr(self, 'morfo_validator', None) else 'N/A'} | "
        f"knjiga={knjiga_id}"
    )


# ── Quality scoring helper ────────────────────────────────────────────────────


async def _quality_scoring(
    self,
    finalno: str,
    original_chunk,
    chunk_idx: int,
    file_name: str,
    tip_bloka: str,
    prov_label: str,
    tip_ocjenjivanja: str = "opci",
    prevodilac_provider: str = None,
) -> None:
    _PARATEKST_KW = (
        "halftitle",
        "title",
        "otherbyauthor",
        "alsoby",
        "seriespage",
        "copyright",
        "dedication",
        "contents",
        "toc",
        "colophon",
        "frontmatter",
        "backmatter",
        "epigraph",
        "acknowledgment",
        "aboutauthor",
        "cover",
        "insert",
    )
    fn_lower = file_name.lower().replace("_", "").replace("-", "")
    je_paratekst = any(kw in fn_lower for kw in _PARATEKST_KW)

    stem_key = f"{file_name}_blok_{chunk_idx}"
    if not hasattr(self, "_quality_scores"):
        self._quality_scores = {}
    if "quality_scores" not in self.shared_stats:
        self.shared_stats["quality_scores"] = {}

    # T3.2 (shadow, 2026-11-01): signali kvara po bloku, NE mijenja ocjenu.
    # Prije ranih povrataka jer su TOC blokovi imali odsjecen kraj i
    # procurjeli "{ „korektura" bez ikakvog signala (nonprose -> 10.0).
    try:
        from core.metrics import accuracy_shadow

        _acc = accuracy_shadow(
            finalno,
            original_chunk if tip_ocjenjivanja == "prevod" else None,
        )
        _ap = self.checkpoint_dir / "quality_accuracy.json"
        with _QS_LOCK:
            _ex = {}
            if _ap.exists():
                try:
                    _ex = json.loads(_ap.read_text("utf-8"))
                except Exception:
                    _ex = {}
            _ex[stem_key] = _acc
            self._atomic_write(
                _ap,
                json.dumps(_ex, ensure_ascii=False, separators=(",", ":")),
            )
    except Exception:
        logger.exception("[T3.2] accuracy shadow Exception")

    if je_paratekst:
        score_float = 8.5
        self._quality_scores[stem_key] = score_float
        self.shared_stats["quality_scores"][stem_key] = score_float
        self.log(
            f"[{file_name}] Blok {chunk_idx}: paratekst → ocjena {score_float}", "tech"
        )
        return

    # 2026-10-26 M fix: nonprose blokovi (TOC, copyright, dedication, itd.)
    # ne idu kroz AI scorer niti ratio check — samo 10.0
    try:
        from core.quality import _je_nonprose_blok as _nonprose_check

        if _nonprose_check(finalno or ""):
            score_float = 10.0
            self._quality_scores[stem_key] = score_float
            self.shared_stats["quality_scores"][stem_key] = score_float
            self.log(
                f"[{file_name}] Blok {chunk_idx}: nonprose (TOC/paratekst) → 10.0",
                "tech",
            )
            return
    except Exception:
        logger.debug("[C3_fallback] pipeline.py:750 Exception")

    try:
        from core.quality import _scoruj_kvalitetu

        score = await _scoruj_kvalitetu(
            finalno,
            self._call_ai_engine,
            chunk_idx,
            file_name,
            self_obj=self,
            tip_ocjenjivanja=tip_ocjenjivanja,
            prevodilac_provider=prevodilac_provider,
        )
        score_float = float(max(1.0, min(10.0, score)))
        if original_chunk:
            orig_len = _plain_len(original_chunk)
            out_len = _plain_len(finalno)
            if (
                orig_len >= _MIN_ORIG_LEN_FOR_LOSS_CHECK
                and out_len >= _MIN_CAND_LEN_FOR_LOSS_CHECK
            ):
                ratio = out_len / max(1, orig_len)
                old_score = score_float
                # Cap-ovi su namjerno stepenasti: što je veći pad dužine, niži
                # maksimalni score, da nepotpuni blok ne može završiti s 9+.
                # FIX: BCS koristi ~15-25% manje riječi od EN, pa su granice
                # spuštene. Stare (0.60/0.72/0.82) rušile su dobre prijevode
                # na 7.0 čim je ratio bio 0.78-0.82.
                if ratio < 0.55:
                    score_float = min(score_float, 5.0)
                elif ratio < 0.65:
                    score_float = min(score_float, 6.5)
                elif ratio < 0.75:
                    score_float = min(score_float, 7.5)
                if score_float < old_score:
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: score cap zbog mogućeg gubitka teksta "
                        f"(ratio={ratio:.2f}, {old_score:.1f}→{score_float:.1f})",
                        "warning",
                    )

        preview = BeautifulSoup(finalno, "html.parser").get_text()[:80]
        self._quality_scores[stem_key] = score_float
        self.shared_stats["quality_scores"][stem_key] = score_float

        # F3a: metrike — deterministicki brojaci gresaka, paralelno sa score-om.
        # Upisuju se u odvojen fajl quality_metrics.json (ne dira quality_scores).
        try:
            from core.metrics import compute_metrics

            _metrics = compute_metrics(finalno, original_chunk)
            _mp = self.checkpoint_dir / "quality_metrics.json"
            _existing_m = {}
            if _mp.exists():
                try:
                    import json as _json_m

                    _existing_m = _json_m.loads(_mp.read_text("utf-8"))
                except Exception:
                    _existing_m = {}
            try:
                from core.metrics import classify_metrics as _classify

                _metrics["quality_class"] = _classify(_metrics)
            except Exception:
                _metrics["quality_class"] = "?"
            _existing_m[stem_key] = _metrics
            self._atomic_write(
                _mp,
                __import__("json").dumps(_existing_m, ensure_ascii=False, indent=2),
            )
        except Exception:
            logger.exception("[C1_kriticno] pipeline.py:823 Exception")

        if score_float < 6.5:
            _prov = prevodilac_provider or "?"
            self.log(
                f"⚠️ [{file_name}] Blok {chunk_idx} [{tip_bloka}]: "
                f"score={score_float:.1f} (prevodilac: {_prov}) — {preview[:60]}…",
                "warning",
            )
            hr_path = self.checkpoint_dir / "human_review.json"
            try:
                hr_data = (
                    json.loads(_strip_ai_json(hr_path.read_text("utf-8")))
                    if hr_path.exists()
                    else []
                )
                if not any(item.get("stem") == stem_key for item in hr_data):
                    hr_data.append(
                        {
                            "stem": stem_key,
                            "score": score_float,
                            "tip": tip_bloka,
                            "preview": preview,
                        }
                    )
                    self._atomic_write(
                        hr_path,
                        json.dumps(hr_data, ensure_ascii=False, indent=2),
                    )
            except Exception:
                logger.exception("[C1_kriticno] pipeline.py:853 Exception")

        done = self.global_done_chunks
        if done > 0 and done % 10 == 0:
            gc.collect()
            try:
                import json as _json

                qs_path = self.checkpoint_dir / "quality_scores.json"

                # FIX B2: lock oko read-merge-write (sprecava race izmedju niti)
                with _QS_LOCK:
                    existing = {}
                    if qs_path.exists():
                        try:
                            existing = _json.loads(qs_path.read_text("utf-8"))
                        except Exception:
                            existing = {}

                    # Spoji: shared_stats ima prioritet (novije ocjene)
                    merged = dict(existing)
                    for k, v in self.shared_stats.get("quality_scores", {}).items():
                        merged[k] = v

                    # Atomicki upis (B3) — sprecava korupciju pri padu
                    atomic_write_json(qs_path, merged)

                    # Sinhronizuj shared_stats da ne raste bezveze
                    self.shared_stats["quality_scores"] = merged
            except Exception:
                logger.exception("[C1_kriticno] pipeline.py:883 Exception")

    except Exception:
        logger.exception("[C1_kriticno] pipeline.py:886 Exception")


# ── Glavni AI pipeline ────────────────────────────────────────────────────────


async def _posalji_po_paragrafima(
    self, chunk, chunk_idx, file_name, fusion_sys, tip_bloka
):
    """
    Kad Gemini blokira cijeli chunk (PROHIBITED_CONTENT / CONTENT_FILTER),
    pokusaj svaki paragraf zasebno. Toxicne paragrafe markiraj (sa originalom
    u HTML komentaru), ostale prevedi.
    Vraca (tekst, broj_markiranih) ili (None, 0) ako nema paragrafa.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(chunk, "html.parser")
    paras = soup.find_all("p")

    if not paras:
        tekst = soup.get_text().strip()
        if not tekst:
            return None, 0
        recenice = re.split(r"(?<=[.!?])\s+", tekst)
        if len(recenice) < 2:
            return None, 0
        dijelovi = [" ".join(recenice[i : i + 3]) for i in range(0, len(recenice), 3)]
        paras_iter = [(None, d) for d in dijelovi]
        is_html = False
    else:
        paras_iter = [(p, str(p)) for p in paras]
        is_html = True

    rezultati = []
    markirano = 0

    for i, (_, p_html) in enumerate(paras_iter):
        raw, prov = await self._call_ai_engine(
            f"Engleski tekst za prevod:\n{p_html}",
            chunk_idx,
            uloga="PREVODILAC",
            filename=file_name,
            sys_override=fusion_sys,
            tip_bloka=tip_bloka,
        )
        if prov == "CONTENT_FILTER" or not raw:
            original_esc = p_html.replace("--", "- -")
            if is_html:
                rezultati.append(
                    f"<p>[[MANUAL: chunk {chunk_idx}, dio {i + 1}]]"
                    f"<!-- EN: {original_esc} --></p>"
                )
            else:
                rezultati.append(
                    f"[[MANUAL: chunk {chunk_idx}, dio {i + 1}]]"
                    f"<!-- EN: {original_esc} -->"
                )
            markirano += 1
        else:
            tekst = _smart_extract(raw)
            if is_html:
                rezultati.append(f"<p>{tekst}</p>")
            else:
                rezultati.append(tekst)

    return "\n".join(rezultati), markirano


async def process_chunk_with_ai(self, chunk, prev_ctx, next_ctx, chunk_idx, file_name):
    """
    Obrađuje jedan HTML chunk kroz AI pipeline.

    V3.1 pipeline:
      1. Cache provjera
      2. AI prevođenje/lektura
      3. Kalkovi engine (Korak 2) — deterministička korekcija
      4. Morfo validator (Korak 3) — AI provjera glagola
      5. Quality scoring
      6. .chk upis
    """
    force_reprocess = getattr(self, "_force_reprocess", False)

    # 2026-10-24 B4b: glosar_hash pre cache check-a (za keš validaciju po glosaru)
    rel_glosar = self._extract_relevant_glossary(chunk)
    glosar_hash = _hash_glosar(rel_glosar)

    # ── Cache provjera ───────────────────────────────────────────────────────
    if not force_reprocess:
        cached_final = _chk_read(
            self, file_name, chunk_idx, chunk_for_hash=chunk, glosar_hash=glosar_hash
        )
        if cached_final and _detektuj_en_ostatke(cached_final) < 0.08:
            qs = self.shared_stats.get("quality_scores", {})
            stem_key = f"{file_name}_blok_{chunk_idx}"
            raw_val = qs.get(stem_key, None)
            cached_score = _norm_score(raw_val) if raw_val is not None else None

            if cached_score is None or cached_score >= _CACHE_ACCEPT_SCORE:
                if cached_score is None:
                    # Blok nema pohranjenu ocjenu — scoruj keširani sadržaj
                    tip_bloka_c = detektuj_tip_bloka(chunk)
                    await _quality_scoring(
                        self,
                        cached_final,
                        chunk,
                        chunk_idx,
                        file_name,
                        tip_bloka_c,
                        "DATABASE",
                        tip_ocjenjivanja="opci",
                    )
                    new_qs_val = self.shared_stats.get("quality_scores", {}).get(
                        stem_key
                    )
                    cached_score = (
                        _norm_score(new_qs_val) if new_qs_val is not None else None
                    )
                score_info = (
                    f"score={cached_score:.1f}"
                    if cached_score is not None
                    else "score=?"
                )
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: 💾 Učitan iz cache-a ({score_info}).",
                    "tech",
                )
                self.spaseno_iz_checkpointa += 1
                self.global_done_chunks += 1
                return cached_final, "DATABASE"
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ♻️ Cache ignorisan "
                f"(score={cached_score:.1f} < {_CACHE_ACCEPT_SCORE}) — ponovo obrađujem.",
                "warning",
            )

    # ── Setup ────────────────────────────────────────────────────────────────
    knjiga_mode = getattr(self, "knjiga_mode", None)
    if knjiga_mode is None:
        knjiga_mode = self._detect_language(chunk)

    # 2026-10-24 B4b: rel_glosar je vec pomeren gore (pre cache check-a)
    tip_bloka = detektuj_tip_bloka(chunk)
    chapter_summary = self._get_chapter_summary_for_lektor(file_name)

    # ════════════════════════════════════════════════════════════════════════
    # LEKTURA mod
    # ════════════════════════════════════════════════════════════════════════
    if knjiga_mode == "LEKTURA":
        if not force_reprocess:
            cached_lek = _chk_read(
                self,
                file_name,
                chunk_idx,
                "lektura",
                chunk_for_hash=chunk,
                glosar_hash=glosar_hash,
            )
            if cached_lek:
                if not _chk_path(self, file_name, chunk_idx).exists():
                    _chk_write(
                        self, file_name, chunk_idx, cached_lek, chunk_for_hash=chunk
                    )
                qs_l = self.shared_stats.get("quality_scores", {})
                stem_key_l = f"{file_name}_blok_{chunk_idx}"
                raw_val_l = qs_l.get(stem_key_l, None)
                cached_score_l = (
                    _norm_score(raw_val_l) if raw_val_l is not None else None
                )
                if cached_score_l is None:
                    # Blok nema pohranjenu ocjenu — scoruj keširani sadržaj
                    tip_bloka_l = detektuj_tip_bloka(chunk)
                    await _quality_scoring(
                        self,
                        cached_lek,
                        chunk,
                        chunk_idx,
                        file_name,
                        tip_bloka_l,
                        "DATABASE/LEKTURA",
                        tip_ocjenjivanja="lektura",
                        prevodilac_provider="DATABASE/LEKTURA",
                    )
                    new_qs_val_l = self.shared_stats.get("quality_scores", {}).get(
                        stem_key_l
                    )
                    cached_score_l = (
                        _norm_score(new_qs_val_l) if new_qs_val_l is not None else None
                    )
                if cached_score_l is not None and cached_score_l < _CACHE_ACCEPT_SCORE:
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: ♻️ Lektura cache ignorisan "
                        f"(score={cached_score_l:.1f} < {_CACHE_ACCEPT_SCORE}) — ponovo lektoriram.",
                        "warning",
                    )
                else:
                    score_info_l = (
                        f"score={cached_score_l:.1f}"
                        if cached_score_l is not None
                        else "score=?"
                    )
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: 💾 Lektura učitana iz cache-a ({score_info_l}).",
                        "tech",
                    )
                    self.spaseno_iz_checkpointa += 1
                    self.global_done_chunks += 1
                    return cached_lek, "DATABASE/LEKTURA"

        sirovo = _automatska_korekcija(chunk)
        lek_sys = self._get_lektor_prompt(
            prev_kraj=prev_ctx,
            glosar_injekcija=rel_glosar,
            chapter_summary=chapter_summary,
            tip_bloka=tip_bloka,
        )
        lek_sys += _next_ctx_blok(next_ctx)
        p_lek = (
            f"IZVORNI TEKST (već na hrvatskom):\n{sirovo}\n\n"
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

        if raw_l:
            finalno = _smart_extract(raw_l)
            if not finalno or _je_placeholder_lokalni(finalno):
                finalno = sirovo
        else:
            finalno = sirovo
            prov_l = "AUTO-HR"
        if _je_sumnjiv_gubitak_teksta(chunk, finalno, uloga="LEKTOR"):
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Lektor vratio prekratak tekst — vraćam sigurni ulaz.",
                "warning",
            )
            finalno = sirovo

        cist_priv = _agresivno_cisti(finalno)
        if not cist_priv or len(cist_priv.strip()) < 30:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Čišćenje dalo prazno – čuvam original.",
                "warning",
            )
            finalno = chunk
        else:
            finalno = _post_process_tipografija(cist_priv)

        # ── KOREKTOR pass (temp 0.15) ─────────────────────────────────────────
        pre_korektor_l = finalno
        raw_kor_l, prov_kor_l = await self._call_ai_engine(
            finalno,
            chunk_idx,
            uloga="KOREKTOR",
            filename=file_name,
            tip_bloka=tip_bloka,
        )
        if raw_kor_l:
            kor_l = _smart_extract(raw_kor_l)
            if kor_l and not _je_placeholder_lokalni(kor_l) and len(kor_l.strip()) > 20:
                if _je_sumnjiv_gubitak_teksta(pre_korektor_l, kor_l, uloga="LEKTOR"):
                    self.log(
                        f"[{file_name}] Blok {chunk_idx}: ⚠️ Korektor skratio blok — zadržavam lektor verziju.",
                        "warning",
                    )
                else:
                    finalno = kor_l

        finalno = _primijeni_kalkove_i_validator(self, finalno, file_name, chunk_idx)

        if _je_placeholder_lokalni(finalno):
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⚠️ Lektor vratio meta-odgovor umjesto teksta — vraćam sigurni ulaz.",
                "warning",
            )
            finalno = sirovo

        # FIX 1.7: Provera prekinutog teksta
        if _je_prekinut_tekst(chunk, finalno):
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ✂️ Tekst prekinut (nema interpunkcije na kraju) — odbijam upis, pokušavam ponovo.",
                "warning",
            )
            self.chunk_skips += 1
            return None, "TRUNCATED"

        _chk_write(
            self,
            file_name,
            chunk_idx,
            finalno,
            "lektura",
            chunk_for_hash=chunk,
            glosar_hash=glosar_hash,
            model_hash=prov_l,
        )
        _chk_write(
            self,
            file_name,
            chunk_idx,
            finalno,
            chunk_for_hash=chunk,
            glosar_hash=glosar_hash,
            model_hash=prov_l,
        )

        self.global_done_chunks += 1
        self.stvarno_prevedeno_u_sesiji += 1
        self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji
        gc.collect()
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ✍️ HR lektura ({prov_l}→{prov_kor_l})",
            "tech",
        )

        await _quality_scoring(
            self,
            finalno,
            chunk,
            chunk_idx,
            file_name,
            tip_bloka,
            f"LEKTURA/{prov_l}",
            tip_ocjenjivanja="lektura",
            prevodilac_provider=prov_l,
        )
        return finalno, f"LEKTURA/{prov_l}→{prov_kor_l}"

    # ════════════════════════════════════════════════════════════════════════
    # PREVOD mod
    # ════════════════════════════════════════════════════════════════════════

    sirovo_cached = None
    if not force_reprocess:
        sirovo_cached = _chk_read(
            self,
            file_name,
            chunk_idx,
            "prevod",
            chunk_for_hash=chunk,
            glosar_hash=glosar_hash,
        )
        if sirovo_cached:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ♻️ Sirovi prijevod iz cache-a — nastavljam od lektora.",
                "tech",
            )

    if sirovo_cached:
        sirovo = sirovo_cached
        prov1 = "DATABASE/PREVOD"
    else:
        fusion_sys = self._get_prevodilac_prompt(
            glosar_chunk=rel_glosar, prev_kraj=prev_ctx, tip_bloka=tip_bloka
        )
        fusion_sys += _next_ctx_blok(next_ctx)
        # V1.0: Dodaj few-shot primjere iz globalne baze
        if _FEW_SHOT_OK and formatiraj_za_prompt:
            try:
                en_plain = BeautifulSoup(chunk, "html.parser").get_text()[:300]
                fs_text = formatiraj_za_prompt(en_plain, tip_bloka, max_n=2)
                if fs_text:
                    fusion_sys += "\n" + fs_text
            except Exception:
                logger.exception("[C1_http] pipeline.py:1256 Exception")
        p_fusion = f"Engleski tekst za prevod:\n{chunk}"
        raw_fusion, prov1 = await self._call_ai_engine(
            p_fusion,
            chunk_idx,
            uloga="PREVODILAC",
            filename=file_name,
            sys_override=fusion_sys,
            tip_bloka=tip_bloka,
        )
        if prov1 == "CONTENT_FILTER":
            self.log(
                f"[{file_name}] Blok {chunk_idx}: ⛔ Content filter — "
                f"pokusavam paragraf po paragraf",
                "warning",
            )
            bisekt, markirano = await _posalji_po_paragrafima(
                self,
                chunk,
                chunk_idx,
                file_name,
                fusion_sys,
                tip_bloka,
            )
            if bisekt:
                raw_fusion = bisekt
                prov1 = f"BISEKCIJA/{markirano}mark"
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ✅ Bisekcija "
                    f"prosla, markirano {markirano} paragraf(a)",
                    "tech",
                )
            else:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ❌ Bisekcija "
                    f"nije uspjela (nema paragrafa)",
                    "warning",
                )
                self.chunk_skips += 1
                return None, "CONTENT_FILTER"
        if not raw_fusion:
            if prov1 == "ALL_FAILED":
                marker = (
                    f"<p>[[NEPREVEDENO: chunk {chunk_idx}]]</p>\n"
                    f"<p><!-- EN original sacuvan u .prevod fajlu --></p>"
                )
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ❌ Svi provideri pali "
                    f"poslije 3 kruga — upisujem marker, nastavljam dalje",
                    "error",
                )
                self.chunk_skips += 1
                _chk_write(
                    self,
                    file_name,
                    chunk_idx,
                    chunk,
                    "prevod",
                    chunk_for_hash=chunk,
                    glosar_hash=glosar_hash,
                )
                _chk_write(
                    self,
                    file_name,
                    chunk_idx,
                    marker,
                    chunk_for_hash=chunk,
                    glosar_hash=glosar_hash,
                )
                return marker, "ALL_FAILED"
            self.chunk_skips += 1
            return None, "N/A"

        sirovo = _agresivno_cisti(_smart_extract(raw_fusion))
        _chk_write(
            self,
            file_name,
            chunk_idx,
            sirovo,
            "prevod",
            chunk_for_hash=chunk,
            glosar_hash=glosar_hash,
            model_hash=prov1,
        )

    lek_sys = self._get_lektor_prompt(
        prev_kraj=prev_ctx,
        glosar_injekcija=rel_glosar,
        chapter_summary=chapter_summary,
        tip_bloka=tip_bloka,
    )
    lek_sys += _next_ctx_blok(next_ctx)
    p_lek = (
        f"IZVORNI ENGLESKI TEKST:\n{chunk}\n\n"
        f"SIROVI PRIJEVOD:\n{sirovo}\n\n"
        f"Profesionalno lektoriraj na hrvatski."
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

    if _detektuj_en_ostatke(finalno) > 0.10:
        spas, _ = await _spasi_od_sirovog(
            self,
            sirovo,
            chunk,
            chunk_idx,
            file_name,
            prev_ctx,
            rel_glosar,
            "en>15%",
            tip_bloka,
        )
        if spas:
            finalno = spas

    if _detektuj_halucinaciju(chunk, finalno):
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ⚠️ Sumnja na halucinaciju — pokušavam rescue",
            "warning",
        )
        spas_hal, _ = await _spasi_od_sirovog(
            self,
            sirovo,
            chunk,
            chunk_idx,
            file_name,
            prev_ctx,
            rel_glosar,
            "halucinacija",
            tip_bloka,
        )
        if spas_hal:
            finalno = spas_hal
    if _je_sumnjiv_gubitak_teksta(chunk, finalno, uloga="PREVODILAC"):
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ⚠️ Moguć gubitak teksta nakon lekture — pokušavam rescue.",
            "warning",
        )
        spas_gubitak, _ = await _spasi_od_sirovog(
            self,
            sirovo,
            chunk,
            chunk_idx,
            file_name,
            prev_ctx,
            rel_glosar,
            "gubitak teksta",
            tip_bloka,
        )
        if spas_gubitak and not _je_sumnjiv_gubitak_teksta(
            chunk, spas_gubitak, uloga="PREVODILAC"
        ):
            finalno = spas_gubitak
        else:
            finalno = sirovo

    # ── KOREKTOR pass (temp 0.15) ─────────────────────────────────────────────
    # V1.0: Skip Oracle — preskoči korektor ako je lektor jedva išta mijenjao
    pre_korektor = finalno
    skip_kor = False
    prov3 = "N/A"  # BUG #1/#2 fix: inicijalizacija prije uvjetnih blokova
    raw_kor = None  # BUG #1/#2 fix: spriječava UnboundLocalError pri exceptu
    if _SKIP_ORACLE_OK and moze_skipovati_korektor:
        try:
            prevod_score = self.shared_stats.get("quality_scores", {}).get(
                f"{file_name}_blok_{chunk_idx}", 0.0
            )
            moze, razlog = moze_skipovati_korektor(prevod_score, sirovo, finalno)
            if moze:
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚡ Korektor preskočen ({razlog})",
                    "tech",
                )
                skip_kor = True
                prov3 = "SKIP_ORACLE"
        except Exception:
            logger.exception("[C1_http] pipeline.py:1440 Exception")

    if not skip_kor:
        raw_kor, prov3 = await self._call_ai_engine(
            finalno,
            chunk_idx,
            uloga="KOREKTOR",
            filename=file_name,
            tip_bloka=tip_bloka,
        )
    if not skip_kor and raw_kor:
        kor = _smart_extract(raw_kor)
        if kor and not _je_placeholder_lokalni(kor) and len(kor.strip()) > 20:
            if _je_sumnjiv_gubitak_teksta(pre_korektor, kor, uloga="LEKTOR"):
                self.log(
                    f"[{file_name}] Blok {chunk_idx}: ⚠️ Korektor skratio sadržaj — zadržavam prethodnu verziju.",
                    "warning",
                )
            else:
                finalno = kor

    finalno = _post_process_tipografija(_agresivno_cisti(finalno))
    finalno = _primijeni_kalkove_i_validator(self, finalno, file_name, chunk_idx)

    if _je_placeholder_lokalni(finalno):
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ⚠️ Meta-odgovor umjesto prevoda — vraćam sigurnu verziju.",
            "warning",
        )
        finalno = sirovo

    # FIX 1.7: Provera prekinutog teksta
    if _je_prekinut_tekst(chunk, finalno):
        self.log(
            f"[{file_name}] Blok {chunk_idx}: ✂️ Tekst prekinut (nema interpunkcije na kraju) — odbijam upis, pokušavam ponovo.",
            "warning",
        )
        self.chunk_skips += 1
        return None, "TRUNCATED"

    _chk_write(
        self,
        file_name,
        chunk_idx,
        finalno,
        chunk_for_hash=chunk,
        glosar_hash=glosar_hash,
        model_hash=prov1,
    )
    with contextlib.suppress(Exception):
        _chk_path(self, file_name, chunk_idx, "prevod").unlink(missing_ok=True)

    self.global_done_chunks += 1
    self.stvarno_prevedeno_u_sesiji += 1
    self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji

    prov_label = f"{prov1}→{prov2}→{prov3}"
    await _quality_scoring(
        self,
        finalno,
        chunk,
        chunk_idx,
        file_name,
        tip_bloka,
        prov_label,
        tip_ocjenjivanja="prevod",
        prevodilac_provider=prov1,
    )

    # Korak 9 — Dinamički few-shot: dodaj dobar prijevod u BookContext
    if _BOOK_CTX_OK and getattr(self, "book_context", None):
        try:
            stem_key = f"{file_name}_blok_{chunk_idx}"
            qs_score = self.shared_stats.get("quality_scores", {}).get(stem_key, 0.0)
            if qs_score >= 8.5:
                en_tekst = BeautifulSoup(chunk, "html.parser").get_text()[:200]
                hr_tekst = BeautifulSoup(finalno, "html.parser").get_text()[:200]
                self.book_context.dodaj_few_shot_par(
                    originalni=en_tekst,
                    prevedeni=hr_tekst,
                    score=qs_score,
                )
                # V1.0: Dodaj i u GLOBALNI few-shot (za sve buduće knjige)
                if _FEW_SHOT_OK and dodaj_odlican_prevod:
                    with contextlib.suppress(Exception):
                        dodaj_odlican_prevod(en_tekst, hr_tekst, qs_score, tip_bloka)
        except Exception:
            logger.exception("[C1_http] pipeline.py:1527 Exception")

    aud = (
        f"📦 Blok {chunk_idx} [{tip_bloka}] | {prov1}→{prov2} | "
        f"EN: {BeautifulSoup(chunk, 'html.parser').get_text()[:50]}… → "
        f"HR: {BeautifulSoup(finalno, 'html.parser').get_text()[:50]}…"
    )
    self.log("", "accordion", en_text=aud)
    return finalno, f"{prov1}→{prov2}→{prov3}"


# ── Retry wrapper ─────────────────────────────────────────────────────────────


async def process_chunk_with_retry(
    self, chunk, prev_ctx, next_ctx, chunk_idx, file_name, max_retries=3
):
    """
    Obrađuje chunk sa ponavljanjem ako ne uspije.
    V3.1: Ispravan async poziv workers_v2 (WorkerV2 je sync klasa,
    pokreće se u executor-u da ne blokira event loop).
    """
    if USE_WORKERS_V2 and _V2_DOSTUPAN:
        self.log(f"[{file_name}] Blok {chunk_idx}: 🚀 V10.4 workers_v2 aktivan", "tech")
        try:
            tip_bloka = detektuj_tip_bloka(chunk)
            chapter_summary = self._get_chapter_summary_for_lektor(file_name)

            worker = WorkerV2(
                uloga="prevodilac"
                if getattr(self, "knjiga_mode", "PREVOD") == "PREVOD"
                else "lektor",
                tip_bloka=tip_bloka,
                book_context=getattr(self, "book_context", None),
                chapter_summary=chapter_summary,
            )

            # WorkerV2.obradi_chunk je sinkron — pokreni u thread pool-u
            # BUG #6 fix: get_event_loop() deprecated u Python 3.10+
            rezultat = await asyncio.get_running_loop().run_in_executor(
                None, lambda: worker.obradi_chunk(chunk)
            )

            if rezultat and rezultat.get("success") and rezultat.get("tekst"):
                tekst = rezultat["tekst"]
                engine_label = f"V2/{rezultat.get('provider', '?')}/{rezultat.get('model_ime', '?')}"
                if not hasattr(self, "_v2_engine_stats"):
                    self._v2_engine_stats = {}
                self._v2_engine_stats[f"{file_name}_blok_{chunk_idx}"] = engine_label

                # ── Korak 7: Zabilježi prevoditelja za nezavisni scorer ──
                if _SCORER_V2_OK and _zabilježi_prev:
                    with contextlib.suppress(Exception):
                        _zabilježi_prev(file_name, chunk_idx, engine_label)

                # Upis checkpointa i quality scoringa
                _chk_write(self, file_name, chunk_idx, tekst, chunk_for_hash=chunk)
                self.global_done_chunks += 1
                self.stvarno_prevedeno_u_sesiji += 1
                self.shared_stats["stvarno_prevedeno"] = self.stvarno_prevedeno_u_sesiji

                # Sačuvaj quality score iz V2
                stem_key = f"{file_name}_blok_{chunk_idx}"
                if not hasattr(self, "_quality_scores"):
                    self._quality_scores = {}
                if "quality_scores" not in self.shared_stats:
                    self.shared_stats["quality_scores"] = {}
                # F2: uvek pozovi _quality_scoring (AI scorer) — jedan izvor istine.
                # V2 heuristicki score ostaje samo kao interni hint u WorkersV2
                # (za retry odluku), ne pise se u quality_scores.json.
                # Ako AI scorer padne, fallback na V2 heuristicki.
                try:
                    await _quality_scoring(
                        self,
                        tekst,
                        chunk,
                        chunk_idx,
                        file_name,
                        tip_bloka,
                        engine_label,
                        tip_ocjenjivanja="prevod",
                        prevodilac_provider=engine_label,
                    )
                    qs = self.shared_stats.get("quality_scores", {}).get(stem_key, 0.0)
                except Exception as _qs_err:
                    qs_raw = rezultat.get("quality_score", 0.0)
                    qs = float(qs_raw) if qs_raw else 0.0
                    self.log(
                        f"⚠️ [{file_name}] Blok {chunk_idx}: AI scorer pao "
                        f"({_qs_err}), koristim V2 heuristicki ({qs:.1f})",
                        "warning",
                    )
                    self._quality_scores[stem_key] = qs
                    self.shared_stats["quality_scores"][stem_key] = qs

                return tekst, engine_label

            self.log(
                f"⚠️ [{file_name}] Blok {chunk_idx}: V2 nije vratio tekst — fallback na V1",
                "warning",
            )
        except Exception as v2_err:
            self.log(
                f"⚠️ [{file_name}] Blok {chunk_idx}: V2 iznimka "
                f"({type(v2_err).__name__}: {v2_err}) — fallback na V1",
                "warning",
            )

    # ── V1 fallback ──────────────────────────────────────────────────────────
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
        f"❌ Blok {chunk_idx} nije obrađen ni nakon {max_retries} pokušaja — upisujem NEPREVEDENO marker",
        "error",
    )
    _marker = f"<p>[[NEPREVEDENO: blok {chunk_idx}]]</p>"
    try:
        _chk_write(self, file_name, chunk_idx, _marker, chunk_for_hash=chunk)
    except Exception as _e:
        self.log(f"⚠️ Ne mogu upisati marker .chk: {_e}", "warning")
    _stem = f"{file_name}_blok_{chunk_idx}"
    if not hasattr(self, "_quality_scores"):
        self._quality_scores = {}
    if "quality_scores" not in self.shared_stats:
        self.shared_stats["quality_scores"] = {}
    self._quality_scores[_stem] = 1.0
    self.shared_stats["quality_scores"][_stem] = 1.0
    return _marker, "NEPREVEDENO-MARKER"