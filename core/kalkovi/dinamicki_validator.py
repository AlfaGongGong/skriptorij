"""
Korak 11b — Validator i karantena
Promovira kandidate iz karantene u aktivne kalkove nakon provjere.
Schema: kandidat → na_cekanju → potvrđen | odbijen
"""

import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "kalkovi_karantena.db"

# Pragovi za automatsku promociju
MIN_POJAVLJIVANJA = 5       # Minimum puta viđen
MAX_AVG_SCORE = 8.2         # Prosječni quality score mora biti ispod ovoga
MIN_KNJIGA_RAZNOLIKOST = 2  # Mora se pojaviti u bar 2 različite knjige


# Tipovi koji se NIKAD ne promoviraju globalno (book-specifični)
# rod_mijesanje: ovisi o imenima likova koji su per-knjiga
# info: pasivna statistika, ne kalkovi pattern
NIKAD_PROMOVISATI_TIPOVI: frozenset = frozenset({"rod_mijesanje", "info"})


class DinamickiValidator:
    """
    Validira kandidate iz karantene i odlučuje o promociji.
    Logika:
      - Kandidat se promovira ako se pojavljuje dovoljno puta,
        u dovoljno knjiga, i korelira s nižim quality scoreom.
      - Kandidat se odbija ako je score visok (dobar prijevod s tim uzorkom).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        """Dodaje kolone ako ne postoje (migracija)."""
        with sqlite3.connect(self.db_path) as conn:
            # Dodaj kolone za validaciju ako ne postoje
            kolonе = [r[1] for r in conn.execute("PRAGMA table_info(kandidati)").fetchall()]
            if 'knjige_set' not in kolonе:
                conn.execute("ALTER TABLE kandidati ADD COLUMN knjige_set TEXT DEFAULT '[]'")
            if 'rollback_count' not in kolonе:
                conn.execute("ALTER TABLE kandidati ADD COLUMN rollback_count INTEGER DEFAULT 0")
            if 'validator_napomena' not in kolonе:
                conn.execute("ALTER TABLE kandidati ADD COLUMN validator_napomena TEXT DEFAULT ''")
            conn.commit()

    def azuriraj_knjige(self, pattern: str, tip: str, knjiga: str):
        """Ažurira set knjiga u kojima se pattern pojavio."""
        if not knjiga:
            return
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT knjige_set FROM kandidati WHERE pattern=? AND tip=?",
                (pattern, tip)
            ).fetchone()
            if row:
                try:
                    knjige = json.loads(row[0] or '[]')
                except Exception:
                    knjige = []
                if knjiga not in knjige:
                    knjige.append(knjiga)
                    conn.execute(
                        "UPDATE kandidati SET knjige_set=? WHERE pattern=? AND tip=?",
                        (json.dumps(knjige), pattern, tip)
                    )
                    conn.commit()

    def _ocijeni_kandidata(self, row: dict) -> tuple[bool, str]:
        """
        Vraća (treba_promovirati: bool, razlog: str).
        """
        pojavljivanja = row['broj_pojavljivanja']
        avg_score = row['avg_score']
        knjige = json.loads(row.get('knjige_set') or '[]')
        raznolikost = len(set(knjige))

        # Odbij ako je avg score visok — pattern nije problem
        if avg_score > 8.8:
            return False, f"avg_score previsok ({avg_score:.1f}) — pattern nije štetan"

        # Odbij ako nema dovoljno podataka
        if pojavljivanja < MIN_POJAVLJIVANJA:
            return False, f"premalo pojavljivanja ({pojavljivanja} < {MIN_POJAVLJIVANJA})"

        if raznolikost < MIN_KNJIGA_RAZNOLIKOST:
            return False, f"samo u {raznolikost} knjig(a) — premalo raznolikosti"

        # Promovira ako: dosta puta, u više knjiga, niski avg score
        if (pojavljivanja >= MIN_POJAVLJIVANJA and
                raznolikost >= MIN_KNJIGA_RAZNOLIKOST and
                avg_score <= MAX_AVG_SCORE):
            return True, (
                f"pojavljivanja={pojavljivanja}, "
                f"knjige={raznolikost}, "
                f"avg_score={avg_score:.1f}"
            )

        return False, "uvjeti nisu ispunjeni"

    def provjeri_sve_kandidate(self, dry_run: bool = False) -> dict:
        """
        Prolazi kroz sve kandidate i odlučuje o statusu.
        dry_run=True: samo izvješće, bez promjena u bazi.
        """
        rezultat = {
            "promovirati": [],
            "odbiti": [],
            "cekati": [],
        }

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, pattern, tip, broj_pojavljivanja,
                       CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score,
                       knjige_set, rollback_count
                FROM kandidati
                WHERE status = 'kandidat'
            """).fetchall()

            for row in rows:
                rdict = dict(row)

                # Nikad ne promoviraj book-specifične tipove globalno
                if rdict.get("tip") in NIKAD_PROMOVISATI_TIPOVI:
                    rezultat['cekati'].append(rdict['pattern'])
                    continue

                treba, razlog = self._ocijeni_kandidata(rdict)

                if treba:
                    rezultat['promovirati'].append({
                        "id": rdict['id'],
                        "pattern": rdict['pattern'],
                        "tip": rdict['tip'],
                        "razlog": razlog
                    })
                    if not dry_run:
                        conn.execute("""
                            UPDATE kandidati
                            SET status='na_cekanju',
                                validator_napomena=?,
                                datum_zadnjeg=datetime('now')
                            WHERE id=?
                        """, (razlog, rdict['id']))
                elif rdict['broj_pojavljivanja'] >= MIN_POJAVLJIVANJA and float(rdict['avg_score']) > 8.8:
                    rezultat['odbiti'].append({
                        "id": rdict['id'],
                        "pattern": rdict['pattern'],
                        "razlog": razlog
                    })
                    if not dry_run:
                        conn.execute("""
                            UPDATE kandidati
                            SET status='odbijen',
                                validator_napomena=?,
                                datum_zadnjeg=datetime('now')
                            WHERE id=?
                        """, (razlog, rdict['id']))
                else:
                    rezultat['cekati'].append(rdict['pattern'])

            if not dry_run:
                conn.commit()

        return rezultat

    def dohvati_na_cekanju(self) -> list:
        """Vraća kandidate koji čekaju ručnu potvrdu."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT pattern, tip, broj_pojavljivanja,
                       CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score,
                       validator_napomena, knjige_set
                FROM kandidati WHERE status='na_cekanju'
                ORDER BY broj_pojavljivanja DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def rucna_potvrda(self, pattern: str, tip: str, potvrdi: bool, napomena: str = ""):
        """Ručna potvrda ili odbijanje kandidata."""
        novi_status = 'potvrden' if potvrdi else 'odbijen'
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE kandidati
                SET status=?, validator_napomena=?, datum_zadnjeg=datetime('now')
                WHERE pattern=? AND tip=?
            """, (novi_status, napomena, pattern, tip))
            conn.commit()
        log.info(f"Kandidat '{pattern}' ({tip}) → {novi_status}")

    def izvjestaj(self) -> str:
        """Tekstualni izvještaj stanja karantene."""
        with sqlite3.connect(self.db_path) as conn:
            po_statusu = conn.execute("""
                SELECT status, COUNT(*) FROM kandidati GROUP BY status
            """).fetchall()
        linije = ["=== Karantena stanje ==="]
        for status, br in po_statusu:
            linije.append(f"  {status:15s}: {br}")
        return "\n".join(linije)
