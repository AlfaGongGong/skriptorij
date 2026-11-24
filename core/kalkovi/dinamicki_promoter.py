"""
Korak 11c — Promoter i feedback loop zaštita
Promovira potvrđene kalkove u aktivnu listu + rollback zaštita.
"""

import ast
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "kalkovi_karantena.db"
DINAMICKI_LISTA_PATH = BASE_DIR / "core" / "kalkovi" / "dinamicki_lista.py"

MAX_DOZVOLJENI_PAD_SCORE = 0.3
MIN_KNJIGA_ZA_PROMOCIJU = 3


_UNOS_RE = re.compile(
    r"""^\s*\(\s*([rR]?(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'))\s*,"""
)


def _unos_pattern(linija: str):
    """Prvi string literal iz retka liste ('(r"\\bx\\b", "y"),') ili None."""
    m = _UNOS_RE.match(linija)
    if not m:
        return None
    try:
        v = ast.literal_eval(m.group(1))
    except (ValueError, SyntaxError):
        return None
    return v if isinstance(v, str) else None


def _unos_ima_pattern(linija: str, pattern: str) -> bool:
    """Točno podudaranje (ne podniz): 'deteta' nije 'dete' (R11b-4)."""
    lit = _unos_pattern(linija)
    if lit is None:
        return False
    esc = re.escape(pattern)
    return lit in (pattern, esc, r"\b" + esc + r"\b", r"\b" + pattern + r"\b")


def _atomarno_pisi(path: Path, tekst: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(tekst, encoding="utf-8")
    os.replace(tmp, path)


class DinamickiPromoter:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def _dohvati_potvrdjene(self) -> list:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            stupci = {r[1] for r in conn.execute("PRAGMA table_info(kandidati)")}
            zam = "zamjena," if "zamjena" in stupci else "'' AS zamjena,"
            rows = conn.execute(f"""
                SELECT id, pattern, tip, {zam} broj_pojavljivanja,
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
            row = conn.execute(
                """
                SELECT CASE WHEN broj_pojavljivanja > 0
                            THEN ukupan_score / broj_pojavljivanja
                            ELSE 0 END as avg_score
                FROM kandidati WHERE pattern=?
            """,
                (pattern,),
            ).fetchone()
        avg = row[0] if row else 0.0
        if avg < 7.5:
            return avg, "los_score"
        if avg < 8.2:
            return avg, "prihvatljiv"
        return avg, "dobar_score_mozda_nije_kalk"

    def _generisi_python_unos(self, pattern: str, tip: str, zamjena: str = "") -> str:
        """Prazna zamjena = nema unosa (''): prazan niz bi BRISAO riječ iz knjige."""
        if not isinstance(zamjena, str) or not zamjena.strip():
            return ""
        lit = repr(r"\b" + re.escape(pattern) + r"\b")
        tip_s = " ".join(str(tip).split())
        return f"    ({lit}, {zamjena!r}),  # auto: {tip_s}"

    def _ucitaj_dinamicki_listu(self) -> list:
        """Retci unosa između 'DINAMICKI_KALKOVI = [' i zatvarajuće ']' (ne lomi se na ']' u regexu)."""
        if not DINAMICKI_LISTA_PATH.exists():
            return []
        out, unutra = [], False
        for l in DINAMICKI_LISTA_PATH.read_text(encoding="utf-8").splitlines():
            if not unutra:
                unutra = l.strip().startswith("DINAMICKI_KALKOVI") and l.rstrip().endswith("[")
                continue
            if l.rstrip() == "]":
                break
            if l.strip():
                out.append(l.rstrip())
        return out

    def _spasi_dinamicki_listu(self, unosi: list):
        sadrzaj = (
            '"""\nDinamicki generirane liste kalkova.\n'
            "Automatski azurirano od DinamickiPromoter-a.\n"
            f'Zadnje azuriranje: {datetime.now().strftime("%Y-%m-%d %H:%M")}\n"""\n\n'
            "DINAMICKI_KALKOVI = [\n" + "\n".join(unosi) + "\n]\n"
        )
        compile(sadrzaj, str(DINAMICKI_LISTA_PATH), "exec")  # ne upisuj neispravan Python
        _atomarno_pisi(DINAMICKI_LISTA_PATH, sadrzaj)

    def promoviraj(self, dry_run: bool = False) -> dict:
        kandidati = self._dohvati_potvrdjene()
        rezultat = {"promoviran": [], "odbijen_korelacija": [], "preskocan": []}
        postojeci_unosi = self._ucitaj_dinamicki_listu()
        novi_unosi = list(postojeci_unosi)

        for k in kandidati:
            pattern = k["pattern"]
            tip = k["tip"]
            if any(_unos_ima_pattern(u, pattern) for u in postojeci_unosi):
                rezultat["preskocan"].append(pattern)
                continue

            avg_score, ocjena = self._provjeri_korelaciju(pattern)
            if ocjena == "dobar_score_mozda_nije_kalk":
                rezultat["odbijen_korelacija"].append(
                    {"pattern": pattern, "razlog": f"avg_score={avg_score:.2f}"}
                )
                if not dry_run:
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute(
                            "UPDATE kandidati SET status='odbijen', validator_napomena=? WHERE pattern=?",
                            (f"korelacija negativna: {avg_score:.2f}", pattern),
                        )
                        conn.commit()
                continue

            novi_unos = self._generisi_python_unos(pattern, tip, k.get("zamjena", ""))
            if not novi_unos:
                rezultat["preskocan"].append(pattern)  # bez poznate zamjene ne promoviramo
                continue
            novi_unosi.append(novi_unos)
            rezultat["promoviran"].append(
                {
                    "pattern": pattern,
                    "tip": tip,
                    "avg_score": avg_score,
                    "ocjena": ocjena,
                }
            )
            if not dry_run:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "UPDATE kandidati SET status='aktivan', datum_zadnjeg=datetime('now') WHERE pattern=?",
                        (pattern,),
                    )
                    conn.commit()

        if not dry_run and len(novi_unosi) != len(postojeci_unosi):
            self._spasi_dinamicki_listu(novi_unosi)
            log.info(
                f"Dinamicka lista azurirana: +{len(rezultat['promoviran'])} patterna"
            )

        return rezultat

    def rollback_pattern(self, pattern: str, razlog: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE kandidati
                SET status='rollback',
                    rollback_count = rollback_count + 1,
                    validator_napomena = ?,
                    datum_zadnjeg = datetime('now')
                WHERE pattern = ?
            """,
                (f"rollback: {razlog}", pattern),
            )
            conn.commit()
        if DINAMICKI_LISTA_PATH.exists():
            content = DINAMICKI_LISTA_PATH.read_text(encoding="utf-8")
            linije = [l for l in content.splitlines() if not _unos_ima_pattern(l, pattern)]
            _atomarno_pisi(DINAMICKI_LISTA_PATH, "\n".join(linije) + "\n")
            log.warning(
                f"Rollback: '{pattern}' uklonjen iz dinamicke liste. Razlog: {razlog}"
            )

    def provjeri_score_pad(
        self, knjiga: str, score_prije: float, score_poslije: float
    ) -> bool:
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
                    razlog=f"score pad {score_prije:.2f}->{score_poslije:.2f} u '{knjiga}'",
                )
                return True
        return False
