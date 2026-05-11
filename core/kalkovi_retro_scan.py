"""
kalkovi_retro_scan.py
─────────────────────────────────────────────────────────────────────────────
Retroaktivni scanner kalk-uzoraka iz svih .chk fajlova + automatska primjena
u kalkovi_karantena.db kada je prikupljeno dovoljno podataka.

UPOTREBA:
    python kalkovi_retro_scan.py [--scan] [--apply] [--status] [--help]

    --scan    Skenira sve .chk fajlove i puni DB (može se ponavljati)
    --apply   Primijeni potvrđene kalkove u qa_benchmark.py (≥ MIN_POJAVLJIVANJA)
    --status  Prikaži statistiku iz DB-a bez izmjena
    --all     --scan + --apply u jednom koraku

KONFIGURACIJA (prilagodi na vrhu fajla):
    CHK_ROOT          — root direktorij booklyfi checkpointa
    DB_PATH           — putanja do kalkovi_karantena.db
    QA_BENCHMARK_PATH — putanja do qa_benchmark.py (za --apply)
    MIN_POJAVLJIVANJA — minimalan broj pojavljivanja da bi kalk bio primijenjen
    MIN_AVG_SCORE     — minimalni prosječni quality score bloka da bi bio relevantan
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURACIJA — prilagodi prema svom sistemu
# ─────────────────────────────────────────────────────────────────────────────

CHK_ROOT = Path("/storage/emulated/0/booklyfi_checkpoints")
DB_PATH = Path("/storage/emulated/0/booklyfi_checkpoints/kalkovi_karantena.db")

# qa_benchmark.py — apsolutna putanja ili relativna od mjesta poziva
QA_BENCHMARK_PATH = Path(__file__).parent  / "qa_benchmark.py"

# Prag za automatsku primjenu u qa_benchmark.py
MIN_POJAVLJIVANJA = 3  # kalk mora biti viđen u ≥ 3 bloka
MIN_KNJIGA = 2  # u ≥ 2 različite knjige (sprječava book-specific false positive)
MIN_AVG_SCORE = 4.0  # ignoriramo blokove s prosječnim score < 4.0 (loš prijevod)

# Kalk-regex lista iz qa_benchmark.py (mora biti sinkronizirana — ažurira se --apply-om)
# Kopirano ovdje samo za standalone rad bez importa
_KALKOVI_REGEX_LOKALNO = [
    (r"\bbio je u stanju da\b", "kalk: bio je u stanju da"),
    (r"\bnije bio u mogu[ćc]nosti\b", "kalk: nije bio u mogućnosti"),
    (r"\buspio je da\b", "kalk: uspio je da"),
    (r"\bpokušao je da\b", "kalk: pokušao je da"),
    (r"\bu pogledu toga\b", "kalk: u pogledu toga"),
    (r"\bod strane\s+\w+a\b", "kalk: od strane X-a"),
    (r"\bpo pitanju\s+", "kalk: po pitanju"),
    (r"\bu odnosu na to\b", "kalk: u odnosu na to"),
    (r"\bkoristeći se\b", "kalk: koristeći se"),
    (r"\bimati u vidu\b", "kalk: imati u vidu"),
    (r"\buzeti u obzir to da\b", "kalk: uzeti u obzir to da"),
    (r"\bu svjetlu toga\b", "kalk: u svjetlu toga"),
    (r"\bna osnovu toga\b", "kalk: na osnovu toga"),
    (r"\biz razloga što\b", "kalk: iz razloga što"),
    (r"\bimajući u vidu\b", "kalk: imajući u vidu"),
    (r"\bprema tome\b", "kalk: prema tome"),
    (r"\bu cilju\b", "kalk: u cilju"),
    (r"\bs ciljem da\b", "kalk: s ciljem da"),
    (r"\bsa svrhom\b", "kalk: sa svrhom"),
    (r"\bna neki način\b", "kalk: na neki način"),
]

# Novi kandidati koje tražimo a NISU u postojećoj listi
# Proširena lista sumnjivih konstrukcija za dark fantasy/horror žanr
_NOVI_KANDIDATI_REGEX = [
    (r"\bu stvari\b", "kalk: u stvari (eng. in fact)"),
    (r"\bnaravno da\b", "kalk: naravno da (eng. of course)"),
    (r"\bpored toga\b", "kalk: pored toga (eng. besides that)"),
    (r"\bs druge strane\b", "kalk: s druge strane (eng. on the other hand)"),
    (r"\bčini se da\b", "kalk: čini se da (eng. it seems that)"),
    (r"\bkaže se da\b", "kalk: kaže se da (eng. it is said that)"),
    (r"\bshodno tome\b", "kalk: shodno tome (eng. accordingly)"),
    (r"\buz to\b", "kalk: uz to (eng. in addition)"),
    (r"\bu okviru\b", "kalk: u okviru (eng. within the framework)"),
    (r"\bu kontekstu\b", "kalk: u kontekstu (eng. in the context of)"),
    (r"\bkako bi\s+\w+\s+mogao\b", "kalk: kako bi X mogao (eng. so that X could)"),
    (r"\bu skladu s tim\b", "kalk: u skladu s tim (eng. in accordance)"),
    (r"\bprije nego što\s+bi\b", "kalk: prije nego što bi (eng. before he would)"),
    (r"\bima smisla da\b", "kalk: ima smisla da (eng. it makes sense)"),
    (r"\bnemati smisla\b", "kalk: nemati smisla (eng. make no sense)"),
    (r"\bučiniti to da\b", "kalk: učiniti to da (eng. make it so that)"),
    (r"\bpristupiti\s+\w+anju\b", "kalk: pristupiti X-anju (eng. to proceed to)"),
    (r"\bmorati se suočiti\b", "kalk: morati se suočiti (eng. have to face)"),
    (r"\bdonijeti odluku\b", "kalk: donijeti odluku (eng. make a decision)"),
    (r"\bpruž(?:iti|a)\s+podršku\b", "kalk: pružiti podršku (eng. provide support)"),
    (r"\bobratiti pažnju\b", "kalk: obratiti pažnju (eng. pay attention)"),
    (r"\bu tom smislu\b", "kalk: u tom smislu (eng. in that sense)"),
    (r"\bna kraju krajeva\b", "kalk: na kraju krajeva (eng. after all)"),
    (r"\bindividualno\b", "kalk: individualno (eng. individually)"),
    (r"\bidentificirati\b", "kalk: identificirati (eng. identify — srbizam)"),
    (r"\bkolektivno\b", "kalk: kolektivno (eng. collectively — srbizam)"),
    (r"\bprioritet(?:an|izirati)?\b", "kalk: prioritet/prioritizirati (eng. priority)"),
    (r"\bfokusirati se\b", "kalk: fokusirati se (eng. focus on)"),
    (r"\bimplementirati\b", "kalk: implementirati (eng. implement)"),
    (r"\boptimizirati\b", "kalk: optimizirati (eng. optimize)"),
]

# Sve regex liste za scan (postojeće + novi kandidati)
_SVE_REGEX = _KALKOVI_REGEX_LOKALNO + _NOVI_KANDIDATI_REGEX

# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("kalkovi_retro")


# ─── DB helpers ───────────────────────────────────────────────────────────────


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _db_init(conn)
    return conn


def _db_init(conn: sqlite3.Connection) -> None:
    """Kreira tablice ako ne postoje."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS kandidati (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern             TEXT NOT NULL,
            tip                 TEXT NOT NULL,
            kontekst            TEXT,
            knjiga              TEXT,
            chunk_idx           INTEGER,
            broj_pojavljivanja  INTEGER DEFAULT 1,
            ukupan_score        REAL DEFAULT 0.0,
            status              TEXT DEFAULT 'kandidat',
            datum_prvog         TEXT,
            datum_zadnjeg       TEXT,
            UNIQUE(pattern, knjiga, chunk_idx)
        );

        CREATE TABLE IF NOT EXISTS primijenjeni (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern         TEXT NOT NULL UNIQUE,
            tip             TEXT NOT NULL,
            datum_primjene  TEXT NOT NULL,
            broj_knjiga     INTEGER,
            ukupno_vidjeno  INTEGER
        );
    """)
    conn.commit()


# ─── HTML → čisti tekst ───────────────────────────────────────────────────────


def _html_u_tekst(html: str) -> str:
    """Skida HTML tagove i vraća čisti tekst za regex matching."""
    tekst = re.sub(r"<[^>]+>", " ", html)
    tekst = re.sub(r"&[a-z]+;", " ", tekst)
    tekst = re.sub(r"\s+", " ", tekst)
    return tekst.strip()


# ─── Parsiranje .chk fajla ────────────────────────────────────────────────────


def _parsiraj_chk(chk_path: Path) -> dict | None:
    """
    Čita .chk fajl i vraća {tekst, score, knjiga, chunk_idx} ili None.
    Podržava JSON format s 'finalno_polirano' poljem.
    """
    try:
        raw = chk_path.read_text(encoding="utf-8").strip()
    except Exception as e:
        log.warning(f"Ne mogu čitati {chk_path}: {e}")
        return None

    tekst = None
    score = None

    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            # Redosljed ključeva: finalno_polirano > korektura > translated > tekst > text
            for k in ("finalno_polirano", "korektura", "translated", "tekst", "text"):
                if k in data and data[k]:
                    tekst = str(data[k]).strip()
                    break
            score = data.get("quality_score") or data.get("score")
        except json.JSONDecodeError:
            # Regex fallback za finalno_polirano
            m = re.search(r'"finalno_polirano"\s*:\s*"(.+?)"\s*[},]', raw, re.DOTALL)
            if m:
                tekst = m.group(1).strip()
    else:
        tekst = raw

    if not tekst or len(tekst.strip()) < 30:
        return None

    # Izvuci chunk_idx iz naziva fajla (npr. chapter0006.html_blok_5.chk → 5)
    m_idx = re.search(r"_blok_(\d+)|_(\d+)\.chk$|(\d+)\.chk$", chk_path.name)
    chunk_idx = int(next(g for g in m_idx.groups() if g is not None)) if m_idx else 0

    # Knjiga = naziv mape iznad checkpoints/
    # Struktura: CHK_ROOT/_skr_ImeKnjige/checkpoints/file.chk
    knjiga = (
        chk_path.parts[-3] if len(chk_path.parts) >= 3 else chk_path.parent.parent.name
    )

    return {
        "tekst": _html_u_tekst(tekst),
        "score": float(score) if score is not None else None,
        "knjiga": knjiga,
        "chunk_idx": chunk_idx,
        "chk_path": str(chk_path),
    }


# ─── Scanner ──────────────────────────────────────────────────────────────────


def scan_sve_knjige(conn: sqlite3.Connection) -> dict:
    """
    Prolazi kroz sve .chk fajlove u CHK_ROOT i puni DB kandidatima.
    Vraća statistiku.
    """
    if not CHK_ROOT.exists():
        log.error(f"CHK_ROOT ne postoji: {CHK_ROOT}")
        sys.exit(1)

    chk_fajlovi = list(CHK_ROOT.rglob("*.chk"))
    log.info(f"Pronađeno {len(chk_fajlovi)} .chk fajlova u {CHK_ROOT}")

    stat = {
        "ukupno_fajlova": len(chk_fajlovi),
        "procesirano": 0,
        "novih_nalaza": 0,
        "ažuriranih": 0,
        "preskočeno": 0,
    }

    sada = datetime.now().isoformat(timespec="seconds")

    for chk_path in sorted(chk_fajlovi):
        chunk = _parsiraj_chk(chk_path)
        if chunk is None:
            stat["preskočeno"] += 1
            continue

        # Ignoriramo blokove s niskim quality score-om
        if chunk["score"] is not None and chunk["score"] < MIN_AVG_SCORE:
            stat["preskočeno"] += 1
            continue

        tekst_lower = chunk["tekst"].lower()
        stat["procesirano"] += 1
        nasao_nesto = False

        for pattern, opis in _SVE_REGEX:
            m = re.search(pattern, tekst_lower)
            if not m:
                continue

            nasao_nesto = True
            # Kontekst: 60 znakova oko nalaza
            start = max(0, m.start() - 60)
            end = min(len(chunk["tekst"]), m.end() + 60)
            kontekst = "…" + chunk["tekst"][start:end] + "…"

            try:
                # INSERT OR IGNORE + UPDATE broj_pojavljivanja
                conn.execute(
                    """
                    INSERT INTO kandidati
                        (pattern, tip, kontekst, knjiga, chunk_idx,
                         broj_pojavljivanja, ukupan_score, status,
                         datum_prvog, datum_zadnjeg)
                    VALUES (?, ?, ?, ?, ?, 1, ?, 'kandidat', ?, ?)
                    ON CONFLICT(pattern, knjiga, chunk_idx) DO UPDATE SET
                        broj_pojavljivanja = broj_pojavljivanja + 1,
                        ukupan_score       = ukupan_score + excluded.ukupan_score,
                        datum_zadnjeg      = excluded.datum_zadnjeg
                """,
                    (
                        pattern,
                        opis,
                        kontekst,
                        chunk["knjiga"],
                        chunk["chunk_idx"],
                        chunk["score"] or 0.0,
                        sada,
                        sada,
                    ),
                )
                if conn.execute("SELECT changes()").fetchone()[0] > 0:
                    stat["novih_nalaza"] += 1
                else:
                    stat["ažuriranih"] += 1
            except sqlite3.Error as e:
                log.warning(f"DB greška za {chk_path.name}: {e}")

        if nasao_nesto:
            conn.commit()

    conn.commit()
    return stat


# ─── Status prikaz ────────────────────────────────────────────────────────────


def prikazi_status(conn: sqlite3.Connection) -> None:
    """Prikaži statistiku DB-a u terminalu."""
    print("\n" + "═" * 64)
    print("  KALKOVI KARANTENA — STATUS")
    print("═" * 64)

    ukupno = conn.execute("SELECT COUNT(*) FROM kandidati").fetchone()[0]
    print(f"\n  Ukupno kandidata u DB:  {ukupno}")

    # Top 20 po broju pojavljivanja (grupirani po patternu)
    print("\n  Top 20 kalk-kandidata (grupirani po patternu):\n")
    print(
        f"  {'#':>4}  {'Pojavljivanja':>13}  {'Knjiga':>6}  Status      Pattern / Opis"
    )
    print("  " + "─" * 78)

    rows = conn.execute("""
        SELECT
            pattern,
            tip,
            SUM(broj_pojavljivanja)   AS ukupno,
            COUNT(DISTINCT knjiga)    AS knjige,
            AVG(ukupan_score)         AS avg_score,
            status,
            datum_zadnjeg
        FROM kandidati
        GROUP BY pattern
        ORDER BY ukupno DESC
        LIMIT 20
    """).fetchall()

    for i, r in enumerate(rows, 1):
        oznaka = (
            "✅"
            if r["ukupno"] >= MIN_POJAVLJIVANJA and r["knjige"] >= MIN_KNJIGA
            else "  "
        )
        print(
            f"  {i:>3}.  {r['ukupno']:>5} ({r['knjige']} knj.)  "
            f"{r['avg_score']:>5.1f}  {r['status']:<10}  {oznaka} {r['tip']}"
        )

    # Primijenjeni
    prim = conn.execute("SELECT COUNT(*) FROM primijenjeni").fetchone()[0]
    print(f"\n  Već primijenjenih u qa_benchmark.py: {prim}")

    # Spremni za primjenu
    spremni = conn.execute(
        """
        SELECT COUNT(DISTINCT pattern) FROM kandidati
        WHERE status = 'kandidat'
        GROUP BY pattern
        HAVING SUM(broj_pojavljivanja) >= ? AND COUNT(DISTINCT knjiga) >= ?
    """,
        (MIN_POJAVLJIVANJA, MIN_KNJIGA),
    ).fetchall()
    print(
        f"  Spremnih za primjenu (≥{MIN_POJAVLJIVANJA} pojavljivanja, ≥{MIN_KNJIGA} knjige): {len(spremni)}"
    )
    print("\n" + "═" * 64 + "\n")


# ─── Automatska primjena u qa_benchmark.py ────────────────────────────────────


def _dohvati_gotove(conn: sqlite3.Connection) -> list[dict]:
    """Vraća kalk-uzorke koji ispunjavaju MIN_POJAVLJIVANJA i MIN_KNJIGA."""
    rows = conn.execute(
        """
        SELECT
            pattern,
            tip,
            SUM(broj_pojavljivanja) AS ukupno,
            COUNT(DISTINCT knjiga)  AS knjige
        FROM kandidati
        WHERE status = 'kandidat'
        GROUP BY pattern
        HAVING ukupno >= ? AND knjige >= ?
        ORDER BY ukupno DESC
    """,
        (MIN_POJAVLJIVANJA, MIN_KNJIGA),
    ).fetchall()
    return [dict(r) for r in rows]


def _vec_primijenjen(conn: sqlite3.Connection, pattern: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM primijenjeni WHERE pattern = ?", (pattern,)
        ).fetchone()
        is not None
    )


def _vec_u_regex_listi(pattern: str) -> bool:
    """Provjeri da li je pattern već u postojećoj _KALKOVI_REGEX listi."""
    return any(p == pattern for p, _ in _KALKOVI_REGEX_LOKALNO)


def primijeni_u_qa_benchmark(conn: sqlite3.Connection) -> dict:
    """
    Ubacuje nove kalk-uzorke u _KALKOVI_REGEX listu u qa_benchmark.py.
    Vraća statistiku.
    """
    gotovi = _dohvati_gotove(conn)
    if not gotovi:
        log.info("Nema novih kalk-uzoraka za primjenu.")
        return {"primijenjeno": 0, "preskočeno": 0}

    if not QA_BENCHMARK_PATH.exists():
        log.error(f"qa_benchmark.py nije nađen na: {QA_BENCHMARK_PATH}")
        log.error("Prilagodi QA_BENCHMARK_PATH na vrhu skripte.")
        sys.exit(1)

    src = QA_BENCHMARK_PATH.read_text(encoding="utf-8")

    # Marker u qa_benchmark.py gdje dodajemo nove redove
    MARKER = "_KALKOVI_REGEX = ["
    if MARKER not in src:
        log.error(f"Marker '{MARKER}' nije nađen u qa_benchmark.py")
        sys.exit(1)

    sada = datetime.now().isoformat(timespec="seconds")
    stat = {"primijenjeno": 0, "preskočeno": 0}
    novi_redovi = []

    for k in gotovi:
        pattern = k["pattern"]
        opis = k["tip"]

        if _vec_primijenjen(conn, pattern) or _vec_u_regex_listi(pattern):
            stat["preskočeno"] += 1
            continue

        # Formatiraj red kao ostatak liste
        # Npr.: (r"\bna kraju krajeva\b",   "kalk: na kraju krajeva"),
        pattern_repr = repr(pattern).replace("'", '"')
        # Ukloni vanjski r"..." i dodaj raw prefix
        pattern_str = f'r"{pattern}"'
        red = f"    ({pattern_str:<45} {repr(opis):<55}),  # AUTO: {sada}"
        novi_redovi.append((red, k, sada))

    if not novi_redovi:
        log.info("Nema novih uzoraka za dodavanje (svi su već primijenjeni).")
        return stat

    # Dodaj nove redove odmah iza MARKER-a
    novi_blok = "\n".join(red for red, _, _ in novi_redovi) + "\n"
    src_novi = src.replace(
        MARKER,
        MARKER
        + "\n    # ── AUTO-DODANO iz kalkovi_karantena.db ──\n"
        + novi_blok
        + "    # ── KRAJ AUTO ──\n",
        1,
    )

    # Backup originalnog fajla
    backup_path = QA_BENCHMARK_PATH.with_suffix(".py.bak")
    QA_BENCHMARK_PATH.rename(backup_path)
    log.info(f"Backup sačuvan: {backup_path}")

    QA_BENCHMARK_PATH.write_text(src_novi, encoding="utf-8")

    # Označi kao primijenjene u DB-u
    for red, k, ts in novi_redovi:
        conn.execute(
            """
            INSERT OR REPLACE INTO primijenjeni
                (pattern, tip, datum_primjene, broj_knjiga, ukupno_vidjeno)
            VALUES (?, ?, ?, ?, ?)
        """,
            (k["pattern"], k["tip"], ts, k["knjige"], k["ukupno"]),
        )
        conn.execute(
            """
            UPDATE kandidati SET status = 'primijenjen'
            WHERE pattern = ?
        """,
            (k["pattern"],),
        )
        stat["primijenjeno"] += 1

    conn.commit()
    log.info(
        f"Primijenjeno {stat['primijenjeno']} novih kalk-uzoraka u qa_benchmark.py"
    )
    return stat


# ─── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Booklyfi — retroaktivni kalk scanner i primjena u qa_benchmark.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Primjeri:
  python kalkovi_retro_scan.py --status          # Prikaži stanje DB-a
  python kalkovi_retro_scan.py --scan            # Skeniraj sve .chk fajlove
  python kalkovi_retro_scan.py --apply           # Primijeni gotove u qa_benchmark.py
  python kalkovi_retro_scan.py --all             # Scan + apply u jednom koraku
        """,
    )
    parser.add_argument("--scan", action="store_true", help="Skeniraj sve .chk fajlove")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Primijeni gotove kalkove u qa_benchmark.py",
    )
    parser.add_argument("--status", action="store_true", help="Prikaži statistiku DB-a")
    parser.add_argument("--all", action="store_true", help="--scan + --apply")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        sys.exit(0)

    conn = db_connect()

    if args.all:
        args.scan = True
        args.apply = True

    if args.scan:
        log.info(f"Počinjem retroaktivni scan: {CHK_ROOT}")
        stat = scan_sve_knjige(conn)
        log.info(
            f"Scan završen — fajlova: {stat['ukupno_fajlova']}, "
            f"procesirano: {stat['procesirano']}, "
            f"novih nalaza: {stat['novih_nalaza']}, "
            f"ažuriranih: {stat['ažuriranih']}, "
            f"preskočeno: {stat['preskočeno']}"
        )
        prikazi_status(conn)

    if args.apply:
        log.info(
            f"Primjenjujem kalkove u qa_benchmark.py (prag: ≥{MIN_POJAVLJIVANJA} pojavljivanja, ≥{MIN_KNJIGA} knjige)"
        )
        stat = primijeni_u_qa_benchmark(conn)
        log.info(
            f"Primijenjeno: {stat['primijenjeno']}, preskočeno: {stat['preskočeno']}"
        )

    if args.status and not args.scan:
        prikazi_status(conn)

    conn.close()


if __name__ == "__main__":
    main()
