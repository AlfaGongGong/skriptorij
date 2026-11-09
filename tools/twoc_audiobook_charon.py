#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TWOC Audiobook - Charon (3.1) v2
- Model: gemini-3.1-flash-tts-preview | Glas: Charon
- Kljucevi iz tools/.tts_keys (jedan po liniji) ili env TTS_KEYS (zarezom)
- Round-robin + razmak po kljucu (KEY_GAP) + cooldown po kljucu
- 429 dnevna kvota -> kljuc pauziran do reseta (pamti se u keystate.json)
- 429 minutna -> cooldown po retryDelay
- Svi kljucevi pauzirani ili 3 poglavlja zaredom puknu -> cisto staje
Env: START_FROM, SKIP_FINAL_MERGE=1, KEY_GAP=30, RESET_KEYS=1
"""
import os, sys, json, re, time, subprocess, base64, wave, html
from pathlib import Path
from urllib import request, error
from datetime import datetime, timedelta, timezone

HERE = Path(__file__).resolve().parent
EPUB = os.environ.get("EPUB", "")
CK_DIR = Path("/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints")
BASE_OUT = Path("/storage/emulated/0/Download/BOOKLYFI_AUDIOBOOK")
OUT_DIR = BASE_OUT / "CHARON_3.1"
if EPUB:
    _slug = re.sub(r"[^A-Za-z0-9]+", "_", Path(EPUB).stem)[:60].strip("_")
    OUT_DIR = BASE_OUT / (_slug + "_" + os.environ.get("VOICE", "Charon"))
    CK_DIR = OUT_DIR / "src"
CHUNKS_DIR = OUT_DIR / "chunks"
LISTEN_DIR = OUT_DIR / "LISTEN"
CHAPTERS_WAV = OUT_DIR / "chapters_wav"
STATE_FILE = OUT_DIR / "keystate.json"

START_FROM = os.environ.get("START_FROM", "part0000" if EPUB else "part0220")
MAX_PARTS = int(os.environ.get("MAX_PARTS", "0") or 0)
STYLE = os.environ.get("STYLE", "")
SKIP_FINAL_MERGE = os.environ.get("SKIP_FINAL_MERGE", "0") == "1"
RESET_KEYS = os.environ.get("RESET_KEYS", "0") == "1"
KEY_GAP = float(os.environ.get("KEY_GAP", "30"))
LONG_WAIT = 600
MAX_FAIL_STREAK = 10

MODEL = os.environ.get("MODEL", "gemini-3.1-flash-tts-preview")
VOICE = os.environ.get("VOICE", "Charon")
CHUNK_SIZE = 1000
SAMPLE_RATE = 24000

BOOK_TITLE = os.environ.get("BOOK_TITLE", "The Wisdom of Crowds")
BOOK_AUTHOR = os.environ.get("BOOK_AUTHOR", "Joe Abercrombie")


class StopRun(Exception):
    pass


class AllKeysDead(StopRun):
    def __init__(self, until):
        super().__init__("svi kljucevi pauzirani")
        self.until = until


def load_keys():
    keys = [k.strip() for k in os.environ.get("TTS_KEYS", "").split(",") if k.strip()]
    kf = HERE / ".tts_keys"
    if not keys and kf.exists():
        for line in kf.read_text("utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                keys.append(line)
    out = []
    for k in keys:
        if k not in out:
            out.append(k)
    return out


def next_reset_ts():
    # Google dnevna kvota se resetuje u ponoc Pacific vremena
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        return nxt.timestamp()
    except Exception:
        now = datetime.now(timezone.utc)
        nxt = now.replace(hour=8, minute=5, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        return nxt.timestamp()


class KeyPool:
    def __init__(self, keys):
        self.keys = keys
        self.reqs = [0] * len(keys)
        self.st = {}
        if not RESET_KEYS and STATE_FILE.exists():
            try:
                self.st = json.loads(STATE_FILE.read_text("utf-8"))
            except Exception:
                self.st = {}
        for k in keys:
            self.st.setdefault(k[-8:], {"dead_until": 0, "last": 0})

    def s(self, i):
        return self.st[self.keys[i][-8:]]

    def save(self):
        try:
            STATE_FILE.write_text(json.dumps(self.st))
        except Exception:
            pass

    def dead_for(self, i):
        return max(0, self.s(i)["dead_until"] - time.time())

    def ready_at(self, i):
        return max(self.s(i)["dead_until"], self.s(i)["last"] + KEY_GAP)

    def kill(self, i, secs):
        self.s(i)["dead_until"] = time.time() + secs
        self.save()

    def status(self):
        out = []
        for i in range(len(self.keys)):
            d = self.dead_for(i)
            if d <= 0:
                out.append(f"K{i+1}: ok")
            else:
                t = datetime.fromtimestamp(time.time() + d).strftime("%H:%M")
                out.append(f"K{i+1}: pauza do {t}")
        return " | ".join(out)

    def acquire(self):
        alive = [i for i in range(len(self.keys)) if self.dead_for(i) <= LONG_WAIT]
        if not alive:
            raise AllKeysDead(min(self.s(i)["dead_until"] for i in range(len(self.keys))))
        i = min(alive, key=self.ready_at)
        wait = self.ready_at(i) - time.time()
        if wait > 0:
            if wait > 3:
                print(f"[cekam {wait:.0f}s] ", end="", flush=True)
            time.sleep(wait)
        self.s(i)["last"] = time.time()
        self.save()
        return i


def extract_text(chk_path):
    t = chk_path.read_text("utf-8")
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def extract_title(chk_path):
    t = chk_path.read_text("utf-8")
    m = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
    if m:
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if title:
            return title
    return None


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name)
    return re.sub(r"\s+", " ", name).strip()[:80]


def split_into_chunks(text, max_chars=CHUNK_SIZE):
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current.strip())
            current = s
        else:
            current += (" " if current else "") + s
    if current.strip():
        chunks.append(current.strip())
    return chunks


def call_tts(text, key, out_wav):
    """Vraca (kod, info). 200=OK, 0=nema audia, -1=mrezna greska, ostalo=HTTP kod."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": (STYLE + " " + text) if STYLE else text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    req = request.Request(url, data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode())
    except error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8", "ignore")
        except Exception:
            msg = ""
        return e.code, msg
    except Exception as e:
        return -1, type(e).__name__
    cand = (data.get("candidates") or [{}])[0]
    for p in (cand.get("content") or {}).get("parts") or []:
        inline = p.get("inlineData") or p.get("inline_data") or {}
        if inline.get("data"):
            pcm = base64.b64decode(inline["data"])
            if len(pcm) < 2000:
                continue
            rate = SAMPLE_RATE
            m = re.search(r"rate=(\d+)", inline.get("mimeType", "") or "")
            if m:
                rate = int(m.group(1))
            tmp = out_wav.with_name(out_wav.name + ".tmp")
            with wave.open(str(tmp), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate)
                wf.writeframes(pcm)
            os.replace(tmp, out_wav)
            return 200, ""
    return 0, "NO_AUDIO " + str(cand.get("finishReason", ""))


def generate_chunk(text, out_wav, pool):
    """Vraca 'OK' ili opis greske. Baca AllKeysDead kad nema vise upotrebljivih kljuceva."""
    max_tries = len(pool.keys) + 2
    noaudio = 0
    last = "?"
    for attempt in range(max_tries):
        i = pool.acquire()
        lab = f"K{i+1}"
        pool.reqs[i] += 1
        code, info = call_tts(text, pool.keys[i], out_wav)
        if code == 200:
            return "OK"
        last = f"HTTP{code}" if code > 0 else (info or "ERR")
        if code == 429:
            if re.search(r"PerDay|per day", info, re.I):
                secs = max(next_reset_ts() - time.time(), 3600)
                pool.kill(i, secs)
                t = datetime.fromtimestamp(time.time() + secs).strftime("%H:%M")
                print(f"{lab}:429 dnevna kvota, pauza do {t}; ", end="", flush=True)
            else:
                m = (re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', info)
                     or re.search(r"retry in (\d+(?:\.\d+)?)s", info))
                secs = (float(m.group(1)) if m else 60) + 5
                pool.kill(i, secs)
                print(f"{lab}:429 cooldown {secs:.0f}s; ", end="", flush=True)
        elif code in (401, 403) or (code == 400 and re.search(
                r"API_KEY_INVALID|API key not valid|API key expired", info)):
            pool.kill(i, 86400)
            print(f"{lab}:kljuc odbijen ({code}); ", end="", flush=True)
        elif code == 400:
            msg = re.sub(r"\s+", " ", info)[:140]
            print(f"{lab}:400 {msg}", end=" ", flush=True)
            return last
        elif code == 0:
            noaudio += 1
            print(f"{lab}:bez audia; ", end="", flush=True)
            if noaudio >= 2:
                return last
            time.sleep(3)
        else:
            print(f"{lab}:{last}; ", end="", flush=True)
            time.sleep(5 * (attempt + 1))
    return last


def get_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 0


def process_part(num, total, part, chunk_srcs, pool):
    """True = poglavlje gotovo (ili prazno), False = nekompletno."""
    print(f"\n[{num}/{total}] {part}")
    full_text, title = "", None
    for idx, chk_path in chunk_srcs:
        full_text += " " + extract_text(chk_path)
        if not title:
            title = extract_title(chk_path)
    full_text = full_text.strip()
    if not full_text:
        print("  Prazno, preskacem.")
        return True

    title = title or f"Poglavlje {num}"
    chunks = split_into_chunks(full_text)
    print(f"  Naslov: {title}")
    print(f"  {len(full_text)} char -> {len(chunks)} chunkova")

    part_dir = CHUNKS_DIR / part
    part_dir.mkdir(exist_ok=True)

    chunk_files = []
    for ci, chunk_text in enumerate(chunks):
        cf = part_dir / f"chunk_{ci:04d}.wav"
        if cf.exists() and cf.stat().st_size > 1000:
            chunk_files.append(cf)
            continue
        print(f"  chunk {ci+1}/{len(chunks)} ({len(chunk_text)}c): ", end="", flush=True)
        t0 = time.time()
        result = generate_chunk(chunk_text, cf, pool)
        if result == "OK":
            print(f"\u2713 {time.time()-t0:.0f}s")
            chunk_files.append(cf)
        else:
            print(f"FAIL ({result})")
            break

    if len(chunk_files) != len(chunks):
        print(f"  NEKOMPLETNO ({len(chunk_files)}/{len(chunks)})")
        return False

    ch_wav = CHAPTERS_WAV / f"{part}.wav"
    if not ch_wav.exists() or ch_wav.stat().st_size < 10000:
        lst = part_dir / "list.txt"
        with open(lst, "w") as f:
            for cf in chunk_files:
                f.write(f"file '{cf}'\n")
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(ch_wav)], check=True, capture_output=True, timeout=300)
        except Exception as e:
            print(f"  WAV spajanje greska: {str(e)[:80]}")
            return False

    listen_mp3 = LISTEN_DIR / f"{num:03d} - {sanitize(title)}.mp3"
    if not listen_mp3.exists() or listen_mp3.stat().st_size < 5000:
        print("  MP3...", end="", flush=True)
        try:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(ch_wav),
                "-metadata", f"title={title}",
                "-metadata", f"artist={BOOK_AUTHOR}",
                "-metadata", f"album={BOOK_TITLE} (Charon)",
                "-metadata", f"track={num}/{total}",
                "-metadata", "genre=Audiobook",
                "-codec:a", "libmp3lame", "-b:a", "128k", str(listen_mp3)
            ], check=True, capture_output=True, timeout=300)
            dur = get_duration(listen_mp3)
            m, s = int(dur // 60), int(dur % 60)
            print(f" \u2705 {listen_mp3.name} ({m}:{s:02d})")
        except Exception as e:
            print(f" \u274c {str(e)[:80]}")
    return True


def epub_to_chk():
    """EPUB -> CK_DIR/partNNNN.html_blok_0.chk (cisti HTML bez inline tagova). Ispisuje popis poglavlja."""
    global BOOK_TITLE, BOOK_AUTHOR
    import zipfile
    import xml.etree.ElementTree as ET
    from collections import Counter
    from urllib.parse import unquote
    CK_DIR.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(EPUB)
    cont = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = [e.get("full-path") for e in cont.iter() if e.tag.endswith("rootfile")][0]
    opf = ET.fromstring(z.read(opf_path))
    base = os.path.dirname(opf_path)
    man = {e.get("id"): e.get("href") for e in opf.iter() if e.tag.endswith("}item")}
    spine = [e.get("idref") for e in opf.iter() if e.tag.endswith("itemref")]
    tt = [e.text.strip() for e in opf.iter() if e.tag.endswith("}title") and e.text]
    aa = [e.text.strip() for e in opf.iter() if e.tag.endswith("}creator") and e.text]
    if tt and "BOOK_TITLE" not in os.environ:
        BOOK_TITLE = tt[0]
    if aa and "BOOK_AUTHOR" not in os.environ:
        BOOK_AUTHOR = aa[0]
    skip = re.compile(r"nav|naslovna|impresum|cover|toc|titlepage", re.I)
    raw = []
    for idref in spine:
        href = man.get(idref)
        if not href or not href.lower().endswith(("html", "htm")):
            continue
        if skip.search(os.path.basename(href)):
            continue
        h = z.read((base + "/" if base else "") + unquote(href)).decode("utf-8", "replace")
        b = re.search(r"(?is)<body[^>]*>(.*)</body>", h)
        raw.append((href, b.group(1) if b else h))

    def _txt(x):
        return html.unescape(re.sub(r"<[^>]+>", "", x)).strip()

    hpat = r"(?is)<h[1-3][^>]*>(.*?)</h[1-3]>"
    cnt = Counter(t for _, b in raw for t in set(_txt(m) for m in re.findall(hpat, b)) if t)
    running = {t for t, c in cnt.items() if c > max(1, len(raw) // 2)}
    print("EPUB: %s | %s | %s" % (Path(EPUB).name, BOOK_TITLE, BOOK_AUTHOR))
    k = 0
    for href, b in raw:
        b = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", b)
        b = re.sub(hpat, lambda m: "" if _txt(m.group(1)) in running
                   else "<h1>" + html.escape(_txt(m.group(1)), quote=False) + "</h1>", b)
        b = re.sub(r"(?is)<img[^>]*>", "", b)
        b = re.sub(r"(?is)</?(span|em|i|b|strong|a|sup|sub|small|u)\b[^>]*>", "", b)
        b = re.sub(r"\[\[NEPREVEDENO[^\]]*\]\]", "", b)
        plain = html.unescape(re.sub(r"<[^>]+>", " ", b))
        if len(re.sub(r"\s+", "", plain)) < 40:
            continue
        name = "part%04d" % k
        (CK_DIR / (name + ".html_blok_0.chk")).write_text(b, "utf-8")
        t1 = re.search(r"<h1>(.*?)</h1>", b, re.S)
        print("  %s  %7d znakova  %s" % (name, len(plain), (t1.group(1) if t1 else "-")[:50]))
        k += 1
    print("  poglavlja: %d" % k)


def main():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
    except Exception:
        print("GRESKA: ffmpeg nije instaliran. Pokreni: pkg install ffmpeg")
        sys.exit(1)

    keys = load_keys()
    if not keys:
        print("GRESKA: nema kljuceva. Upisi ih u tools/.tts_keys (jedan po liniji) ili postavi TTS_KEYS.")
        sys.exit(1)

    for d in (OUT_DIR, CHUNKS_DIR, LISTEN_DIR, CHAPTERS_WAV):
        d.mkdir(parents=True, exist_ok=True)
    if EPUB:
        epub_to_chk()

    all_parts = {}
    for p in CK_DIR.glob("*.chk"):
        if p.name.endswith((".prevod.chk", ".lektura.chk")):
            continue
        m = re.match(r"(part\d+)\.html_blok_(\d+)\.chk", p.name)
        if not m:
            continue
        all_parts.setdefault(m.group(1), []).append((int(m.group(2)), p))
    for part in all_parts:
        all_parts[part].sort()

    parts_to_process = sorted([p for p in all_parts if p >= START_FROM])
    if MAX_PARTS:
        parts_to_process = parts_to_process[:MAX_PARTS]
    if not parts_to_process:
        print(f"Nema poglavlja od {START_FROM}")
        sys.exit(1)

    pool = KeyPool(keys)
    print(f"Poglavlja: {len(parts_to_process)} ({parts_to_process[0]} -> {parts_to_process[-1]})")
    print(f"Model: {MODEL} | Glas: {VOICE}")
    print(f"Kljucevi: {pool.status()}")
    print(f"Razmak po kljucu: {KEY_GAP:.0f}s")
    print(f"Output: {OUT_DIR}")
    print("=" * 70)

    stopped = False
    fail_streak = 0
    try:
        for i, part in enumerate(parts_to_process):
            ok = process_part(i + 1, len(parts_to_process), part, all_parts[part], pool)
            fail_streak = 0 if ok else fail_streak + 1
            if fail_streak >= MAX_FAIL_STREAK:
                raise StopRun(f"{MAX_FAIL_STREAK} poglavlja zaredom nisu uspjela")
    except AllKeysDead as e:
        stopped = True
        print("\n" + "=" * 70)
        print("SVI KLJUCEVI ISCRPLJENI/PAUZIRANI.")
        print("Najranije opet oko " + datetime.fromtimestamp(e.until).strftime("%H:%M %d.%m."))
        print("Pokreni isto opet tada, nastavlja gdje je stao.")
    except StopRun as e:
        stopped = True
        print("\n" + "=" * 70)
        print(f"STOP: {e}. Provjeri log iznad, pa pokreni opet (resume radi).")

    print("Zahtjeva u ovom runu: " + ", ".join(f"K{i+1}={n}" for i, n in enumerate(pool.reqs)))

    if stopped:
        print("Prekinuto - finalni merge preskocen.")
        sys.exit(2)

    if SKIP_FINAL_MERGE:
        print("\nSKIP_FINAL_MERGE=1 - preskacem finalno spajanje.")
    else:
        print("\n" + "=" * 70)
        print("Final merge u M4B sa poglavljima...")
        mp3s = sorted(LISTEN_DIR.glob("*.mp3"))
        if not mp3s:
            print("Nema MP3, prekidam.")
            sys.exit(1)
        cf = OUT_DIR / "concat.txt"
        with open(cf, "w") as f:
            for m in mp3s:
                f.write(f"file '{m}'\n")
        mf = OUT_DIR / "meta.txt"
        with open(mf, "w") as f:
            f.write(";FFMETADATA1\n")
            cur = 0
            for m in mp3s:
                dur = get_duration(m)
                end = cur + int(dur * 1000)
                mm = re.match(r"\d+ - (.+)\.mp3", m.name)
                t = mm.group(1) if mm else m.stem
                f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={cur}\nEND={end}\ntitle={t}\n")
                cur = end
        m4b = OUT_DIR / ("TWOC_Charon.m4b" if not EPUB else OUT_DIR.name + ".m4b")
        try:
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(cf),
                            "-i", str(mf), "-map_metadata", "1", "-c:a", "aac", "-b:a", "128k",
                            "-metadata", f"title={BOOK_TITLE}", "-metadata", f"artist={BOOK_AUTHOR}",
                            str(m4b)], check=True, capture_output=True, timeout=3600)
            print(f"OK M4B: {m4b} ({m4b.stat().st_size/1024/1024:.1f} MB)")
        except subprocess.CalledProcessError as e:
            print(f"M4B greska: {e.stderr.decode()[:300]}")

    print("\n" + "=" * 70)
    print("ZAVRSENO!")
    print(f"LISTEN folder: {LISTEN_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
