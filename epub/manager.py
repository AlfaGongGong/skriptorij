"""
EpubStylerManager facade module (epub/manager.py)
Unified manager za kontrolu i koordinaciju stilizovanja EPUB dokumenata.

Zove run_epub_styler iz epub.styler. Jedan mod — nema više standard/ai/booklyfi.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional


class EpubStylerManager:
    def __init__(
        self,
        epub_path: Path | str,
        output_path: Optional[Path | str] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        options: Optional[dict] = None,
        fleet: Optional[Any] = None
    ):
        self.epub_path = Path(epub_path)
        self.output_path = Path(output_path) if output_path else None
        self.log_callback = log_callback or (lambda msg, atype="info": print(f"[{atype.upper()}] {msg}"))
        self.options = options or {}
        self.fleet = fleet

    def log(self, message: str, atype: str = "info") -> None:
        if self.log_callback:
            self.log_callback(message, atype)

    def stilizuj(self, *args, **kwargs):
        """Omotač: iza stilizacije čisti mrtve slike i linkove (P2.10, P2.11)."""
        r = self._stilizuj_bez_ciscenja(*args, **kwargs)
        try:
            import os as _os
            p = r.get("epub_path") if isinstance(r, dict) else None
            if p and _os.path.isfile(str(p)):
                from epub.ocisti import ocisti_epub
                r["ocisceno"] = ocisti_epub(p)
        except Exception as _e:
            print("[ocisti] greška:", _e)
        return r

    def _stilizuj_bez_ciscenja(self, options: Optional[dict] = None) -> Dict[str, Any]:
        self.log(f"EpubStylerManager: {self.epub_path.name}", "info")

        try:
            from epub.styler import run_epub_styler

            merged_options = {**self.options, **(options or {})}
            result = run_epub_styler(
                epub_path=self.epub_path,
                output_path=self.output_path,
                fleet=self.fleet,
                log_callback=self.log_callback,
                options=merged_options
            )

            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "epub_path": str(self.epub_path),
                    "chapters": 0,
                    "error": "run_epub_styler vratio nevažeći format odgovora."
                }

            return result

        except Exception as e:
            err_msg = f"{type(e).__name__}: {str(e)}"
            self.log(f"EpubStylerManager izuzetak: {err_msg}", "error")
            return {
                "ok": False,
                "epub_path": str(self.epub_path),
                "chapters": 0,
                "error": err_msg
            }


def style_epub(
    epub_path: Path | str,
    output_path: Optional[Path | str] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
    options: Optional[dict] = None
) -> Dict[str, Any]:
    manager = EpubStylerManager(
        epub_path=epub_path,
        output_path=output_path,
        log_callback=log_callback,
        options=options
    )
    return manager.stilizuj()
