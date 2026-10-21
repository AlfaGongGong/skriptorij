#!/usr/bin/env python3
"""Dijagnostika: probudi Gemmu. Ne dira produkcijski kod.
Troši: GET /models za sve ključeve (0 kvote) + 1 generateContent (1 kvota).
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _mask(key: str) -> str:
    return f"...{key[-4:]}" if len(key) > 4 else "????"


def _load_keys() -> list[str]:
    """Gemma ključevi — FleetManager, pa ai_config, pa env."""
    out: list[str] = []
    try:
        from api_fleet import FleetManager
        fm = FleetManager()
        fleet = getattr(fm, "fleet", None)
        if isinstance(fleet, dict):
            gemma = fleet.get("GEMMA")
            if isinstance(gemma, list):
                for ks in gemma:
                    k = getattr(ks, "key", None)
                    if isinstance(k, str) and k.strip():
                        out.append(k)
    except Exception as e:
        print(f"[!] FleetManager: {e}")

    if not out:
        try:
            from config import ai_config
            for attr in dir(ai_config):
                if "GEMMA" in attr.upper() and "KEY" in attr.upper():
                    val = getattr(ai_config, attr)
                    if isinstance(val, list):
                        out.extend(v for v in val if isinstance(v, str))
        except Exception as e:
            print(f"[!] ai_config: {e}")

    if not out:
        for name in os.environ:
            if "GEMMA" in name.upper() and "KEY" in name.upper():
                out.append(os.environ[name])

    seen: set[str] = set()
    clean: list[str] = []
    for k in out:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            clean.append(k)
    return clean


def _load_model() -> str | None:
    """Gemma model — model_discovery, pa ai_config. NIKAD hardkod (P12)."""
    try:
        from network import model_discovery
        for fn_name in ("get_models", "models_for", "discover", "get_for_provider"):
            fn = getattr(model_discovery, fn_name, None)
            if callable(fn):
                try:
                    res = fn("GEMMA")
                except TypeError:
                    try:
                        res = fn("GEMMA", None)
                    except Exception:
                        continue
                except Exception:
                    continue
                if isinstance(res, list) and res:
                    return res[0]
                if isinstance(res, str):
                    return res
    except Exception as e:
        print(f"[!] model_discovery: {e}")

    try:
        from config import ai_config
        mm = getattr(ai_config, "MODEL_MAP", None)
        if isinstance(mm, dict):
            for k, v in mm.items():
                if "GEMMA" in str(k).upper():
                    if isinstance(v, list) and v:
                        return v[0]
                    if isinstance(v, str):
                        return v
        strings = getattr(ai_config, "AI_MODEL_STRINGS", None)
        if isinstance(strings, dict):
            for k, v in strings.items():
                if "GEMMA" in str(k).upper() and isinstance(v, str):
                    return v
    except Exception as e:
        print(f"[!] ai_config.MODEL_MAP: {e}")

    return None


async def main() -> int:
    try:
        import httpx
    except ImportError:
        print("[!] httpx nije instaliran.")
        return 1

    keys = _load_keys()
    model = _load_model()
    print(f"=== Gemma ključeva: {len(keys)} ===")
    print(f"=== Gemma model   : {model!r} ===")
    if not keys:
        print("[!] Nijedan Gemma ključ nije nađen.")
        print("    Reci mi tačan naziv polja u FleetManager.")
        return 2
    if not model:
        print("[!] Gemma model nije nađen.")
        print("    Reci mi tačan naziv polja (MODEL_MAP? AI_MODEL_STRINGS?).")
        return 3

    print()
    valid_key: str | None = None
    async with httpx.AsyncClient() as c:
        for i, k in enumerate(keys, 1):
            url = f"{GEMINI_BASE}/models?key={k}"
            try:
                r = await c.get(url, timeout=20)
                if r.status_code == 200:
                    print(f"  #{i} {_mask(k)}: GET /models 200 OK")
                    if valid_key is None:
                        valid_key = k
                else:
                    try:
                        msg = r.json().get("error", {}).get("message", r.text[:150])
                    except Exception:
                        msg = r.text[:150]
                    print(f"  #{i} {_mask(k)}: GET /models {r.status_code} FAIL — {msg}")
            except Exception as e:
                print(f"  #{i} {_mask(k)}: GET /models EXC — {type(e).__name__}: {e}")

        if valid_key:
            print(f"\n=== Test generacije na {_mask(valid_key)} ===")
            url = f"{GEMINI_BASE}/models/{model}:generateContent?key={valid_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": "Odgovori jednom riječju: OK"}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 10},
            }
            try:
                r = await c.post(url, json=payload, timeout=30)
                print(f"  HTTP status: {r.status_code}")
                try:
                    data = r.json()
                except Exception:
                    print(f"  Body (raw): {r.text[:300]}")
                    return 0
                fb = data.get("promptFeedback", {}) or {}
                if fb.get("blockReason"):
                    print(f"  blockReason: {fb['blockReason']}")
                cands = data.get("candidates", []) or []
                if cands:
                    print(f"  finishReason: {cands[0].get('finishReason')}")
                    parts = cands[0].get("content", {}).get("parts", []) or []
                    txt = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                    print(f"  text: {txt!r}")
                if r.status_code != 200:
                    err = data.get("error", {}) or {}
                    print(f"  error.status: {err.get('status')}")
                    print(f"  error.message: {err.get('message')}")
            except Exception as e:
                print(f"  EXC: {type(e).__name__}: {e}")
        else:
            print("\n[!] Nijedan ključ nije validan — generacija se ne može testirati.")
            return 4

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
