"""
Globalni Few-Shot — uči iz svih obrađenih knjiga.
BEZ DEGRADACIJE: koristi se samo za NOVE chunkove, ne mijenja postojeće.
"""

import json, re
from pathlib import Path
from difflib import SequenceMatcher

FEW_SHOT_PATH = Path("data/few_shot_global.json")
MAX_SHOTS = 200
MIN_SCORE = 9.0       # BEZ DEGRADACIJE: samo odlični (9+) idu u bazu
MIN_SIMILARITY = 0.75 # koliko sličan mora biti chunk da se few-shot primijeni

def _norm(s):
    return re.sub(r'\s+', ' ', s).strip().lower()

def _similarity(a, b):
    return SequenceMatcher(None, _norm(a)[:300], _norm(b)[:300]).ratio()

def load_shots():
    if FEW_SHOT_PATH.exists():
        return json.loads(FEW_SHOT_PATH.read_text())
    return []

def save_shots(shots):
    FEW_SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEW_SHOT_PATH.write_text(json.dumps(shots, ensure_ascii=False, indent=2))

def dodaj_odlican_prevod(en_text, bs_text, score, tip_bloka):
    """Dodaje prevod u globalnu bazu. BEZ DEGRADACIJE: samo score >= 9.0"""
    if score < MIN_SCORE:
        return
    if not en_text or not bs_text:
        return
    shots = load_shots()
    # Provjeri da nije duplikat
    en_norm = _norm(en_text)[:200]
    for s in shots:
        if _similarity(en_norm, s["en"]) > 0.90:
            return  # već imamo sličan primjer
    
    shots.append({
        "en": en_text[:500],
        "bs": bs_text[:500],
        "score": score,
        "tip": tip_bloka,
    })
    shots.sort(key=lambda x: x["score"], reverse=True)
    shots = shots[:MAX_SHOTS]
    save_shots(shots)

def pronadji_slicne(en_text, tip_bloka=None, max_n=3):
    """Vraća top N sličnih primjera iz baze za zadati tekst."""
    shots = load_shots()
    if tip_bloka:
        shots = [s for s in shots if s.get("tip") == tip_bloka]
    if not shots:
        return []
    
    scored = [(s, _similarity(en_text, s["en"])) for s in shots]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s for s, sim in scored[:max_n] if sim >= MIN_SIMILARITY]

def formatiraj_za_prompt(en_text, tip_bloka=None, max_n=3):
    """Formatira few-shot primjere za ubacivanje u prompt."""
    primjeri = pronadji_slicne(en_text, tip_bloka, max_n)
    if not primjeri:
        return ""
    
    lines = ["\nPRIMJERI SLIČNIH PREVODA (iz prethodnih knjiga):"]
    for i, p in enumerate(primjeri, 1):
        lines.append(f"{i}. EN: {p['en'][:150]}...")
        lines.append(f"   BS: {p['bs'][:150]}...")
    return "\n".join(lines)

def broj_primjera():
    return len(load_shots())
