# -*- coding: utf-8 -*-
"""processing/verifier_hook.py — P2.1 hook: shadow verifikator EN vs HR po bloku.

Ukljucen samo uz BOOKLYFI_VERIFIER=1. NE mijenja ocjenu bloka; rezultat ide u
quality_verifier.json ({"verifier": "ok"} | {"verifier": "flags", ...} |
{"verifier": "skip", ...}). Greska ovdje nikad ne smije srusiti pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def ukljucen() -> bool:
    return os.environ.get("BOOKLYFI_VERIFIER", "") == "1"


def sazetak(res: dict) -> dict:
    status = res.get("status", "")
    if status == "ok":
        return {"verifier": "ok"}
    if status == "greske":
        g = res.get("greske") or []
        return {"verifier": "flags", "n": len(g), "score": res.get("score"), "greske": g}
    return {"verifier": "skip", "status": status, "error": res.get("error", "")}


async def verifikuj_blok(self, finalno, original_chunk, stem_key, chunk_idx,
                         file_name, tip_bloka, glosar=None):
    if not ukljucen():
        return None
    if not isinstance(original_chunk, str) or not original_chunk.strip():
        return None
    if not isinstance(finalno, str) or not finalno.strip():
        return None
    try:
        from core.verifier import provjeri_blok_async

        async def _fleet(prompt, sys_p):
            return await self._call_ai_engine(
                prompt, chunk_idx, uloga="VERIFIER", filename=file_name,
                sys_override=sys_p, tip_bloka=tip_bloka,
            )

        res = await provjeri_blok_async(original_chunk, finalno, glosar or {}, fleet=_fleet)
        out = sazetak(res)
        p = self.checkpoint_dir / "quality_verifier.json"
        with _LOCK:
            ex = {}
            if p.exists():
                try:
                    ex = json.loads(p.read_text("utf-8"))
                except Exception:
                    logger.exception("[P2.1] quality_verifier.json nečitljiv, počinjem iznova")
                    ex = {}
            ex[stem_key] = out
            self._atomic_write(p, json.dumps(ex, ensure_ascii=False, indent=2))
        if out["verifier"] == "flags":
            self.log(
                f"[{file_name}] Blok {chunk_idx}: 🔎 verifikator: {out['n']} sumnji "
                f"(score={out.get('score')})",
                "warning",
            )
        return out
    except Exception:
        logger.exception("[P2.1] verifier hook")
        return None
