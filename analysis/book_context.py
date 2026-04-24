# analysis/book_context.py
import json
from bs4 import BeautifulSoup

class BookContextManager:
    def __init__(self, checkpoint_dir, log_fn):
        self.checkpoint_dir = checkpoint_dir
        self.log = log_fn
        self.book_context = {"zanr":"nepoznat","ton":"neutralan","likovi":{},"glosar":{},"stilski_vodic":""}
    def build_glosar_tekst(self): return ""
    def extract_relevant_glossary(self, chunk, glosar): return ""

    async def analiziraj_knjigu(self, intro_text):
        """Analizira uvodni tekst knjige i gradi book_context."""
        # TODO: implementacija iz originalnog skriptorij.py
        pass

    async def _inkrementalna_analiza_glosara(self, tekst, ime):
        """Inkrementalno ažurira glosar novim terminima iz teksta."""
        pass

    async def _generiraj_chapter_summary(self, ime, tekst):
        """Generira kratki sažetak poglavlja za kontekst lektora."""
        pass

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
            import json
            cached = json.loads(cache_file.read_text("utf-8"))
            self.book_context.update(cached)
            self.knjiga_analizirana = True
            self.glosar_tekst = self._build_glosar_tekst()
            self.log("📂 Analiza učitana iz cache-a", "system")
            return
        except Exception:
            pass
    
    self.shared_stats["status"] = "ANALIZA KNJIGE..."
    self.log("🔬 Analiziram kontekst + stilski vodič...", "system")
    try:
        from bs4 import BeautifulSoup
        clean = BeautifulSoup(intro_text, "html.parser").get_text()[:2500]
        raw, engine = await self._call_ai_engine(clean, 0, uloga="ANALIZA")
        if raw:
            import json, re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            ctx = json.loads(m.group() if m else raw)
            self.book_context.update(ctx)
            self.knjiga_analizirana = True
            self.glosar_tekst = self._build_glosar_tekst()
            self._atomic_write(cache_file, json.dumps(self.book_context, ensure_ascii=False, indent=2))
            self.log(f"✅ Analiza završena ({engine})", "system")
    except Exception as e:
        self.log(f"Analiza pala: {e}. Nastavljam s defaultima.", "warning")

async def _inkrementalna_analiza_glosara(self, poglavlje_tekst, poglavlje_ime):
    """Ažurira glosar svakih N poglavlja."""
    try:
        import json, re
        from bs4 import BeautifulSoup
        postoji_glosar = json.dumps({
            "likovi": list(self.book_context.get("likovi", {}).keys()),
            "glosar": list(self.book_context.get("glosar", {}).keys()),
        }, ensure_ascii=False)
        clean = BeautifulSoup(poglavlje_tekst, "html.parser").get_text()[:2000]
        prompt = f"POSTOJEĆI GLOSAR:\n{postoji_glosar}\n\nNOVI DIO TEKSTA:\n{clean}"
        raw, engine = await self._call_ai_engine(prompt, 0, uloga="GLOSAR_UPDATE")
        if raw:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                obj = json.loads(m.group())
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
                    self.glosar_tekst = self._build_glosar_tekst()
                    import json
                    cache_file = self.checkpoint_dir / "book_analysis.json"
                    self._atomic_write(cache_file, json.dumps(self.book_context, ensure_ascii=False, indent=2))
                    self.log(f"📖 Glosar ažuriran: +{dodano} unosa", "tech")
    except Exception as e:
        self.log(f"⚠️ Glosar update pao: {e}", "warning")
