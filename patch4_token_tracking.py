#!/usr/bin/env python3
"""
PATCH 4: Token tracking fix — mapirati Gemini usageMetadata.totalTokenCount
Fajl: network/rate_limiter.py

PROBLEM:
  _extract_total_tokens() gleda samo body["usage"]["total_tokens"] (OpenAI format).
  Gemini native endpoint vraća tokene u:
    body["usageMetadata"]["totalTokenCount"]
    (a komponente: promptTokenCount + candidatesTokenCount)

  Bez ovoga, Gemini token potrošnja nije evidentirana, tpm_gap je uvijek 0,
  i rate_limiter ne može prilagoditi gap po stvarnoj potrošnji.

ISPRAVKA:
  Proširiti _extract_total_tokens() da proba oba formata:
  1. Gemini: usageMetadata.totalTokenCount
  2. OpenAI: usage.total_tokens (ili prompt+completion)
  3. Cohere: meta.tokens.input_tokens + output_tokens
"""

import sys
from pathlib import Path

TARGET = Path("network/rate_limiter.py")

OLD = '''\
def _extract_total_tokens(body) -> float | None:
    if not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if total is None:
        prompt = _to_float(usage.get("prompt_tokens")) or 0.0
        completion = _to_float(usage.get("completion_tokens")) or 0.0
        total = prompt + completion
    return _to_float(total)'''

NEW = '''\
def _extract_total_tokens(body) -> float | None:
    """
    PATCH4: Podržava više response formata za token tracking.
    
    Prioritet:
      1. Gemini native: usageMetadata.totalTokenCount
      2. OpenAI compat: usage.total_tokens (ili prompt+completion)
      3. Cohere v2:     meta.tokens.{input,output}_tokens
    """
    if not isinstance(body, dict):
        return None

    # 1. Gemini native format — usageMetadata.totalTokenCount
    usage_meta = body.get("usageMetadata")
    if isinstance(usage_meta, dict):
        total = _to_float(usage_meta.get("totalTokenCount"))
        if total and total > 0:
            return total
        # Fallback: zbroj komponenti ako totalTokenCount nije prisutan
        prompt = _to_float(usage_meta.get("promptTokenCount")) or 0.0
        candidates = _to_float(usage_meta.get("candidatesTokenCount")) or 0.0
        if prompt > 0 or candidates > 0:
            return prompt + candidates

    # 2. OpenAI compat format — usage.total_tokens
    usage = body.get("usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            prompt = _to_float(usage.get("prompt_tokens")) or 0.0
            completion = _to_float(usage.get("completion_tokens")) or 0.0
            total = prompt + completion
        result = _to_float(total)
        if result and result > 0:
            return result

    # 3. Cohere v2 format — meta.tokens
    meta = body.get("meta")
    if isinstance(meta, dict):
        tokens = meta.get("tokens")
        if isinstance(tokens, dict):
            inp = _to_float(tokens.get("input_tokens")) or 0.0
            out = _to_float(tokens.get("output_tokens")) or 0.0
            if inp > 0 or out > 0:
                return inp + out

    return None'''

def apply(root: Path = Path(".")):
    path = root / TARGET
    if not path.exists():
        print(f"[PATCH4] ❌  Fajl nije nađen: {path}")
        sys.exit(1)

    src = path.read_text(encoding="utf-8")

    if "PATCH4" in src or "usageMetadata" in src:
        print("[PATCH4] ✅  Već primijenjeno — preskačem.")
        return

    if OLD not in src:
        print("[PATCH4] ❌  Stari kod nije nađen. Provjeri ručno:")
        for i, line in enumerate(src.splitlines(), 1):
            if "_extract_total_tokens" in line:
                print(f"         Linija {i}: {line}")
        sys.exit(1)

    patched = src.replace(OLD, NEW, 1)
    path.write_text(patched, encoding="utf-8")
    print(f"[PATCH4] ✅  Primijenjeno: token tracking + Gemini usageMetadata  ({path})")

if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    apply(root)
