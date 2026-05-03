# analysis/book_context.py
import json
import re
from bs4 import BeautifulSoup


def _strip_ai_json(text: str) -> str:
    """Strip ```json ... ``` ili ``` ... ``` wrappers iz AI odgovora."""
    if not text:
        return text
    t = text.strip()
    # Ukloni leading ```json ili ```
    t = re.sub(r'^```(?:json)?\s*', '', t, flags=re.IGNORECASE)  # FIX: bio neispravan lazy quantifier \s*?
    # Ukloni trailing ```
    t = re.sub(r'```\s*$', '', t)  # FIX: bio neispravan vodeći ? (r'?```\s*$')
    return t.strip()


def _clean_json_response(raw: str) -> str:
    """Ukloni markdown fence (```json ... ```) pre parsiranja JSON-a."""
    raw = re.sub(r'^```(?:json)?\s*\n?', '', raw, flags=re.DOTALL)
    raw = re.sub(r'\n?```\s*$', '', raw, flags=re.DOTALL)
    return raw.strip()


def _strip_json_markdown(raw: str) -> str:
    """Uklanja ```json i ``` markdown wrappere iz AI odgovora."""
    if not raw:
        return raw
    raw = raw.strip()
    # Ukloni ```json ... ``` ili ``` ... ```
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Ukloni prvu liniju (```json ili ```)
        lines = lines[1:]
        # Ukloni zadnju liniju ako je ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


class BookContextManager:
    def __init__(self, checkpoint_dir, log_fn):
        self.checkpoint_dir = checkpoint_dir
        self.log = log_fn
        self.book_context = {
            "zanr": "nepoznat",
            "ton": "neutralan",
            "likovi": {},
            "glosar": {},
            "stilski_vodic": ""
        }

    async def analiziraj_knjigu(self, intro_text):
        """Delegira na module-level implementaciju."""
        pass  # engine poziva modul-level analiziraj_knjigu(self, ...) direktno

    async def _inkrementalna_analiza_glosara(self, tekst, ime):
        """Delegira na module-level implementaciju."""
        pass  # engine poziva _inkrementalna_analiza_glosara(self, ...) direktno

    async def _generiraj_chapter_summary(self, ime, tekst):
        """Delegira na module-level implementaciju."""
        pass  # engine poziva _generiraj_chapter_summary(self, ...) direktno

    def build_glosar_tekst(self):
        """Gradi string od glosara za injekciju u promptove."""
        glosar = self.book_context.get("glosar", {})
        likovi = self.book_context.get("likovi", {})
        parts = []
        if likovi:
            parts.append("LIKOVI: " + "; ".join(f"{k}: {v}" for k, v in list(likovi.items())[:10]))
        if glosar:
            parts.append("TERMINI: " + "; ".join(f"{k}={v}" for k, v in list(glosar.items())[:15]))
        return "\n".join(parts) if parts else ""

    def extract_relevant_glossary(self, chunk_text, glosar_tekst=""):
        """Vraća relevantne dijelove glosara za dati chunk."""
        if not glosar_tekst:
            glosar_tekst = self.build_glosar_tekst()  # FIX: bio self.context_mgr.build_glosar_tekst() — nepostojeći atribut
        return glosar_tekst[:800] if glosar_tekst else ""


async def _generiraj_chapter_summary(self, file_name, file_content):
    """Generira kratki sažetak poglavlja."""
    try:
        from bs4 import BeautifulSoup
        clean = BeautifulSoup(file_content, "html.parser").get_text()[:3000]
        raw, _ = await self._call_ai_engine(
            f"Napiši sažetak ovog poglavlja:\n{clean}",
            0,
            uloga="CHAPTER_SUMMARY",
        )
        if raw:
            from core.text_utils import _agresivno_cisti
            summary = _agresivno_cisti(raw).strip()
            self._chapter_summaries[file_name] = summary
            self._save_chapter_summaries()
            self.log(f"📝 Chapter summary generiran: {file_name}", "tech")
    except Exception as e:
        self.log(f"⚠️ Chapter summary neuspješan ({file_name}): {e}", "warning")


async def analiziraj_knjigu(self, intro_text):
    """Analizira knjigu i postavlja kontekst."""
    cache_file = self.checkpoint_dir / "book_analysis.json"
    if cache_file.exists():
        try:
            cached = json.loads(_strip_ai_json(cache_file.read_text("utf-8")))
            self.book_context.update(cached)
            self.knjiga_analizirana = True
            self.glosar_tekst = self.context_mgr.build_glosar_tekst()
            self.log("📂 Analiza učitana iz cache-a", "system")
            return
        except Exception:
            pass

    self.shared_stats["status"] = "ANALIZA KNJIGE..."
    self.log("🔬 Analiziram kontekst + stilski vodič...", "system")
    try:
        clean = BeautifulSoup(intro_text, "html.parser").get_text()[:2500]
        raw, engine = await self._call_ai_engine(clean, 0, uloga="ANALIZA")
        if raw:
            raw = _clean_json_response(raw)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                ctx = json.loads(_strip_ai_json(m.group()))
            else:
                ctx = json.loads(_strip_ai_json(_strip_json_markdown(raw)))  # fallback
            self.book_context.update(ctx)
            self.knjiga_analizirana = True
            self.glosar_tekst = self.context_mgr.build_glosar_tekst()
            self._atomic_write(cache_file, json.dumps(self.book_context, ensure_ascii=False, indent=2))
            self.log(f"✅ Analiza završena ({engine})", "system")
    except Exception as e:
        self.log(f"Analiza pala: {e}. Nastavljam s defaultima.", "warning")


async def _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime):
    """Ažurira glosar svakih N poglavlja."""
    try:
        postoji_glosar = json.dumps({
            "likovi": list(self.book_context.get("likovi", {}).keys()),
            "glosar": list(self.book_context.get("glosar", {}).keys()),
        }, ensure_ascii=False)
        clean = BeautifulSoup(poglavlje_tekst, "html.parser").get_text()[:2000]
        # FIX: prompt string bio prekinut ubačenom funkcijom _strip_json_markdown u sredini koda
        prompt = f"POSTOJEĆI GLOSAR:\n{postoji_glosar}\n\nNOVI DIO TEKSTA:\n{clean}"
        raw, engine = await self._call_ai_engine(prompt, 0, uloga="GLOSAR_UPDATE")
        if raw:
            raw = _clean_json_response(raw)
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                obj = json.loads(_strip_ai_json(m.group()))
            else:
                obj = json.loads(_strip_ai_json(_strip_json_markdown(raw)))
            novi_likovi = obj.get("novi_likovi", {})
            novi_termini = obj.get("novi_termini", {})
            dodano = 0
            for k, v in novi_likovi.items():
                if k and k not in self.book_context["likovi"]:
                    self.book_context["likovi"][k] = v
                    dodano += 1
            for k, v in novi_termini.items():
                if k and k not in self.book_context["glosar"]:
                    self.book_context["glosar"][k] = v
                    dodano += 1
            if dodano > 0:
                self.glosar_tekst = self.context_mgr.build_glosar_tekst()
                cache_file = self.checkpoint_dir / "book_analysis.json"
                self._atomic_write(cache_file, json.dumps(self.book_context, ensure_ascii=False, indent=2))
                self.log(f"📖 Glosar ažuriran: +{dodano} unosa", "tech")
    except Exception as e:
        self.log(f"⚠️ Glosar update pao: {e}", "warning")