import json
import random
import re
import asyncio
import requests
import zipfile
import shutil
import os
from pathlib import Path
from bs4 import BeautifulSoup
from api_fleet import FleetManager, register_active_fleet

# ============================================================================
# API ENDPOINTI
# ============================================================================
def _url_gemini_base(model, key):
    return f"https://generativelanguage.googleapis.com/v1beta/{model}:generateContent?key={key}"

MIN_GAP = 0.4

# ============================================================================
# GLAVNA LOGIKA: TTS PROCESSOR
# ============================================================================
class TTSProcessor:
    def __init__(self, book_path, provider, shared_stats, shared_controls):
        self.book_path = Path(book_path)
        self.provider = provider.upper() if provider else "AUTO_FLEET"
        self.shared_stats = shared_stats
        self.shared_controls = shared_controls

        self.fleet = FleetManager(config_path="dev_api.json")
        self.fleet.reload()
        register_active_fleet(self.fleet)

        # Checkpoint se čuva pored knjige
        self.checkpoint_path = self.book_path.parent / "tts_map_checkpoint.json"
        self.phonetic_dictionary = self._load_checkpoint()

        self.hr_stopwords = {
            "da", "ne", "je", "su", "se", "bi", "će", "te", "ili", "ako",
            "za", "na", "od", "do", "iz", "sa", "uz", "kroz", "prema", "kao",
            "što", "koji", "koja", "koje", "kako", "tako", "samo", "sve", "svi",
            "ima", "nema", "bio", "bila", "bili", "kad", "onda", "tamo", "ovdje",
            "onaj", "ova", "ovo",
        }
        self.rejected_count = 0

    def log(self, msg, tip="info"):
        if tip == "error":
            html = f"<div class='audit-card p-3 border-l-red-500'><span class='text-red-500 font-bold uppercase text-[10px] block'>Greška</span><span class='text-gray-300'>{msg}</span></div>"
        elif tip == "warning":
            html = f"<div class='audit-card p-3 border-l-amber-500'><span class='text-amber-500 font-bold uppercase text-[10px] block'>Upozorenje</span><span class='text-gray-300'>{msg}</span></div>"
        elif tip == "system":
            html = f"<div class='audit-card p-3 border-l-sky-500'><span class='text-sky-500 font-bold uppercase text-[10px] block'>Sistem</span><span class='text-gray-300'>{msg}</span></div>"
        else:
            html = f"<div class='p-2 text-gray-400 border-b border-gray-800'>{msg}</div>"
        
        self.shared_stats["live_audit"] += html

    def _load_checkpoint(self):
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_checkpoint(self):
        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(self.phonetic_dictionary, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    async def _async_http_post(self, url, headers, payload, prov_upper, key):
        """Mrežni sloj usklađen sa V8 Omni-Core FleetManagerom"""
        timeout_tuple = (15.0, 120.0)
        try:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=payload,
                timeout=timeout_tuple,
                verify=False,
            )
            
            if hasattr(self.fleet, 'analyze_response'):
                self.fleet.analyze_response(prov_upper, key, resp.status_code, resp.headers)
            if hasattr(self.fleet, 'record_request'):
                self.fleet.record_request(prov_upper, key)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (429, 425):
                self.log(f"[{prov_upper}] API Mreža preopterećena (HTTP {resp.status_code})", "warning")
                return None
            else:
                self.log(f"[{prov_upper}] Greška servera (HTTP {resp.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"[{prov_upper}] Mrežni Timeout / Greška veze", "warning")
            return None

    async def _call_ai_batch(self, batch_words, batch_idx, total_batches):
        # ⚡ KLJUČNI FIX: V8_TURBO je sada na listi auto-flota
        auto_fleet_names = ["AUTO_FLEET", "QUAD_CORE", "V6_TURBO", "V8_TURBO", "V8_OMNI_CORE", "OMNI_CORE"]
        dozvoljeni_motori = ["CEREBRAS", "MISTRAL", "COHERE", "GROQ", "SAMBANOVA", "GEMINI", "GITHUB", "TOGETHER", "FIREWORKS", "CHUTES", "KLUSTER", "HUGGINGFACE"]
        
        if self.provider in auto_fleet_names:
            providers = [
                p for p in self.fleet.fleet.keys()
                if p.upper() in dozvoljeni_motori
            ]
        else:
            providers = [self.provider] if self.provider in self.fleet.fleet.keys() else []

        if not providers:
            self.log(f"⚠️ Nema dostupnih ključeva za traženi motor ({self.provider})! Preskačem API.", "error")
            return False

        random.shuffle(providers)
        words_str = "\n".join(batch_words)
        
        for attempt in range(4):
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                return False

            for prov in providers:
                prov_upper = prov.upper()
                key = self.fleet.get_best_key(prov_upper)
                if not key:
                    continue

                self.shared_stats["active_engine"] = prov_upper
                self.shared_stats["current_worker"] = prov_upper

                sys_content = (
                    "Ti si lingvistički API za fonetizaciju. Dobit ćeš listu sumnjivih riječi (strana imena, gradovi, engleski izrazi, akronimi).\n"
                    "ZADATAK: Vrati ISKLJUČIVO fonetizovani prevod onih riječi koje to zaista zahtijevaju, u formatu:\n"
                    "Original#->#Fonetizovano\n"
                    "ZABRANJENO: Ne vraćaj obične hrvatske/bosanske riječi. Ako u listi nema riječi za fonetizaciju, vrati 'SKIP'."
                )

                headers = {"Content-Type": "application/json"}
                opt_temp = 0.10

                try:
                    if prov_upper == "GEMINI":
                        url = _url_gemini_base("models/gemini-flash-latest", key)
                        payload = {
                            "systemInstruction": {"parts": [{"text": sys_content}]},
                            "contents": [{"parts": [{"text": words_str}]}],
                            "generationConfig": {"temperature": opt_temp},
                        }
                    else:
                        api_model = self.fleet.get_active_model(prov_upper)
                        if not api_model:
                            if prov_upper == "CEREBRAS": api_model = "llama3.1-70b"
                            elif prov_upper == "SAMBANOVA": api_model = "Meta-Llama-3.1-70B-Instruct"
                            elif prov_upper == "GITHUB": api_model = "gpt-4o"
                            else: api_model = "llama-3.3-70b-versatile"

                        url_map = {
                            "GROQ":        "https://api.groq.com/openai/v1/chat/completions",
                            "CEREBRAS":    "https://api.cerebras.ai/v1/chat/completions",
                            "SAMBANOVA":   "https://api.sambanova.ai/v1/chat/completions",
                            "MISTRAL":     "https://api.mistral.ai/v1/chat/completions",
                            "OPENROUTER":  "https://openrouter.ai/api/v1/chat/completions",
                            "GITHUB":      "https://models.inference.ai.azure.com/chat/completions",
                            "TOGETHER":    "https://api.together.xyz/v1/chat/completions",
                            "FIREWORKS":   "https://api.fireworks.ai/inference/v1/chat/completions",
                            "CHUTES":      "https://llm.chutes.ai/v1/chat/completions",
                            "HUGGINGFACE": "https://router.huggingface.co/v1/chat/completions",
                            "KLUSTER":     "https://api.kluster.ai/v1/chat/completions",
                            "GEMMA":       "https://api.together.xyz/v1/chat/completions",
                        }
                        
                        url = url_map.get(prov_upper, url_map["GROQ"])
                        headers["Authorization"] = f"Bearer {key.strip()}"
                        payload = {
                            "model": api_model,
                            "messages": [
                                {"role": "system", "content": sys_content},
                                {"role": "user", "content": words_str},
                            ],
                            "temperature": opt_temp,
                        }

                    # SLANJE HTTP ZAHTJEVA
                    data = await self._async_http_post(url, headers, payload, prov_upper, key)
                    self.shared_stats["current_worker"] = "NONE"

                    if data:
                        raw = ""
                        try:
                            if prov_upper == "GEMINI":
                                raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                            else:
                                raw = data["choices"][0]["message"]["content"].strip()
                        except Exception:
                            continue

                        if not raw:
                            continue

                        if "SKIP" in raw.upper() and len(raw) < 10:
                            return True

                        found_this_batch = []
                        lines = raw.split("\n")
                        for line in lines:
                            if "#->#" in line:
                                parts = line.split("#->#")
                                if len(parts) == 2:
                                    orig, fon = parts[0].strip(), parts[1].strip()
                                    if orig.lower() != fon.lower():
                                        self.phonetic_dictionary[orig] = fon
                                        found_this_batch.append(f"{orig} ➔ {fon}")

                        if found_this_batch:
                            self.log(
                                f"✅ Mreža {prov_upper} ulovila {len(found_this_batch)} novih riječi.<br><small class='text-gray-500'>{', '.join(found_this_batch[:5])}...</small>"
                            )
                        else:
                            self.log(f"⚡ Mreža {prov_upper} nije detektovala strane riječi u ovom bloku.", "system")

                        self._save_checkpoint()
                        return True
                except Exception as e:
                    pass
            await asyncio.sleep(1)
        
        self.log(f"⚠️ Preskočen blok {batch_idx} jer su svi motori zauzeti ili preopterećeni.", "warning")
        return False

    def _extract_and_filter_words(self, text):
        raw_words = re.findall(r"\b[A-Z][a-z]+\b|\b[A-Z]{2,}\b", text)
        filtered = set()
        self.rejected_count = 0
        hr_spec = set("čćžšđČĆŽŠĐ")

        for w in set(raw_words):
            if len(w) <= 2:
                self.rejected_count += 1
                continue
            if w.lower() in self.hr_stopwords:
                self.rejected_count += 1
                continue
            if any(c in w for c in hr_spec):
                self.rejected_count += 1
                continue
            if w in self.phonetic_dictionary:
                continue

            filtered.add(w)

        return list(filtered)

    def _save_moon_reader_filter(self):
        """
        Kreira .ttsfilter za Moon+ Reader, gasi ukrase i mapira velika slova u mala.
        """
        filter_name = f"(TTS)_{self.book_path.stem}.ttsfilter"
        filter_path = self.book_path.parent / filter_name

        lines = [
            "~ ♦ ~#-># ",
            "~♦️~#-># ",
            "♦#-># ",
            "❧ ✦ ❧❧ ✦ ❧*❧ ✦ ❧*❧ ✦ ❧❧ ✦ ❧❧ ✦ ❧*❧ ✦ ❧*❧ ✦ ❧#-># ",
            "------------#-># "
        ]

        for char in "ABCČĆDĐEFGHIJKLMNOPQRSŠTUVWXYZŽ":
            lines.append(f"{char}#->#{char.lower()}")

        lines.append("\n// --- AI FONETIZACIJA ---")
        for eng, fon in sorted(self.phonetic_dictionary.items()):
            lines.append(f"{eng}#->#{fon}")

        with open(filter_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            
        self.log(f"🟢 GOTOVO! Moon+ Reader Filter kreiran:<br><small class='text-sky-300'>{filter_path.name}</small>", "system")

    async def run(self):
        self.shared_stats["status"] = "SKENIRANJE EPUB-A..."
        self.work_dir = Path("tts_radni_folder")
        if self.work_dir.exists():
            shutil.rmtree(self.work_dir)
        self.work_dir.mkdir()

        all_text = ""
        try:
            with zipfile.ZipFile(self.book_path, "r") as z:
                z.extractall(self.work_dir)
                for item in z.namelist():
                    if item.endswith((".html", ".xhtml")):
                        all_text += (
                            BeautifulSoup(
                                z.read(item).decode("utf-8", errors="ignore"),
                                "html.parser",
                            ).get_text()
                            + " "
                        )
        except Exception as e:
            self.log(f"Greška prilikom čitanja EPUB arhive: {e}", "error")
            return

        self.shared_stats["status"] = "LOKALNI FILTER..."
        suspicious = self._extract_and_filter_words(all_text)

        self.log(
            f"📊 <b>Audit:</b> Skenirano {len(set(all_text.split()))} riječi.<br>"
            f"❌ Odbačeno (HR/Kratko): {self.rejected_count}<br>"
            f"🧠 Već poznato: {len(self.phonetic_dictionary)}<br>"
            f"🔍 Za AI obradu: <b>{len(suspicious)}</b>",
            "system",
        )

        batch_size = 150
        batches = [
            suspicious[i : i + batch_size]
            for i in range(0, len(suspicious), batch_size)
        ]
        total_b = len(batches)

        self.shared_stats["status"] = "API MREŽA AKTIVNA..."
        for idx, batch in enumerate(batches, 1):
            if self.shared_controls.get("stop") or self.shared_controls.get("reset"):
                break
            self.shared_stats["ok"] = f"{idx} / {total_b}"
            self.shared_stats["pct"] = int((idx / max(1, total_b)) * 100)
            await self._call_ai_batch(batch, idx, total_b)

        if not self.shared_controls.get("stop"):
            self.shared_stats["status"] = "PAKOVANJE KNJIGE"

            out_name = f"(TTS)_{self.book_path.stem}.epub"
            final_epub = self.book_path.parent / out_name

            with zipfile.ZipFile(final_epub, "w", zipfile.ZIP_DEFLATED) as z:
                for f in self.work_dir.rglob("*"):
                    if f.is_file():
                        z.write(f, f.relative_to(self.work_dir))

            self._save_moon_reader_filter()
            
            self.shared_stats["status"] = "ZAVRŠENO"
            self.shared_stats["pct"] = 100
            self.shared_stats["active_engine"] = "---"
            self.shared_stats["current_worker"] = "---"

        shutil.rmtree(self.work_dir, ignore_errors=True)

# ============================================================================
# ENTRY POINT
# ============================================================================
def start_from_master(book_path, model, shared_stats, shared_controls):
    processor = TTSProcessor(book_path, model, shared_stats, shared_controls)
    asyncio.run(processor.run())
