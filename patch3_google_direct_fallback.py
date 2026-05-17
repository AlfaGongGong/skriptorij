#!/usr/bin/env python3
"""
PATCH 3: Direktni Google URL fallback kad CF Worker vrati 429
Fajl: network/http_client.py  +  network/provider_urls.py

PROBLEM:
  Svi Gemini pozivi idu kroz Cloudflare Worker proxy
  (booklyfi.jasenkobozinovic.workers.dev). Ako Worker sam dobije rate limit
  (429) ili padne, svi Gemini pozivi propadaju iako Google API sam po sebi
  ima kvotu.

ISPRAVKA:
  1. provider_urls.py — dodati GEMINI_DIRECT_BASE_URL i get_gemini_direct_url()
  2. http_client.py — u _call_gemini_with_full_rotation(), ako _async_http_post
     vrati None I ks.available=True (ključ OK, možda Worker problem), pokušaj
     s direktnim URL-om kao fallback.

  Direktni URL: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  (isti endpoint koji već postoji u get_url("GEMINI") kao legacy)
"""

import sys
from pathlib import Path

# ─── ISPRAVKA 1: provider_urls.py ────────────────────────────────────────────

URLS_TARGET = Path("network/provider_urls.py")

URLS_OLD = '''\
GEMINI_BASE_URL = "https://booklyfi.jasenkobozinovic.workers.dev"

def get_gemini_url(model: str) -> str:
    """
    Vraća native Gemini endpoint s ugrađenim modelom, kroz Cloudflare Worker proxy.
    Native endpoint podržava free tier (za razliku od /v1beta/openai/ koji zahtijeva billing).
    Worker transparentno proslijeđuje zahtjev Googleu sa svoje IP adrese.
    """
    return f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent"'''

URLS_NEW = '''\
GEMINI_BASE_URL = "https://booklyfi.jasenkobozinovic.workers.dev"
GEMINI_DIRECT_BASE_URL = "https://generativelanguage.googleapis.com"  # PATCH3: direktni fallback

def get_gemini_url(model: str) -> str:
    """
    Vraća native Gemini endpoint kroz Cloudflare Worker proxy.
    Primarni URL — Worker zaobilazi IP blokade prema Googleu.
    """
    return f"{GEMINI_BASE_URL}/v1beta/models/{model}:generateContent"

def get_gemini_direct_url(model: str) -> str:
    """
    PATCH3: Direktni Google API URL (fallback kad Worker vrati 429/pade).
    Bez proxy-ja — može biti blokiran za neke IP-ove ali vrijedi probati.
    """
    return f"{GEMINI_DIRECT_BASE_URL}/v1beta/models/{model}:generateContent"'''

# ─── ISPRAVKA 2: http_client.py ───────────────────────────────────────────────

HTTP_TARGET = Path("network/http_client.py")

# Tražimo blok unutar _call_gemini_with_full_rotation gdje se provjerava ks.available
# Dodajemo direktni fallback pokušaj
HTTP_OLD = '''\
            if data is not None:
                content = _extract_gemini_native(data)
                if content:
                    return content, f"GEMINI-{current_model}"
                # data vraćen ali prazan sadržaj (SAFETY filter itd.) → sljedeći model
            
            # Ako je ključ ušao u cooldown (429/kvota/500) → sljedeći ključ
            if not ks.available:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} u cooldownu — preskačem na sljedeći ključ",
                    "warning",
                )
                break'''

HTTP_NEW = '''\
            if data is not None:
                content = _extract_gemini_native(data)
                if content:
                    return content, f"GEMINI-{current_model}"
                # data vraćen ali prazan sadržaj (SAFETY filter itd.) → sljedeći model

            # PATCH3: Direktni Google URL fallback ako Worker nije odgovoran za fail
            # Pokušavamo direktni URL samo ako ključ nije u cooldownu
            # (cooldown = Google problem; bez cooldowna = možda Worker problem)
            elif ks.available:
                from network.provider_urls import get_gemini_direct_url
                direct_url = f"{get_gemini_direct_url(current_model)}?key={key}"
                self.log(
                    f"[GEMINI] Worker fallback — probam direktni Google URL za {current_model}",
                    "warning",
                )
                data_direct = await _async_http_post(
                    self, direct_url, headers, payload, "GEMINI", "GEMINI", key, _proxy=None
                )
                if data_direct is not None:
                    content = _extract_gemini_native(data_direct)
                    if content:
                        return content, f"GEMINI-direct-{current_model}"

            # Ako je ključ ušao u cooldown (429/kvota/500) → sljedeći ključ
            if not ks.available:
                self.log(
                    f"[GEMINI] Ključ ...{key[-4:]} u cooldownu — preskačem na sljedeći ključ",
                    "warning",
                )
                break'''

def apply(root: Path = Path(".")):
    errors = []

    # --- provider_urls.py ---
    urls_path = root / URLS_TARGET
    if not urls_path.exists():
        errors.append(f"[PATCH3] ❌  Fajl nije nađen: {urls_path}")
    else:
        src = urls_path.read_text(encoding="utf-8")
        if "PATCH3" in src or "get_gemini_direct_url" in src:
            print("[PATCH3a] ✅  provider_urls.py već patchiran — preskačem.")
        elif URLS_OLD not in src:
            errors.append("[PATCH3a] ❌  Stari kod u provider_urls.py nije nađen.")
        else:
            patched = src.replace(URLS_OLD, URLS_NEW, 1)
            urls_path.write_text(patched, encoding="utf-8")
            print(f"[PATCH3a] ✅  provider_urls.py: dodan get_gemini_direct_url()")

    # --- http_client.py ---
    http_path = root / HTTP_TARGET
    if not http_path.exists():
        errors.append(f"[PATCH3] ❌  Fajl nije nađen: {http_path}")
    else:
        src = http_path.read_text(encoding="utf-8")
        if "PATCH3" in src:
            print("[PATCH3b] ✅  http_client.py već patchiran — preskačem.")
        elif HTTP_OLD not in src:
            errors.append("[PATCH3b] ❌  Stari kod u http_client.py nije nađen.")
        else:
            patched = src.replace(HTTP_OLD, HTTP_NEW, 1)
            http_path.write_text(patched, encoding="utf-8")
            print(f"[PATCH3b] ✅  http_client.py: dodan direktni URL fallback")

    if errors:
        for e in errors:
            print(e)
        sys.exit(1)

if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    apply(root)
