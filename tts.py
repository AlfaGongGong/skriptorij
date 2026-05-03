"""
tts.py — TTS filter mod za Moon+ Reader

BUGFIX:
  B15: engine.run() ne postoji — TTS sad prolazi kroz workers direktno.
  B16: tts_mode flag postavljen ali nikad čitan — sada pipeline prima info
       kroz shared_stats["tts_mode"] i workers generišu čisti tekst.
  B17: Nije generisan .ttsfilter fajl — sada se eksplicitno generira.
  B18: shared_stats["live_audit"] se postavljao kao string direktno,
       zaobilazeći add_audit HTML sistem — sada koristi add_audit.

TTS FILTER FORMAT (Moon+ Reader):
  Fajl s ekstenzijom .ttsfilter sadrži čisti tekst knjige bez HTML-a,
  jedan paragraf po retku, bez tipografskih znakova koji zbunjuju TTS:
    - Em-crtice (—) → zarez i razmak
    - Elipsis (…)   → tačka
    - Navodnici („") → ništa (TTS ih ne izgovara dobro)
"""

from pathlib import Path
import asyncio
import zipfile
import shutil
import re
from bs4 import BeautifulSoup
from utils.logging import add_audit
from config.settings import OUTPUT_DIR, CHECKPOINT_BASE_DIR


def _html_to_tts_tekst(html: str) -> str:
    """
    Konvertuje HTML u TTS-friendly plain text.
    Primjenjuje TTS-specifična čišćenja koja su drugačija od standardnog čišćenja.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        tekst = soup.get_text(separator="\n")
    except Exception:
        tekst = re.sub(r"<[^>]+>", " ", html)

    # TTS zamjene
    tekst = tekst.replace("—", ", ")  # Em-crtica → kratka pauza
    tekst = tekst.replace("–", ", ")  # En-crtica
    tekst = tekst.replace("…", ".")  # Elipsis → tačka (TTS pauza)
    tekst = tekst.replace("„", "")  # Otvoreni navodnik
    tekst = tekst.replace("'", "")  #

    # Čisti višestruke prazne redove → jedan
    tekst = re.sub(r"\n{3,}", "\n\n", tekst)
    # Čisti višestruke razmake
    tekst = re.sub(r" {2,}", " ", tekst)

    return tekst.strip()


def _generiraj_ttsfilter(html_files: list, output_path: Path, log_fn) -> bool:
    """
    B17 FIX: Generira .ttsfilter fajl iz liste HTML fajlova.
    Vraća True ako uspješno, False ako greška.
    """
    dijelovi = []
    for hf in html_files:
        try:
            html = Path(hf).read_text("utf-8", errors="ignore")
            tts_tekst = _html_to_tts_tekst(html)
            if tts_tekst:
                dijelovi.append(tts_tekst)
        except Exception as e:
            log_fn(f"⚠️ TTS: Greška pri čitanju {hf}: {e}", "warning")

    if not dijelovi:
        log_fn("❌ TTS: Nema teksta za generisanje.", "error")
        return False

    kompletan_tekst = "\n\n".join(dijelovi)

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(kompletan_tekst, encoding="utf-8")
        log_fn(f"✅ TTS fajl generisan: {output_path}", "success")
        return True
    except Exception as e:
        log_fn(f"❌ TTS: Greška pri pisanju fajla: {e}", "error")
        return False


def start_from_master(
    book_path: str, model: str, shared_stats: dict, shared_controls: dict
):
    """
    B15 FIX: Ne poziva engine.run() — TTS ima vlastiti tok.
    B16 FIX: TTS mod se komunicira kroz shared_stats["tts_mode"].
    B18 FIX: Koristi add_audit umjesto direktnog string postavljanja.
    """

    # B18 FIX: koristi add_audit, ne direktno postavljanje stringa
    def log(msg: str, tip: str = "info"):
        add_audit(msg, tip, shared_stats=shared_stats)

    shared_stats["status"] = "TTS OBRADA..."
    shared_stats["tts_mode"] = True  # B16 FIX: flag za pipeline
    log("🔊 TTS filter mod pokrenut...", "system")

    try:
        from core.engine import SkriptorijAllInOne

        engine = SkriptorijAllInOne(book_path, model, shared_stats, shared_controls)
        book_path_obj = Path(book_path)

        # Raspakuj epub u work_dir (isto kao run.py)
        engine.work_dir.mkdir(parents=True, exist_ok=True)
        engine.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        if not book_path_obj.exists():
            log(f"❌ Knjiga nije pronađena: {book_path}", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        log(f"📖 Raspakovavam: {book_path_obj.name}", "tech")
        try:
            with zipfile.ZipFile(book_path_obj, "r") as z:
                z.extractall(engine.work_dir)
        except Exception as e:
            log(f"❌ Nije moguće raspakovanje EPUB-a: {e}", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        # Pronađi HTML fajlove
        html_files = sorted(
            [
                f
                for f in engine.work_dir.rglob("*")
                if f.suffix.lower() in [".html", ".htm", ".xhtml"]
            ],
            key=lambda x: x.name,
        )

        if not html_files:
            log("❌ TTS: Nema HTML fajlova u EPUB-u.", "error")
            shared_stats["status"] = "GREŠKA (TTS)"
            return

        log(f"📄 Pronađeno {len(html_files)} poglavlja za TTS obradu.", "system")

        # Provjeri postoje li već prevedeni/lektorirani checkpointi
        chk_files = list(engine.checkpoint_dir.glob("*.chk"))
        log(f"💾 Pronađeno {len(chk_files)} checkpoint blokova.", "tech")

        # Ako postoje checkpointi, zamijeni HTML sadržaj s lektoriranim verzijama
        if chk_files:
            log("♻️ Učitavam lektorirani sadržaj iz checkpointa...", "system")
            _primijeni_checkpointe_na_html(html_files, engine.checkpoint_dir, log)

        # B17 FIX: Generiraj .ttsfilter fajl
        clean_name = engine.clean_book_name or "knjiga"
        output_path = OUTPUT_DIR / f"{clean_name}.ttsfilter"

        shared_stats["status"] = "GENERISANJE TTS FAJLA..."
        shared_stats["pct"] = 50

        uspjeh = _generiraj_ttsfilter(html_files, output_path, log)

        if uspjeh:
            shared_stats["status"] = "ZAVRŠENO (TTS)"
            shared_stats["pct"] = 100
            shared_stats["output_file"] = str(output_path)
            log(f"✅ TTS filter generisan: {output_path.name}", "success")
        else:
            shared_stats["status"] = "GREŠKA (TTS)"

        # Čišćenje work_dir
        try:
            shutil.rmtree(engine.work_dir, ignore_errors=True)
        except Exception:
            pass

    except Exception as exc:
        import traceback

        shared_stats["status"] = f"GREŠKA (TTS): {type(exc).__name__}"
        add_audit(f"❌ TTS Greška: {exc}", "error", shared_stats=shared_stats)
        add_audit(traceback.format_exc()[-500:], "tech", shared_stats=shared_stats)


def _primijeni_checkpointe_na_html(
    html_files: list, checkpoint_dir: Path, log_fn
) -> None:
    """
    Zamjenjuje sadržaj HTML fajlova s lektoriranim blokovima iz checkpointa.
    Koristi se u TTS modu da se generira TTS od finalnog lektoriranog teksta.
    """
    from utils.checkpoint_cleaner import _ocisti_json_wrapper

    for hf in html_files:
        file_name = hf.name
        # Pronađi sve blokove koji pripadaju ovom fajlu
        blok_fajlovi = sorted(
            [
                f
                for f in checkpoint_dir.glob(f"{file_name}_blok_*.chk")
                if not (f.stem.endswith(".prevod") or f.stem.endswith(".lektura"))
            ],
            key=lambda f: int(re.search(r"_blok_(\d+)", f.stem).group(1))
            if re.search(r"_blok_(\d+)", f.stem)
            else 0,
        )

        if not blok_fajlovi:
            continue  # Ovaj fajl nije obrađen — koristi original

        try:
            dijelovi = []
            for blok in blok_fajlovi:
                sadrzaj = blok.read_text("utf-8", errors="ignore")
                sadrzaj = _ocisti_json_wrapper(sadrzaj)
                if sadrzaj and len(sadrzaj.strip()) > 5:
                    dijelovi.append(sadrzaj)

            if dijelovi:
                hf.write_text("\n".join(dijelovi), encoding="utf-8")
        except Exception as e:
            log_fn(
                f"⚠️ TTS: Greška pri primjeni checkpointa za {file_name}: {e}", "warning"
            )
