"""
Korak 11a — Dinamički detektor kalkova (pasivni mod)
Skuplja kandidate iz prijevoda bez mijenjanja postojećih lista.
Stack: classla + hunspell + regex + rapidfuzz
"""

import re
import json
import sqlite3
import subprocess
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

try:
    import classla
    CLASSLA_DOSTUPAN = True
except ImportError:
    CLASSLA_DOSTUPAN = False

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_DOSTUPAN = True
except ImportError:
    RAPIDFUZZ_DOSTUPAN = False

from core.kalkovi import SVE_LISTE

log = logging.getLogger(__name__)

# --- Putanje ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "kalkovi_karantena.db"
HUNSPELL_LANG = "hr_HR"

# --- Ekavizmi za detekciju ---
EKAVIZMI_REGEX = re.compile(
    r'\b(neverovatno|neverovatan|poseduje|posedovati|posedujem|'
    r'odredjuje|određuje|izvrsiti|izvršiti|zaista|zapravo|'
    r'upravo|posebno|sledeci|sledeći|prethodn[oi]|'
    r'cinjenica|međutim|medutim|naravno|svakako|'
    r'ustvari|u stvari|dakle|naime|ipak)\b',
    re.IGNORECASE
)

# --- Poznati kalkovi iz engine-a (za deduplikaciju) ---
def _ucitaj_poznate_kalkove() -> set:
    poznati = set()
    for lista in SVE_LISTE.values():
        for unos in lista:
            if isinstance(unos, (list, tuple)) and len(unos) >= 2:
                # format: (pattern, zamjena) ili [pattern, zamjena]
                poznati.add(str(unos[0]).lower())
            elif isinstance(unos, str):
                poznati.add(unos.lower())
    return poznati

POZNATI_KALKOVI: set = set()  # lazy init


def _init_poznati():
    global POZNATI_KALKOVI
    if not POZNATI_KALKOVI:
        try:
            POZNATI_KALKOVI = _ucitaj_poznate_kalkove()
        except Exception as e:
            log.warning(f"Nije moguće učitati poznate kalkove: {e}")
            POZNATI_KALKOVI = set()


# --- Classla NLP pipeline (lazy init) ---
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None and CLASSLA_DOSTUPAN:
        try:
            classla.download('hr', dir=str(BASE_DIR / "data" / "classla_resources"))
            _nlp = classla.Pipeline(
                'hr',
                processors='tokenize,pos,lemma',
                dir=str(BASE_DIR / "data" / "classla_resources"),
                logging_level='ERROR'
            )
        except Exception as e:
            log.warning(f"classla init greška: {e}")
            _nlp = None
    return _nlp


# --- Hunspell provjera ---
def _hunspell_neispravna(rijec: str) -> bool:
    """Vraća True ako hunspell smatra riječ neispravnom."""
    try:
        result = subprocess.run(
            ['hunspell', '-d', HUNSPELL_LANG, '-a'],
            input=f"{rijec}\n",
            capture_output=True,
            text=True,
            timeout=2
        )
        # Hunspell izlaz: '&' = pogrešno, '*' = ispravno, '+' = ispravno (složenica)
        for line in result.stdout.splitlines():
            if line.startswith('&') or line.startswith('#'):
                return True
        return False
    except Exception:
        return False


# --- N-gram ekstrakcija ---
def _ekstraktuj_ngrame(tekst: str, n: int = 3) -> list:
    """Ekstraktuje n-grame riječi iz teksta."""
    rijeci = re.findall(r'\b[a-zA-ZčćđšžČĆĐŠŽ]+\b', tekst.lower())
    if len(rijeci) < n:
        return []
    return [tuple(rijeci[i:i+n]) for i in range(len(rijeci) - n + 1)]


# --- Engleski kalkovi — pattern detekcija ---
EN_KALK_SIGNALI = [
    # Srpski/engleski leksički kalkovi koji se provlače
    (r'\b(imati smisla|napraviti smisao)\b', 'make sense kalk'),
    (r'\b(uzeti u obzir|uzimati u obzir)\b', 'take into account kalk'),
    (r'\b(biti u pravu)\b', 'be right kalk — provjeri kontekst'),
    (r'\b(dati sve od sebe)\b', 'give all of himself kalk'),
    (r'\b(on je bio kao)\b', 'he was like kalk'),
    (r'\b(u redu je)\b', 'it\'s okay kalk — možda OK'),
    (r'\bmislim da\b.{0,20}\bda\b', 'I think that that — dupli veznik'),
    (r'\b(od kada|otkad)\b.{0,30}\bda\b', 'since ... that — kalk'),
    (r'\bkoji je bio\b', 'who was — možda nominalizacija'),
    (r'\bkoja je bila\b', 'who was — možda nominalizacija'),
]

EN_KALK_RE = [(re.compile(p, re.IGNORECASE), opis) for p, opis in EN_KALK_SIGNALI]


class DinamickiDetektor:
    """
    Pasivni detektor — analizira prijevode i sprema kandidate u karantenu.
    Ne mijenja prijevode, samo bilježi sumnjive obrasce.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        _init_poznati()
        self._init_db()

    def _init_db(self):
        """Inicijalizira SQLite bazu ako ne postoji."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kandidati (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    tip TEXT NOT NULL,
                    kontekst TEXT,
                    knjiga TEXT,
                    chunk_idx INTEGER,
                    broj_pojavljivanja INTEGER DEFAULT 1,
                    ukupan_score REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'kandidat',
                    datum_prvog TEXT DEFAULT (datetime('now')),
                    datum_zadnjeg TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pattern_tip
                ON kandidati(pattern, tip)
            """)
            conn.commit()

    def _zapisi_kandidata(
        self,
        pattern: str,
        tip: str,
        kontekst: str = "",
        knjiga: str = "",
        chunk_idx: int = 0,
        score: float = 0.0
    ):
        """Sprema ili ažurira kandidata u bazi."""
        pattern = pattern.strip().lower()[:200]
        if not pattern or len(pattern) < 3:
            return
        # Preskoči ako je već u poznatim kalkovima
        if pattern in POZNATI_KALKOVI:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                existing = conn.execute(
                    "SELECT id, broj_pojavljivanja, ukupan_score FROM kandidati WHERE pattern=? AND tip=?",
                    (pattern, tip)
                ).fetchone()
                if existing:
                    conn.execute("""
                        UPDATE kandidati
                        SET broj_pojavljivanja = broj_pojavljivanja + 1,
                            ukupan_score = ukupan_score + ?,
                            kontekst = ?,
                            knjiga = ?,
                            datum_zadnjeg = datetime('now')
                        WHERE id = ?
                    """, (score, kontekst[:500], knjiga, existing[0]))
                else:
                    conn.execute("""
                        INSERT INTO kandidati
                        (pattern, tip, kontekst, knjiga, chunk_idx, ukupan_score)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (pattern, tip, kontekst[:500], knjiga, chunk_idx, score))
                conn.commit()
        except Exception as e:
            log.debug(f"DB greška pri zapisu kandidata: {e}")

    def analiziraj(
        self,
        original: str,
        prijevod: str,
        knjiga: str = "",
        chunk_idx: int = 0,
        quality_score: float = 0.0
    ) -> dict:
        """
        Glavna metoda — analizira par (original, prijevod).
        Vraća rječnik s pronađenim kandidatima.
        Poziva se pasivno, ne utječe na prijevod.
        """
        rezultati = defaultdict(list)

        # 1. Ekavizmi
        for m in EKAVIZMI_REGEX.finditer(prijevod):
            word = m.group(0)
            self._zapisi_kandidata(
                pattern=word,
                tip='ekavizam',
                kontekst=prijevod[max(0, m.start()-40):m.end()+40],
                knjiga=knjiga,
                chunk_idx=chunk_idx,
                score=quality_score
            )
            rezultati['ekavizmi'].append(word)

        # 2. Engleski kalkovi
        for regex, opis in EN_KALK_RE:
            for m in regex.finditer(prijevod):
                phrase = m.group(0)
                self._zapisi_kandidata(
                    pattern=phrase,
                    tip=f'kalk_en:{opis}',
                    kontekst=prijevod[max(0, m.start()-40):m.end()+40],
                    knjiga=knjiga,
                    chunk_idx=chunk_idx,
                    score=quality_score
                )
                rezultati['kalkovi_en'].append(phrase)

        # 3. Classla — morfološka analiza (ako dostupno)
        nlp = _get_nlp()
        if nlp and len(prijevod) < 2000:
            try:
                doc = nlp(prijevod)
                for sent in doc.sentences:
                    for word in sent.words:
                        # Detekcija dugih nominalizacija (imenice na -nje, -ost, -stvo)
                        if (word.upos == 'NOUN' and word.lemma and
                                re.search(r'(anje|enje|nost|stvo|acija)$', word.lemma)):
                            # Provjeri hunspell
                            if len(word.lemma) > 8:
                                rezultati['nominalizacije_kandidati'].append(word.lemma)
            except Exception as e:
                log.debug(f"classla analiza greška: {e}")

        # 4. N-gram statistika — ponavljajući obrasci
        if len(prijevod) > 200:
            ngrami = _ekstraktuj_ngrame(prijevod, n=3)
            frekv = defaultdict(int)
            for ng in ngrami:
                frekv[ng] += 1
            # Bilježi trigrade koji se pojavljuju 3+ puta
            for ng, br in frekv.items():
                if br >= 3:
                    phrase = ' '.join(ng)
                    if phrase not in POZNATI_KALKOVI:
                        self._zapisi_kandidata(
                            pattern=phrase,
                            tip='ngram_ponavljanje',
                            kontekst=f"Pojavilo se {br}x u chunku",
                            knjiga=knjiga,
                            chunk_idx=chunk_idx,
                            score=quality_score
                        )
                        rezultati['ngrami_ponavljanje'].append((phrase, br))

        return dict(rezultati)

    def dohvati_top_kandidate(self, limit: int = 50, min_pojavljivanja: int = 3) -> list:
        """Vraća top kandidate sortirane po broju pojavljivanja."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT pattern, tip, broj_pojavljivanja,
                       CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score,
                       kontekst, datum_zadnjeg
                FROM kandidati
                WHERE status = 'kandidat'
                  AND broj_pojavljivanja >= ?
                ORDER BY broj_pojavljivanja DESC, avg_score ASC
                LIMIT ?
            """, (min_pojavljivanja, limit)).fetchall()
        return [
            {
                "pattern": r[0], "tip": r[1],
                "pojavljivanja": r[2], "avg_score": round(r[3], 2),
                "kontekst": r[4], "datum": r[5]
            }
            for r in rows
        ]

    def statistika(self) -> dict:
        """Brza statistika karantene."""
        with sqlite3.connect(self.db_path) as conn:
            ukupno = conn.execute("SELECT COUNT(*) FROM kandidati").fetchone()[0]
            po_tipu = conn.execute("""
                SELECT tip, COUNT(*) FROM kandidati GROUP BY tip ORDER BY COUNT(*) DESC
            """).fetchall()
            gotovi = conn.execute(
                "SELECT COUNT(*) FROM kandidati WHERE status != 'kandidat'"
            ).fetchone()[0]
        return {
            "ukupno_kandidata": ukupno,
            "gotovi": gotovi,
            "po_tipu": dict(po_tipu)
        }
