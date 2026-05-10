"""
core/kalkovi/rod_detektor.py
─────────────────────────────
Aktivni detektor i korektor miješanja gramatičkog roda (GPR) kroz cijelu
knjigu. Radi u dva moda:

  1. LIVE (per-chunk u pipeline/workers_v2):
     - Gradi per-knjiga registar lika→rod iz textualnih clue-ova i glosara
     - Primjenjuje deterministiku korekciju za poznate likove
     - Bilježi propuštene greške u kalkovi_karantena.db

  2. RETRO (batch nad .chk fajlovima):
     - Čita sve finalne .chk fajlove
     - Primjenjuje iste korekcije bez AI
     - Ažurira .chk in-place i vraća statistiku

Problem: AI modeli miješaju muški i ženski rod glagolskih pridjeva radnih
(GPR) za iste likove — npr. "Marija je rekla" u jednom poglavlju i
"Marija je rekao" u sljedećem.

Korištenje:
    from core.kalkovi.rod_detektor import RodDetektor
    detektor = RodDetektor()
    tekst, n = detektor.primijeni(tekst, knjiga_id="moja_knjiga",
                                   glosar_rod={"Marija": "Ž", "Ivan": "M"})
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REGISTRI_DIR = BASE_DIR / "data" / "rod_registri"
DB_PATH = BASE_DIR / "data" / "kalkovi_karantena.db"

# Minimalni broj clue-ova iste vrijednosti da se rod registrira
MIN_CLUE = 3

# ── GPR parovi: muški oblik → ženski oblik ────────────────────────────────────
# Format: {muški_GPR: ženski_GPR}
GPR_M_Z: dict[str, str] = {
    # biti
    "bio": "bila",
    # ići i složenice
    "išao": "išla", "otišao": "otišla", "prišao": "prišla",
    "ušao": "ušla", "izašao": "izašla", "prošao": "prošla",
    "sišao": "sišla", "dočekao": "dočekala", "došao": "došla",
    "našao": "našla", "pronašao": "pronašla",
    # reći/govoriti
    "rekao": "rekla", "kazao": "kazala", "govorio": "govorila",
    "progovorio": "progovorila", "odgovorio": "odgovorila",
    # vidjeti/gledati
    "vidio": "vidjela", "gledao": "gledala", "pogledao": "pogledala",
    "ugledao": "ugledala", "primijetio": "primijetila",
    # čuti
    "čuo": "čula",
    # modalci
    "htio": "htjela", "mogao": "mogla", "morao": "morala",
    "smio": "smjela", "znao": "znala", "trebao": "trebala",
    # imati/dati/uzeti
    "imao": "imala", "dao": "dala", "uzeo": "uzela",
    # sjesti/ležati/ustati/stati/stajati
    "sjeo": "sjela", "legao": "legla", "ustao": "ustala",
    "stao": "stala", "sjedio": "sjedila", "stajao": "stajala",
    # kretanje
    "krenuo": "krenula", "okrenuo": "okrenula", "trčao": "trčala",
    "hodao": "hodala", "bježao": "bježala", "pobjegao": "pobjegla",
    # pasti/doći/nastaviti
    "pao": "pala", "počeo": "počela", "prestao": "prestala",
    "nastavio": "nastavila", "vratio": "vratila", "ostao": "ostala",
    # misliti/osjećati/razumjeti
    "mislio": "mislila", "osjetio": "osjetila", "osjećao": "osjećala",
    "razumio": "razumjela", "shvatio": "shvatila", "pomislio": "pomislila",
    "sjetio": "sjetila", "zaboravio": "zaboravila",
    # raditi/napraviti
    "radio": "radila", "uradio": "uradila", "napravio": "napravila",
    "odlučio": "odlučila", "pokušao": "pokušala",
    # dati/uzimati
    "ponudio": "ponudila", "prihvatio": "prihvatila",
    "odbio": "odbila", "zamolio": "zamolila", "pozvao": "pozvala",
    "zvao": "zvala", "nazvao": "nazvala",
    # nositi/nosio
    "nosio": "nosila", "tražio": "tražila",
    # geste i emocije
    "klimnuo": "klimnula", "slegnuo": "slegnula",
    "osmjehnuo": "osmjehnula", "nasmijao": "nasmijala",
    "smijao": "smijala", "plakao": "plakala", "vikao": "vikala",
    "šaputao": "šaputala",
    # otvoriti/zatvoriti
    "otvorio": "otvorila", "zatvorio": "zatvorila",
    "spustio": "spustila", "podigao": "podigla",
    # čitati/pisati/pjevati/spavati
    "čitao": "čitala", "pisao": "pisala", "pjevao": "pjevala",
    "spavao": "spavala",
    # jesti/piti
    "jeo": "jela", "pio": "pila",
    # posjetiti/sjetiti/dobiti/izgubiti
    "posjetio": "posjetila", "dobio": "dobila", "izgubio": "izgubila",
    # pričati/pitati/čekati
    "pričao": "pričala", "pitao": "pitala", "čekao": "čekala",
}

# Reverse: ženski → muški
GPR_Z_M: dict[str, str] = {v: k for k, v in GPR_M_Z.items()}

# Sve poznate muške forme (za regex)
_SVE_M = sorted(GPR_M_Z.keys(), key=len, reverse=True)
# Sve poznate ženske forme (za regex)
_SVE_Z = sorted(GPR_Z_M.keys(), key=len, reverse=True)

# ── Regex patterne za detekciju ─────────────────────────────────────────────
# Vlastito ime: počinje velikim slovom, 2-25 slova (BS/HR dijakritici uključeni)
_IME_PAT = r"[A-ZČĆŠĐŽА-Я][a-zA-ZčćšđžА-Я\-]{1,24}"

# Forward: "Ime [se] je GPR" — najčešći oblik
_FWD_M_RE = re.compile(
    rf"\b({_IME_PAT})\s+(?:se\s+)?je\s+({'|'.join(re.escape(f) for f in _SVE_M)})\b",
    re.UNICODE,
)
_FWD_Z_RE = re.compile(
    rf"\b({_IME_PAT})\s+(?:se\s+)?je\s+({'|'.join(re.escape(f) for f in _SVE_Z)})\b",
    re.UNICODE,
)
# Backward: "GPR je Ime" — inverzni red (dijaloški uvod: 'rekao je Ivan')
_BWD_M_RE = re.compile(
    rf"\b({'|'.join(re.escape(f) for f in _SVE_M)})\s+je\s+({_IME_PAT})\b",
    re.UNICODE,
)
_BWD_Z_RE = re.compile(
    rf"\b({'|'.join(re.escape(f) for f in _SVE_Z)})\s+je\s+({_IME_PAT})\b",
    re.UNICODE,
)
# Titule — signalizuju rod bez GPR
_TITULA_Z_RE = re.compile(
    rf"\b(?:gospođa|gđa|mrs\.?|ms\.?|lady|miss)\s+({_IME_PAT})\b",
    re.IGNORECASE | re.UNICODE,
)
_TITULA_M_RE = re.compile(
    rf"\b(?:gospodin|g\.|mr\.?|sir|lord|dr\.?\s+)({_IME_PAT})\b",
    re.IGNORECASE | re.UNICODE,
)

# Zaustavne riječi — vlastita imena koja zapravo nisu (homonimi)
_ZAUSTAVI = frozenset({
    "Ali", "Jer", "Dok", "Kad", "Što", "Koji", "Koja", "Koje",
    "Ovaj", "Ova", "Ovo", "Taj", "Ta", "To", "Jedan", "Jedna",
    "Ovdje", "Tamo", "Gdje", "Ili", "Nego", "Dakle", "Naime",
    "Ipak", "Međutim", "Također", "Tek", "Već", "Baš", "Samo",
    "Sve", "Svi", "Svaki", "Svaka", "Svako", "Nije", "Nema",
    "Bio", "Bila", "Bili", "Rekao", "Rekla", "Otišao", "Otišla",
})


# ── Karantena upis ────────────────────────────────────────────────────────────

def _zapisi_rod_gresku(ime: str, gpr_greska: str, kontekst: str, knjiga: str) -> None:
    """Upisuje rod_mijesanje u karantena DB (fail-safe)."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        pattern = f"rod:{ime}:{gpr_greska}"[:200]
        with sqlite3.connect(DB_PATH) as conn:
            # Osiguraj da tablica postoji
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kandidati (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT NOT NULL,
                    tip TEXT NOT NULL,
                    kontekst TEXT,
                    knjiga TEXT,
                    chunk_idx INTEGER DEFAULT 0,
                    broj_pojavljivanja INTEGER DEFAULT 1,
                    ukupan_score REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'kandidat',
                    datum_prvog TEXT DEFAULT (datetime('now')),
                    datum_zadnjeg TEXT DEFAULT (datetime('now')),
                    knjige_set TEXT DEFAULT '[]',
                    rollback_count INTEGER DEFAULT 0,
                    validator_napomena TEXT DEFAULT ''
                )
            """)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_pattern_tip ON kandidati(pattern, tip)"
            )
            existing = conn.execute(
                "SELECT id FROM kandidati WHERE pattern=? AND tip='rod_mijesanje'",
                (pattern,),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE kandidati
                       SET broj_pojavljivanja = broj_pojavljivanja + 1,
                           kontekst = ?,
                           knjiga = ?,
                           datum_zadnjeg = datetime('now')
                       WHERE id = ?""",
                    (kontekst[:500], knjiga, existing[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO kandidati
                       (pattern, tip, kontekst, knjiga, status)
                       VALUES (?, 'rod_mijesanje', ?, ?, 'info')""",
                    (pattern, kontekst[:500], knjiga),
                )
            conn.commit()
    except Exception as e:
        log.debug(f"[rod_detektor] DB greška: {e}")


# ── Registar per-knjiga ────────────────────────────────────────────────────────

class _RodRegistar:
    """
    Per-knjiga evidencija lika → rod.
    Perzistira u REGISTRI_DIR/{knjiga_id}.json.
    Threadsafe.
    """

    def __init__(self, knjiga_id: str):
        self.knjiga_id = knjiga_id
        self._lock = threading.Lock()
        # {ime: {"rod": "M"|"Ž"|None, "clue_m": int, "clue_z": int}}
        self._data: dict[str, dict] = {}
        self._path = REGISTRI_DIR / f"{knjiga_id}.json"
        self._ucitaj()

    def _ucitaj(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def spremi(self) -> None:
        try:
            REGISTRI_DIR.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.debug(f"[rod_detektor] Snimanje registra palo: {e}")

    def dodaj_clue(self, ime: str, rod: str) -> None:
        """Dodaje clue za rod (M ili Ž). Ne mijenja potvrđeni rod."""
        if ime in _ZAUSTAVI or len(ime) < 2:
            return
        with self._lock:
            entry = self._data.setdefault(
                ime, {"rod": None, "clue_m": 0, "clue_z": 0}
            )
            if rod == "M":
                entry["clue_m"] = entry.get("clue_m", 0) + 1
            elif rod == "Ž":
                entry["clue_z"] = entry.get("clue_z", 0) + 1

            # Registriraj rod kad ima dovoljno clue-ova i prevlada jedan
            if entry["rod"] is None:
                if entry["clue_m"] >= MIN_CLUE and entry["clue_m"] > entry["clue_z"]:
                    entry["rod"] = "M"
                    log.debug(f"[rod_detektor] '{ime}' registriran kao M (clue_m={entry['clue_m']})")
                elif entry["clue_z"] >= MIN_CLUE and entry["clue_z"] > entry["clue_m"]:
                    entry["rod"] = "Ž"
                    log.debug(f"[rod_detektor] '{ime}' registriran kao Ž (clue_z={entry['clue_z']})")

    def dodaj_iz_glosara(self, glosar_rod: dict[str, str]) -> None:
        """Inicijalizira registar iz book_context glosara (visoka pouzdanost)."""
        with self._lock:
            for ime, rod in glosar_rod.items():
                if rod in ("M", "Ž") and ime not in _ZAUSTAVI:
                    entry = self._data.setdefault(
                        ime, {"rod": None, "clue_m": 0, "clue_z": 0}
                    )
                    # Glosar ima prioritet — direktno postavi rod
                    entry["rod"] = rod
                    # Dodaj i clue-ove da spriječi prepisivanje
                    kljucni_clue = "clue_m" if rod == "M" else "clue_z"
                    entry[kljucni_clue] = max(entry.get(kljucni_clue, 0), MIN_CLUE)

    def rod_za(self, ime: str) -> Optional[str]:
        """Vraća 'M', 'Ž', ili None ako rod nije poznat."""
        return self._data.get(ime, {}).get("rod")

    def svi_poznati(self) -> dict[str, str]:
        """Vraća {ime: rod} za sve poznate likove."""
        return {
            ime: v["rod"]
            for ime, v in self._data.items()
            if v.get("rod") in ("M", "Ž")
        }

    def statistika(self) -> dict:
        poznati = self.svi_poznati()
        return {
            "ukupno": len(self._data),
            "muski": sum(1 for r in poznati.values() if r == "M"),
            "zenski": sum(1 for r in poznati.values() if r == "Ž"),
            "nepoznati": len(self._data) - len(poznati),
        }


# ── Korekcija — zamjena pogrešnog GPR-a ──────────────────────────────────────

def _sacuvaj_velicinu(original: str, zamjena: str) -> str:
    """Prilagodi veliko/malo početno slovo zamjene prema originalu."""
    if not original or not zamjena:
        return zamjena
    if original[0].isupper():
        return zamjena[0].upper() + zamjena[1:]
    return zamjena


def _koriguj_chunk(
    tekst: str,
    poznati: dict[str, str],
    knjiga_id: str,
) -> tuple[str, int]:
    """
    Primjenjuje rod korekcije na tekst.
    Vraća (ispravljeni_tekst, broj_korekcija).
    """
    if not tekst or not poznati:
        return tekst, 0

    n_ukupno = 0

    for ime, rod in poznati.items():
        if rod not in ("M", "Ž"):
            continue

        # Odaberi par: tražimo pogrešan rod, zamjenjujemo ispravnim
        if rod == "Ž":
            pogresni = GPR_M_Z   # muška forma = pogrešna za ženski lik
            ispravni = GPR_Z_M   # ženski oblici (za lookup)
        else:
            pogresni = GPR_Z_M   # ženska forma = pogrešna za muški lik
            ispravni = GPR_M_Z

        ime_esc = re.escape(ime)

        for pogresna_forma, ispravna_forma in pogresni.items():
            # Forward: "Ime [se] je pogresna_forma"
            pat_fwd = re.compile(
                rf"\b{ime_esc}(\s+(?:se\s+)?je\s+){re.escape(pogresna_forma)}\b",
                re.UNICODE | re.IGNORECASE,
            )
            if pat_fwd.search(tekst):
                novi_tekst = pat_fwd.sub(
                    lambda m, pf=pogresna_forma, iz=ispravna_forma: (
                        m.group(0).replace(
                            # pronađi originalnu formu (različita velika/mala slova)
                            re.search(re.escape(pf), m.group(0), re.IGNORECASE).group(0),
                            _sacuvaj_velicinu(
                                re.search(re.escape(pf), m.group(0), re.IGNORECASE).group(0),
                                iz
                            ),
                            1
                        )
                    ),
                    tekst,
                )
                if novi_tekst != tekst:
                    n_ukupno += 1
                    _zapisi_rod_gresku(
                        ime, pogresna_forma,
                        f"[{rod}] {ime} je {pogresna_forma} → {ispravna_forma}",
                        knjiga_id,
                    )
                    tekst = novi_tekst

            # Backward: "pogresna_forma je Ime" — dijaloški uvod (case-insensitive)
            pat_bwd = re.compile(
                rf"\b{re.escape(pogresna_forma)}(\s+je\s+){ime_esc}\b",
                re.UNICODE | re.IGNORECASE,
            )
            if pat_bwd.search(tekst):
                novi_tekst = pat_bwd.sub(
                    lambda m, pf=pogresna_forma, iz=ispravna_forma: (
                        m.group(0).replace(
                            re.search(re.escape(pf), m.group(0), re.IGNORECASE).group(0),
                            _sacuvaj_velicinu(
                                re.search(re.escape(pf), m.group(0), re.IGNORECASE).group(0),
                                iz
                            ),
                            1
                        )
                    ),
                    tekst,
                )
                if novi_tekst != tekst:
                    n_ukupno += 1
                    _zapisi_rod_gresku(
                        ime, pogresna_forma,
                        f"[{rod}] {pogresna_forma} je {ime} → {ispravna_forma} je {ime}",
                        knjiga_id,
                    )
                    tekst = novi_tekst

    return tekst, n_ukupno


# ── Detekcija clue-ova iz teksta ──────────────────────────────────────────────

def _detektuj_clue_ove(tekst: str, registar: _RodRegistar) -> None:
    """Skenira tekst i ažurira rod_registar s novim clue-ovima."""
    # Forward clue-ovi: "Ime je verbM" → Ime je muškarac
    for m in _FWD_M_RE.finditer(tekst):
        registar.dodaj_clue(m.group(1), "M")
    # Forward clue-ovi: "Ime je verbŽ" → Ime je žena
    for m in _FWD_Z_RE.finditer(tekst):
        registar.dodaj_clue(m.group(1), "Ž")
    # Backward clue-ovi: "verbM je Ime"
    for m in _BWD_M_RE.finditer(tekst):
        registar.dodaj_clue(m.group(2), "M")
    # Backward clue-ovi: "verbŽ je Ime"
    for m in _BWD_Z_RE.finditer(tekst):
        registar.dodaj_clue(m.group(2), "Ž")
    # Titule
    for m in _TITULA_Z_RE.finditer(tekst):
        registar.dodaj_clue(m.group(1), "Ž")
    for m in _TITULA_M_RE.finditer(tekst):
        registar.dodaj_clue(m.group(1), "M")


# ── Glavna klasa ──────────────────────────────────────────────────────────────

class RodDetektor:
    """
    Singleton-like rod detektor za upotrebu u pipeline/workers_v2.
    Jedan objekt može opsluživati više knjiga — koristi odvojene registre.

    Upotreba:
        detektor = RodDetektor()
        tekst, n = detektor.primijeni(tekst, knjiga_id="moja_knjiga",
                                       glosar_rod={"Marija": "Ž"})
    """

    def __init__(self) -> None:
        # {knjiga_id: _RodRegistar}
        self._registri: dict[str, _RodRegistar] = {}
        self._lock = threading.Lock()

    def _dohvati_registar(self, knjiga_id: str) -> _RodRegistar:
        safe_id = re.sub(r"[^\w\-]", "_", knjiga_id or "default")[:80]
        with self._lock:
            if safe_id not in self._registri:
                self._registri[safe_id] = _RodRegistar(safe_id)
            return self._registri[safe_id]

    def primijeni(
        self,
        tekst: str,
        knjiga_id: str = "",
        glosar_rod: Optional[dict[str, str]] = None,
    ) -> tuple[str, int]:
        """
        Glavna metoda — detektuje i ispravlja rod u jednom chunku.

        Args:
            tekst:      Ulazni prevedeni tekst (može biti HTML).
            knjiga_id:  Identifikator knjige (za per-knjiga registar).
            glosar_rod: Rječnik {ime: 'M'|'Ž'} iz BookContext.

        Returns:
            (ispravljeni_tekst, broj_korekcija)
        """
        if not tekst or not tekst.strip():
            return tekst, 0

        registar = self._dohvati_registar(knjiga_id)

        # 1. Inicijaliziraj registar iz glosara (visoka pouzdanost)
        if glosar_rod:
            registar.dodaj_iz_glosara(glosar_rod)

        # 2. Detektuj clue-ove iz teksta (gradi registar organički)
        _detektuj_clue_ove(tekst, registar)

        # 3. Primijeni korekcije za sve poznate likove
        poznati = registar.svi_poznati()
        if not poznati:
            return tekst, 0

        tekst, n_korekcija = _koriguj_chunk(tekst, poznati, knjiga_id)

        # 4. Spremi registar (periodično — svaki poziv)
        registar.spremi()

        return tekst, n_korekcija

    def batch_primijeni(
        self,
        chk_fajlovi: list[Path],
        knjiga_id: str = "",
        glosar_rod: Optional[dict[str, str]] = None,
        log_fn=None,
    ) -> dict:
        """
        Retroaktivna batch korekcija nad listom .chk fajlova.
        Čita, ispravlja i piše nazad. Vraća statistiku.

        Args:
            chk_fajlovi: Lista Path objekata za .chk fajlove.
            knjiga_id:   Identifikator knjige.
            glosar_rod:  Opcioni rječnik {ime: rod} iz BookContext.
            log_fn:      Callback za logiranje (engine.log).

        Returns:
            {"obradjeno": int, "korigovano": int, "korekcija_ukupno": int,
             "po_fajlu": {stem: int}}
        """
        def _log(msg, nivo="info"):
            if log_fn:
                log_fn(msg, nivo)
            else:
                log.info(msg)

        statistika = {
            "obradjeno": 0,
            "korigovano": 0,
            "korekcija_ukupno": 0,
            "po_fajlu": {},
        }

        if not chk_fajlovi:
            _log("⚠️ [rod_detektor] Nema .chk fajlova za retro korekciju", "warning")
            return statistika

        registar = self._dohvati_registar(knjiga_id)
        if glosar_rod:
            registar.dodaj_iz_glosara(glosar_rod)

        # Prva prolaznica — samo detekcija (gradi registar iz svih .chk fajlova)
        _log(
            f"[rod_detektor] Retro scan: detektujem rod iz {len(chk_fajlovi)} .chk fajlova...",
            "tech",
        )
        for chk in chk_fajlovi:
            try:
                tekst = chk.read_text("utf-8", errors="ignore")
                _detektuj_clue_ove(tekst, registar)
            except Exception as e:
                log.debug(f"[rod_detektor] Scan greška ({chk.name}): {e}")

        registar.spremi()
        poznati = registar.svi_poznati()
        _log(
            f"[rod_detektor] Registar: {len(poznati)} likova s poznatim rodom "
            f"({sum(1 for r in poznati.values() if r=='M')} M / "
            f"{sum(1 for r in poznati.values() if r=='Ž')} Ž)",
            "system",
        )

        if not poznati:
            _log("ℹ️ [rod_detektor] Nijedan lik s poznatim rodom — korekcija preskočena", "tech")
            return statistika

        # Druga prolaznica — korekcija
        for chk in chk_fajlovi:
            try:
                tekst_orig = chk.read_text("utf-8", errors="ignore")
                tekst_kor, n = _koriguj_chunk(tekst_orig, poznati, knjiga_id)
                statistika["obradjeno"] += 1
                if n > 0:
                    # Atomičan upis (privremeni fajl → rename)
                    tmp = chk.with_suffix(".rod_tmp")
                    tmp.write_text(tekst_kor, encoding="utf-8")
                    tmp.replace(chk)
                    statistika["korigovano"] += 1
                    statistika["korekcija_ukupno"] += n
                    statistika["po_fajlu"][chk.stem] = n
                    _log(
                        f"[rod_detektor] ✅ {chk.name}: {n} rod korekcija", "tech"
                    )
            except Exception as e:
                log.warning(f"[rod_detektor] Greška u {chk.name}: {e}")

        _log(
            f"[rod_detektor] 🔄 Retro završen: {statistika['korigovano']}/"
            f"{statistika['obradjeno']} fajlova korigovano, "
            f"{statistika['korekcija_ukupno']} ukupnih zamjena",
            "system",
        )
        return statistika


# ── Gotova instanca ───────────────────────────────────────────────────────────

rod_detektor: RodDetektor = RodDetektor()


# ── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

    testovi = [
        ("Marija je rekao da želi ostati.", {"Marija": "Ž"}),
        ("Ivan je rekla da odlazi.", {"Ivan": "M"}),
        ("Rekao je Aida: 'Idem kući.'", {"Aida": "Ž"}),
        ("Rekla je John: 'Ostani.'", {"John": "M"}),
        ("Marko je otišla bez riječi.", {"Marko": "M"}),
        ("Ispravna rečenica: Sara je otišla kući.", {"Sara": "Ž"}),
    ]

    detektor = RodDetektor()
    print("=== RodDetektor — lokalni test ===\n")
    for tekst, glosar in testovi:
        rezultat, n = detektor.primijeni(tekst, knjiga_id="test", glosar_rod=glosar)
        status = "✅ ISPRAVNO" if n == 0 else f"🔧 {n} korekcija"
        print(f"[{status}]")
        print(f"  IN:  {tekst}")
        if n:
            print(f"  OUT: {rezultat}")
        print()
