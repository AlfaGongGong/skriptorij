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
    Automatski promoviše kalkove koji zadovoljavaju kriterije.
    
    BEZ DEGRADACIJE:
    - Bar 10 pojavljivanja
    - Bar 3 različite knjige
    - Ne postoji u aktivnim listama (provjera duplikata)
    """
    conn = _get_db()
    promoted = _load_promoted()
    vec_promovisani = {p["pattern"] for p in promoted}
    
    # Dohvati kandidate koji zadovoljavaju pragove
    try:
        rows = conn.execute("""
            SELECT pattern, zamjena, tip, COUNT(DISTINCT knjiga) as knjige, 
                   SUM(pojavljivanja) as ukupno
            FROM kandidati 
            GROUP BY pattern, zamjena
            HAVING ukupno >= ? AND knjige >= ?
            ORDER BY ukupno DESC
        """, (MIN_POTVRDA, MIN_KNJIGA)).fetchall()
    except sqlite3.OperationalError:
        logger.warning("[auto_promoter] Tabela 'kandidati' ne postoji — preskačem")
        return []
    
    novi = []
    for row in rows:
        pattern = row["pattern"]
        if pattern in vec_promovisani:
            continue
        
        entry = {
            "pattern": pattern,
            "zamjena": row["zamjena"],
            "tip": row["tip"],
            "knjige": row["knjige"],
            "pojavljivanja": row["ukupno"],
            "promoted_at": datetime.now().isoformat(),
        }
        
        if not dry_run:
            # Dodaj u aktivnu listu (dinamicki_lista.py)
            try:
                lista_path = Path("core/kalkovi/dinamicki_lista.py")
                if lista_path.exists():
                    linija = f'    ("{pattern}", "{row["zamjena"]}"),  # auto-promoted {datetime.now():%Y-%m-%d}\n'
                    sadrzaj = lista_path.read_text()
                    # Nađi zadnju tuple liniju prije "]"
                    marker = sadrzaj.rfind("    (")
                    if marker > 0:
                        kraj_linije = sadrzaj.find("\n", marker)
                        sadrzaj = sadrzaj[:kraj_linije+1] + linija + sadrzaj[kraj_linije+1:]
                        lista_path.write_text(sadrzaj)
            except Exception as e:
                logger.warning(f"[auto_promoter] Greška pri dodavanju u listu: {e}")
        
        novi.append(entry)
        vec_promovisani.add(pattern)
    
    if novi and not dry_run:
        promoted.extend(novi)
        _save_promoted(promoted)
        logger.info(f"[auto_promoter] Promovisano {len(novi)} kalkova")
    
    conn.close()
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
    except:
        ukupno, spremni = 0, 0
    conn.close()
    return {"ukupno_kandidata": ukupno, "spremno_za_promociju": spremni}
