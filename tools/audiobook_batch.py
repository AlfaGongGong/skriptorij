#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch generator audiobooka iz .chk fajlova.
- Grupise .chk po poglavljima (partNNNN.html)
- Za svako poglavlje generise audio preko Gemini TTS
- Spaja u jedan M4B sa chapterima (ako ffmpeg podrzava), inace MP3
"""
import os, sys, json, re, time, subprocess, shutil
from pathlib import Path


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

# --- Podesavanja ---
CK_DIR = Path("/storage/emulated/0/booklyfi_checkpoints/_skr_The_Wisdom_of_Crowds/checkpoints")
OUT_DIR = Path("/storage/emulated/0/Download/BOOKLYFI_AUDIOBOOK")
TMP_DIR = OUT_DIR / "_tmp"
API_KEY = _tts_key(4)  # zameni ako zelis
MODEL = "gemini-3.1-flash-tts-preview"
VOICE = "Charon"
SAMPLE_RATE = 24000
MAX_CHARS = 800  # podeli tekst na delove od ~800 karaktera

# --- 1. Grupisi .chk po poglavljima ---
def grupisi_chk():
    poglavlja = {}
    for p in CK_DIR.glob("*.chk"):
        if p.name.endswith((".prevod.chk", ".lektura.chk")):
            continue
        m = re.match(r"(part\d+\.html)_blok_(\d+)\.chk", p.name)
        if not m:
            continue
        part = m.group(1)
        idx = int(m.group(2))
        poglavlja.setdefault(part, []).append((idx, p))
    # Sortiraj blokove unutar svakog poglavlja
    for part in poglavlja:
        poglavlja[part].sort(key=lambda x: x[0])
    return poglavlja

# --- 2. Izvuci cist tekst iz .chk ---
def cist_tekst(chk_path):
    t = chk_path.read_text("utf-8")
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# --- 3. Generisi audio za deo teksta preko Gemini ---
def generisi_audio(tekst, idx_dela, out_wav):
    import urllib.request, urllib.error
    body = {
        "contents": [{"parts": [{"text": tekst}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  HTTP greska: {e.code}")
        return False

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for p in parts:
        if "inlineData" in p and p["inlineData"].get("data"):
            import base64
            pcm = base64.b64decode(p["inlineData"]["data"])
            # Snimi kao WAV
            import wave
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(pcm)
            return True
    print("  Nema audio u odgovoru.")
    return False

# --- 4. Glavna funkcija ---
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    poglavlja = grupisi_chk()
    print(f"Pronadjeno poglavlja: {len(poglavlja)}")

    # Za svako poglavlje, generisi audio
    for part in sorted(poglavlja.keys()):
        blokovi = poglavlja[part]
        print(f"\n=== Poglavlje: {part} ({len(blokovi)} blokova) ===")
        # Spoji tekst svih blokova
        full_text = " ".join(cist_tekst(p) for _, p in blokovi)
        # Podeli na delove
        delovi = [full_text[i:i+MAX_CHARS] for i in range(0, len(full_text), MAX_CHARS)]
        print(f"  Delova: {len(delovi)}")

        # Generisi audio za svaki deo
        wav_files = []
        for i, deo in enumerate(delovi):
            wav_out = TMP_DIR / f"{part}_deo_{i:03d}.wav"
            if wav_out.exists():
                print(f"  Deo {i+1}/{len(delovi)} vec postoji, preskacem.")
                wav_files.append(wav_out)
                continue
            print(f"  Generisem deo {i+1}/{len(delovi)}...")
            if generisi_audio(deo, i, wav_out):
                wav_files.append(wav_out)
            else:
                print(f"  Greska na delu {i+1}. Preskacem poglavlje.")
                break
            time.sleep(1)  # da ne prekoracimo RPM

        if len(wav_files) != len(delovi):
            print(f"  Poglavlje {part} nije kompletno, preskacem spajanje.")
            continue

        # Spoji WAV-ove u jedan WAV za poglavlje
        poglavlje_wav = OUT_DIR / f"{part}.wav"
        if len(wav_files) == 1:
            shutil.copy(wav_files[0], poglavlje_wav)
        else:
            # Napravi fajl listu za ffmpeg concat
            list_file = TMP_DIR / f"{part}_lista.txt"
            with open(list_file, "w") as f:
                for w in wav_files:
                    f.write(f"file '{w}'\n")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(poglavlje_wav)],
                check=True, capture_output=True
            )
        print(f"  Sacuvano: {poglavlje_wav}")

    # --- 5. Napravi M4B sa chapterima (ako ima ffmpeg i ffprobe) ---
    # Za sada samo MP3 spoj svih poglavlja
    print("\n=== Spajam sve u jedan MP3 ===")
    mp3_out = OUT_DIR / "The_Wisdom_of_Crowds.mp3"
    wav_list = sorted(OUT_DIR.glob("part*.wav"))
    if wav_list:
        list_file = TMP_DIR / "svi_delovi.txt"
        with open(list_file, "w") as f:
            for w in wav_list:
                f.write(f"file '{w}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:a", "libmp3lame", "-b:a", "128k", str(mp3_out)],
            check=True, capture_output=True
        )
        print(f"✅ Gotovo: {mp3_out}")
    else:
        print("Nema WAV fajlova za spajanje.")

if __name__ == "__main__":
    main()
