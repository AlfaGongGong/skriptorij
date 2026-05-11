#!/usr/bin/env python3
"""
check_provider.py — Provjera API ključeva i info o provideru
Pokretanje: python3 check_provider.py
"""

import json
import sys
import os
import asyncio
import httpx
from datetime import datetime

# ── Putanje ──────────────────────────────────────────────────────────────────
PROJ = "/storage/emulated/0/termux/Skriptorij"
DEV_API = os.path.join(PROJ, "dev_api.json")

# ── Boje za terminal ──────────────────────────────────────────────────────────
G  = "\033[92m"   # zeleno
R  = "\033[91m"   # crveno
Y  = "\033[93m"   # žuto
B  = "\033[94m"   # plavo
C  = "\033[96m"   # cyan
W  = "\033[97m"   # bijelo
DIM = "\033[2m"   # tamno
BOLD = "\033[1m"
RST = "\033[0m"   # reset

def p(tekst): print(tekst)
def ok(t):    print(f"  {G}✓{RST} {t}")
def err(t):   print(f"  {R}✗{RST} {t}")
def warn(t):  print(f"  {Y}⚠{RST} {t}")
def info(t):  print(f"  {C}→{RST} {t}")
def sep():    print(f"  {DIM}{'─'*60}{RST}")

# ── Provider definicije ───────────────────────────────────────────────────────
# Svaki provider ima:
#   url_chat:      chat/completions endpoint
#   url_models:    endpoint za listu modela (ili None)
#   url_account:   endpoint za info o računu/kreditima (ili None)
#   url_usage:     endpoint za usage stats (ili None)
#   auth_header:   kako se šalje ključ
#   auth_prefix:   prefix ispred ključa ("Bearer", "")
#   model_test:    model za test poziv
#   extra_headers: dodatni headeri (dict ili None)
#   parse_models:  lambda za parsiranje liste modela iz odgovora
#   parse_account: lambda za parsiranje account info
#   parse_usage:   lambda za parsiranje usage

PROVIDERS = {
    "GEMINI": {
        "url_chat":    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "url_models":  "https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "gemini-2.0-flash",
        "extra_headers": None,
        "parse_models": lambda r: [
            m.get("name","?").replace("models/","") + 
            f" [{m.get('supportedGenerationMethods',['?'])[0]}]"
            for m in r.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "GROQ": {
        "url_chat":    "https://api.groq.com/openai/v1/chat/completions",
        "url_models":  "https://api.groq.com/openai/v1/models",
        "url_account": None,
        "url_usage":   "https://api.groq.com/openai/v1/usage",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "llama-3.3-70b-versatile",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')} [ctx:{m.get('context_window','?')}]"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   lambda r: [
            f"Requests today: {r.get('requests_today','?')}",
            f"Tokens today:   {r.get('tokens_today','?')}",
        ],
    },
    "CEREBRAS": {
        "url_chat":    "https://api.cerebras.ai/v1/chat/completions",
        "url_models":  "https://api.cerebras.ai/v1/models",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "llama-3.3-70b",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')}"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "SAMBANOVA": {
        "url_chat":    "https://api.sambanova.ai/v1/chat/completions",
        "url_models":  "https://api.sambanova.ai/v1/models",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "Meta-Llama-3.1-405B-Instruct",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')}"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "MISTRAL": {
        "url_chat":    "https://api.mistral.ai/v1/chat/completions",
        "url_models":  "https://api.mistral.ai/v1/models",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "mistral-large-latest",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')} [owned:{m.get('owned_by','?')}]"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "COHERE": {
        "url_chat":    "https://api.cohere.com/v2/chat",
        "url_models":  "https://api.cohere.com/v2/models",
        "url_account": "https://api.cohere.com/v1/users/me",
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "command-r-plus",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('name','?')} [ctx:{m.get('context_length','?')} "
            f"max_out:{m.get('max_output_tokens','?')}]"
            for m in r.get("models", [])
        ],
        "parse_account": lambda r: [
            f"Name:  {r.get('name','?')}",
            f"Email: {r.get('email','?')}",
            f"Org:   {r.get('organization',{}).get('name','?')}",
            f"Plan:  {r.get('organization',{}).get('plan','?')}",
        ],
        "parse_usage": None,
    },
    "OPENROUTER": {
        "url_chat":    "https://openrouter.ai/api/v1/chat/completions",
        "url_models":  "https://openrouter.ai/api/v1/models",
        "url_account": "https://openrouter.ai/api/v1/auth/key",
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "meta-llama/llama-3.3-70b-instruct:free",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/AlfaGongGong/skriptorij",
            "X-Title": "BooklyFi",
        },
        "parse_models": lambda r: [
            f"{m.get('id','?')} "
            f"[ctx:{m.get('context_length','?')} "
            f"p_in:${float(m.get('pricing',{}).get('prompt',0))*1e6:.4f}/1M "
            f"p_out:${float(m.get('pricing',{}).get('completion',0))*1e6:.4f}/1M]"
            for m in r.get("data", [])
            if float(m.get("pricing", {}).get("prompt", 1)) == 0
        ][:30],  # samo besplatni, max 30
        "parse_account": lambda r: [
            f"Label:    {r.get('data',{}).get('label','?')}",
            f"Krediti:  ${r.get('data',{}).get('limit_remaining', r.get('data',{}).get('usage',0)):.4f}",
            f"Usage:    ${r.get('data',{}).get('usage',0):.4f}",
            f"Limit:    {r.get('data',{}).get('rate_limit',{}).get('requests','?')} req/interval",
            f"Is free:  {r.get('data',{}).get('is_free_tier','?')}",
        ],
        "parse_usage": None,
    },
    "GITHUB": {
        "url_chat":    "https://models.inference.ai.azure.com/chat/completions",
        "url_models":  "https://models.inference.ai.azure.com/models",
        "url_account": "https://api.github.com/user",
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "gpt-4o-mini",
        "extra_headers": {
            "X-GitHub-Api-Version": "2022-11-28",
        },
        "parse_models": lambda r: [
            f"{m.get('id', m.get('name','?'))} "
            f"[{m.get('publisher','?')}]"
            for m in (r if isinstance(r, list) else r.get("data", []))
        ],
        "parse_account": lambda r: [
            f"Login:     {r.get('login','?')}",
            f"Name:      {r.get('name','?')}",
            f"Email:     {r.get('email','?')}",
            f"Plan:      {r.get('plan',{}).get('name','?')}",
            f"Followers: {r.get('followers','?')}",
        ],
        "parse_usage": None,
    },
    "KLUSTER": {
        "url_chat":    "https://api.kluster.ai/v1/chat/completions",
        "url_models":  "https://api.kluster.ai/v1/models",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "klusterai/Meta-Llama-3.1-405B-Instruct-Turbo",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')}"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "CHUTES": {
        "url_chat":    "https://llm.chutes.ai/v1/chat/completions",
        "url_models":  "https://llm.chutes.ai/v1/models",
        "url_account": None,
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "deepseek-ai/DeepSeek-V3-0324",
        "extra_headers": None,
        "parse_models": lambda r: [
            f"{m.get('id','?')}"
            for m in r.get("data", [])
        ],
        "parse_account": None,
        "parse_usage":   None,
    },
    "HUGGINGFACE": {
        "url_chat":    "https://api-inference.huggingface.co/v1/chat/completions",
        "url_models":  None,
        "url_account": "https://huggingface.co/api/whoami-v2",
        "url_usage":   None,
        "auth_header": "Authorization",
        "auth_prefix": "Bearer",
        "model_test":  "mistralai/Mistral-7B-Instruct-v0.3",
        "extra_headers": None,
        "parse_models": None,
        "parse_account": lambda r: [
            f"Name:     {r.get('name','?')}",
            f"Email:    {r.get('email','?')}",
            f"Type:     {r.get('type','?')}",
            f"PRO:      {r.get('isPro', False)}",
            f"Orgs:     {', '.join(o.get('name','?') for o in r.get('orgs',[]))}",
        ],
        "parse_usage": None,
    },
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def get_json(client, url, headers):
    """GET zahtjev, vraća (status_code, dict_or_none)."""
    try:
        r = await client.get(url, headers=headers, timeout=12.0)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"_raw": r.text[:300]}
    except Exception as e:
        return 0, {"_error": str(e)}


async def test_chat(client, url, headers, model):
    """Kratki chat poziv za provjeru da ključ stvarno radi."""
    payload = {
        "model": model,
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "Hi"}],
    }
    try:
        r = await client.post(url, headers=headers, json=payload, timeout=20.0)
        if r.status_code == 200:
            data = r.json()
            tok = data.get("usage", {})
            return True, (
                f"OK — {tok.get('prompt_tokens','?')}p + "
                f"{tok.get('completion_tokens','?')}c tokena"
            )
        else:
            try:
                msg = r.json().get("error", {})
                if isinstance(msg, dict):
                    msg = msg.get("message", r.text[:120])
            except Exception:
                msg = r.text[:120]
            return False, f"HTTP {r.status_code}: {msg}"
    except Exception as e:
        return False, str(e)[:120]


# ── Provjera jednog ključa ────────────────────────────────────────────────────

async def provjeri_kljuc(client, kljuc, cfg, idx, ukupno, provjeri_modele, provjeri_chat):
    masked = kljuc[:8] + "..." + kljuc[-6:]
    print(f"\n  {BOLD}{B}[{idx+1}/{ukupno}]{RST} Ključ: {C}{masked}{RST}")
    sep()

    # Headeri
    headers = {
        cfg["auth_header"]: f"{cfg['auth_prefix']} {kljuc}".strip(),
        "Content-Type": "application/json",
    }
    if cfg.get("extra_headers"):
        headers.update(cfg["extra_headers"])

    # Gemini models endpoint ima key u URL-u, ne u headeru
    url_models = cfg.get("url_models")
    if url_models and "{key}" in url_models:
        url_models = url_models.format(key=kljuc)
        headers_models = {}  # bez auth headera
    else:
        headers_models = headers

    rezultati = {}

    # 1. Chat test
    if provjeri_chat:
        ok_chat, msg_chat = await test_chat(
            client, cfg["url_chat"], headers, cfg["model_test"]
        )
        rezultati["chat"] = (ok_chat, msg_chat)
        if ok_chat:
            ok(f"Chat test:    {msg_chat}")
        else:
            err(f"Chat test:    {msg_chat}")

    # 2. Modeli
    if provjeri_modele and url_models and cfg.get("parse_models"):
        status, data = await get_json(client, url_models, headers_models)
        if status == 200 and "_error" not in data:
            modeli = cfg["parse_models"](data)
            rezultati["modeli"] = modeli
            info(f"Dostupni modeli ({len(modeli)}):")
            for m in modeli[:25]:
                print(f"      {DIM}•{RST} {m}")
            if len(modeli) > 25:
                print(f"      {DIM}... i još {len(modeli)-25} modela{RST}")
        elif status == 401:
            err(f"Modeli: 401 Unauthorized")
        elif status == 429:
            warn(f"Modeli: 429 Rate limit")
        else:
            warn(f"Modeli: HTTP {status}")

    # 3. Account info
    url_acc = cfg.get("url_account")
    if url_acc and cfg.get("parse_account"):
        acc_headers = headers.copy()
        # GitHub account API — treba User-Agent
        if "github" in url_acc.lower():
            acc_headers["User-Agent"] = "BooklyFi/1.0"
        status, data = await get_json(client, url_acc, acc_headers)
        if status == 200 and "_error" not in data:
            acc_info = cfg["parse_account"](data)
            rezultati["account"] = acc_info
            info("Account info:")
            for line in acc_info:
                print(f"      {line}")
        elif status == 401:
            err("Account: 401 Unauthorized")
        elif status == 404:
            warn("Account: endpoint nije dostupan")
        else:
            warn(f"Account: HTTP {status}")

    # 4. Usage
    url_usage = cfg.get("url_usage")
    if url_usage and cfg.get("parse_usage"):
        status, data = await get_json(client, url_usage, headers)
        if status == 200 and "_error" not in data:
            usage_info = cfg["parse_usage"](data)
            info("Usage:")
            for line in usage_info:
                print(f"      {line}")

    return rezultati


# ── Glavni meni ───────────────────────────────────────────────────────────────

def ucitaj_kljuceve():
    if not os.path.exists(DEV_API):
        # Pokušaj lokalnu putanju
        local = "dev_api.json"
        if os.path.exists(local):
            with open(local, "r", encoding="utf-8") as f:
                return json.load(f)
        print(f"{R}GREŠKA: dev_api.json nije pronađen na:{RST}")
        print(f"  {DEV_API}")
        print(f"  ./dev_api.json")
        sys.exit(1)
    with open(DEV_API, "r", encoding="utf-8") as f:
        return json.load(f)


def izbornik_provider(kljucevi):
    dostupni = {
        k: v for k, v in kljucevi.items()
        if k in PROVIDERS
    }
    nepoznati = {
        k: v for k, v in kljucevi.items()
        if k not in PROVIDERS
    }

    print(f"\n{BOLD}{W}════════════════════════════════════════{RST}")
    print(f"{BOLD}{W}  BOOKLYFI — Provjera API ključeva{RST}")
    print(f"{BOLD}{W}════════════════════════════════════════{RST}\n")
    print(f"  {DIM}Učitano iz: {DEV_API}{RST}\n")

    opcije = list(dostupni.keys())
    # Dodaj ALL opciju
    opcije_prikaz = ["SVE (svi provideri)"] + opcije

    for i, naziv in enumerate(opcije_prikaz):
        if i == 0:
            print(f"  {G}{i+1:2}.{RST} {BOLD}{naziv}{RST}")
            continue
        prov = naziv
        kljucevi_prov = dostupni.get(prov, [])
        n = len(kljucevi_prov)
        boja = G if n > 0 else R
        status = f"{n} ključ{'a' if n != 1 else ''}" if n > 0 else "NEMA KLJUČEVA"
        print(f"  {boja}{i+1:2}.{RST} {naziv:<15} {DIM}[{status}]{RST}")

    if nepoznati:
        print(f"\n  {Y}Nepoznati provideri (nemaju definiciju):{RST}")
        for k, v in nepoznati.items():
            print(f"    {DIM}• {k}: {len(v)} ključeva{RST}")

    print()
    while True:
        try:
            izbor = input(f"  {W}Odaberi [1-{len(opcije_prikaz)}]: {RST}").strip()
            idx = int(izbor) - 1
            if 0 <= idx < len(opcije_prikaz):
                if idx == 0:
                    return opcije  # SVE
                return [opcije[idx - 1]]
        except (ValueError, KeyboardInterrupt):
            pass
        print(f"  {R}Nevažeći unos.{RST}")


def izbornik_opcije():
    print(f"\n  {W}Opcije provjere:{RST}")
    print(f"  {G}1.{RST} Chat test + modeli + account (sve)")
    print(f"  {G}2.{RST} Samo chat test (brzo)")
    print(f"  {G}3.{RST} Samo modeli + account (bez chat testa)")
    print()
    while True:
        try:
            izbor = input(f"  {W}Odaberi [1-3]: {RST}").strip()
            if izbor == "1": return True, True
            if izbor == "2": return True, False
            if izbor == "3": return False, True
        except KeyboardInterrupt:
            sys.exit(0)
        print(f"  {R}Nevažeći unos.{RST}")


# ── Async runner ──────────────────────────────────────────────────────────────

async def main():
    kljucevi = ucitaj_kljuceve()
    odabrani = izbornik_provider(kljucevi)
    provjeri_chat, provjeri_modele = izbornik_opcije()

    print(f"\n  {DIM}Počinjem provjeru u {datetime.now().strftime('%H:%M:%S')}...{RST}")

    async with httpx.AsyncClient(
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as client:

        for provider in odabrani:
            cfg = PROVIDERS[provider]
            prov_kljucevi = kljucevi.get(provider, [])

            print(f"\n{BOLD}{W}{'═'*60}{RST}")
            print(f"{BOLD}{W}  PROVIDER: {C}{provider}{RST}")
            n = len(prov_kljucevi)
            boja = G if n > 0 else R
            print(f"  Ključeva: {boja}{n}{RST}")
            print(f"{BOLD}{W}{'═'*60}{RST}")

            if not prov_kljucevi:
                warn("Nema ključeva za ovaj provider.")
                continue

            rezultati_svih = []
            for i, kljuc in enumerate(prov_kljucevi):
                res = await provjeri_kljuc(
                    client, kljuc, cfg, i, len(prov_kljucevi),
                    provjeri_modele=provjeri_modele,
                    provjeri_chat=provjeri_chat,
                )
                rezultati_svih.append(res)

            # Sažetak
            if provjeri_chat:
                print(f"\n  {BOLD}Sažetak — {provider}:{RST}")
                radnih = sum(
                    1 for r in rezultati_svih
                    if r.get("chat", (False, ""))[0]
                )
                neradnih = len(prov_kljucevi) - radnih
                print(f"  {G}✓ Rade:     {radnih}{RST}")
                if neradnih:
                    print(f"  {R}✗ Ne rade:  {neradnih}{RST}")

    print(f"\n{DIM}  Gotovo. {datetime.now().strftime('%H:%M:%S')}{RST}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Y}  Prekinuto.{RST}\n")
