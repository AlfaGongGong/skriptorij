#!/usr/bin/env python3
"""Periodično osvježavanje keša modela (pokreće se svakih 12 sati)."""
import json
import time
import requests
from pathlib import Path

def update_model_cache():
    cache_file = Path("openrouter_models_cache.json")
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            free_models = {}
            for model in data.get("data", []):
                if ":free" in model["id"]:
                    provider = model["id"].split("/")[0].upper()
                    if provider not in free_models:
                        free_models[provider] = []
                    free_models[provider].append({
                        "id": model["id"],
                        "name": model.get("name", model["id"]),
                        "context_length": model.get("context_length", 4096),
                    })
            with open(cache_file, 'w') as f:
                json.dump({"timestamp": time.time(), "models": free_models}, f, indent=2)
            print(f"✅ Model keš ažuriran: {sum(len(v) for v in free_models.values())} modela")
    except Exception as e:
        print(f"⚠️ Greška pri ažuriranju modela: {e}")

if __name__ == "__main__":
    update_model_cache()
