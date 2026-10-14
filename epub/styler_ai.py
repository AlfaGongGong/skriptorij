"""epub/styler_ai.py — Wrapper oko stil_ai.py (subprocess)."""
import subprocess
import sys
from pathlib import Path

STIL_AI_PATH = "/root/skriptorij/stil_ai.py"


def run_epub_styler_ai(epub_path, output_path=None, log_callback=None, bez_ai=False):
    """
    Pokreni stil_ai.py na EPUB-u kao subprocess.
    
    Args:
        epub_path: Path ili str do EPUB-a
        output_path: ako je zadano, kopiraj rezultat tamo
        log_callback: funkcija(msg, type) za streaming log
        bez_ai: ako True, dodaj --bez-ai flag
    
    Returns: dict {ok, error, output, log, chapters, mode}
    """
    epub_path = Path(epub_path)
    if not epub_path.exists():
        return {"ok": False, "error": f"EPUB ne postoji: {epub_path}"}
    
    if not Path(STIL_AI_PATH).exists():
        return {"ok": False, "error": f"stil_ai.py ne postoji: {STIL_AI_PATH}"}
    
    cmd = [sys.executable, STIL_AI_PATH, str(epub_path)]
    if bez_ai:
        cmd.append("--bez-ai")
    
    if log_callback:
        log_callback(f"Pokrećem AI stilizaciju: {epub_path.name}", "info")
    
    # Pokreni s live output
    lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd="/root/skriptorij",
        )
        
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            lines.append(line)
            if log_callback:
                # Detektiraj razinu
                lvl = "info"
                low = line.lower()
                if "greska" in low or "error" in low or "❌" in line:
                    lvl = "error"
                elif "upozorenje" in low or "⚠" in line:
                    lvl = "warn"
                elif "✅" in line or "gotovo" in low:
                    lvl = "success"
                log_callback(line, lvl)
        
        proc.wait(timeout=1800)  # 30 min max
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"ok": False, "error": "Stilizacija prekinuta (timeout 30 min)",
                "log": "\n".join(lines[-50:])}
    except Exception as e:
        return {"ok": False, "error": f"Subprocess greška: {e}",
                "log": "\n".join(lines[-50:])}
    
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"stil_ai.py vratio kod {proc.returncode}",
            "log": "\n".join(lines[-50:]),
        }
    
    # Ako je output_path zadan i različit — kopiraj
    final_path = epub_path
    if output_path:
        output_path = Path(output_path)
        if output_path != epub_path:
            import shutil
            shutil.copy2(epub_path, output_path)
            final_path = output_path
    
    # Izvuci statistiku iz loga
    chapters = 0
    for line in lines:
        m = __import__("re").match(r"\[(\d+)/(\d+)\]", line)
        if m:
            chapters = max(chapters, int(m.group(2)))
    
    return {
        "ok": True,
        "output": str(final_path),
        "epub_path": str(final_path),
        "chapters": chapters,
        "mode": "ai",
        "log": "\n".join(lines[-50:]),
    }
