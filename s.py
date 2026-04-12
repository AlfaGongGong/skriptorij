import os
import re
import shutil
import zipfile
import time
import json
import asyncio
import random
import requests
import urllib3
import warnings
from datetime import timedelta, datetime
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, XMLParsedAsHTMLWarning

# Magični dekoder za MOBI fajlove
try:
    import mobi

    HAS_MOBI = True
except ImportError:
    HAS_MOBI = False

try:
    import tiktoken

    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

# ============================================================================
# SISTEMSKA KONFIGURACIJA I UTIŠAVANJE
# ============================================================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from api_fleet import FleetManager

# ============================================================================
# KONFIGURACIJA - PROXY LISTA
# Proxy konfiguracija se učitava iz proxies.json (nije u verzioniranju).
# Format: lista stringova "ip:port:korisnik:lozinka"
# Primjer: kopirajte proxies.json.example u proxies.json i unesite vaše podatke.
# ============================================================================
def _load_proxies():
    proxy_file = Path(__file__).parent / "proxies.json"
    try:
        with open(proxy_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(p) for p in data if p]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


RAW_PROXIES = _load_proxies()


def get_random_proxy():
    if not RAW_PROXIES:
        return None
    p = random.choice(RAW_PROXIES).strip()
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pw = (
            parts[0].strip(),
            parts[1].strip(),
            parts[2].strip(),
            parts[3].strip(),
        )
        proxy_url = f"http://{user}:{pw}@{ip}:{port}"
        return {"http": proxy_url, "https": proxy_url}
    return None


# ============================================================================
# URL GENERATORI
# ============================================================================
def _url_gemini_base(url_mod, key):
    return (
        "https://"
        + "generativelanguage"
        + ".googleapis"
        + ".c"
        + "om/v1beta/"
        + url_mod
        + ":generateContent?key="
        + key.strip()
    )


def _url_groq():
    return "https://" + "api" + ".groq" + ".c" + "om/openai/v1/chat/completions"


def _url_samba():
    return "https://" + "api" + ".sambanova" + ".a" + "i/v1/chat/completions"


def _url_cerebras():
    return "https://" + "api" + ".cerebras" + ".a" + "i/v1/chat/completions"


def _url_mistral():
    return "https://" + "api" + ".mistral" + ".a" + "i/v1/chat/completions"


def _url_cohere():
    return "https://" + "api" + ".cohere" + ".c" + "om/v2/chat"


def _url_w3():
    return "http://" + "www" + ".w3" + ".or" + "g/1999/xhtml"


def _url_daisy():
    return "http://" + "www" + ".daisy" + ".or" + "g/z3986/2005/ncx/"


# ============================================================================
# GLOBALS & MREŽNE POSTAVKE
# ============================================================================
_GLOBAL_DOOR = None
_LAST_CALLS = {
    "GEMINI": 0.0,
    "GROQ": 0.0,
    "SAMBANOVA": 0.0,
    "CEREBRAS": 0.0,
    "MISTRAL": 0.0,
    "COHERE": 0.0,
}
MIN_GAP = 12.0


async def _ensure_global_lock():
    """Lazy initialization of asyncio Lock in the current event loop."""
    global _GLOBAL_DOOR
    if _GLOBAL_DOOR is None:
        _GLOBAL_DOOR = asyncio.Lock()
    return _GLOBAL_DOOR


BASE_PATH = Path("/storage/emulated/0/termux/Termux_ai_lektor")
PROJECTS_ROOT = BASE_PATH / "format_projects"

audit_logs = []


def add_audit(msg, type="info", en_text="", shared_stats=None):
    global audit_logs
    ts = datetime.now().strftime("%H:%M:%S")

    if type == "system":
        log_entry = f"<div class='global-only' style='border-left:4px solid #c026d3; background:#2e0b36; padding:12px; margin-bottom:10px; color:#f0abfc; border-radius:4px;'><div style='font-weight:bold; font-size:1.1em;'>[{ts}] {msg}</div>{en_text}</div>"
    elif type == "tech":
        log_entry = f"<div class='tech-log' style='border-left:3px solid #cbd5e1; background:#1e293b; padding:8px; margin-bottom:5px; color:#94a3b8; font-size:0.85em; border-radius:4px;'><b>[{ts}] MREŽA:</b> {msg}</div>"
    elif type == "warning":
        log_entry = f"<div style='color:#fa0; background:#310; padding:8px; margin-bottom:5px; border-left:3px solid #fa0;'><b>[{ts}] PAUZA / INFO:</b> {msg}</div>"
    elif type == "error":
        log_entry = f"<div style='color:#f44; background:#300; padding:10px; margin-bottom:5px; border-left:4px solid #f44;'><b style='text-transform:uppercase;'>[{ts}] KRITIČNA GREŠKA:</b><br><span style='font-family:monospace; font-size:0.9em; white-space:pre-wrap;'>{msg}</span></div>"
    elif type == "accordion":
        log_entry = f"<div class='accordion-log'>{en_text}</div>"
    else:
        log_entry = f"<div class='global-only' style='color:#94a3b8; padding:5px 0; border-bottom:1px solid #334155; font-size:0.9em;'>[{ts}] {msg}</div>"

    audit_logs.append(log_entry)
    if shared_stats is not None:
        shared_stats["live_audit"] = "".join(audit_logs[-180:])


# ============================================================================
# AI FORMATER I STILISTA (ZVIJER ZA PREPAKOVANJE)
# ============================================================================
class FormaterAllInOne:
    def __init__(self, book_path_str, model_name, shared_stats, shared_controls):
        self.book_path = Path(book_path_str).resolve()
        self.model_name = model_name
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls
        self.fleet = FleetManager()

        self.semafor = asyncio.Semaphore(1)
        self.spaseno_iz_checkpointa = 0

        target_upper = ""
        if "GROQ" in self.model_name.upper():
            target_upper = "GROQ"
        elif "SAMBA" in self.model_name.upper():
            target_upper = "SAMBANOVA"
        elif "CEREBRAS" in self.model_name.upper():
            target_upper = "CEREBRAS"
        elif "MISTRAL" in self.model_name.upper():
            target_upper = "MISTRAL"
        elif "COHERE" in self.model_name.upper():
            target_upper = "COHERE"
        elif "V8" in self.model_name.upper() or "V6" in self.model_name.upper():
            target_upper = "V6_TURBO"
        else:
            target_upper = "GEMINI"

        self.provider = target_upper
        if self.provider != "V6_TURBO":
            for p in self.fleet.fleet.keys():
                if p.upper() == target_upper:
                    self.provider = p
                    break

        raw_name = self.book_path.name.replace(".epub", "").replace(".mobi", "")
        self.clean_book_name = re.sub(
            r"^\(HR-L-S\)_|^\(HR-L\)_|^\(HR\)_|^\(TITAN\)_|^\(FORMATIRANO\)_",
            "",
            raw_name,
        )

        display_engine = (
            "V6 FORMATER" if self.provider == "V6_TURBO" else self.model_name
        )
        self.shared_stats["book"] = self.clean_book_name
        self.shared_stats["active_engine"] = f"FORMATER ({display_engine})"
        self.shared_stats["keys_status"] = "Inicijalizacija flote..."
        self.shared_stats["context_loaded"] = "Ne (Samo formatiranje)"

        p_dir = PROJECTS_ROOT / f"FORMATER_{re.sub(r'\W+', '_', self.book_path.stem)}"
        self.work_dir = p_dir / "work"
        self.checkpoint_dir = self.work_dir / "checkpoints"
        self.out_path = (
            self.book_path.parent / f"(FORMATIRANO)_{self.clean_book_name}.epub"
        )
        self.checkpoint_file = self.work_dir / "formater_progress.json"

        self.processed_files = []
        self.file_progress = {}
        self.toc_entries = []
        self.stats = {"dropcaps": 0, "chapters_in_toc": 0}
        self.chapter_counter = 0
        self.chunk_skips = 0

        self.ukupno_blokova = 0
        self.zavrseno_blokova = 0
        self.total_files = 0
        self.files_done = 0
        self.stvarno_prevedeno_u_sesiji = 0
        self.start_time = 0.0

        self.parser_type = (
            "lxml"
            if "lxml" in BeautifulSoup("", "lxml").builder.NAME
            else "html.parser"
        )

        if (
            not self.shared_controls.get("reset")
            and p_dir.exists()
            and self.checkpoint_file.exists()
        ):
            try:
                with open(self.checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.processed_files = data.get("processed", [])
                    self.file_progress = data.get("file_progress", {})
                    self.toc_entries = data.get("toc", [])
                    self.chapter_counter = data.get("chapter_counter", 0)
                self.log(
                    f"Checkpoint učitan! Nastavljam od {len(self.processed_files)}. fajla.",
                    "tech",
                )
            except:
                self.log("Checkpoint oštećen, počinjem ispočetka.", "warning")
        else:
            if p_dir.exists():
                shutil.rmtree(p_dir)
            p_dir.mkdir(parents=True, exist_ok=True)
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            self.save_checkpoint()

    def log(self, msg, type="system", en_text=""):
        add_audit(msg, type, en_text, shared_stats=self.shared_stats)

    def _atomic_write(self, putanja, sadrzaj):
        putanja_obj = Path(putanja)
        putanja_obj.parent.mkdir(parents=True, exist_ok=True)
        tmp = putanja_obj.with_suffix(f".tmp_{random.randint(10000, 99999)}")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(sadrzaj)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, putanja_obj)
        except Exception as e:
            safe_e = str(e).replace("<", "&lt;").replace(">", "&gt;")
            self.log(f"Greška pri upisu fajla {putanja_obj.name}: {safe_e}", "error")
            if tmp.exists():
                try:
                    tmp.unlink()
                except:
                    pass

    def save_checkpoint(self):
        try:
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "processed": self.processed_files,
                        "file_progress": self.file_progress,
                        "toc": self.toc_entries,
                        "chapter_counter": self.chapter_counter,
                    },
                    f,
                )
        except:
            pass

    def update_keys_status(self, provider, key=None):
        if not key:
            return
        if provider in self.fleet.fleet and key in self.fleet.fleet[provider]:
            mask = f"...{key[-6:]}"
            self.shared_stats["active_engine"] = f"{provider} ({mask})"

    def _clean_ai_response(self, text, filename, chunk_idx):
        triple_tick = "`" * 3
        text = re.sub(
            r"^" + triple_tick + r"(?:html|json|text)?\s*",
            "",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        text = re.sub(triple_tick + r"\s*$", "", text, flags=re.MULTILINE)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "html" in parsed:
                text = parsed["html"]
        except:
            pass

        text = text.strip()
        if "<p" not in text and "<h" not in text:
            paras = [f"<p>{p.strip()}</p>" for p in text.split("\n\n") if p.strip()]
            text = "\n".join(paras)
        return text

    def _get_raw_text_chunks(self, html_path):
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), self.parser_type)
            for tag in soup(["script", "style", "head", "title", "meta", "link"]):
                tag.decompose()

            raw_text = soup.get_text(separator="\n\n", strip=True)
            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

            chunks, current_chunk, current_token_count = [], [], 0
            max_tokens = 950 if HAS_TIKTOKEN else 750
            if HAS_TIKTOKEN:
                encoder = tiktoken.get_encoding("cl100k_base")

            for p in paragraphs:
                cost = len(encoder.encode(p)) if HAS_TIKTOKEN else len(p.split())
                if current_token_count + cost > max_tokens and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk, current_token_count = [p], cost
                else:
                    current_chunk.append(p)
                    current_token_count += cost
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
            return chunks
        except Exception as e:
            self.log(f"Greška u čitanju fajla: {e}", "error")
            return []

    def _naivni_chunker(self, tekst, max_duzina=2800):
        blokovi, trenutni = [], ""
        for dio in re.split(r"(</p>|</div>)", tekst, flags=re.IGNORECASE):
            trenutni += dio
            if len(trenutni) > max_duzina and dio.lower() in ["</p>", "</div>"]:
                blokovi.append(trenutni)
                trenutni = ""
        if trenutni.strip():
            blokovi.append(trenutni)
        return blokovi

    async def _async_http_post(
        self, url, headers, payload, prov_exact, prov_upper, key
    ):
        if not url:
            return None
        timeout_tuple = (15.0, 120.0)

        if prov_upper not in ["COHERE", "MISTRAL", "CEREBRAS"]:
            proxy_dict = get_random_proxy()
            if proxy_dict:
                try:
                    resp = await asyncio.to_thread(
                        requests.post,
                        url,
                        headers=headers,
                        json=payload,
                        proxies=proxy_dict,
                        timeout=timeout_tuple,
                        verify=False,
                    )
                    self.fleet.analyze_response(
                        prov_exact, key, resp.status_code, resp.headers
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code == 429:
                        self.log(
                            f"[{prov_upper}] 429 Limit. ⬇️ Čekam (<span class='cd-timer text-amber-500 font-bold'>10</span> sec) ⏳",
                            "warning",
                        )
                        return None
                except Exception:
                    pass

        try:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=payload,
                timeout=timeout_tuple,
                verify=False,
            )
            self.fleet.analyze_response(prov_exact, key, resp.status_code, resp.headers)

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                self.log(
                    f"[{prov_upper}] 429 Limit. ⬇️ Čekam (<span class='cd-timer text-amber-500 font-bold'>25</span> sec) ⏳",
                    "warning",
                )
                return None
            if resp.status_code in [401, 403]:
                return None

            safe_err = resp.text[:250].replace("<", "&lt;").replace(">", "&gt;")
            self.log(
                f"[{prov_upper}] ODBIO UPIT (HTTP {resp.status_code}): {safe_err}",
                "error",
            )
            return None
        except Exception as e:
            return None

    async def _call_ai_engine(self, prompt, chunk_idx, filename=""):
        providers = (
            [
                p
                for p in self.fleet.fleet.keys()
                if p.upper()
                in ["CEREBRAS", "MISTRAL", "COHERE", "GROQ", "SAMBANOVA", "GEMINI"]
            ]
            if self.provider == "V6_TURBO"
            else [self.provider]
        )
        random.shuffle(providers)

        patience = 0
        while patience < 999:
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return None, "N/A"

            for prov in providers:
                prov_upper = prov.upper()
                for _ in range(2):
                    key = self.fleet.get_best_key(prov)
                    if not key:
                        break
                    self.update_keys_status(prov, key)

                    # PROMPT SPECIFIČAN ZA FORMATIRANJE
                    sys_content = "You are a master typographer and eBook formatter. Your ONLY job is to format text properly. NO translation. Output clean HTML."
                    headers = {"Content-Type": "application/json"}
                    payload = {}

                    try:
                        if prov_upper == "GEMINI":
                            api_model = "gemini-flash-latest"
                            url = _url_gemini_base(
                                (
                                    api_model
                                    if api_model.startswith("models/")
                                    else f"models/{api_model}"
                                ),
                                key,
                            )
                            payload = {
                                "systemInstruction": {"parts": [{"text": sys_content}]},
                                "contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"temperature": 0.15},
                            }
                        elif prov_upper == "COHERE":
                            url = _url_cohere()
                            headers["Authorization"] = f"Bearer {key.strip()}"
                            headers["Accept"] = "application/json"
                            payload = {
                                "model": "command-a-03-2025",
                                "messages": [
                                    {"role": "system", "content": sys_content},
                                    {"role": "user", "content": prompt},
                                ],
                                "temperature": 0.15,
                            }
                        else:
                            api_model = (
                                "llama3.1-8b"
                                if prov_upper == "CEREBRAS"
                                else (
                                    "mistral-large-latest"
                                    if prov_upper == "MISTRAL"
                                    else "llama-3.3-70b-versatile"
                                )
                            )
                            url = (
                                _url_cerebras()
                                if prov_upper == "CEREBRAS"
                                else (
                                    _url_mistral()
                                    if prov_upper == "MISTRAL"
                                    else _url_groq()
                                )
                            )
                            headers["Authorization"] = f"Bearer {key.strip()}"
                            payload = {
                                "model": api_model,
                                "messages": [
                                    {"role": "system", "content": sys_content},
                                    {"role": "user", "content": prompt},
                                ],
                                "temperature": 0.15,
                            }
                            if prov_upper == "CEREBRAS":
                                payload["max_completion_tokens"] = 2500

                        lock = await _ensure_global_lock()
                        async with lock:
                            razmak = time.time() - _LAST_CALLS.get(prov_upper, 0)
                            if razmak < MIN_GAP:
                                await asyncio.sleep(MIN_GAP - razmak)
                            _LAST_CALLS[prov_upper] = time.time()

                        data = await self._async_http_post(
                            url, headers, payload, prov, prov_upper, key
                        )

                        if data:
                            if prov_upper == "GEMINI":
                                if not data.get("candidates"):
                                    continue
                                raw = data["candidates"][0]["content"]["parts"][0][
                                    "text"
                                ].strip()
                            elif prov_upper == "COHERE":
                                if "message" not in data:
                                    continue
                                raw = data["message"]["content"][0]["text"].strip()
                            else:
                                if not data.get("choices"):
                                    continue
                                raw = data["choices"][0]["message"]["content"].strip()

                            res = self._clean_ai_response(raw, filename, chunk_idx)
                            if res:
                                return res, prov_upper
                        else:
                            await asyncio.sleep(2.5)

                    except Exception as e:
                        await asyncio.sleep(2.5)

            patience += 1
            self.log(
                f"[{filename}] Motori zauzeti. ⬇️ Čekam (<span class='cd-timer text-amber-500 font-bold'>20</span> sec) ⏳",
                "warning",
            )
            await asyncio.sleep(20.0)
        return None, "N/A"

    def _azuriraj_statistiku(self):
        pct = int((self.zavrseno_blokova / max(1, self.ukupno_blokova)) * 100)
        self.shared_stats["pct"] = pct
        self.shared_stats["ok"] = f"{self.zavrseno_blokova} / {self.ukupno_blokova}"
        self.shared_stats["files_done"] = f"{self.files_done} / {self.total_files}"

        preostalo = self.ukupno_blokova - self.zavrseno_blokova
        eta_min = int((preostalo * 15) / 60)  # Brže jer je samo formatiranje
        self.shared_stats["est"] = f"{eta_min} min preostalo"

        # Dodana status boja
        if pct < 50:
            self.shared_stats["status_color"] = "#f59e0b"
        elif pct < 100:
            self.shared_stats["status_color"] = "#10b981"
        else:
            self.shared_stats["status_color"] = "#3b82f6"

        if self.spaseno_iz_checkpointa > 0:
            self.shared_stats["batch_info"] = (
                f"Checkpoints: {self.spaseno_iz_checkpointa} | Aktivno: {self.zavrseno_blokova - self.spaseno_iz_checkpointa}"
            )

    async def _process_chunk_with_ai(
        self, chunk, previous_context, chunk_idx, file_name
    ):
        checkpoint_fajl = self.checkpoint_dir / f"{file_name}_blok_{chunk_idx}.chk"

        if checkpoint_fajl.exists():
            try:
                with open(checkpoint_fajl, "r", encoding="utf-8") as f:
                    zapamceno = f.read()
                if zapamceno and len(zapamceno) > 10:
                    self.spaseno_iz_checkpointa += 1
                    self.zavrseno_blokova += 1
                    self._azuriraj_statistiku()
                    return zapamceno
            except:
                pass

        async with self.semafor:
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return None

            prompt = (
                f"Ti si stručni dizajner i formater knjiga (AI Stylist).\n"
                f"ZADATAK: Formatiraj sljedeći sirovi tekst u čisti, prelopljeni HTML.\n"
                f"PRAVILA:\n"
                f"1. Dijalozi (rečenice koje počinju crticom - ili navodnicima) idu u novi red (<p>).\n"
                f"2. Pazi na tipografiju. Nemoj prevoditi tekst, zadrži originalan jezik!\n"
                f"3. Vrati isključivo HTML tagove, bez 'Evo rezultata'.\n\n"
                f"--- PRETHODNI TEKST (Samo za tok) ---\n{previous_context}\n\n"
                f"--- TEKST ZA FORMATIRANJE ---\n{chunk}"
            )

            for pokusaj in range(4):
                result_html, provider_used = await self._call_ai_engine(
                    prompt, chunk_idx, file_name
                )

                if result_html:
                    self._atomic_write(checkpoint_fajl, result_html)
                    self.zavrseno_blokova += 1
                    self._azuriraj_statistiku()

                    clean_eng = chunk.strip().replace("\n", "<br>")
                    clean_hr = BeautifulSoup(result_html, "html.parser").get_text(
                        separator="<br>", strip=True
                    )
                    det_id = f"det_{int(time.time() * 1000)}_{random.randint(0,9999)}"

                    audit_box = (
                        f"<div class='audit-card p-4' style='border-left-color:#c026d3;'>"
                        f"<div class='text-[11px] font-bold text-fuchsia-400 dark:text-fuchsia-300 uppercase tracking-wider mb-1'>"
                        f"<span class='mr-1'>📤</span> Šaljem: <span class='text-gray-800 dark:text-white'>{file_name} (Blok {chunk_idx})</span> na AI: <span class='text-theme'>{provider_used}</span></div>"
                        f"<div class='text-[10px] text-gray-500 ml-1.5 border-l-2 border-gray-300 dark:border-gray-700 pl-3 py-1'>⬇️ Formatiranje u toku...</div>"
                        f"<div class='text-[11px] font-bold text-green-600 dark:text-green-500 ml-1.5 border-l-2 border-gray-300 dark:border-gray-700 pl-3 py-1 mb-2'>"
                        f"⬇️ Odgovor AI:<br>Blok {chunk_idx} ✅ FORMATIRAN</div>"
                        f"<details id='{det_id}' class='ml-4 bg-gray-100 dark:bg-[#0a0a0a] rounded-lg p-3 border border-gray-300 dark:border-gray-800 shadow-inner'>"
                        f"<summary class='cursor-pointer text-theme font-bold text-[10px] uppercase tracking-wider outline-none user-select-none'>▶ Klikni za provjeru stila</summary>"
                        f"<div class='mt-3 pt-3 border-t border-gray-300 dark:border-gray-800 space-y-3'>"
                        f"<div class='text-gray-600 dark:text-gray-400'><span class='text-[9px] uppercase font-bold block text-gray-500 dark:text-gray-600 mb-1'>📄 Sirovi ulaz</span>{clean_eng}</div>"
                        f"<div class='text-gray-900 dark:text-gray-200'><span class='text-[9px] uppercase font-bold block text-theme mb-1'>✨ Formatirano</span>{clean_hr}</div>"
                        f"</div></details></div>"
                    )
                    self.log("", "accordion", en_text=audit_box)
                    return result_html
                else:
                    self.log(
                        f"Blok {chunk_idx} Retry {pokusaj+1} nije uspio.", "warning"
                    )

            self.chunk_skips += 1
            self.shared_stats["skipped"] = f"{self.chunk_skips}"
            return None

    def _inject_background(self, new_soup):
        style = new_soup.new_tag("style")
        bg_url = (
            "file:///"
            + "storage/emulated/0/Download/photo-1637325258040-d2f09636ecf6.jpeg"
        )
        # OVDJE JE POPRAVLJEN CSS F-STRING BUG (Duplane zagrade {{ i }})
        style.string = (
            f"body {{ background-image: url('{bg_url}') !important; background-size: cover !important; background-attachment: fixed !important; color: #1a1a1a !important; font-family: 'Georgia', serif; }} "
            "p { line-height: 1.75 !important; text-indent: 1.8em !important; margin-bottom: 0.8em !important; font-size: 1.15em !important; text-align: justify; } "
            "h2 { page-break-before: always; text-align: center; color: #8b0000; font-family: serif; font-size: 2.5em; font-weight: bold; padding-top: 25vh; line-height: 1.2; margin-bottom: 2.5em; text-transform: uppercase; letter-spacing: 0.1em; }"
        )
        new_soup.head.append(style)

    def _apply_dropcap_and_toc(self, soup, html_file):
        needs_dropcap = True
        for h2 in soup.find_all("h2"):
            self.chapter_counter += 1
            tag_id = f"skr_h_{self.chapter_counter}"
            h2["id"] = tag_id
            self.toc_entries.append(
                {
                    "title": h2.get_text(strip=True),
                    "abs_path": str(html_file),
                    "anchor": tag_id,
                }
            )
            h2.insert_before(
                soup.new_tag("div", style="page-break-before: always; height: 1px;")
            )
            needs_dropcap = True

        for p in soup.find_all("p"):
            if not needs_dropcap:
                continue
            txt = p.get_text(strip=True)
            if len(txt) > 30 and not txt.lower().startswith("bilješka"):
                first_node = next(
                    (
                        node
                        for node in p.descendants
                        if isinstance(node, NavigableString) and node.strip()
                    ),
                    None,
                )
                if first_node:
                    content = first_node.string.lstrip()
                    span = soup.new_tag(
                        "span",
                        attrs={
                            "style": "float: left; font-size: 4em; line-height: 0.8; margin-right: 0.1em; color: #8b0000; font-family: 'Old English Text MT', cursive; font-weight: bold;"
                        },
                    )
                    offset = (
                        2
                        if content[0] in ["'", '"', "“", "‘", "„"] and len(content) > 1
                        else 1
                    )
                    span.string = content[:offset]
                    first_node.replace_with(content[offset:])
                    p.insert(0, span)
                    needs_dropcap = False

    async def _process_single_file_worker(self, html_path):
        if self.shared_controls["stop"] or self.shared_controls["reset"]:
            return False
        chunks = self._get_raw_text_chunks(html_path)
        if not chunks:
            return True

        if html_path.name not in self.file_progress:
            self.file_progress[html_path.name] = {}
        final_html_parts = []
        previous_context = "Početak segmenta."

        ukupno_lokalnih = len(chunks)
        self.shared_stats["local_pct"] = 0

        for i, chunk in enumerate(chunks):
            if self.shared_controls["stop"] or self.shared_controls["reset"]:
                return False
            while self.shared_controls["pause"]:
                await asyncio.sleep(1)

            c_idx = str(i + 1)
            self.shared_stats["local_pct"] = int((i / ukupno_lokalnih) * 100)
            self.shared_stats["local_info"] = f"Blok {c_idx} / {ukupno_lokalnih}"

            translated_html = await self._process_chunk_with_ai(
                chunk, previous_context, i + 1, html_path.name
            )
            if not translated_html:
                self.log(f"[{html_path.name}] Preskačem mrtav blok {c_idx}.", "error")
                translated_html = (
                    f"<p>{chunk}</p>"  # Fallback na sirovi tekst da ne pukne EPUB
                )

            self.file_progress[html_path.name][c_idx] = translated_html
            self.save_checkpoint()
            final_html_parts.append(translated_html)

            temp_soup = BeautifulSoup(translated_html, self.parser_type)
            clean_txt = temp_soup.get_text(separator=" ", strip=True)
            previous_context = clean_txt[-350:] if len(clean_txt) > 350 else clean_txt

        new_soup = BeautifulSoup(
            f'<!DOCTYPE html><html xmlns="{_url_w3()}"><head><meta charset="utf-8"/><title>{self.clean_book_name}</title></head><body></body></html>',
            "xml",
        )
        self._inject_background(new_soup)
        temp_body = BeautifulSoup("".join(final_html_parts), self.parser_type)
        for elem in list(temp_body.contents):
            new_soup.body.append(elem.extract())
        self._apply_dropcap_and_toc(new_soup, html_path)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(str(new_soup))
        self.processed_files.append(html_path.name)
        self.save_checkpoint()

        self.files_done += 1
        self._azuriraj_statistiku()

        self.shared_stats["local_pct"] = 100
        self.shared_stats["local_info"] = "Završeno."
        return True

    async def _run_process(self):
        self.log(f"Pronađeno {self.book_path.name}. Analiziram format...", "system")

        try:
            with open("last_book.json", "w", encoding="utf-8") as f:
                json.dump({"last_book": str(self.book_path)}, f)
        except:
            pass

        # === MOBI DEKOMPAJLER ===
        if self.book_path.suffix.lower() == ".mobi":
            if not HAS_MOBI:
                self.log(
                    "Greška! MOBI dekoder nije instaliran. OTVORI TERMUX I KUCAJ: <b>pip install mobi</b>",
                    "error",
                )
                self.shared_stats["status"] = "ZAUSTAVLJENO"
                return

            self.log(
                f"Razbijam binarnu MOBI strukturu: {self.book_path.name}...", "system"
            )
            self.shared_stats["status"] = "RASPAKOVANJE MOBI-ja..."

            try:
                tempdir, filepath = await asyncio.to_thread(
                    mobi.extract, str(self.book_path)
                )
                extracted_path = Path(filepath)

                if extracted_path.is_file() and extracted_path.suffix.lower() in [
                    ".html",
                    ".htm",
                    ".xhtml",
                ]:
                    shutil.copy(
                        extracted_path,
                        self.work_dir / f"{self.clean_book_name}_mobi_izvuceno.html",
                    )
                elif extracted_path.is_dir():
                    for item in extracted_path.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(extracted_path)
                            target = self.work_dir / rel_path
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy(item, target)
                elif extracted_path.suffix.lower() == ".epub":
                    with zipfile.ZipFile(extracted_path, "r") as z:
                        z.extractall(self.work_dir)

                self.log(
                    "MOBI uspješno pretvoren u sirovi HTML. Započinjem V6 formatiranje.",
                    "tech",
                )
            except Exception as e:
                self.log(f"MOBI Dekompajler je pao: {e}", "error")
                self.shared_stats["status"] = "ZAUSTAVLJENO"
                return
        else:
            with zipfile.ZipFile(self.book_path, "r") as z:
                z.extractall(self.work_dir)

        html_files = sorted(
            list(self.work_dir.rglob("*.html"))
            + list(self.work_dir.rglob("*.xhtml"))
            + list(self.work_dir.rglob("*.htm"))
        )
        self.total_files = len(html_files)

        self.log(
            f"Započinjem V6 Formater. Ukupno HTML dokumenata: {self.total_files}",
            "system",
        )

        for f in html_files:
            try:
                sadrzaj = f.read_text("utf-8", errors="ignore")
                self.ukupno_blokova += len(self._naivni_chunker(sadrzaj))
            except:
                pass

        self._azuriraj_statistiku()
        self.start_time = time.time()
        self.shared_stats["status"] = "FORMATIRANJE U TOKU..."

        # POPRAVLJEN BUG: Provjera da li smo već sve obradili prije ulaska u petlju
        if self.zavrseno_blokova >= self.ukupno_blokova and self.ukupno_blokova > 0:
            self.log("Svi blokovi su već završeni i učitani iz checkpointa!", "system")
        else:
            for f in html_files:
                if f.name not in self.processed_files:
                    await self._process_single_file_worker(f)
                    if self.shared_controls["stop"] or self.shared_controls["reset"]:
                        break

        if not self.shared_controls["stop"] and not self.shared_controls["reset"]:
            self.shared_stats["status"] = "ZAVRŠNO PAKOVANJE..."
            self.rebuild_toc()
            self.finalize()

    def rebuild_toc(self):
        ncx_list = list(self.work_dir.rglob("*.ncx"))
        ncx_file = ncx_list[0] if ncx_list else self.work_dir / "OEBPS/toc.ncx"
        ncx_dir = ncx_file.parent
        ncx_dir.mkdir(exist_ok=True, parents=True)

        header = f'<?xml version="1.0" encoding="UTF-8"?><ncx xmlns="{_url_daisy()}" version="2005-1"><head><meta name="dtb:uid" content="skr-{int(time.time())}"/><meta name="dtb:depth" content="1"/></head><docTitle><text>{self.clean_book_name}</text></docTitle><navMap>'
        body = ""
        for i, entry in enumerate(self.toc_entries, 1):
            rel = Path(os.path.relpath(entry["abs_path"], ncx_dir)).as_posix()
            body += f'<navPoint id="np-{i}" playOrder="{i}"><navLabel><text>{entry["title"]}</text></navLabel><content src="{rel}#{entry["anchor"]}"/></navPoint>'
        with open(ncx_file, "w", encoding="utf-8") as f:
            f.write(header + body + "</navMap></ncx>")

    def finalize(self):
        with zipfile.ZipFile(self.out_path, "w") as z:
            if (self.work_dir / "mimetype").exists():
                z.write(
                    self.work_dir / "mimetype",
                    "mimetype",
                    compress_type=zipfile.ZIP_STORED,
                )
            for file in self.work_dir.rglob("*"):
                if file.is_file() and file.name != "mimetype":
                    z.write(
                        file,
                        file.relative_to(self.work_dir),
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
        self.shared_stats["status"] = "ZAVRŠENO"
        self.shared_stats["pct"] = 100
        self.log(f"Knjiga uspješno spašena: {self.out_path.name}", "system")


def start_from_master(book_path_str, model_name, shared_stats, shared_controls):
    global audit_logs
    audit_logs = []
    engine = FormaterAllInOne(book_path_str, model_name, shared_stats, shared_controls)
    try:
        asyncio.run(engine._run_process())
    except Exception as e:
        safe_e = str(e).replace("<", "&lt;").replace(">", "&gt;")
        engine.log(f"Pad u jezgri Formatera: {safe_e}", "error")
