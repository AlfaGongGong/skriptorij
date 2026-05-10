"""
tts.py — TTS filter generator za Moon+ Reader

FORMAT .ttsfilter fajla:
  Svaki red je zamjena u obliku: original#->#fonetizovano
  Primjeri:
    A#->#a
    George#->#Džordž
    me #-># meh

LOGIKA:
  1. Učitava tekst iz checkpointa (ako postoje) ili iz originalnog EPUB-a
  2. Upisuje hardkodirane zamjene (velika slova BS abecede)
  3. Skenira tekst za strane riječi (q/w/x/y, vlastita imena, strani idiomi)
  4. Šalje skenirane strane riječi AI-u za fonetizaciju na BS izgovor
  5. Snima .ttsfilter fajl pored izlazne knjige (OUTPUT_DIR)
"""

import re
import asyncio
import zipfile
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from utils.logging import add_audit
from config.settings import OUTPUT_DIR


# ── Hardkodirane zamjene: velika slova BS abecede → mala (za TTS) ─────────────
_HARDKODIRANI = """A#->#a
B#->#b
C#->#c
Č#->#č
Ć#->#ć
D#->#d
Dž#->#dž
Đ#->#đ
E#->#e
F#->#f
G#->#g
H#->#h
I#->#i
J#->#j
K#->#k
L#->#l
Lj#->#lj
M#->#m
N#->#n
Nj#->#nj
O#->#o
P#->#p
Q#->#q
R#->#r
S#->#s
Š#->#š
T#->#t
U#->#u
V#->#v
W#->#w
X#->#x
Y#->#y
Z#->#z
Ž#->#ž
me #-># meh"""

# BS/HR znakovi koji su normalni (ne tretiramo kao strani)
_BS_ZNAKOVI = set("aAbBcCčČćĆdDđĐeEfFgGhHiIjJkKlLmMnNoOpPrRsStTuUvVzZšŠžŽ")

# Regex za strane/nepoznate znakove (q, w, x, y — ne postoje u BS abecedi)
_STRANI_ZNAKOVI_RE = re.compile(r"[qwxyQWXY]")

# Regex za izvlačenje čistih riječi iz teksta
_RIJEC_RE = re.compile(r"\b[A-ZČĆŽŠĐa-zčćžšđ][a-zA-ZčćžšđČĆŽŠĐ\-']{2,}\b")

# Engleski prijedlozi/veznici koji zbune TTS (kratke engl. riječi)
_ENGLESKI_KRATKI = {
    "the", "a", "an", "in", "on", "at", "to", "of", "for", "with",
    "from", "by", "or", "and", "but", "not", "is", "are", "was",
    "were", "be", "been", "has", "have", "had", "do", "does", "did",
    "will", "would", "can", "could", "should", "may", "might", "shall",
    "no", "yes", "it", "he", "she", "we", "they", "you", "me", "my",
    "his", "her", "its", "our", "their", "this", "that", "these",
    "those", "what", "which", "who", "how", "when", "where", "why",
}

# Fonetizacija engleskih kratkih riječi → BS izgovor
_ENGLESKI_KRATKI_FONETIKA = {
    "the": "de",
    "a": "ej",
    "an": "en",
    "in": "in",
    "on": "on",
    "at": "et",
    "to": "tu",
    "of": "ov",
    "for": "for",
    "with": "vid",
    "from": "from",
    "by": "baj",
    "or": "or",
    "and": "end",
    "but": "bat",
    "not": "not",
    "is": "iz",
    "are": "ar",
    "was": "woz",
    "it": "it",
    "he": "hi",
    "she": "ši",
    "we": "wi",
    "they": "dej",
    "you": "ju",
    "me": "mi",
    "my": "maj",
    "his": "hiz",
    "her": "her",
    "no": "nou",
    "yes": "jes",
}


def _html_u_tekst(html: str) -> str:
    """Konvertuje HTML u čisti tekst za analizu."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator=" ")
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)


def _je_strana_rijec(rijec: str) -> bool:
    """
    Vraća True ako je rijec vjerovatno strana (ne-BS).
    Kriteriji:
      - Sadrži q, w, x, y
      - Sve je caps i duža od 1 slova (kratica/akronim)
      - Sadrži nestandardnu kombinaciju suglasnika za BS
    """
    if not rijec or len(rijec) < 2:
        return False
    r_lower = rijec.lower()
    if _STRANI_ZNAKOVI_RE.search(rijec):
        return True
    if r_lower in _ENGLESKI_KRATKI:
        return True
    # Dvostruki suglasnici nekarakteristični za BS
    if re.search(r"(ll|rr|tt|pp|bb|dd|gg|ss|ff|cc|zz)", r_lower):
        return True
    return False


def _ekstraktuj_strane_rijeci(tekst: str) -> list[str]:
    """
    Izvlači listu jedinstvenih stranih riječi iz teksta.
    Vraća sortiranu listu bez duplikata.
    """
    kandidati = set()
    rijeci = _RIJEC_RE.findall(tekst)
    for r in rijeci:
        if _je_strana_rijec(r):
            kandidati.add(r)
    # Kratke engl. riječi (lowercase)
    sve_lowercase = re.findall(r"\b[a-z]{2,5}\b", tekst)
    for r in sve_lowercase:
        if r in _ENGLESKI_KRATKI:
            kandidati.add(r)
    return sorted(kandidati)


def _regex_fonetizacija(rijeci: list[str]) -> dict[str, str]:
    """
    Regex-based fonetizacija poznatih slučajeva bez AI poziva.
    Vraća dict {original: fonetizovano}.
    """
    rezultat = {}
    for r in rijeci:
        r_lower = r.lower()
        if r_lower in _ENGLESKI_KRATKI_FONETIKA:
            rezultat[r] = _ENGLESKI_KRATKI_FONETIKA[r_lower]
    return rezultat


async def _ai_fonetizacija(
    strane_rijeci: list[str], engine, log_fn
) -> dict[str, str]:
    """
    Šalje strane/nefonetizovane riječi AI modelu za fonetizaciju.
    AI vraća linije u formatu: original#->#fonetizovano
    """
    if not strane_rijeci:
        return {}

    lista_rijeci = "\n".join(strane_rijeci)
    system_prompt = (
        "Ti si fonetski ekspert za bosanski jezik. "
        "Za svaku stranu riječ ili vlastito ime koje dobiješ, napiši kako se izgovara na bosanskom. "
        "Format odgovora — svaka zamjena u zasebnom retku:\n"
        "original#->#fonetizovano\n\n"
        "Pravila:\n"
        "- Samo fonetski zapis, bez objašnjenja\n"
        "- Koristi bosanska slova (š, č, ž, đ, ć)\n"
        "- Svaka linija: tocno jedna zamjena\n"
        "- Ako rijec vec zvuci bosanski, ipak je napiši (original#->#original)\n"
        "Primjeri:\n"
        "George#->#Džordž\n"
        "Harry#->#Hari\n"
        "London#->#London\n"
        "thriller#->#triler\n"
        "coffee#->#kofi\n"
    )
    prompt = f"Fonetizuj sljedeće riječi:\n{lista_rijeci}"

    try:
        odgovor, _ = await engine._call_ai_engine(
            prompt,
            0,
            uloga="LEKTOR",
            filename="tts_fonetizacija",
            sys_override=system_prompt,
            tip_bloka="naracija",
        )
    except Exception as e:
        log_fn(f"⚠️ TTS AI fonetizacija greška: {e}", "warning")
        return {}

    if not odgovor:
        return {}

    # Parsiraj odgovor: original#->#fonetizovano
    rezultat = {}
    for linija in odgovor.splitlines():
        linija = linija.strip()
        if "#->#" in linija:
            dijelovi = linija.split("#->#", 1)
            if len(dijelovi) == 2:
                orig = dijelovi[0].strip()
                fonet = dijelovi[1].strip()
                if orig and fonet and orig != fonet:
                    rezultat[orig] = fonet

    log_fn(f"✅ TTS: AI fonetizirao {len(rezultat)} od {len(strane_rijeci)} stranih riječi.", "tech")
    return rezultat


def _generiraj_ttsfilter_sadrzaj(ai_fonetika: dict[str, str]) -> str:
    """
    Gradi kompletan .ttsfilter sadržaj:
    1. Hardkodirane zamjene
    2. AI-fonetizovane strane riječi
    """
    linije = [_HARDKODIRANI]

    if ai_fonetika:
        linije.append("")  # prazan red kao separator
        linije.append("# Strane rijeci i vlastita imena")
        for original, fonetizovano in sorted(ai_fonetika.items()):
            linije.append(f"{original}#->#{fonetizovano}")

    return "\n".join(linije) + "\n"


def start_from_master(
    book_path: str, model: str, shared_stats: dict, shared_controls: dict
):
    """
    TTS filter generator. NE pokreće AI prijevod/lekturu.
    Generira .ttsfilter fajl za Moon+ Reader u OUTPUT_DIR.
    """

    def log(msg: str, tip: str = "info"):
        add_audit(msg, tip, shared_stats=shared_stats)

    shared_stats["status"] = "TTS OBRADA..."
    log("🔊 TTS filter generator pokrenut...", "system")

    try:
        from core.engine import SkriptorijAllInOne

        engine = SkriptorijAllInOne(book_path, model, shared_stats, shared_controls)
        book_path_obj = Path(book_path)

        if not book_path_obj.exists():
            log(f"❌ Knjiga nije pronađena: {book_path}", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        # ── Raspakivanje EPUB-a ──────────────────────────────────────────────
        engine.work_dir.mkdir(parents=True, exist_ok=True)
        engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        log(f"📖 Raspakovavam: {book_path_obj.name}", "tech")
        try:
            with zipfile.ZipFile(book_path_obj, "r") as z:
                z.extractall(engine.work_dir)
        except Exception as e:
            log(f"❌ Nije moguće raspakovanje EPUB-a: {e}", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        # ── Pronađi HTML fajlove ─────────────────────────────────────────────
        html_files = sorted(
            [
                f
                for f in engine.work_dir.rglob("*")
                if f.suffix.lower() in (".html", ".htm", ".xhtml")
            ],
            key=lambda x: x.name,
        )

        if not html_files:
            log("❌ TTS: Nema HTML fajlova u EPUB-u.", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        log(f"📄 Pronađeno {len(html_files)} poglavlja.", "system")

        # ── Primijeni checkpointe ako postoje ────────────────────────────────
        chk_files = list(engine.checkpoint_dir.glob("*.chk"))
        if chk_files:
            log(f"♻️ Učitavam {len(chk_files)} lektoriranih blokova...", "system")
            _primijeni_checkpointe_na_html(html_files, engine.checkpoint_dir, log)
        else:
            log("ℹ️ Nema checkpointa — koristim originalni tekst iz EPUB-a.", "info")

        # ── Izvuci sav tekst za analizu ──────────────────────────────────────
        shared_stats["status"] = "TTS: Skeniranje teksta..."
        shared_stats["pct"] = 20

        sav_tekst = []
        for hf in html_files:
            try:
                html = hf.read_text("utf-8", errors="ignore")
                sav_tekst.append(_html_u_tekst(html))
            except Exception as e:
                log(f"⚠️ TTS: Greška pri čitanju {hf.name}: {e}", "warning")

        kompletan_tekst = " ".join(sav_tekst)

        # ── Pronađi strane riječi ────────────────────────────────────────────
        strane_rijeci = _ekstraktuj_strane_rijeci(kompletan_tekst)
        log(f"🔍 TTS: Pronađeno {len(strane_rijeci)} stranih/nepoznatih izraza.", "tech")

        # Regex fonetizacija za poznate slučajeve
        fonetika = _regex_fonetizacija(strane_rijeci)
        preostale = [r for r in strane_rijeci if r not in fonetika]

        # ── AI fonetizacija za preostale ─────────────────────────────────────
        shared_stats["status"] = "TTS: AI fonetizacija..."
        shared_stats["pct"] = 50

        ai_fonetika = {}
        if preostale:
            # Ograniči na max 200 riječi da izbjegnemo predugačak prompt
            batch = preostale[:200]
            log(f"🤖 TTS: Šaljem {len(batch)} riječi na AI fonetizaciju...", "tech")
            try:
                ai_fonetika = asyncio.run(
                    _ai_fonetizacija(batch, engine, log)
                )
            except Exception as e:
                log(f"⚠️ TTS AI fonetizacija nije uspjela: {e} — nastavljam bez AI.", "warning")

        # Spoji regex + AI fonetiku
        fonetika.update(ai_fonetika)

        # ── Generiraj i snimi .ttsfilter ─────────────────────────────────────
        shared_stats["status"] = "TTS: Generisanje fajla..."
        shared_stats["pct"] = 85

        clean_name = engine.clean_book_name or "knjiga"
        output_path = OUTPUT_DIR / f"{clean_name}.ttsfilter"

        sadrzaj = _generiraj_ttsfilter_sadrzaj(fonetika)

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(sadrzaj, encoding="utf-8")
            log(f"✅ TTS filter sačuvan: {output_path}", "success")
        except Exception as e:
            log(f"❌ TTS: Greška pri pisanju fajla: {e}", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        shared_stats["status"] = "ZAVRŠENO (TTS)"
        shared_stats["pct"] = 100
        shared_stats["output_file"] = str(output_path)
        log(f"🔊 .ttsfilter generisan: {output_path.name} ({len(fonetika)} zamjena)", "success")

    except Exception as exc:
        import traceback
        shared_stats["status"] = f"GREŠKA (TTS): {type(exc).__name__}"
        add_audit(f"❌ TTS Greška: {exc}", "error", shared_stats=shared_stats)
        add_audit(traceback.format_exc()[-800:], "tech", shared_stats=shared_stats)

    finally:
        # Čišćenje privremenih fajlova
        try:
            if "engine" in dir():
                shutil.rmtree(engine.work_dir, ignore_errors=True)
        except Exception:
            pass


def _primijeni_checkpointe_na_html(
    html_files: list, checkpoint_dir: Path, log_fn
) -> None:
    """
    Zamjenjuje sadržaj HTML fajlova s finalnim lektoriranim blokovima iz checkpointa.
    Koristi .chk fajlove koji su finalni (bez .prevod/.lektura sufiksa u imenu).
    """
    for hf in html_files:
        file_name = hf.name
        # Pronađi sve finalne blokove za ovaj fajl (ne intermediate .prevod/.lektura)
        blok_fajlovi = sorted(
            [
                f
                for f in checkpoint_dir.glob(f"{file_name}_blok_*.chk")
                if not (f.stem.endswith(".prevod") or f.stem.endswith(".lektura"))
            ],
            key=lambda f: int(m.group(1))
            if (m := re.search(r"_blok_(\d+)", f.stem))
            else 0,
        )

        if not blok_fajlovi:
            continue  # Poglavlje nije obrađeno — koristi original

        try:
            dijelovi = []
            for blok in blok_fajlovi:
                sadrzaj = blok.read_text("utf-8", errors="ignore").strip()
                if sadrzaj and len(sadrzaj) > 5:
                    dijelovi.append(sadrzaj)

            if dijelovi:
                hf.write_text("\n".join(dijelovi), encoding="utf-8")
        except Exception as e:
            log_fn(
                f"⚠️ TTS: Greška pri primjeni checkpointa za {file_name}: {e}",
                "warning",
            )
