"""
core/engine.py — SkriptorijAllInOne V12.0

IZMJENE (knjiga_mode patch + checkpoint putanja):
  - __init__(): self.work_dir i self.checkpoint_dir sada koriste
    CHECKPOINT_BASE_DIR/_skr_X umjesto book_path.parent/_skr_X.
    self.out_path ostaje u OUTPUT_DIR.
  - _detect_knjiga_mode() — analizira cijelu knjigu i vraća "PREVOD" / "LEKTURA".
  - _detect_language() zadržan kao interni helper.
"""

import re
import json
from pathlib import Path

from api_fleet import FleetManager
from utils.logging import add_audit
from analysis.book_context import BookContextManager
from config.settings import CHECKPOINT_BASE_DIR, OUTPUT_DIR


class SkriptorijAllInOne:
    GLOSAR_UPDATE_INTERVAL = 5
    BATCH_SIZE = 1

    def __init__(self, book_path, model_name, shared_stats, shared_controls):
        self.book_path = Path(book_path)
        self.model_name = model_name
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls
        try:
            from config.settings import CONFIG_PATH as _cfg
        except ImportError:
            _cfg = "dev_api.json"
        self.fleet = FleetManager(config_path=_cfg)
        try:
            from api_fleet import register_active_fleet
            register_active_fleet(self.fleet)
        except Exception:
            pass

        # ── Provjera i auto-discovery modela pri startu ──────────────────────
        # startup_key_check: validira sve ključeve (401/429 → disable/cooldown)
        #   i cachira modele kao sporedni efekat (GET /v1/models za svaki ključ).
        # prime_cache_sync: popunjava model cache za provajdere koji ga nemaju
        #   (nakon key_check-a većina će već biti cachirana, ovo popunjava ostatak).
        # start_background_refresh: osvježava cache svakih sat vremena.
        try:
            from network.model_discovery import startup_key_check, prime_cache_sync, start_background_refresh
            startup_key_check(self.fleet)
            prime_cache_sync(self.fleet)
            start_background_refresh(self.fleet)
        except Exception:
            pass

        self.clean_book_name = re.sub(r"[^a-zA-Z0-9_\-]", "", self.book_path.stem)

        # ── IZMJENA: work_dir i checkpoint_dir u CHECKPOINT_BASE_DIR ────────
        # Staro: self.book_path.parent / f"_skr_{self.clean_book_name}"
        # Novo:  CHECKPOINT_BASE_DIR  / f"_skr_{self.clean_book_name}"
        self.work_dir       = CHECKPOINT_BASE_DIR / f"_skr_{self.clean_book_name}"
        self.checkpoint_dir = self.work_dir / "checkpoints"

        # out_path ostaje u OUTPUT_DIR (Moon+ Reader biblioteka)
        self.out_path = OUTPUT_DIR / f"PREVEDENO_{self.clean_book_name}.epub"

        self.context_mgr = BookContextManager(self.checkpoint_dir, self.log)
        self.book_context = self.context_mgr.book_context
        # Povežuj book_context s engine-om da koristi fleet za AI summary pozive
        try:
            if self.book_context and hasattr(self.book_context, "set_engine"):
                self.book_context.set_engine(self)
        except Exception:
            pass
        self.knjiga_analizirana = False
        self.glosar_tekst = ""
        try:
            self._auto_generiraj_kanon()
        except Exception:
            pass

        self._chapter_summaries = {}
        self._chapter_order = []
        self._last_live_epub_time = 0.0
        self._chapters_processed = 0

        self.toc_entries, self.chapter_counter = [], 0
        self.global_total_chunks = self.global_done_chunks = 0
        self.stvarno_prevedeno_u_sesiji = self.spaseno_iz_checkpointa = 0
        self.chunk_skips = 0
        self.html_files = []

        self._quality_scores = {}
        self.pipeline_mode = "STANDARD"

        # ── knjiga_mode: "PREVOD" | "LEKTURA" | None ─────────────────────────
        # Postavljeno od _detect_knjiga_mode() u run.py PRIJE main_loop.
        # None znači "nije još određeno" (pipeline čita self.knjiga_mode).
        self.knjiga_mode: str | None = None

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # ── FIX: učitaj quality_scores odmah u shared_stats ──────────────────
        # Bez ovoga, shared_stats["quality_scores"] je {} na startu pa svaki
        # cached blok bez prethodno učitane ocjene prolazi kroz AI scorer
        # (_quality_scoring s "DATABASE") trošeći API kvotu na svakom restartu.
        qs_path = self.checkpoint_dir / "quality_scores.json"
        if qs_path.exists():
            try:
                loaded_qs = json.loads(qs_path.read_text("utf-8"))
                if isinstance(loaded_qs, dict):
                    self.shared_stats.setdefault("quality_scores", {}).update(loaded_qs)
                    self.log(
                        f"📊 Učitani quality scores: {len(loaded_qs)} blokova iz prethodne sesije",
                        "info",
                    )
            except Exception as _e:
                self.log(f"⚠️ Greška pri učitavanju quality_scores.json: {_e}", "warning")
        self.log(
            f"V10.2 Engine inicijaliziran: {self.book_path.name} [STANDARD mod] "
            f"| checkpoint: {self.checkpoint_dir}",
            "tech",
        )

    # =========================================================================
    # LOGGING
    # =========================================================================

    def log(self, msg, ltype="info", en_text=""):
        add_audit(msg, ltype, en_text, self.shared_stats)

    # =========================================================================
    # I/O UTIL
    # =========================================================================

    def _atomic_write(self, path: Path, content: str) -> None:
        """Atomicno pisanje fajla — piše u .tmp pa zamjenjuje originalni."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        try:
            tmp.write_text(content, encoding='utf-8')
            tmp.replace(path)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            path.write_text(content, encoding='utf-8')
            self.log(f"[atomic_write] Fallback pisanje za {path.name}: {e}", "warning")

    # =========================================================================
    # DETEKCIJA JEZIKA — per-chunk (zadržan kao interni helper)
    # =========================================================================

    def _detect_language(self, text: str) -> str:
        """
        Brza per-chunk detekcija jezika za interne/fallback upotrebe.
        Vraća "HR" ili "EN".
        NAPOMENA: Za glavni pipeline koristi self.knjiga_mode (postavljeno jednom
                  za cijelu knjigu), ne ovaj metod.
        """
        from core.text_utils import _detektuj_en_ostatke, _HR_DIACRITICALS
        cist = re.sub(r"<[^>]+>", "", text)
        if any(c in _HR_DIACRITICALS for c in cist):
            return "HR"
        return "EN" if _detektuj_en_ostatke(text) > 0.08 else "HR"

    # =========================================================================
    # DETEKCIJA MODA KNJIGE — jednom za cijelu knjigu
    # =========================================================================

    def _detect_knjiga_mode(self, html_files: list, n_files: int = 5) -> str:
        """
        Analizira prvih N HTML fajlova knjige i određuje globalni mod obrade:

          "LEKTURA" — knjiga je već na bosanskom/hrvatskom (lektoriraj, ne prevodi)
          "PREVOD"  — knjiga je na engleskom (prevedi + lektoriraj)

        Algoritam:
          1. Konkatenira tekst prvih N fajlova (max 5000 znakova po fajlu)
          2. Računa % HR dijakritičkih znakova i EN stop-word postotak
          3. Odluka: ako je ≥60% sadržaja HR → "LEKTURA", inače → "PREVOD"

        Rezultat se sprema u self.knjiga_mode.
        """
        from core.text_utils import _detektuj_en_ostatke, _HR_DIACRITICALS
        from bs4 import BeautifulSoup

        uzorak_fajlova = html_files[:n_files]
        if not uzorak_fajlova:
            self.knjiga_mode = "PREVOD"
            return self.knjiga_mode

        ukupno_znakova = 0
        hr_znakova = 0
        svi_tekstovi = []

        for hf in uzorak_fajlova:
            try:
                sirovi = hf.read_text("utf-8", errors="ignore")
                tekst = BeautifulSoup(sirovi, "html.parser").get_text()[:5000]
                svi_tekstovi.append(tekst)
                ukupno_znakova += len(tekst)
                hr_znakova += sum(1 for c in tekst if c in _HR_DIACRITICALS)
            except Exception:
                continue

        if ukupno_znakova == 0:
            self.knjiga_mode = "PREVOD"
            return self.knjiga_mode

        kombinovano = "\n".join(svi_tekstovi)

        # Kriterij 1: HR dijakritika — jak signal
        hr_dijakritika_ratio = hr_znakova / max(1, ukupno_znakova)

        # Kriterij 2: EN stop-word postotak (iz text_utils)
        en_ratio = _detektuj_en_ostatke(kombinovano)

        # Odluka:
        # - Ako ima ikakve HR dijakritike (>0.3%) → LEKTURA
        # - Ili ako je EN stop-word ratio nizak (<8%) → LEKTURA
        # - Inače → PREVOD
        if hr_dijakritika_ratio > 0.003:
            mode = "LEKTURA"
        elif en_ratio < 0.08:
            mode = "LEKTURA"
        else:
            mode = "PREVOD"

        self.knjiga_mode = mode

        # Informiraj korisnika
        self.log(
            f"🔍 Detekcija knjige: mod=<b>{mode}</b> "
            f"(HR dijakritika={hr_dijakritika_ratio:.2%}, EN ratio={en_ratio:.2%}, "
            f"fajlova analizirano={len(uzorak_fajlova)})",
            "system"
        )
        # Spremi u shared_stats za UI prikaz
        self.shared_stats["knjiga_mode"] = mode
        self.shared_stats["knjiga_mode_info"] = (
            f"{mode} — {len(uzorak_fajlova)} fajl(ov)a analizirano "
            f"(HR={hr_dijakritika_ratio:.1%}, EN={en_ratio:.1%})"
        )

        return mode

    # =========================================================================
    # GLOSAR & KONTEKST
    # =========================================================================

    def _ucitaj_kanon_glosar(self):
        """Ucitaj glosar iz data/kanon/knjige/<knjiga_id>.json.

        Vraća SVE potvrđene termine, uključujući one gdje je hr == en
        (za njih piše: "ostavi kako jest").
        """
        try:
            import json as _json
            from pathlib import Path as _P
            knjiga_id = _P(self.book_path).stem
            kanon_path = _P("/root/skriptorij/data/kanon/knjige") / (knjiga_id + ".json")
            if not kanon_path.exists():
                return ""
            data = _json.loads(kanon_path.read_text(encoding="utf-8"))
            termini = data.get("termini", {})
            linije = []
            for en, info in sorted(termini.items()):
                if not info.get("potvrdjeno"):
                    continue
                hr = info.get("hr", en)
                kat = info.get("kategorija", "?")
                spoji = info.get("spoji_sa", "")
                if hr and hr != en:
                    linija = "- " + en + " -> " + hr
                    if spoji and spoji != en:
                        linija += " (spoji sa: " + spoji + ")"
                    linija += " [" + kat + "]"
                    linije.append(linija)
                else:
                    # hr == en: ime ostaje kako jest, NE prevodi se
                    linija = "- " + en + " (OSTAVI KAKO JEST, ne prevodi) [" + kat + "]"
                    linije.append(linija)
            return "\n".join(linije)
        except Exception:
            return ""

    def _auto_generiraj_kanon(self):
        """Auto-generiraj kanon ako ne postoji."""
        try:
            import json as _json
            import re as _re
            import zipfile as _zip
            import shutil as _sh
            from pathlib import Path as _P
            from collections import Counter as _Counter
            from bs4 import BeautifulSoup as _BS
        except ImportError:
            return False

        knjiga_id = _P(self.book_path).stem
        kanon_path = _P("/root/skriptorij/data/kanon/knjige") / (knjiga_id + ".json")

        if kanon_path.exists():
            return True

        self.log("Kanon ne postoji — generiram automatski...", "system")

        imena = _Counter()
        try:
            with _zip.ZipFile(self.book_path) as z:
                for n in z.namelist():
                    if not n.endswith((".xhtml", ".html", ".htm")):
                        continue
                    try:
                        html = z.read(n).decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    soup = _BS(html, "html.parser")
                    tekst = soup.get_text(" ", strip=True)
                    for m in _re.finditer(r"\b([A-ZČĆŠĐŽ][a-zčćšđž]{2,})\b", tekst):
                        imena[m.group(1)] += 1
        except Exception as e:
            self.log("Ekstrakcija pala: " + str(e), "warning")
            return False

        from core.glosar_ekstrakcija import mehanicka_cistka, posalji_ai_batch, detektuj_jezik
        jezik = detektuj_jezik(self.book_path)
        self.log("Jezik knjige: " + jezik, "system")

        cisto = mehanicka_cistka(imena, min_pojava=3)
        if len(cisto) > 300:
            cisto = dict(sorted(cisto.items(), key=lambda x: x[1], reverse=True)[:300])
        self.log("Kandidata za glosar: " + str(len(cisto)), "tech")

        fleet = getattr(self, "fleet", None)
        if fleet is None:
            try:
                from api_fleet import FleetManager
                from config.settings import CONFIG_PATH
                fleet = FleetManager(config_path=CONFIG_PATH)
            except Exception:
                return False

        # ─── AI obrada s timeoutom i progress logom ───
        import time as _time
        rezultati = {}
        termini = list(cisto.keys())
        ukupno_b = (len(termini) + 9) // 10
        t_start = _time.time()
        TIMEOUT_S = 300.0  # 5 min max za glosar
        neuspjesi_uzastopni = 0

        for i in range(0, len(termini), 10):
            # Timeout
            if _time.time() - t_start > TIMEOUT_S:
                self.log("Glosar timeout (" + str(TIMEOUT_S) + "s) — prekidam, nastavljam bez", "warning")
                break

            # Ako 3 batcha zaredom vrate 0, odustani
            if neuspjesi_uzastopni >= 3:
                self.log("Glosar: 3 neuspjesna batcha — odustajem od AI obrade", "warning")
                break

            batch = termini[i:i+10]
            broj = i // 10 + 1
            self.log("Glosar: batch " + str(broj) + "/" + str(ukupno_b) + " (" + str(len(batch)) + " termina)", "tech")

            try:
                r = posalji_ai_batch(jezik, batch, fleet)
            except Exception as e:
                self.log("Glosar batch greska: " + str(e), "warning")
                r = {}

            if r:
                rezultati.update(r)
                neuspjesi_uzastopni = 0
                self.log("Glosar: batch " + str(broj) + " OK (" + str(len(r)) + " rezultata)", "tech")
            else:
                neuspjesi_uzastopni += 1
                self.log("Glosar: batch " + str(broj) + " prazan (neuspjeh " + str(neuspjesi_uzastopni) + "/3)", "warning")

        self.log("Glosar: " + str(len(rezultati)) + " od " + str(len(termini)) + " termina obrađeno", "system")

        glosar = {"knjiga": knjiga_id, "jezik": jezik, "termini": {}}
        for ime, broj in cisto.items():
            r = rezultati.get(ime, {})
            if r.get("izbaci"):
                continue
            glosar["termini"][ime] = {
                "hr": r.get("hr", ime),
                "kategorija": r.get("kategorija", "?"),
                "odbacene_varijante": [],
                "broj_pojava": broj,
                "spoji_sa": r.get("spoji_sa", ""),
                "potvrdjeno": bool(r.get("kategorija")),
            }

        kanon_path.parent.mkdir(parents=True, exist_ok=True)
        kanon_path.write_text(
            _json.dumps(glosar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log("Kanon sacuvan: " + kanon_path.name + " (" + str(len(glosar["termini"])) + ")", "system")

        try:
            dst = _P("/storage/emulated/0/Books/MoonReader/kanon") / kanon_path.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            _sh.copy2(kanon_path, dst)
        except Exception:
            pass

        return True


    def _build_glosar_tekst(self):
        kanon = self._ucitaj_kanon_glosar()
        if kanon:
            return kanon
        return self.context_mgr.build_glosar_tekst()

    def _extract_relevant_glossary(self, chunk_text):
        return self.context_mgr.extract_relevant_glossary(chunk_text, self.glosar_tekst)

    def _get_chapter_summary_for_lektor(self, current_file_name):
        try:
            idx = self._chapter_order.index(current_file_name)
            if idx > 0:
                prev_name = self._chapter_order[idx - 1]
                summary = self._chapter_summaries.get(prev_name, "")
                if summary:
                    return f"Prethodno poglavlje ({prev_name}): {summary}"
        except (ValueError, IndexError):
            pass
        return "Pocetak knjige ili kontekst nije dostupan."

    def _save_chapter_summaries(self):
        cache = self.checkpoint_dir / "chapter_summaries.json"
        data = {"summaries": self._chapter_summaries, "order": self._chapter_order}
        self._atomic_write(cache, json.dumps(data, ensure_ascii=False, indent=2))

    def _load_chapter_summaries(self):
        cache = self.checkpoint_dir / "chapter_summaries.json"
        if cache.exists():
            try:
                data = json.loads(cache.read_text("utf-8"))
                self._chapter_summaries = data.get("summaries", {})
                self._chapter_order = data.get("order", [])
            except Exception:
                pass

    # =========================================================================
    # PROMPT DELEGACIJA
    # =========================================================================

    def _get_prevodilac_prompt(self, glosar_chunk="", prev_kraj="", tip_bloka="naracija"):
        from core.prompts import get_prevodilac_prompt
        return get_prevodilac_prompt(
            self.book_context,
            glosar_chunk or self.glosar_tekst,
            prev_kraj,
            tip_bloka=tip_bloka,
        )

    def _get_lektor_prompt(self, prev_kraj="", glosar_injekcija="", chapter_summary="",
                           tip_bloka="naracija"):
        from core.prompts import get_lektor_prompt
        return get_lektor_prompt(
            self.book_context,
            prev_kraj,
            glosar_injekcija or self.glosar_tekst,
            chapter_summary,
            tip_bloka=tip_bloka,
        )

    def _get_korektor_prompt(self):
        from core.prompts import KOREKTOR_TEMPLATE
        return KOREKTOR_TEMPLATE

    def _get_guardian_prompt(self):
        from core.prompts import GUARDIAN_SYS
        return GUARDIAN_SYS

    def _get_polish_prompt(self, tip_bloka="naracija"):
        from core.prompts import get_polish_prompt
        return get_polish_prompt(self.book_context, tip_bloka)

    # =========================================================================
    # CHUNKING
    # =========================================================================

    def chunk_html(self, html_content: str, max_words=500) -> list:
        from core.chunking import chunk_html
        return chunk_html(html_content, max_words)

    def get_context_window(self, chunks, idx, file_name):
        from core.chunking import get_context_window
        return get_context_window(self.checkpoint_dir, chunks, idx, file_name)

    # =========================================================================
    # EPUB
    # =========================================================================

    def buildlive_epub(self):
        from epub.packager import buildlive_epub
        buildlive_epub(self)

    def apply_dropcap_and_toc(self, soup, html_file, samo_dropcap=False):
        from epub.packager import apply_dropcap_and_toc
        apply_dropcap_and_toc(self, soup, html_file, samo_dropcap)

    def generate_ncx(self):
        from epub.packager import generate_ncx
        generate_ncx(self)

    def finalize(self):
        from epub.packager import finalize
        finalize(self)

    # =========================================================================
    # NETWORK
    # =========================================================================

    async def _async_http_post(self, *args, **kwargs):
        from network.http_client import _async_http_post
        return await _async_http_post(self, *args, **kwargs)

    async def _call_single_provider(self, *args, **kwargs):
        from network.provider_router import _call_single_provider
        return await _call_single_provider(self, *args, **kwargs)

    async def _call_ai_engine(self, *args, **kwargs):
        from network.provider_router import _call_ai_engine
        return await _call_ai_engine(self, *args, **kwargs)

    # =========================================================================
    # PIPELINE
    # =========================================================================

    async def process_chunk_with_ai(self, *args, **kwargs):
        from processing.pipeline import process_chunk_with_ai
        return await process_chunk_with_ai(self, *args, **kwargs)

    async def process_single_file_worker(self, *args, **kwargs):
        from processing.workers import process_single_file_worker
        return await process_single_file_worker(self, *args, **kwargs)

    # =========================================================================
    # ANALIZA KNJIGE
    # =========================================================================

    async def analiziraj_knjigu(self, intro_text):
        from analysis.book_context import analiziraj_knjigu
        await analiziraj_knjigu(self, intro_text)

    async def _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime):
        from analysis.book_context import _inkrementalna_analiza_glosara
        try:
            await _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime)
        except Exception as e:
            import logging
            logging.warning(f"Glosar analiza preskočena: {e}")

    async def _generiraj_chapter_summary(self, file_name, file_content):
        from analysis.book_context import _generiraj_chapter_summary
        try:
            await _generiraj_chapter_summary(self, file_name, file_content)
        except Exception as e:
            import logging
            logging.warning(f"Chapter summary preskočen: {e}")

    # =========================================================================
    # RETRO RE-LEKTURA
    # =========================================================================


    # =========================================================================
    # CACHE MANAGEMENT — PATCH v1.0
    # =========================================================================

    def obrisi_cache(self, samo_losi: bool = False, threshold: float = None) -> int:
        """
        Briše .chk fajlove iz checkpoint_dir.

        samo_losi=False → briše sve .chk fajlove (potpuni reset)
        samo_losi=True  → briše samo fajlove čiji je score ispod threshold-a
        """
        from core.quality import _QUALITY_RESCUE_THRESHOLD
        threshold = threshold or _QUALITY_RESCUE_THRESHOLD
        chk_fajlovi = list(self.checkpoint_dir.glob("*.chk"))

        if not chk_fajlovi:
            self.log("ℹ️ Cache je prazan — nema .chk fajlova.", "info")
            return 0

        obrisano = 0

        if samo_losi:
            qs_cache = self.checkpoint_dir / "quality_scores.json"
            scores = {}
            if qs_cache.exists():
                try:
                    scores = json.loads(qs_cache.read_text("utf-8"))
                except Exception:
                    pass

            for chk in chk_fajlovi:
                score = scores.get(chk.stem, None)
                if score is not None and score < threshold:
                    try:
                        chk.unlink()
                        obrisano += 1
                    except Exception:
                        pass

            self.log(
                f"🧹 Obrisano {obrisano}/{len(chk_fajlovi)} loših .chk fajlova "
                f"(score < {threshold}).",
                "system",
            )
        else:
            for chk in chk_fajlovi:
                try:
                    chk.unlink()
                    obrisano += 1
                except Exception:
                    pass
            self.log(
                f"🗑️ Kompletan cache obrisan: {obrisano} .chk fajlova.", "system"
            )

        return obrisano

    def obrisi_cache_fajla(self, file_name: str) -> int:
        """Briše sve .chk fajlove koji pripadaju jednom HTML fajlu (poglavlju)."""
        pattern = f"{file_name}_blok_*.chk"
        chk_fajlovi = list(self.checkpoint_dir.glob(pattern))
        for chk in chk_fajlovi:
            try:
                chk.unlink()
            except Exception:
                pass
        self.log(
            f"🗑️ Cache fajla '{file_name}': {len(chk_fajlovi)} blokova obrisano.",
            "system",
        )
        return len(chk_fajlovi)

    def postavi_force_reprocess(self, aktivan: bool = True):
        """Postavi flag da pipeline ignorira cache za sve sljedeće blokove."""
        self._force_reprocess = aktivan
        if aktivan:
            self.log("⚡ force_reprocess=True — cache se ignorira za sve blokove.", "system")
        else:
            self.log("💾 force_reprocess=False — cache se koristi normalno.", "system")

    # ── RETRO / REVIZIJA delegacija ───────────────────────────────────────────

    async def send_to_fix(self, score_threshold: float = None):
        from processing.retro import send_to_fix
        return await send_to_fix(self, score_threshold or 6.5)

    async def retroaktivna_relektura_v10(self, *args, **kwargs):
        from processing.retro import retroaktivna_relektura_v10
        await retroaktivna_relektura_v10(self, *args, **kwargs)

    def retroaktivna_rod_korekcija(
        self, samo_loše: bool = False, bad_threshold: float = 6.5
    ) -> dict:
        """
        Deterministička retroaktivna korekcija miješanja roda nad .chk fajlovima.
        Ne troši AI — brza, pokretljiva u bilo kom trenutku.

        Args:
            samo_loše:     Obradi samo blokove s quality scoreom < bad_threshold.
            bad_threshold: Threshold za 'loš' blok (default: 6.5).

        Returns:
            dict s statistikom: obradjeno, korigovano, korekcija_ukupno, po_fajlu
        """
        from processing.retro import retroaktivna_rod_korekcija
        return retroaktivna_rod_korekcija(
            self, samo_loše=samo_loše, bad_threshold=bad_threshold
        )