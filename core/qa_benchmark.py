# core/qa_benchmark.py
"""
BooklyFi — Korak 10: QA Benchmark
==================================
BEZ AI-a. Klasificira greške pomoću regex-a, hunspell-a i statistike.

Poziv:
    from core.qa_benchmark import qa_benchmark
    await qa_benchmark.analiziraj_fajl(file_name, quality_scores_path)

Generira:
    logs/qa_baseline_<knjiga>_<datum>.json
    logs/qa_trend_<knjiga>.json  (usporedba s prethodnim baseline-om)
"""

import json
import re
import os
import random
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import CHECKPOINT_BASE_DIR, INPUT_DIR

logger = logging.getLogger(__name__)

# ─── Putanje ──────────────────────────────────────────────────────────────────

_LOGS_DIR = INPUT_DIR / "_logs"
_CHK_DIR  = CHECKPOINT_BASE_DIR

try:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    _LOGS_DIR = Path(os.path.expanduser("~")) / "skriptorij_logs"
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Konstante ────────────────────────────────────────────────────────────────

UZORAKA_PO_KNJIZI = 20   # koliko random chunkova analiziramo
MIN_DULJINA_BLOKA = 60   # kraći blokovi se preskačaju (naslovi, meta)

# ─── Regex liste grešaka ──────────────────────────────────────────────────────

# Ekavizmi — oblici koji NE smiju biti u ijekavskom tekstu
_EKAVIZMI = [
    r"\bvreme\b", r"\bvremena\b", r"\bvremenu\b",
    r"\bneverovatan\b", r"\bneverovatno\b", r"\bneverovatna\b",
    r"\bposedujem?\b", r"\bposeduje\b", r"\bposedovati\b",
    r"\bprofesor\b(?!ica)",              # samo kada nije profesorica
    r"\bsredio\b", r"\bsređuje\b",
    r"\bkree\b", r"\bkrenuo sam\b",     # krenuo = ok, ali kree nije
    r"\bmeđutim\b",                      # medjutim je ekavski oblik bez đ
    r"\bmoze\b", r"\bmogu[ćc]e\b(?<!\bmoguće\b)",
    r"\bvidi se\b",
    r"\bzapravo\b",                      # nije ekavizam ali provjeravamo
    r"\bčovek\b", r"\bčoveka\b",
    r"\bvolim\b",                        # ok samo kao kontrola da regex radi
    r"\bniko\b",                         # niko = ekavizam; nitko = ijekavski
    r"\bsvako\b(?!m\b)",                 # svako/svakog ok, ali svakome problematično
    r"\bsrp[sc]ki\b",
    r"\bne mogu[ćc]e\b",
    r"\bte[žz]ak\b",
    r"\bte[žz]e\b",
    r"\btre[bć]a\b",
    r"\bopste\b", r"\bopšte\b",
    r"\bpametan\b", r"\bpametno\b",
]

# Čisti ekavizmi (je→e zamjena)
_EKAVIZMI_JEKAVSKI = [
    (r"\bvrijeme\b", r"\bvreme\b"),        # vrijeme → vreme = greška
    (r"\bdijete\b",  r"\bdete\b"),
    (r"\blijepo\b",  r"\blijepo\b"),       # samo provjera da je lijepo, ne lepo
    (r"\bvidjeti\b", r"\bvidjeti\b"),
]

# Strogi ekavizmi (uvijek greška u ijekavici)
_EKAVIZMI_STROGI = [
    r"\bvreme\b",
    r"\bniko\b",
    r"\bčovek\b",
    r"\bdete\b",
    r"\bdecu\b",
    r"\bdevojka\b",
    r"\bdevojke\b",
    r"\bdevojku\b",
    r"\blepo\b",
    r"\blepše\b",
    r"\blepota\b",
    r"\bposedujem?\b",
    r"\bposeduje\b",
    r"\bopšte\b",
    r"\bsvakome\b",
]

# Kalkovi — konstrukacije koje treba izbjegavati
_KALKOVI_REGEX = [
    (r"\bbio je u stanju da\b",         "kalk: bio je u stanju da"),
    (r"\bnije bio u mogu[ćc]nosti\b",   "kalk: nije bio u mogućnosti"),
    (r"\buspio je da\b",                "kalk: uspio je da"),
    (r"\bpokušao je da\b",              "kalk: pokušao je da"),
    (r"\bu pogledu toga\b",             "kalk: u pogledu toga"),
    (r"\bod strane\s+\w+a\b",           "kalk: od strane X-a"),
    (r"\bpo pitanju\s+",                "kalk: po pitanju"),
    (r"\bu odnosu na to\b",             "kalk: u odnosu na to"),
    (r"\bkoristeći se\b",               "kalk: koristeći se"),
    (r"\bimati u vidu\b",               "kalk: imati u vidu"),
    (r"\buzeti u obzir to da\b",        "kalk: uzeti u obzir to da"),
    (r"\bu svjetlu toga\b",             "kalk: u svjetlu toga"),
    (r"\bna osnovu toga\b",             "kalk: na osnovu toga"),
    (r"\biz razloga što\b",             "kalk: iz razloga što"),
    (r"\bimajući u vidu\b",             "kalk: imajući u vidu"),
    (r"\bprema tome\b",                 "kalk: prema tome"),
    (r"\bu cilju\b",                    "kalk: u cilju"),
    (r"\bs ciljem da\b",                "kalk: s ciljem da"),
    (r"\bsa svrhom\b",                  "kalk: sa svrhom"),
    (r"\bna neki način\b",              "kalk: na neki način"),
]

# Tipografija — regex za greške
_TIPOGRAFIJA_REGEX = [
    (r'"[^"]{1,80}"',                   'ascii navodnici umjesto „..."'),
    (r"\s,",                            "razmak ispred zareza"),
    (r"\s\.",                           "razmak ispred točke"),
    (r"  +",                            "višestruki razmak"),
    (r"\.{4,}",                         "više od 3 tačke (elipsa)"),
    (r"--",                             "dvostruka crtica umjesto em-crtice"),
    (r"\s—\s*$",                        "em-crtica bez zatvaranja"),
    (r"^\s*—\s*$",                      "osamljena em-crtica"),
]

# Engleski ostaci (uvijek greška)
_ENGLESKI_OSTACI = [
    r"\bin order to\b",
    r"\bnevertheless\b",
    r"\bhowever\b",
    r"\bmoreover\b",
    r"\bfurthermore\b",
    r"\bconsequently\b",
    r"\btherefore\b",
    r"\bthus\b",
    r"\bhence\b",
    r"\bregarding\b",
    r"\bwhereas\b",
    r"\bthereof\b",
    r"\bherein\b",
    r"\bhereby\b",
    r"\baforesaid\b",
    r"\bnotwithstanding\b",
]


# ─── Hunspell provjera ────────────────────────────────────────────────────────

def _provjeri_hunspell(tekst: str) -> list[str]:
    """
    Pokreće hunspell na tekstu, vraća listu nepoznatih riječi.
    Ako hunspell nije instaliran, vraća prazan niz.
    """
    try:
        result = subprocess.run(
            ["hunspell", "-d", "hr_HR,bs_BA", "-l"],
            input=tekst,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            rijeci = [w.strip() for w in result.stdout.splitlines() if w.strip()]
            # Filtriraj vlastita imena (počinju velikim slovom) i kratke tokene
            rijeci = [r for r in rijeci if len(r) > 3 and not r[0].isupper()]
            return rijeci[:10]  # max 10 grešaka po bloku
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def _hunspell_dostupan() -> bool:
    """Provjeri je li hunspell instaliran."""
    try:
        subprocess.run(["hunspell", "--version"], capture_output=True, timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ─── Analiza jednog bloka ─────────────────────────────────────────────────────

def analiziraj_blok(tekst: str, koristiti_hunspell: bool = False) -> dict:
    """
    Analizira jedan chunk BEZ AI-a.
    Vraća strukturirani dict s greškama i score-om.
    """
    greske = {
        "ekavizmi":   [],
        "kalkovi":    [],
        "tipografija":[],
        "engleski":   [],
        "hunspell":   [],
    }
    tekst_lower = tekst.lower()

    # 1. Ekavizmi
    for pattern in _EKAVIZMI_STROGI:
        if re.search(pattern, tekst_lower):
            greske["ekavizmi"].append(pattern.replace(r"\b", "").replace("\\b", ""))

    # 2. Kalkovi
    for pattern, opis in _KALKOVI_REGEX:
        if re.search(pattern, tekst_lower):
            greske["kalkovi"].append(opis)

    # 3. Tipografija
    for pattern, opis in _TIPOGRAFIJA_REGEX:
        if re.search(pattern, tekst):
            greske["tipografija"].append(opis)

    # 4. Engleski ostaci
    for pattern in _ENGLESKI_OSTACI:
        if re.search(pattern, tekst_lower):
            greske["engleski"].append(pattern.replace(r"\b", "").replace("\\b", ""))

    # 5. Hunspell (opcionalno)
    if koristiti_hunspell:
        greske["hunspell"] = _provjeri_hunspell(tekst)

    # Penalizacija za benchmark score
    kazne = (
        len(greske["ekavizmi"])   * 2.0 +
        len(greske["kalkovi"])    * 1.5 +
        len(greske["tipografija"])* 0.5 +
        len(greske["engleski"])   * 3.0 +
        len(greske["hunspell"])   * 0.3
    )
    benchmark_score = round(max(0.0, 10.0 - kazne), 1)

    ukupno_gresaka = sum(len(v) for v in greske.values())

    return {
        "greske":           greske,
        "ukupno_gresaka":   ukupno_gresaka,
        "benchmark_score":  benchmark_score,
        "ima_ekavizama":    len(greske["ekavizmi"]) > 0,
        "ima_kalkova":      len(greske["kalkovi"]) > 0,
        "ima_tipografije":  len(greske["tipografija"]) > 0,
        "ima_engleskog":    len(greske["engleski"]) > 0,
    }


# ─── Učitavanje chunkova iz .chk fajlova ─────────────────────────────────────

def _ucitaj_chunkove(file_name: str) -> list[dict]:
    """
    Čita sve .chk fajlove za dati file_name.
    Vraća listu {chunk_idx, tekst, quality_score}.
    """
    chunkovi = []
    stem = Path(file_name).stem

    # Tražimo u svim standardnim lokacijama
    pretrazne_putanje = [
        _CHK_DIR / stem,
        _BASE_DIR / "output" / stem,
        _BASE_DIR / "prijevodi" / stem,
    ]

    for dir_path in pretrazne_putanje:
        if not dir_path.exists():
            continue
        for chk_file in sorted(dir_path.glob("*.chk")):
            try:
                with open(chk_file, "r", encoding="utf-8") as f:
                    sadrzaj = f.read().strip()

                # Format: JSON ili plain tekst
                tekst = sadrzaj
                score = None
                if sadrzaj.startswith("{"):
                    try:
                        data = json.loads(sadrzaj)
                        tekst = data.get("text") or data.get("tekst") or sadrzaj
                        score = data.get("quality_score") or data.get("score")
                    except json.JSONDecodeError:
                        pass

                if len(tekst.strip()) >= MIN_DULJINA_BLOKA:
                    # Izvuci chunk index iz naziva fajla (npr. 0042.chk)
                    idx = int(re.search(r"(\d+)", chk_file.stem).group(1)) if re.search(r"(\d+)", chk_file.stem) else 0
                    chunkovi.append({
                        "chunk_idx":     idx,
                        "tekst":         tekst,
                        "quality_score": float(score) if score is not None else None,
                        "chk_fajl":      str(chk_file),
                    })
            except Exception as e:
                logger.warning(f"qa_benchmark: ne mogu čitati {chk_file}: {e}")

        if chunkovi:
            break  # našli smo ih, ne nastavljamo pretragu

    return chunkovi


def _ucitaj_quality_scores(quality_scores_path: Optional[str]) -> dict:
    """Čita quality_scores.json ako postoji."""
    if not quality_scores_path:
        return {}
    try:
        with open(quality_scores_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ─── Trend analiza ────────────────────────────────────────────────────────────

def _ucitaj_trend(trend_path: Path) -> Optional[dict]:
    """Čita prethodni trend fajl ako postoji."""
    try:
        if trend_path.exists():
            with open(trend_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _generiši_trend_report(tekuci: dict, prethodni: Optional[dict]) -> dict:
    """Uspoređuje tekuci baseline s prethodnim."""
    if prethodni is None:
        return {"status": "prvi_baseline", "promjene": {}}

    promjene = {}
    for kljuc in ["avg_benchmark_score", "pct_bez_gresaka",
                  "pct_ekavizmi", "pct_kalkovi", "pct_tipografija"]:
        staro = prethodni.get("summary", {}).get(kljuc)
        novo  = tekuci.get("summary", {}).get(kljuc)
        if staro is not None and novo is not None:
            delta = round(novo - staro, 2)
            promjene[kljuc] = {
                "staro":  staro,
                "novo":   novo,
                "delta":  delta,
                "trend":  "↑" if delta > 0 else ("↓" if delta < 0 else "→"),
            }

    return {
        "status":   "usporedba",
        "promjene": promjene,
        "prethodni_datum": prethodni.get("datum"),
    }


# ─── Glavna klasa ─────────────────────────────────────────────────────────────

class QABenchmark:
    """
    QA Benchmark engine — BEZ AI-a.
    Poziva se na kraju obrade knjige.
    """

    def __init__(self):
        self._hunspell_ok = _hunspell_dostupan()
        if self._hunspell_ok:
            logger.info("qa_benchmark: hunspell dostupan — koristim za provjeru pravopisa")
        else:
            logger.info("qa_benchmark: hunspell nije dostupan — preskačem tu provjeru")

    def analiziraj_fajl(
        self,
        file_name: str,
        quality_scores_path: Optional[str] = None,
    ) -> dict:
        """
        Glavni ulaz. Analizira knjige i sprema baseline + trend.

        Args:
            file_name: naziv EPUB fajla (npr. "knjiga.epub")
            quality_scores_path: putanja do quality_scores.json (opcionalno)

        Returns:
            dict s rezultatima analize
        """
        stem       = Path(file_name).stem
        datum_str  = datetime.now().strftime("%Y%m%d_%H%M")
        baseline_path = _LOGS_DIR / f"qa_baseline_{stem}_{datum_str}.json"
        trend_path    = _LOGS_DIR / f"qa_trend_{stem}.json"

        # 1. Učitaj chunkove
        svi_chunkovi = _ucitaj_chunkove(file_name)

        # Spoji s quality_scores ako postoje
        qs_data = _ucitaj_quality_scores(quality_scores_path)
        for chunk in svi_chunkovi:
            idx  = chunk["chunk_idx"]
            stem_key = f"{stem}_blok_{idx:04d}"
            if stem_key in qs_data and chunk["quality_score"] is None:
                v = qs_data[stem_key]
                chunk["quality_score"] = float(v) if isinstance(v, (int, float)) else float(v.get("score", 0))

        if not svi_chunkovi:
            logger.warning(f"qa_benchmark: nema chunkova za {file_name}")
            return {"greska": "nema_chunkova", "file_name": file_name}

        # 2. Uzorkovanje — max UZORAKA_PO_KNJIZI
        if len(svi_chunkovi) > UZORAKA_PO_KNJIZI:
            uzorak = random.sample(svi_chunkovi, UZORAKA_PO_KNJIZI)
        else:
            uzorak = svi_chunkovi

        # 3. Analiza svakog bloka
        rezultati = []
        for chunk in uzorak:
            analiza = analiziraj_blok(
                chunk["tekst"],
                koristiti_hunspell=self._hunspell_ok,
            )
            rezultati.append({
                "chunk_idx":       chunk["chunk_idx"],
                "quality_score":   chunk.get("quality_score"),
                "benchmark_score": analiza["benchmark_score"],
                "ukupno_gresaka":  analiza["ukupno_gresaka"],
                "greske":          analiza["greske"],
                "ima_ekavizama":   analiza["ima_ekavizama"],
                "ima_kalkova":     analiza["ima_kalkova"],
                "ima_tipografije": analiza["ima_tipografije"],
                "ima_engleskog":   analiza["ima_engleskog"],
                "tekst_preview":   chunk["tekst"][:120].replace("\n", " "),
            })

        # 4. Summary statistika
        n = len(rezultati)
        avg_benchmark = round(sum(r["benchmark_score"] for r in rezultati) / n, 2) if n else 0.0
        avg_quality   = None
        q_vals = [r["quality_score"] for r in rezultati if r["quality_score"] is not None]
        if q_vals:
            avg_quality = round(sum(q_vals) / len(q_vals), 2)

        bez_gresaka   = sum(1 for r in rezultati if r["ukupno_gresaka"] == 0)
        s_ekavizmima  = sum(1 for r in rezultati if r["ima_ekavizama"])
        s_kalkovima   = sum(1 for r in rezultati if r["ima_kalkova"])
        s_tipografijom= sum(1 for r in rezultati if r["ima_tipografije"])
        s_engleskim   = sum(1 for r in rezultati if r["ima_engleskog"])

        summary = {
            "ukupno_uzoraka":    n,
            "ukupno_chunkova":   len(svi_chunkovi),
            "avg_benchmark_score": avg_benchmark,
            "avg_quality_score": avg_quality,
            "bez_gresaka":       bez_gresaka,
            "pct_bez_gresaka":   round(bez_gresaka / n * 100, 1) if n else 0.0,
            "s_ekavizmima":      s_ekavizmima,
            "pct_ekavizmi":      round(s_ekavizmima / n * 100, 1) if n else 0.0,
            "s_kalkovima":       s_kalkovima,
            "pct_kalkovi":       round(s_kalkovima / n * 100, 1) if n else 0.0,
            "s_tipografijom":    s_tipografijom,
            "pct_tipografija":   round(s_tipografijom / n * 100, 1) if n else 0.0,
            "s_engleskim":       s_engleskim,
            "pct_engleski":      round(s_engleskim / n * 100, 1) if n else 0.0,
            "hunspell_koristen": self._hunspell_ok,
        }

        # 5. Trend analiza
        prethodni_trend = _ucitaj_trend(trend_path)
        baseline_payload = {
            "datum":     datum_str,
            "file_name": file_name,
            "summary":   summary,
            "uzorci":    rezultati,
        }
        trend_report = _generiši_trend_report(baseline_payload, prethodni_trend)

        # 6. Spremi baseline
        try:
            with open(baseline_path, "w", encoding="utf-8") as f:
                json.dump(baseline_payload, f, ensure_ascii=False, indent=2)
            logger.info(f"qa_benchmark: baseline spreman → {baseline_path}")
        except Exception as e:
            logger.error(f"qa_benchmark: ne mogu spremiti baseline: {e}")

        # 7. Spremi trend (ažuriraj s tekućim stanjem)
        try:
            with open(trend_path, "w", encoding="utf-8") as f:
                json.dump({**baseline_payload, "trend": trend_report}, f, ensure_ascii=False, indent=2)
            logger.info(f"qa_benchmark: trend spreman → {trend_path}")
        except Exception as e:
            logger.error(f"qa_benchmark: ne mogu spremiti trend: {e}")

        # 8. Log summary u konzolu
        _ispisi_summary(file_name, summary, trend_report)

        return {**baseline_payload, "trend": trend_report}


def _ispisi_summary(file_name: str, summary: dict, trend: dict) -> None:
    """Logira čitljiv summary nakon analize."""
    n   = summary["ukupno_uzoraka"]
    avg = summary["avg_benchmark_score"]
    promjene = trend.get("promjene", {})

    logger.info(
        f"\n{'─'*60}\n"
        f"QA Benchmark — {Path(file_name).stem}\n"
        f"  Uzoraka:           {n} / {summary['ukupno_chunkova']}\n"
        f"  Avg benchmark:     {avg}/10"
        + (f"  {promjene.get('avg_benchmark_score', {}).get('trend', '')}" if promjene else "") +
        f"\n  Bez grešaka:       {summary['bez_gresaka']} ({summary['pct_bez_gresaka']}%)\n"
        f"  Ekavizmi:          {summary['s_ekavizmima']} ({summary['pct_ekavizmi']}%)\n"
        f"  Kalkovi:           {summary['s_kalkovima']} ({summary['pct_kalkovi']}%)\n"
        f"  Tipografija:       {summary['s_tipografijom']} ({summary['pct_tipografija']}%)\n"
        f"  Engleski ostaci:   {summary['s_engleskim']} ({summary['pct_engleski']}%)\n"
        f"  Hunspell:          {'da' if summary['hunspell_koristen'] else 'nije instaliran'}\n"
        f"{'─'*60}"
    )


# ─── Singleton ────────────────────────────────────────────────────────────────

qa_benchmark = QABenchmark()
