#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TWOC Audiobook Generator v2
- Posle SVAKOG poglavlja: pravi LISTEN/NNN - Naslov.mp3 (ID3 tagovi, spremno za slusanje)
- Na kraju: opciono spaja sve u TWOC.m4b (sa chapterima) i TWOC.mp3
- Resume radi (preskace gotove chunkove)
- Env varijable:
    SKIP_FINAL_MERGE=1   -> ne pravi TWOC.m4b/TWOC.mp3 na kraju
    START_FROM=part0220  -> od kog poglavlja (default)
"""
import os, sys, json, re, time, subprocess, base64, wave
from pathlib import Path
from urllib import request, error


def _tts_key(i):
    """Kljuc broj i iz tools/.tts_keys (jedan po liniji, # komentar). P0.8: bez hardkodiranja."""
    from pathlib import Path as _P
    kf = _P(__file__).resolve().parent / ".tts_keys"
    if not kf.exists():
        raise SystemExit("GRESKA: nema tools/.tts_keys (jedan kljuc po liniji)")
    kljucevi = [l.split("#")[0].strip() for l in kf.read_text("utf-8").splitlines() if l.split("#")[0].strip()]
    if i >= len(kljucevi):
        raise SystemExit("GRESKA: tools/.tts_keys nema kljuc broj %d" % (i + 1))
    return kljucevi[i]

CK_DIR = Path("/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints")
OUT_DIR = Path("/storage/emulated/0/Download/BOOKLYFI_AUDIOBOOK")
CHUNKS_DIR = OUT_DIR / "chunks"
CHAPTERS_DIR = OUT_DIR / "chapters"
LISTEN_DIR = OUT_DIR / "LISTEN"

START_FROM = os.environ.get("START_FROM", "part0220")
SKIP_FINAL_MERGE = os.environ.get("SKIP_FINAL_MERGE", "0") == "1"

VOICE_ID = "voice_l6z7xfil1h1i"
MODEL = "gemini-3.8-flash-tts"
CHUNK_SIZE = 400
MAX_RETRIES = 4
SAMPLE_RATE = 24000

BOOK_TITLE = "The Wisdom of Crowds"
BOOK_AUTHOR = "Joe Abercrombie"

API_KEYS = [
    _tts_key(4),
    _tts_key(0),
    _tts_key(1),
    _tts_key(2),
    _tts_key(3),
    _tts_key(13),
    _tts_key(12),
    _tts_key(11),
    _tts_key(10),
    _tts_key(9),
    _tts_key(8),
    _tts_key(7),
    _tts_key(6),
    _tts_key(5),
]

def extract_text(chk_path):
    t = chk_path.read_text("utf-8")
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def extract_title(chk_path):
    t = chk_path.read_text("utf-8")
    m = re.search(r"<h1[^>]*>(.*?)</h1>", t, re.S)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if title:
            return title
    return None

def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:80] if len(name) > 80 else name

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

def generate_chunk(text, out_wav, key_idx=0):
    if out_wav.exists() and out_wav.stat().st_size > 1000:
        return True
    key = API_KEYS[key_idx % len(API_KEYS)]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"voice": VOICE_ID}}
        }
    }
    req = request.Request(url, data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode())
    except error.HTTPError as e:
        print(f"HTTP{e.code}", end=" ")
        return False
    except Exception as e:
        print(f"ERR{str(e)[:20]}", end=" ")
        return False
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        if "inlineData" in p and p["inlineData"].get("data"):
            pcm = base64.b64decode(p["inlineData"]["data"])
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            return True
    return False

def get_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                           capture_output=True, text=True, timeout=10)
        return float(r.stdout.strip())
    except Exception:
        return 0

def main():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
    except Exception:
        print("GRESKA: ffmpeg nije instaliran. Pokreni: pkg install ffmpeg")
        sys.exit(1)

    for d in (OUT_DIR, CHUNKS_DIR, CHAPTERS_DIR, LISTEN_DIR):
        d.mkdir(parents=True, exist_ok=True)

    all_parts = {}
    for p in CK_DIR.glob("*.chk"):
        if p.name.endswith((".prevod.chk", ".lektura.chk")):
            continue
        m = re.match(r"(part\d+)\.html_blok_(\d+)\.chk", p.name)
        if not m: continue
        part, idx = m.group(1), int(m.group(2))
        all_parts.setdefault(part, []).append((idx, p))

    for part in all_parts:
        all_parts[part].sort()

    parts_to_process = sorted([p for p in all_parts.keys() if p >= START_FROM])
    if not parts_to_process:
        print(f"Nema poglavlja od {START_FROM}"); sys.exit(1)

    print(f"Poglavlja: {len(parts_to_process)} ({parts_to_process[0]} -> {parts_to_process[-1]})")
    print(f"Glas: Branko Klubicka ({VOICE_ID})")
    print(f"Pocetak: {time.strftime('%H:%M:%S')}")
    print(f"Listen folder: {LISTEN_DIR}")
    print("=" * 70)

    for i, part in enumerate(parts_to_process):
        chapter_num = i + 1
        print(f"\n[{chapter_num}/{len(parts_to_process)}] {part}")

        full_text = ""
        title = None
        for idx, chk_path in all_parts[part]:
            full_text += " " + extract_text(chk_path)
            if not title:
                t = extract_title(chk_path)
                if t: title = t
        full_text = full_text.strip()
        if not full_text:
            print("  Prazno, preskacem."); continue

        title = title or f"Poglavlje {chapter_num}"
        safe_title = sanitize_filename(title)
        chunks = split_into_chunks(full_text)
        print(f"  Naslov: {title}")
        print(f"  {len(full_text)} char -> {len(chunks)} chunkova")

        part_chunks = CHUNKS_DIR / part
        part_chunks.mkdir(exist_ok=True)

        chunk_files = []
        for ci, chunk_text in enumerate(chunks):
            cf = part_chunks / f"chunk_{ci:04d}.wav"
            if cf.exists() and cf.stat().st_size > 1000:
                chunk_files.append(cf)
                continue
            print(f"  chunk {ci+1}/{len(chunks)} ({len(chunk_text)}c): ", end="", flush=True)
            t0 = time.time()
            ok = False
            for retry in range(MAX_RETRIES):
                if generate_chunk(chunk_text, cf, key_idx=retry):
                    ok = True; break
                time.sleep(2)
            if ok:
                print(f"OK {time.time()-t0:.0f}s")
                chunk_files.append(cf)
            else:
                print("FAIL"); break
            time.sleep(0.3)

        if len(chunk_files) != len(chunks):
            print(f"  NEKOMPLETNO ({len(chunk_files)}/{len(chunks)}), preskacem poglavlje")
            continue

        # Spoji WAV-ove u jedan WAV
        ch_wav = CHAPTERS_DIR / f"{part}.wav"
        if not ch_wav.exists() or ch_wav.stat().st_size < 10000:
            lst = part_chunks / "list.txt"
            with open(lst, "w") as f:
                for cf in chunk_files:
                    f.write(f"file '{cf}'\n")
            subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(ch_wav)],
                           check=True, capture_output=True, timeout=300)

        # === GLAVNA IZMENA: PRAVI LISTEN MP3 SA ID3 TAGOVIMA ===
        listen_mp3 = LISTEN_DIR / f"{chapter_num:03d} - {safe_title}.mp3"
        if not listen_mp3.exists() or listen_mp3.stat().st_size < 5000:
            print(f"  Pretvaram u MP3 sa tagovima...")
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(ch_wav),
                    "-metadata", f"title={title}",
                    "-metadata", f"artist={BOOK_AUTHOR}",
                    "-metadata", f"album={BOOK_TITLE}",
                    "-metadata", f"album_artist={BOOK_AUTHOR}",
                    "-metadata", f"track={chapter_num}/{len(parts_to_process)}",
                    "-metadata", "genre=Audiobook",
                    "-metadata", f"comment=Izvorno poglavlje: {part}",
                    "-codec:a", "libmp3lame", "-b:a", "128k",
                    str(listen_mp3)
                ], check=True, capture_output=True, timeout=300)
                dur = get_duration(listen_mp3)
                mins = int(dur // 60); secs = int(dur % 60)
                size_mb = listen_mp3.stat().st_size / 1024 / 1024
                print(f"  \u2705 SPREMNO ZA SLUSANJE: {listen_mp3.name}")
                print(f"     ({mins}:{secs:02d}, {size_mb:.1f} MB)")
            except subprocess.CalledProcessError as e:
                print(f"  \u274c MP3 greska: {e.stderr.decode()[:200]}")
                continue
        else:
            print(f"  \u2705 Vec postoji: {listen_mp3.name}")

    # === FINALNI MERGE (opciono) ===
    if SKIP_FINAL_MERGE:
        print(f"\n\u2705 SKIP_FINAL_MERGE=1 — preskacem finalno spajanje.")
    else:
        print("\n" + "=" * 70)
        print("Pravim finalni M4B sa poglavljima (moze potrajati 5-10 min)...")
        chapter_mp3s = sorted(LISTEN_DIR.glob("*.mp3"))
        if not chapter_mp3s:
            print("Nema MP3-ova, prekidam."); sys.exit(1)

        concat_file = OUT_DIR / "concat_all.txt"
        with open(concat_file, "w") as f:
            for mp3 in chapter_mp3s:
                f.write(f"file '{mp3}'\n")

        meta_file = OUT_DIR / "chapters_meta.txt"
        with open(meta_file, "w") as f:
            f.write(";FFMETADATA1\n")
            current_ms = 0
            for mp3 in chapter_mp3s:
                dur = get_duration(mp3)
                start, end = current_ms, current_ms + int(dur * 1000)
                # Naslov iz imena fajla "001 - Naslov.mp3"
                m = re.match(r"\d+ - (.+)\.mp3", mp3.name)
                chapter_title = m.group(1) if m else mp3.stem
                f.write(f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle={chapter_title}\n")
                current_ms = end

        m4b = OUT_DIR / "TWOC.m4b"
        try:
            subprocess.run(["ffmpeg", "-y",
                            "-f", "concat", "-safe", "0", "-i", str(concat_file),
                            "-i", str(meta_file),
                            "-map_metadata", "1",
                            "-c:a", "aac", "-b:a", "128k",
                            "-metadata", f"title={BOOK_TITLE}",
                            "-metadata", f"artist={BOOK_AUTHOR}",
                            "-metadata", "genre=Audiobook",
                            str(m4b)],
                           check=True, capture_output=True, timeout=3600)
            print(f"\u2705 M4B: {m4b} ({m4b.stat().st_size/1024/1024:.1f} MB)")
        except subprocess.CalledProcessError as e:
            print(f"\u274c M4B greska: {e.stderr.decode()[:300]}")

    print("\n" + "=" * 70)
    print("ZAVRSENO!")
    print(f"Listen folder (po poglavljima): {LISTEN_DIR}")
    print("=" * 70)

if __name__ == "__main__":
    main()
