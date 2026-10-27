"""
EpubStylerManager facade module (epub/manager.py)
Unified manager za kontrolu i koordinaciju stilizovanja EPUB dokumenata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Callable, Optional
from epub.styler import EpubStyler


class EpubStylerManager:
    def __init__(
        self,
        epub_path: Path | str,
        log_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.epub_path = Path(epub_path)
        self.log_callback = log_callback or (lambda msg, atype="info": print(f"[{atype.upper()}] {msg}"))

    def log(self, message: str, atype: str = "info") -> None:
        if self.log_callback:
            self.log_callback(message, atype)

    def stilizuj(self, mode: str = "standard") -> Dict[str, Any]:
        self.log(f"EpubStylerManager: Inicijalizacija obrade u modu [{mode}]", "info")
        
        valid_modes = {"standard", "ai", "booklyfi"}
        if mode not in valid_modes:
            err_msg = f"Nepoznat mode: '{mode}'. Dozvoljeni modovi su: {valid_modes}"
            self.log(err_msg, "error")
            return {
                "ok": False,
                "mode": mode,
                "epub_path": str(self.epub_path),
                "chapters": 0,
                "error": err_msg
            }

        try:
            styler_engine = EpubStyler(
                epub_path=self.epub_path,
                log_callback=self.log_callback
            )
            
            result = styler_engine.stilizuj(mode=mode)
            
            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "mode": mode,
                    "epub_path": str(self.epub_path),
                    "chapters": 0,
                    "error": "Core styler je vratio nevažeći format odgovora."
                }
                
            return result

        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            self.log(f"EpubStylerManager izuzetak: {err_msg}", "error")
            return {
                "ok": False,
                "mode": mode,
                "epub_path": str(self.epub_path),
                "chapters": 0,
                "error": err_msg
            }


def style_epub(
    epub_path: Path | str,
    mode: str = "standard",
    log_callback: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    manager = EpubStylerManager(epub_path=epub_path, log_callback=log_callback)
    return manager.stilizuj(mode=mode)
