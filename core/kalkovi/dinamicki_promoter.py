"""
Korak 11c — Promoter i feedback loop zaštita
Promovira potvrđene kalkove u aktivnu listu + rollback zaštita.
"""

import re
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "kalkovi_karantena.db"
DINAMICKI_LISTA_PATH = BASE_DIR / "core" / "kalkovi" / "dinamicki_lista.py"

MAX_DOZVOLJENI_PAD_SCORE = 0.3
MIN_KNJIGA_ZA_PROMOCIJU = 3


class DinamickiPromoter:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _dohvati_potvrdjene(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, pattern, tip, broj_pojavljivanja,
                       CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score,
                       knjige_set, rollback_count
                FROM kandidati
                WHERE status = 'potvrden' AND rollback_count < 2
                ORDER BY broj_pojavljivanja DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def _provjeri_korelaciju(self, pattern: str) -> tuple:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score
                FROM kandidati WHERE pattern=?
            """, (pattern,)).fetchone()
        avg = row[0] if row else 0.0
        if avg < 7.5:
            return avg, "los_score"
        elif avg < 8.2:
            return avg, "prihvatljiv"
        else:
            return avg, "dobar_score_mozda_nije_kalk"

    def _generisi_python_unos(self, pattern: str, tip: str) -> str:
        escaped = re.escape(pattern)
        return f'    (r"\\b{escaped}\\b", ""),  # auto: {tip}'

    def _ucitaj_dinamicki_listu(self) -> list:
        if not DINAMICKI_LISTA_PATH.exists():
            return []
        content = DINAMICKI_LISTA_PATH.read_text(encoding='utf-8')
        match = re.search(r'DINAMICKI_KALKOVI\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            return match.group(1).strip().splitlines()
        return []

    def _spasi_dinamicki_listu(self, unosi: list):
        sadrzaj = (
            '"""\nDinamicki generirane liste kalkova.\n'
            'Automatski azurirano od DinamickiPromoter-a.\n'
            f'Zadnje azuriranje: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n"""\n\n'
            'DINAMICKI_KALKOVI = [\n'
            + "\n".join(unosi)
            + "\n]\n"
        )
        DINAMICKI_LISTA_PATH.write_text(sadrzaj, encoding='utf-8')

    def promoviraj(self, dry_run: bool = False) -> dict:
        kandidati = self._dohvati_potvrdjene()
        rezultat = {"promoviran": [], "odbijen_korelacija": [], "preskocan": []}
        postojeci_unosi = self._ucitaj_dinamicki_listu()
        novi_unosi = list(postojeci_unosi)

        for k in kandidati:
            pattern = k['pattern']
            tip = k['tip']
            escaped = re.escape(pattern)
            if any(escaped in u or pattern in u for u in postojeci_unosi):
                rezultat['preskocan'].append(pattern)
                continue

            avg_score, ocjena = self._provjeri_korelaciju(pattern)
            if ocjena == "dobar_score_mozda_nije_kalk":
                rezultat['odbijen_korelacija'].append({
                    "pattern": pattern,
                    "razlog": f"avg_score={avg_score:.2f}"
                })
                if not dry_run:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(
                            "UPDATE kandidati SET status='odbijen', validator_napomena=? WHERE pattern=?",
                            (f"korelacija negativna: {avg_score:.2f}", pattern)
                        )
                        conn.commit()
                continue

            novi_unos = self._generisi_python_unos(pattern, tip)
            novi_unosi.append(novi_unos)
            rezultat['promoviran'].append({
                "pattern": pattern, "tip": tip,
                "avg_score": avg_score, "ocjena": ocjena
            })
            if not dry_run:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE kandidati SET status='aktivan', datum_zadnjeg=datetime('now') WHERE pattern=?",
                        (pattern,)
                    )
                    conn.commit()

        if not dry_run and len(novi_unosi) != len(postojeci_unosi):
            self._spasi_dinamicki_listu(novi_unosi)
            log.info(f"Dinamicka lista azurirana: +{len(rezultat['promoviran'])} patterna")

        return rezultat

    def rollback_pattern(self, pattern: str, razlog: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE kandidati
                SET status='rollback',
                    rollback_count = rollback_count + 1,
                    validator_napomena = ?,
                    datum_zadnjeg = datetime('now')
                WHERE pattern = ?
            """, (f"rollback: {razlog}", pattern))
            conn.commit()
        if DINAMICKI_LISTA_PATH.exists():
            content = DINAMICKI_LISTA_PATH.read_text(encoding='utf-8')
            escaped = re.escape(pattern)
            linije = [l for l in content.splitlines()
                      if pattern not in l and escaped not in l]
            DINAMICKI_LISTA_PATH.write_text("\n".join(linije) + "\n", encoding='utf-8')
            log.warning(f"Rollback: '{pattern}' uklonjen iz dinamicke liste. Razlog: {razlog}")

    def provjeri_score_pad(self, knjiga: str, score_prije: float, score_poslije: float) -> bool:
        pad = score_prije - score_poslije
        if pad > MAX_DOZVOLJENI_PAD_SCORE:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("""
                    SELECT pattern FROM kandidati
                    WHERE status='aktivan'
                    ORDER BY datum_zadnjeg DESC LIMIT 1
                """).fetchone()
            if row:
                self.rollback_pattern(
                    row[0],
                    razlog=f"score pad {score_prije:.2f}->{score_poslije:.2f} u '{knjiga}'"
                )
                return True
        return False
