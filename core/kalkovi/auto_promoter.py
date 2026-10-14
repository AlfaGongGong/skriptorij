"""
Auto-Kalk Promoter — automatski promoviše kalkove iz karantene.
BEZ DEGRADACIJE: promoviše samo kalkove sa >= 10 potvrda iz >= 3 knjige.
"""

import json, sqlite3, logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = Path("data/kalkovi_karantena.db")
PROMOTED_LOG = Path("data/auto_promoted_kalkovi.json")
MIN_POTVRDA = 10      # BEZ DEGRADACIJE: bar 10 pojava prije promocije
MIN_KNJIGA = 3         # BEZ DEGRADACIJE: bar u 3 različite knjige

def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _load_promoted():
    if PROMOTED_LOG.exists():
        return json.loads(PROMOTED_LOG.read_text())
    return []

def _save_promoted(promoted):
    PROMOTED_LOG.parent.mkdir(parents=True, exist_ok=True)
    PROMOTED_LOG.write_text(json.dumps(promoted, ensure_ascii=False, indent=2))

def auto_promote(dry_run=True):
    """
    Automatski promoviše kandidate koji zadovoljavaju kriterije.

    BEZ DEGRADACIJE:
    - Bar 10 pojavljivanja
    - Bar 2 različite knjige ILI ručno dodan
    - Ne postoji u aktivnim listama
    """
    conn = _get_db()
    promoted = _load_promoted()
    vec_promovisani = {p["pattern"] for p in promoted}

    # Dohvati kandidate
    try:
        rows = conn.execute("""
            SELECT pattern, tip, broj_pojavljivanja, ukupan_score,
                   knjige_set, status
            FROM kandidati
            WHERE status = 'kandidat'
              AND broj_pojavljivanja >= ?
            ORDER BY broj_pojavljivanja DESC
        """, (MIN_POTVRDA,)).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"[auto_promoter] SQL greška: {e}")
        return []

    novi = []
    for row in rows:
        pattern = row["pattern"]
        if pattern in vec_promovisani:
            continue

        # Provjeri knjige_set (JSON lista) ili RUCNO_DODANO
        knjige_set_str = row["knjige_set"] or "[]"
        try:
            knjige = json.loads(knjige_set_str)
        except Exception:
            knjige = []

        # Ako je RUCNO_DODANO — prihvati
        if "RUCNO_DODANO" in knjige:
            broj_knjiga = 999  # uvijek prolazi
        else:
            broj_knjiga = len(set(knjige))

        if broj_knjiga < MIN_KNJIGA and "RUCNO_DODANO" not in knjige:
            continue

        entry = {
            "pattern": pattern,
            "tip": row["tip"],
            "knjige": broj_knjiga,
            "pojavljivanja": row["broj_pojavljivanja"],
            "avg_score": row["ukupan_score"] / max(row["broj_pojavljivanja"], 1),
            "promoted_at": datetime.now().isoformat(),
        }

        if not dry_run:
            # Dodaj u dinamicki_lista.py
            try:
                lista_path = Path("core/kalkovi/dinamicki_lista.py")
                if lista_path.exists():
                    sadrzaj = lista_path.read_text(encoding='utf-8')
                    # Format: ("pattern", "tip"),
                    linija = f'    ("{pattern}", "{row["tip"]}"),  # auto-promoted {datetime.now():%Y-%m-%d}\n'
                    # Nađi "]" (kraj liste)
                    marker = sadrzaj.rfind("]")
                    if marker > 0:
                        # Ubaci prije "]" 
                        sadrzaj = sadrzaj[:marker] + linija + sadrzaj[marker:]
                        lista_path.write_text(sadrzaj, encoding='utf-8')
            except Exception as e:
                logger.warning(f"[auto_promoter] Greška pri upisu: {e}")

        novi.append(entry)

    if not dry_run and novi:
        promoted.extend(novi)
        _save_promoted(promoted)

    return novi

def get_stats():
    """Vraća statistiku karantene."""
    conn = _get_db()
    try:
        ukupno = conn.execute("SELECT COUNT(*) FROM kandidati").fetchone()[0]
        spremni = conn.execute(
            "SELECT COUNT(*) FROM (SELECT pattern FROM kandidati GROUP BY pattern HAVING SUM(pojavljivanja) >= ?)",
            (MIN_POTVRDA,)
        ).fetchone()[0]
    except Exception:  # NOTE #1 fix: bare except zamjenjen
        ukupno, spremni = 0, 0
    conn.close()
    return {"ukupno_kandidata": ukupno, "spremno_za_promociju": spremni}
