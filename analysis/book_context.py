"""
analysis/book_context.py
─────────────────────────
Kontekst po knjizi i poglavlju za BooklyFi pipeline.

Funkcionalnosti:
  1. chapter_summary — kratak AI-generiran summary svakog poglavlja
     injektira se u prompt svakog chunka → eliminira gubitak konteksta
  2. Glosar vlastith imena s automatskim dekliniranjem (svi padeži)
     → sprječava rod/padežne greške kroz cijelu knjigu
  3. Persisted state: sprema u analysis/cache/{knjiga_id}_context.json
     → ne računa ponovo pri svakom pokretanju

Korištenje:
    from analysis.book_context import BookContext
    ctx = BookContext(knjiga_id="altered_carbon", api_key=...)
    ctx.dodaj_poglavlje(broj=1, tekst=tekst_poglavlja)
    summary = ctx.summary_poglavlja(1)
    glosar_blok = ctx.glosar_prompt_blok()
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path("analysis/cache")
SUMMARY_PROVIDER = "GEMINI"
SUMMARY_MAX_TOKENS = 200

# ── Deklinacijski predlošci za vlastita imena ──────────────────────────────
_MUSKI_NASTAVCI = [
    ("",    lambda n: [n, n+"a", n+"u", n+"a", n, n+"om", n+"u"]),
    ("o",   lambda n: [n, n[:-1]+"a", n[:-1]+"u", n[:-1]+"a", n, n[:-1]+"om", n[:-1]+"u"]),
    ("e",   lambda n: [n, n+"a", n+"u", n+"a", n, n+"om", n+"u"]),
    ("i",   lambda n: [n, n+"ja", n+"ju", n+"ja", n, n+"jem", n+"ju"]),
]

_ZENSKI_NASTAVCI = [
    ("a",   lambda n: [n, n[:-1]+"e", n[:-1]+"i", n[:-1]+"u", n, n[:-1]+"om", n[:-1]+"i"]),
    ("e",   lambda n: [n, n+"s" if n.endswith("e") else n[:-1]+"e", n, n[:-1]+"u", n, n+"om", n]),
    ("y",   lambda n: [n]*7),
]

PADEZI = ["N", "G", "D", "A", "V", "I", "L"]


def _dekliniraj_ime(ime: str, rod: str = "auto") -> dict[str, str]:
    """
    Automatsko dekliniranje vlastitog imena.
    rod: 'M' = muški, 'Ž' = ženski, 'auto' = heuristika
    Vraća rječnik {padež: oblik}.
    """
    if rod == "auto":
        if ime.endswith("a") and not ime.endswith("ica"):
            rod = "Ž"
        else:
            rod = "M"

    oblici = None

    if rod == "Ž":
        for nastavak, fn in _ZENSKI_NASTAVCI:
            if ime.lower().endswith(nastavak) or nastavak == "":
                try:
                    oblici = fn(ime)
                    break
                except Exception:
                    continue
    
    if oblici is None:
        for nastavak, fn in _MUSKI_NASTAVCI:
            if nastavak == "" or ime.lower().endswith(nastavak):
                try:
                    oblici = fn(ime)
                    break
                except Exception:
                    continue

    if oblici is None:
        oblici = [ime] * 7

    while len(oblici) < 7:
        oblici.append(ime)

    return dict(zip(PADEZI, oblici[:7]))


def _normaliziraj_glosar_entry(ime: str, rod: str = "auto") -> dict:
    """Kreira kompletni glosar entry za jedno vlastito ime."""
    padeži = _dekliniraj_ime(ime, rod)
    return {
        "ime": ime,
        "rod": rod,
        "padeži": padeži,
        "sve_varijante": list(set(padeži.values())),
    }


# ── Data klase ──────────────────────────────────────────────────────────────
@dataclass
class PoglavljeKontekst:
    """Kontekst jednog poglavlja."""
    broj: int
    naslov: str = ""
    summary: str = ""
    lik_count: dict = field(default_factory=dict)
    chunk_ids: list[int] = field(default_factory=list)
    rijeci_count: int = 0


@dataclass
class BookContext:
    """
    Glavni kontekst objekt za jednu knjigu.
    Perzistira u analysis/cache/{knjiga_id}_context.json.
    """
    knjiga_id: str
    naslov_knjige: str = ""
    autor: str = ""
    api_key: Optional[str] = None

    _glosar: dict = field(default_factory=dict)
    _poglavlja: dict = field(default_factory=dict)
    _few_shot_primjeri: list[dict] = field(default_factory=list)
    _cache_path: Optional[Path] = field(default=None, init=False)

    def __post_init__(self):
        if self.api_key is None:
            self.api_key = os.environ.get("GEMINI_API_KEY")
        self._engine = None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache_path = CACHE_DIR / f"{self.knjiga_id}_context.json"
        self._ucitaj_cache()

    # ── Cache ───────────────────────────────────────────────────────────────
    def _ucitaj_cache(self) -> None:
        if self._cache_path and self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                self.naslov_knjige = data.get("naslov_knjige", self.naslov_knjige)
                self.autor = data.get("autor", self.autor)
                self._glosar = data.get("glosar", {})
                self._few_shot_primjeri = data.get("few_shot_primjeri", [])
                for k, v in data.get("poglavlja", {}).items():
                    self._poglavlja[int(k)] = PoglavljeKontekst(**v)
                logger.info(f"[book_context] Cache učitan: {self._cache_path}")
            except Exception as e:
                logger.warning(f"[book_context] Cache učitavanje neuspješno: {e}")

    def _spremi_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            data = {
                "knjiga_id": self.knjiga_id,
                "naslov_knjige": self.naslov_knjige,
                "autor": self.autor,
                "glosar": self._glosar,
                "few_shot_primjeri": self._few_shot_primjeri,
                "poglavlja": {
                    k: {
                        "broj": v.broj,
                        "naslov": v.naslov,
                        "summary": v.summary,
                        "lik_count": v.lik_count,
                        "chunk_ids": v.chunk_ids,
                        "rijeci_count": v.rijeci_count,
                    }
                    for k, v in self._poglavlja.items()
                },
            }
            self._cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[book_context] Cache spremanje neuspješno: {e}")

    # ── Glosar API ──────────────────────────────────────────────────────────
    def dodaj_lik(self, ime: str, rod: str = "auto") -> None:
        """Dodaje vlastito ime u glosar s automatskim deklinacijama."""
        if ime not in self._glosar:
            self._glosar[ime] = _normaliziraj_glosar_entry(ime, rod)
            self._spremi_cache()
            logger.debug(f"[book_context] Glosar: dodan '{ime}'")

    def dodaj_likove_bulk(self, imena: list) -> None:
        """
        Bulk dodavanje likova.
        imena: lista stringova ili (ime, rod) tuplova
        """
        for entry in imena:
            if isinstance(entry, tuple):
                self.dodaj_lik(*entry)
            else:
                self.dodaj_lik(entry)

    def autodetektiraj_likove(self, tekst: str, min_pojavljivanja: int = 3) -> list[str]:
        """
        Heuristička detekcija vlastitih imena iz teksta.
        Traži rijeci s velikim početnim slovom koje se ponavljaju.
        """
        pattern = re.compile(r'(?<![.!?]\s)(?<!\n)\b([A-ZČĆŠĐŽА-Я][a-zčćšđžа-я]{2,})\b')
        kandidati = {}
        for m in pattern.finditer(tekst):
            ime = m.group(1)
            if ime.lower() in {
                "ali", "jer", "dok", "kad", "što", "koji", "koja",
                "koje", "ovaj", "ova", "ovo", "taj", "ta", "to",
                "jedan", "jedna", "jedne", "ovdje", "tamo", "gdje",
            }:
                continue
            kandidati[ime] = kandidati.get(ime, 0) + 1

        pronadeni = [
            ime for ime, count in kandidati.items()
            if count >= min_pojavljivanja
        ]
        logger.info(f"[book_context] Autodetektirano {len(pronadeni)} potencijalnih likova")
        return pronadeni

    def glosar_prompt_blok(self, max_likova: int = 20) -> str:
        """Kreira prompt blok s glosakrom za injektiranje."""
        if not self._glosar:
            return ""

        linije = ["## Glosar likova i deklinacije"]
        linije.append("Koristi ove oblike dosljedno kroz cijeli prijevod:\n")

        za_prikaz = sorted(self._glosar.items())[:max_likova]

        for ime, entry in za_prikaz:
            padeži = entry.get("padeži", {})
            oblici = [
                f"{p}:{o}" for p, o in padeži.items()
                if o != ime
            ]
            if oblici:
                linija = f"- {ime}: " + ", ".join(oblici)
            else:
                linija = f"- {ime}: (nepromjenjivo)"
            linije.append(linija)

        return "\n".join(linije)

    # ── Poglavlje API ───────────────────────────────────────────────────────
    def dodaj_poglavlje(
        self,
        broj: int,
        tekst: str,
        naslov: str = "",
        generiraj_summary: bool = True,
    ) -> PoglavljeKontekst:
        """Registrira poglavlje i opcionalno generira AI summary."""
        poglavlje = PoglavljeKontekst(
            broj=broj,
            naslov=naslov,
            rijeci_count=len(tekst.split()),
        )

        likovi = self.autodetektiraj_likove(tekst)
        for lik in likovi:
            self.dodaj_lik(lik)
            poglavlje.lik_count[lik] = tekst.count(lik)

        if generiraj_summary and self.api_key:
            poglavlje.summary = self._generiraj_summary(tekst, broj, naslov)
        elif generiraj_summary and not self.api_key:
            poglavlje.summary = self._fallback_summary(tekst, poglavlje.lik_count)

        self._poglavlja[broj] = poglavlje
        self._spremi_cache()
        return poglavlje

    def set_engine(self, engine) -> None:
        """
        Povežuje BookContext s engine-om/pipeline-om.
        Engine mora imati atribut 'fleet' (FleetManager).
        Koristi se za dohvaćanje API ključeva kroz fleet management
        umjesto direktnog google.generativeai SDK poziva.
        """
        self._engine = engine
        logger.debug("[book_context] Engine postavljen — koristim fleet za AI pozive")

    def _dohvati_api_key(self) -> Optional[str]:
        """Dohvaća API ključ: iz fleeta ako je engine postavljen, inače direktno."""
        fleet = getattr(self._engine, "fleet", None) if self._engine else None
        if fleet is not None:
            try:
                ks = fleet.get_best_key(SUMMARY_PROVIDER, "CHAPTER_SUMMARY")
                if ks:
                    return ks.key if hasattr(ks, "key") else str(ks)
            except Exception:
                pass
        return self.api_key or os.environ.get("GEMINI_API_KEY")

    def _generiraj_summary(self, tekst: str, broj: int, naslov: str) -> str:
        """
        AI summary poglavlja kroz http_client.api_call.
        Koristi fleet management i quota_tracker — ne zaobilazi nikakav sloj.
        """
        from config.ai_config import GOOGLE_MODEL_POOL
        from network.http_client import api_call

        efektivni_key = self._dohvati_api_key()
        if not efektivni_key:
            return self._fallback_summary(tekst, {})

        model = GOOGLE_MODEL_POOL[0]["model"]
        uzorak = tekst[:3000] if len(tekst) > 3000 else tekst

        sys_prompt = (
            "Ti si asistent koji piše kratke summaryje poglavlja na bosanskom jeziku. "
            "Odgovaraš ISKLJUČIVO kratkim sažetkom (2-3 rečenice, max 150 riječi). "
            "Bez komentara, bez uvoda — samo čisti sadržaj."
        )
        usr_prompt = (
            f"Napiši KRATKI summary (2-3 rečenice, max 150 riječi) poglavlja {broj}"
            f"{f' — {naslov}' if naslov else ''} na bosanskom jeziku.\n"
            f"Fokus: ključni događaji, likovi, atmosfera.\n"
            f"NE komentariši prijevod. SAMO summary sadržaja.\n\n"
            f"Tekst poglavlja (početak):\n{uzorak}"
        )

        try:
            odgovor = api_call(
                provider=SUMMARY_PROVIDER,
                model=model,
                api_key=efektivni_key,
                system=sys_prompt,
                user=usr_prompt,
                temperature=0.3,
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            if odgovor and odgovor.strip():
                return odgovor.strip()
        except Exception as e:
            logger.warning(f"[book_context] Summary generiranje neuspješno: {e}")

        return self._fallback_summary(tekst, {})

    def _fallback_summary(self, tekst: str, lik_count: dict) -> str:
        """Statistički fallback summary bez AI."""
        rijeci = len(tekst.split())
        top_likovi = sorted(lik_count.items(), key=lambda x: -x[1])[:3]
        likovi_str = ", ".join(ime for ime, _ in top_likovi)
        return f"Poglavlje ({rijeci} riječi). Likovi: {likovi_str or 'N/A'}."

    def summary_poglavlja(self, broj: int) -> str:
        """Vraća summary poglavlja ili prazan string."""
        pog = self._poglavlja.get(broj)
        return pog.summary if pog else ""

    def summary_prompt_blok(self, broj_poglavlja: int) -> str:
        """Kreira prompt blok sa summaryjem za injektiranje."""
        summary = self.summary_poglavlja(broj_poglavlja)
        if not summary:
            return ""
        return f"## Kontekst poglavlja\n{summary}"

    # ── Few-shot primjeri API ───────────────────────────────────────────────
    def dodaj_few_shot(
        self,
        originalni: str,
        prevedeni: str,
        komentar: str = "",
        score: float = 0.0,
    ) -> None:
        """Dodaje primjer dobrog prijevoda za few-shot injection."""
        entry = {
            "originalni": originalni[:200],
            "prevedeni": prevedeni[:200],
            "komentar": komentar,
            "score": score,
        }
        # Izbjegni duplikate (isti originalni tekst)
        self._few_shot_primjeri = [
            p for p in self._few_shot_primjeri
            if p["originalni"] != entry["originalni"]
        ]
        self._few_shot_primjeri.append(entry)
        # Čuvaj top-20 po score-u (ne zadnje po redoslijedu)
        self._few_shot_primjeri.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        self._few_shot_primjeri = self._few_shot_primjeri[:20]
        self._spremi_cache()

    def dodaj_few_shot_iz_quality_scores(
        self,
        quality_scores_path: str,
        checkpoint_dir: str,
        min_score: float = 8.5,
        max_primjera: int = 5,
    ) -> int:
        """
        Korak 9 — Dinamički few-shot.
        Čita quality_scores.json, uzima top blokove (score >= min_score),
        učitava njihov .chk sadržaj i dodaje u few_shot_primjeri.
        Vraća broj novih primjera dodanih.
        """
        qs_path = Path(quality_scores_path)
        chk_dir = Path(checkpoint_dir)

        if not qs_path.exists():
            logger.debug("[book_context] few_shot: quality_scores.json ne postoji još")
            return 0

        try:
            quality_scores = json.loads(qs_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[book_context] few_shot: greška pri čitanju quality_scores: {e}")
            return 0

        # Sortiraj po score desc, filtriraj iznad praga
        kandidati = sorted(
            [(stem, score) for stem, score in quality_scores.items()
             if isinstance(score, (int, float)) and score >= min_score],
            key=lambda x: x[1],
            reverse=True,
        )[:max_primjera * 3]  # uzmi više kandidata jer neki .chk mogu nedostajati

        dodano = 0
        for stem_key, score in kandidati:
            if dodano >= max_primjera:
                break

            # stem_key format: "ime_fajla_blok_N"
            chk_file = chk_dir / f"{stem_key}.chk"
            if not chk_file.exists():
                continue

            try:
                prevedeni = chk_file.read_text(encoding="utf-8", errors="ignore").strip()
                if not prevedeni or len(prevedeni) < 30:
                    continue

                # Originalni EN tekst — tražimo u prevod.chk ako postoji
                prevod_chk = chk_dir / f"{stem_key}.prevod.chk"
                if prevod_chk.exists():
                    # prevod.chk čuva sirovi prijevod, ne original — preskačemo EN
                    pass

                # Bez originalnog EN teksta, koristimo samo HR kao stilski primjer
                # Format: samo prevedeni (model uči stil, ne prevođenje)
                self.dodaj_few_shot(
                    originalni=f"[{stem_key}]",  # placeholder za identifikaciju
                    prevedeni=prevedeni[:200],
                    komentar=f"auto:score={score:.1f}",
                    score=score,
                )
                dodano += 1

            except Exception as e:
                logger.debug(f"[book_context] few_shot: greška za {stem_key}: {e}")
                continue

        if dodano:
            logger.info(f"[book_context] Dinamički few-shot: dodano {dodano} primjera (min_score={min_score})")

        return dodano

    def dodaj_few_shot_par(
        self,
        originalni: str,
        prevedeni: str,
        score: float,
        komentar: str = "",
    ) -> None:
        """
        Korak 9 — direktno dodavanje EN→HR para s poznatim score-om.
        Poziva se iz pipeline.py odmah nakon quality scoringa.
        """
        if score < 8.5:
            return
        self.dodaj_few_shot(
            originalni=originalni,
            prevedeni=prevedeni,
            komentar=komentar or f"auto:score={score:.1f}",
            score=score,
        )

    def few_shot_prompt_blok(self, max_primjera: int = 3) -> str:
        """Kreira few-shot prompt blok za injektiranje."""
        if not self._few_shot_primjeri:
            return ""

        # Top primjeri po score-u
        primjeri = self._few_shot_primjeri[:max_primjera]
        linije = ["## Primjeri dobrog prijevoda iz ove knjige"]
        linije.append("(Koristi kao referencu za stil i terminologiju)\n")

        for i, p in enumerate(primjeri, 1):
            score_str = f" [ocjena: {p['score']:.1f}]" if p.get("score", 0) > 0 else ""
            originalni = p["originalni"]
            # Ne prikazuj placeholder identifikatore
            if originalni.startswith("[") and originalni.endswith("]"):
                linije.append(f"Primjer {i}{score_str}:")
                linije.append(f"  BS: {p['prevedeni']}")
            else:
                linije.append(f"Primjer {i}{score_str}:")
                linije.append(f"  EN: {originalni}")
                linije.append(f"  BS: {p['prevedeni']}")
            if p.get("komentar") and not p["komentar"].startswith("auto:"):
                linije.append(f"  // {p['komentar']}")
            linije.append("")

        return "\n".join(linije).strip()

    # ── Kompletni kontekst prompt blok ─────────────────────────────────────
    def kontekst_prompt_blok(self, broj_poglavlja: Optional[int] = None) -> str:
        """Kreira kompletni kontekst blok za injektiranje u chunk prompt."""
        dijelovi = []

        if broj_poglavlja:
            summary_blok = self.summary_prompt_blok(broj_poglavlja)
            if summary_blok:
                dijelovi.append(summary_blok)

        glosar_blok = self.glosar_prompt_blok()
        if glosar_blok:
            dijelovi.append(glosar_blok)

        few_shot = self.few_shot_prompt_blok()
        if few_shot:
            dijelovi.append(few_shot)

        if not dijelovi:
            return ""

        return "\n\n".join(dijelovi)

    
    def get(self, key, default=None):
        """Dictionary-compatible get za backward kompatibilnost."""
        if key == 'glosar' or key == 'glossary':
            return self._glosar
        if key == 'poglavlja' or key == 'chapters':
            return self._poglavlja
        if key == 'few_shot' or key == 'few_shot_primjeri':
            return self._few_shot_primjeri
        if hasattr(self, key):
            return getattr(self, key)
        return default
    
    def __getitem__(self, key):
        """Dictionary-style access."""
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result
    
    def __contains__(self, key):
        """Za 'in' operator."""
        return self.get(key) is not None

    def __repr__(self) -> str:
        return (
            f"BookContext('{self.knjiga_id}', "
            f"likovi={len(self._glosar)}, "
            f"poglavlja={len(self._poglavlja)}, "
            f"few_shot={len(self._few_shot_primjeri)})"
        )


# ── CLI test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== BookContext — lokalni test ===\n")

    ctx = BookContext(knjiga_id="test_knjiga")

    ctx.dodaj_likove_bulk([
        ("Takeshi", "M"),
        ("Ana", "Ž"),
        ("Sarah", "Ž"),
        "Bancroft",
        "Miriam",
    ])

    print("Glosar prompt blok:")
    print(ctx.glosar_prompt_blok())
    print()

    test_tekst = (
        "Takeshi je ušao u sobu. Bancroft ga je gledao hladnim očima. "
        "Sarah je stajala kraj prozora. Takeshi nije znao što reći. "
        "Bancroft se nasmijao. Sarah je okrenula glavu."
    )
    pronadeni = ctx.autodetektiraj_likove(test_tekst, min_pojavljivanja=2)
    print(f"Autodetektirani likovi (min 2 pojavljivanja): {pronadeni}")
    print()

    ctx.dodaj_few_shot(
        "He walked slowly through the empty streets.",
        "Hodao je polako kroz prazne ulice.",
        "Prirodan prijevod, bez kalkova"
    )
    print("Few-shot prompt blok:")
    print(ctx.few_shot_prompt_blok())
    print()

    print(f"Objekt: {ctx}")

# ── BookContextManager — kompatibilnost sa core/engine.py ──────────────────
class BookContextManager:
    """
    Kompatibilni wrapper oko BookContext za core/engine.py.
    """
    def __init__(self, checkpoint_dir, log_func=None):
        import logging
        self.checkpoint_dir = checkpoint_dir
        self.log = log_func or (lambda msg, level="info": logging.info(msg))
        self.book_context = BookContext(knjiga_id=str(checkpoint_dir.name) if checkpoint_dir else "default")
        self._glosar = {}
        self._cache_file = checkpoint_dir / "book_context_cache.json" if checkpoint_dir else None
        self._ucitaj_cache()
    
    def _ucitaj_cache(self):
        if self._cache_file and self._cache_file.exists():
            try:
                import json
                data = json.loads(self._cache_file.read_text("utf-8"))
                self._glosar = data.get("glosar", {})
            except Exception:
                pass
    
    def _spremi_cache(self):
        if self._cache_file:
            try:
                import json
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                self._cache_file.write_text(
                    json.dumps({"glosar": self._glosar}, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
            except Exception:
                pass
    
    def build_glosar_tekst(self):
        """Vraća glosar kao tekst za prompt injection."""
        if not self._glosar:
            return ""
        linije = []
        for ime, varijante in sorted(self._glosar.items()):
            if varijante:
                linije.append(f"{ime}: {', '.join(varijante)}")
            else:
                linije.append(ime)
        return "\n".join(linije)
    
    def extract_relevant_glossary(self, chunk_text, glosar_tekst):
        """Izdvaja relevantne glosar unose za dati chunk — s punim formatom (ime: varijante)."""
        if not self._glosar:
            return ""
        linije = []
        for ime, varijante in self._glosar.items():
            if ime.lower() in chunk_text.lower():
                if varijante:
                    linije.append(f"{ime}: {', '.join(varijante)}")
                else:
                    linije.append(ime)
        return "\n".join(linije) if linije else ""
    
    def dodaj_u_glosar(self, ime, varijante=None):
        """Dodaje vlastito ime u glosar."""
        if ime not in self._glosar:
            self._glosar[ime] = varijante or []
            self._spremi_cache()
    
    def glosar_za_prompt(self, max_likova=20):
        """Vraća glosar za prompt injection (isti kao build_glosar_tekst)."""
        return self.build_glosar_tekst()
    
    def dodaj_kontekst(self, poglavlje, summary):
        """Dodaje chapter summary."""
        if hasattr(self.book_context, '_poglavlja'):
            self.book_context._poglavlja[poglavlje] = type('obj', (object,), {
                'summary': summary,
                'broj': poglavlje
            })()
    
    def kontekst_za_poglavlje(self, poglavlje):
        """Vraća summary za dato poglavlje."""
        if hasattr(self.book_context, '_poglavlja'):
            pog = self.book_context._poglavlja.get(poglavlje)
            return pog.summary if pog else ""
        return ""


# Standalone funkcije koje engine.py importuje
async def analiziraj_knjigu(engine, book_path):
    """Analizira knjigu i popunjava glosar."""
    import logging
    logging.info(f"[book_context] Analiza knjige: {book_path}")
    # Placeholder - glavna analiza se desava u engine.py


async def _inkrementalna_analiza_glosara(engine, poglavlje_tekst, poglavlje_ime):
    """Inkrementalno dodaje likove u glosar."""
    import logging
    import asyncio
    if hasattr(engine, 'context_mgr'):
        if hasattr(engine.context_mgr.book_context, 'autodetektiraj_likove'):
            # Trči u thread poolu
            likovi = await asyncio.to_thread(
                engine.context_mgr.book_context.autodetektiraj_likove,
                poglavlje_tekst, min_pojavljivanja=2
            )
            for lik in likovi:
                engine.context_mgr.dodaj_u_glosar(lik)
    logging.info(f"[book_context] Glosar analiza: {poglavlje_ime}")


async def _generiraj_chapter_summary(engine, file_name, file_content):
    """Generira summary poglavlja."""
    import logging
    import asyncio
    if hasattr(engine, 'context_mgr') and hasattr(engine.context_mgr.book_context, 'dodaj_poglavlje'):
        try:
            # Trči u thread poolu da ne blokira event loop
            await asyncio.to_thread(
                engine.context_mgr.book_context.dodaj_poglavlje,
                broj=hash(file_name) % 10000,
                tekst=file_content[:5000],
                naslov=file_name,
                generiraj_summary=False
            )
        except Exception as e:
            logging.warning(f"[book_context] Summary greška: {e}")
