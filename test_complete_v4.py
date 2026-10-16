#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KOMPLETNI TEST v4 — Booklyfi / Skriptorij
=========================================
Sve u jednom, bez skraćivanja.

Pokriva:
  • Provjera SVIH ključeva (GET /models) po provideru
  • Provjera da modeli postoje (Gemini/Groq/NVIDIA/Mistral/OpenRouter)
  • Retry (3x) sa eksponencijalnim backoff-om
  • Round-robin rotacija ključeva
  • Blokade po (provider, ključ, model) sa cooldown-om
  • Burst kontrola (pauza između poziva istog providera)
  • Detekcija 429 (minutni vs dnevni), 401, 403
  • Detekcija reasoning-a (Gemini thought parts, reasoning_effort,
    <think> tagovi, reasoning_tokens, heuristika za skriveni reasoning)
  • JSON mod (responseMimeType / response_format)
  • System poruka
  • UTF-8 (č ć đ š ž) roundtrip
  • Dugački promptovi (~3000 znakova)
  • Kombinirana produkcijska konfiguracija
  • Više varijanti gašenja reasoning-a
  • Sažetak PASS/FAIL/INFO po provideru + JSON izvještaj
  • Opcionalna burst sonda (--burst N) za mjerenje RPM limita

Pokretanje:
  python3 test_complete_v4.py
  python3 test_complete_v4.py --only GEMINI,GROQ
  python3 test_complete_v4.py --burst 15
  python3 test_complete_v4.py --pause-scale 0.5
"""
import requests, json, time, sys, os, re, argparse, traceback, difflib
from collections import defaultdict
from datetime import datetime

INF = float('inf')

# ═══════════════════════════════════════════════════════════════
# KONFIGURACIJA
# ═══════════════════════════════════════════════════════════════
CFG_PATH = os.environ.get('BOOKLYFI_CFG', '/root/skriptorij/dev_api.json')
OUT_DIR = os.environ.get('BOOKLYFI_OUT', '/storage/emulated/0/Download')
OUT_NAME = 'BOOKLYFI_kompletni_test'
MAX_COOLDOWN_WAIT = 90

GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMMA_MODEL = "gemma-4-26b-a4b-it"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"
NV_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NV_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
MI_URL = "https://api.mistral.ai/v1/chat/completions"
MI_MODEL = "mistral-small-latest"
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
OR_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

GEMINI_LIST_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
GROQ_LIST_URL = "https://api.groq.com/openai/v1/models"
NV_LIST_URL = "https://integrate.api.nvidia.com/v1/models"
MI_LIST_URL = "https://api.mistral.ai/v1/models"
OR_LIST_URL = "https://openrouter.ai/api/v1/models"
OR_KEY_URL = "https://openrouter.ai/api/v1/key"

UTF8_TXT = "Čačak, Ćuprija, Đakovo, Šibenik, Žepče"
UTF8_PROMPT = f"Ponovi tačno ovaj tekst, bez ičega drugog: {UTF8_TXT}"
JSON_PROMPT = 'Vrati JSON: {"ok": true}'
SYS_PROMPT = "Ti si asistent."

ALL_PROVIDERS = ['GEMINI', 'GEMMA', 'GROQ', 'NVIDIA', 'MISTRAL', 'OPENROUTER']
PROVIDER_NS = {'GEMMA': 'GEMINI'}

ap = argparse.ArgumentParser(description="Booklyfi kompletni test providera v4")
ap.add_argument('--only', default='', help='samo ovi provideri, npr. GEMINI,GROQ')
ap.add_argument('--burst', type=int, default=0, help='N brzih poziva po provideru')
ap.add_argument('--burst-gap', type=float, default=0.0, help='razmak između burst poziva (s)')
ap.add_argument('--pause-scale', type=float, default=1.0, help='množilac pauza (0.5 = upola kraće)')
args = ap.parse_args()

ONLY = {p.strip().upper() for p in args.only.split(',') if p.strip()}

def want(provider):
    return not ONLY or provider in ONLY

# ═══════════════════════════════════════════════════════════════
# IZLAZ
# ═══════════════════════════════════════════════════════════════
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def _open_out():
    for dir_ in (OUT_DIR, os.path.expanduser('~'), '/tmp'):
        p = os.path.join(dir_, OUT_NAME + '.txt')
        try:
            return open(p, 'w', encoding='utf-8', buffering=1), p
        except Exception:
            continue
    return None, None

OUT_FH, OUT_PATH = _open_out()
output = []

def log(s=""):
    s = str(s)
    print(s)
    sys.stdout.flush()
    output.append(s)
    if OUT_FH:
        try:
            OUT_FH.write(s + "\n")
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════
# KLJUČEVI
# ═══════════════════════════════════════════════════════════════
try:
    with open(CFG_PATH, encoding='utf-8') as f:
        d = json.load(f)
except Exception as e:
    print(f"❌ Ne mogu učitati {CFG_PATH}: {e}")
    sys.exit(1)

def _keys(v):
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for k in v:
        if isinstance(k, str):
            k = k.strip()
            if k and k not in out:
                out.append(k)
    return out

KEYS = {
    'GEMINI': _keys(d.get('GEMINI')),
    'GEMMA': _keys(d.get('GEMMA')) or _keys(d.get('GEMINI')),
    'GROQ': _keys(d.get('GROQ')),
    'NVIDIA': _keys(d.get('NVIDIA')),
    'MISTRAL': _keys(d.get('MISTRAL')),
    'OPENROUTER': _keys(d.get('OPENROUTER')),
}

BLOCKED_KEYS = set()
BLOCKS = {}
KEY_COUNTER = defaultdict(int)
LAST_CALL = {}
RESULTS = []

def kid(key):
    return "..." + key[-6:]

def redact(s):
    s = str(s)
    s = re.sub(r'([?&]key=)[^&\s\'"]+', r'\1***', s)
    for lst in KEYS.values():
        for k in lst:
            if k in s:
                s = s.replace(k, kid(k))
    return s

# ═══════════════════════════════════════════════════════════════
# BLOKADE / ROTACIJA
# ═══════════════════════════════════════════════════════════════
def _ns(provider):
    return PROVIDER_NS.get(provider, provider)

def _active_block(provider, key, scope):
    now = time.time()
    for sc in ('*', scope):
        b = BLOCKS.get((_ns(provider), key, sc))
        if b and b['until'] > now:
            return b
    return None

def block_key(provider, key, scope, seconds, reason):
    BLOCKS[(_ns(provider), key, scope)] = {'until': time.time() + seconds, 'reason': reason}
    BLOCKED_KEYS.add(key)

def get_next_key(provider, exclude=None, scope='*'):
    keys = KEYS.get(provider, [])
    exclude = exclude or set()
    n = len(keys)
    for i in range(n):
        idx = (KEY_COUNTER[provider] + i) % n
        k = keys[idx]
        if k in exclude or _active_block(provider, k, scope):
            continue
        KEY_COUNTER[provider] = idx + 1
        return k
    return None

def _soonest_unblock(provider, scope):
    now = time.time()
    best = None
    for k in KEYS.get(provider, []):
        until = 0
        for sc in ('*', scope):
            b = BLOCKS.get((_ns(provider), k, sc))
            if b and b['until'] > now:
                until = max(until, b['until'])
        if until == 0:
            return 0.0
        if until != INF and (best is None or until - now < best):
            best = until - now
    return best

DAILY_MARKERS = ('perday', 'per day', 'per-day', '(rpd)', '(tpd)', 'daily')

def classify_429(body, headers=None):
    body = body or ''
    secs = 60.0
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body)
    if m:
        secs = float(m.group(1)) + 1
    ra = (headers or {}).get('retry-after')
    if ra:
        try:
            secs = float(ra) + 1
        except ValueError:
            pass
    q = re.search(r'"quotaId"\s*:\s*"([^"]+)"', body)
    quota = q.group(1) if q else None
    hay = (body + ' ' + (quota or '')).lower()
    kind = 'daily' if any(x in hay for x in DAILY_MARKERS) else 'minute'
    return kind, secs, quota

def pace(provider, gap):
    last = LAST_CALL.get(provider)
    if last is None:
        return
    rest = gap * args.pause_scale - (time.time() - last)
    if rest > 0:
        log(f"    ⏳ pauza {rest:.0f}s...")
        time.sleep(rest)

# ═══════════════════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════════════════
def _rl_headers(h):
    out = {}
    try:
        for k, v in h.items():
            kl = k.lower()
            if kl.startswith('x-ratelimit') or kl == 'retry-after':
                out[kl] = v
    except Exception:
        pass
    return out

def _http(method, url, headers, payload=None, timeout=60):
    try:
        r = requests.request(method, url, headers=headers, json=payload, timeout=(10, timeout))
    except requests.exceptions.Timeout:
        return {'status': 0, 'data': None, 'text': 'timeout', 'headers': {}}
    except Exception as e:
        return {'status': -1, 'data': None,
                'text': redact(f"{type(e).__name__}: {e}")[:300], 'headers': {}}
    hdrs = _rl_headers(r.headers)
    data = None
    if r.status_code == 200:
        try:
            data = r.json()
        except ValueError:
            return {'status': -1, 'data': None,
                    'text': 'HTTP 200 ali tijelo nije JSON: ' + redact(r.text[:150]), 'headers': hdrs}
    return {'status': r.status_code, 'data': data, 'text': redact(r.text[:1500]), 'headers': hdrs}

def call_gemini(key, model, payload, timeout=60):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return _http('POST', url, {"x-goog-api-key": key, "Content-Type": "application/json"},
                 payload, timeout)

def call_openai(key, url, payload, timeout=60):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return _http('POST', url, headers, payload, timeout)

def _call_with_retry(provider, call_fn, model='*', max_retries=3, base_pause=5):
    last_result, last_key, last_err = None, None, None
    tried = set()
    attempt = 0
    waits = 0
    while attempt < max_retries:
        key = get_next_key(provider, exclude=tried, scope=model)
        if key is None:
            key = get_next_key(provider, scope=model)
        if key is None:
            wait = _soonest_unblock(provider, model)
            if wait is not None and wait <= MAX_COOLDOWN_WAIT and waits < 3:
                waits += 1
                log(f"      ⏳ svi ključevi na cooldownu, čekam {wait:.0f}s...")
                time.sleep(wait + 1)
                continue
            err = f"{last_err} — svi ključevi blokirani" if last_err else "svi ključevi blokirani"
            return last_result, last_key, err

        backoff = True
        if attempt > 0:
            log(f"      ⏳ Retry {attempt + 1}/{max_retries}")
        tried.add(key)
        attempt += 1

        try:
            result = call_fn(key)
        except Exception as e:
            result = {'status': -1, 'data': None,
                      'text': redact(f"{type(e).__name__}: {e}")[:300], 'headers': {}}
        LAST_CALL[provider] = time.time()
        status = result.get('status')
        body = result.get('text', '') or ''
        low = body.lower()
        last_result, last_key = result, key

        if status == 200:
            return result, key, None

        if status == 0:
            last_err = "timeout"
            log(f"      ⏱️ timeout na ključu {kid(key)}")
        elif status == -1:
            last_err = "mrežna greška"
            log(f"      ❌ {body[:80]} na ključu {kid(key)}")
        else:
            last_err = f"HTTP {status}"
            if status == 429:
                kind, secs, quota = classify_429(body, result.get('headers'))
                if kind == 'daily':
                    block_key(provider, key, model, INF, '429 dnevna kvota')
                    log(f"      🚫 Ključ {kid(key)} blokiran (HTTP 429, dnevna kvota)")
                else:
                    block_key(provider, key, model, secs, f'429 cooldown {secs:.0f}s')
                    log(f"      🚫 Ključ {kid(key)} blokiran (HTTP 429, minutni, {secs:.0f}s)")
                if quota:
                    log(f"         kvota: {quota}")
                backoff = False
            elif status == 401 or (status in (400, 403) and (
                    'api_key_invalid' in low or 'api key not valid' in low or 'api key expired' in low)):
                block_key(provider, key, '*', INF, f'neispravan ključ (HTTP {status})')
                log(f"      🚫 Ključ {kid(key)} neispravan (HTTP {status})")
                backoff = False
            elif status == 403:
                block_key(provider, key, model, INF, 'HTTP 403 (zabranjeno)')
                log(f"      🚫 Ključ {kid(key)} blokiran (HTTP 403) za model {model}")
                backoff = False
            elif status >= 500 or status == 408:
                log(f"      ⚠️ HTTP {status} (server) na ključu {kid(key)}")
            else:
                return result, key, last_err

        if backoff and attempt < max_retries:
            pause = base_pause * (2 ** (attempt - 1))
            log(f"      ⏳ backoff {pause}s...")
            time.sleep(pause)

    return last_result, last_key, f"neuspjeh nakon {max_retries} pokušaja ({last_err})"

# ═══════════════════════════════════════════════════════════════
# ANALIZA
# ═══════════════════════════════════════════════════════════════
def try_json(txt):
    t = (txt or '').strip()
    try:
        json.loads(t)
        return True, False
    except Exception:
        pass
    m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', t, re.S | re.I)
    if m:
        try:
            json.loads(m.group(1))
            return False, True
        except Exception:
            pass
    return False, False

def split_think(content):
    content = content or ''
    think = ''.join(re.findall(r'<think>(.*?)</think>', content, re.S | re.I))
    rest = re.sub(r'<think>.*?</think>', '', content, flags=re.S | re.I)
    low = rest.lower()
    if '</think>' in low:
        i = low.index('</think>')
        think += rest[:i]
        rest = rest[i + len('</think>'):]
    elif '<think>' in low:
        i = low.index('<think>')
        think += rest[i + 7:]
        rest = rest[:i]
    return think, rest.strip()

def analyze_gemini(data):
    if not data:
        return {}
    info = {'finishReason': None, 'parts_count': 0, 'reasoning_chars': 0, 'answer_chars': 0,
            'answer_text': '', 'answer_preview': '', 'is_json': False, 'json_fenced': False}
    cands = data.get('candidates') or []
    if cands:
        cand = cands[0]
        info['finishReason'] = cand.get('finishReason')
        parts = (cand.get('content') or {}).get('parts') or []
        info['parts_count'] = len(parts)
        thoughts = []
        answers = []
        for p in parts:
            txt = p.get('text', '') or ''
            if p.get('thought', False):
                thoughts.append(txt)
            else:
                answers.append(txt)
        info['reasoning_chars'] = sum(len(t) for t in thoughts)
        info['answer_chars'] = sum(len(t) for t in answers)
        info['answer_text'] = ''.join(answers)
        info['answer_preview'] = (answers[0] if answers else '')[:150]
        info['is_json'], info['json_fenced'] = try_json(info['answer_text'])
    if 'usageMetadata' in data:
        um = data['usageMetadata']
        info['tokens'] = {
            'prompt': um.get('promptTokenCount'),
            'out': um.get('candidatesTokenCount'),
            'thoughts': um.get('thoughtsTokenCount'),
            'total': um.get('totalTokenCount'),
        }
    if 'promptFeedback' in data:
        info['promptFeedback'] = data['promptFeedback']
    return info

def gemini_reasoning_on(info):
    return (info.get('reasoning_chars') or 0) > 0 or \
        ((info.get('tokens') or {}).get('thoughts') or 0) > 0

def analyze_openai(data):
    if not data:
        return {}
    info = {'finish_reason': None, 'answer_chars': 0, 'reasoning_chars': 0, 'answer': '',
            'answer_preview': '', 'reasoning_preview': '', 'is_json': False, 'json_fenced': False,
            'reasoning_tokens': 0, 'hidden_suspect': False}
    choices = data.get('choices') or []
    if choices:
        choice = choices[0]
        msg = choice.get('message') or {}
        content = msg.get('content', '') or ''
        if isinstance(content, list):
            content = ''.join(c.get('text', '') if isinstance(c, dict) else str(c) for c in content)
        reasoning = msg.get('reasoning', '') or msg.get('reasoning_content', '') or ''
        if not reasoning and msg.get('reasoning_details'):
            reasoning = json.dumps(msg['reasoning_details'], ensure_ascii=False)
        think, answer = split_think(content)
        info['finish_reason'] = choice.get('finish_reason')
        info['answer'] = answer
        info['answer_chars'] = len(answer)
        info['reasoning_chars'] = len(reasoning) + len(think)
        info['answer_preview'] = answer[:150]
        rp = reasoning or think
        info['reasoning_preview'] = rp[:100] if rp else ''
        info['is_json'], info['json_fenced'] = try_json(answer)
    if 'usage' in data:
        info['usage'] = data['usage']
        det = (data['usage'].get('completion_tokens_details') or {})
        info['reasoning_tokens'] = det.get('reasoning_tokens') or 0
        ct = data['usage'].get('completion_tokens') or 0
        if ct >= 50 and info['answer_chars'] <= 60 and info['reasoning_chars'] == 0:
            info['hidden_suspect'] = True
    if 'error' in data and not choices:
        info['error'] = data['error']
    return info

def openai_reasoning_on(info):
    return (info.get('reasoning_chars') or 0) > 0 or (info.get('reasoning_tokens') or 0) > 0 \
        or bool(info.get('hidden_suspect'))

def evaluate(answer, is_json, reasoning_on, expect_json, expect_no_reasoning,
             expect_reasoning, expect_text):
    checks = [("odgovor nije prazan", bool((answer or '').strip()))]
    if expect_json:
        checks.append(("validan JSON", bool(is_json)))
    if expect_no_reasoning:
        checks.append(("reasoning isključen", not reasoning_on))
    if expect_reasoning:
        checks.append(("reasoning detektiran", bool(reasoning_on)))
    if expect_text:
        checks.append((f"tekst/dijakritika ({expect_text!r})", expect_text in (answer or '')))
    return checks

def log_checks(checks):
    for c, ok in checks:
        if c == "odgovor nije prazan" and ok:
            continue
        log(f"    {'✅' if ok else '⚠️ PADA:'} {c}")

def record(provider, naziv, status, dt, key, checks=None, info_only=False,
           reasoning_on=None, tag=None, error=None):
    checks = checks or []
    failed = [c for c, ok in checks if not ok]
    good = (status == 200) and not failed
    verdict = 'INFO' if info_only else ('PASS' if good else 'FAIL')
    note = error or '; '.join(failed)
    RESULTS.append({
        'provider': provider, 'test': naziv, 'verdict': verdict, 'status': status,
        'seconds': round(dt, 2), 'key': kid(key) if key else None,
        'reasoning_on': reasoning_on if status == 200 else None, 'tag': tag, 'note': note,
    })

def log_failure(error, dt, result):
    log(f"    ❌ {error} | {dt:.1f}s")
    if result and result.get('text') and result.get('status') not in (0, -1):
        log(f"    tijelo: {result['text'][:400]!r}")

# ═══════════════════════════════════════════════════════════════
# PAYLOAD HELPERI
# ═══════════════════════════════════════════════════════════════
def G(text, system=None, gen=None):
    p = {"contents": [{"role": "user", "parts": [{"text": text}]}]}
    if system:
        p["systemInstruction"] = {"parts": [{"text": system}]}
    if gen:
        p["generationConfig"] = gen
    return p

def O(model, user, system=None, **extra):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": user})
    p = {"model": model, "messages": msgs, "max_tokens": 200}
    p.update(extra)
    return p

# ═══════════════════════════════════════════════════════════════
# TESTOVI
# ═══════════════════════════════════════════════════════════════
def test_gemini(model, naziv, payload, provider='GEMINI', pause_after=10,
                expect_json=False, expect_no_reasoning=False, expect_reasoning=False,
                expect_text=None, info_only=False, timeout=60):
    log(f"\n  ▶ {naziv}")
    pace(provider, pause_after)
    t0 = time.time()
    result, key, error = _call_with_retry(
        provider,
        lambda k: call_gemini(k, model, payload, timeout),
        model=model,
        max_retries=3,
        base_pause=10,
    )
    dt = time.time() - t0

    if result and result.get('status') == 200:
        info = analyze_gemini(result['data'])
        reasoning_on = gemini_reasoning_on(info)
        thoughts = (info.get('tokens') or {}).get('thoughts')
        log(f"    ✅ HTTP 200 | {dt:.1f}s | ključ {kid(key)}")
        log(f"    finishReason: {info.get('finishReason')}")
        log(f"    parts: {info.get('parts_count')} | reasoning: {info.get('reasoning_chars')} znakova | odgovor: {info.get('answer_chars')} znakova")
        log(f"    tokens: {info.get('tokens')}")
        log(f"    reasoning: {'UKLJUČEN' if reasoning_on else 'isključen'} (thoughts tokeni: {thoughts})")
        log(f"    answer: {info.get('answer_preview')!r}")
        if info.get('promptFeedback'):
            log(f"    promptFeedback: {info['promptFeedback']}")
        if info.get('json_fenced'):
            log("    ⚠️ JSON umotan u ``` ograde")
        if result.get('headers'):
            log(f"    limiti: {result['headers']}")
        checks = evaluate(info.get('answer_text'), info.get('is_json'), reasoning_on,
                          expect_json, expect_no_reasoning, expect_reasoning, expect_text)
        log_checks(checks)
        record(provider, naziv, 200, dt, key, checks, info_only, reasoning_on,
               'reasoning_off' if expect_no_reasoning else None)
    else:
        log_failure(error, dt, result)
        record(provider, naziv, (result or {}).get('status'), dt, key, None, info_only,
               None, 'reasoning_off' if expect_no_reasoning else None, error)

def test_openai(provider, url, payload, naziv, pause_after=10,
                expect_json=False, expect_no_reasoning=False, expect_reasoning=False,
                expect_text=None, info_only=False, timeout=60):
    log(f"\n  ▶ {naziv}")
    pace(provider, pause_after)
    model = payload.get('model', '*')
    t0 = time.time()
    result, key, error = _call_with_retry(
        provider,
        lambda k: call_openai(k, url, payload, timeout),
        model=model,
        max_retries=3,
        base_pause=10,
    )
    dt = time.time() - t0

    if result and result.get('status') == 200:
        info = analyze_openai(result['data'])
        reasoning_on = openai_reasoning_on(info)
        log(f"    ✅ HTTP 200 | {dt:.1f}s | ključ {kid(key)}")
        log(f"    finish_reason: {info.get('finish_reason')}")
        log(f"    reasoning: {info.get('reasoning_chars')} znakova | odgovor: {info.get('answer_chars')} znakova")
        log(f"    reasoning: {'UKLJUČEN' if reasoning_on else 'isključen'}"
            f" (reasoning_tokens: {info.get('reasoning_tokens')}"
            f"{', heuristika: puno izlaznih tokena' if info.get('hidden_suspect') else ''})")
        if info.get('reasoning_preview'):
            log(f"    reasoning preview: {info.get('reasoning_preview')!r}")
        log(f"    answer: {info.get('answer_preview')!r}")
        if info.get('usage'):
            log(f"    usage: {info.get('usage')}")
        if info.get('error'):
            log(f"    ⚠️ tijelo error: {str(info['error'])[:300]}")
        if info.get('json_fenced'):
            log("    ⚠️ JSON umotan u ``` ograde")
        if info.get('finish_reason') == 'length':
            log("    ⚠️ finish_reason=length — odsječeno")
        if result.get('headers'):
            log(f"    limiti: {result['headers']}")
        checks = evaluate(info.get('answer'), info.get('is_json'), reasoning_on,
                          expect_json, expect_no_reasoning, expect_reasoning, expect_text)
        log_checks(checks)
        record(provider, naziv, 200, dt, key, checks, info_only, reasoning_on,
               'reasoning_off' if expect_no_reasoning else None)
    else:
        log_failure(error, dt, result)
        record(provider, naziv, (result or {}).get('status'), dt, key, None, info_only,
               None, 'reasoning_off' if expect_no_reasoning else None, error)

def _list_headers(kind, key):
    if kind == 'gemini':
        return {"x-goog-api-key": key}
    return {"Authorization": f"Bearer {key}"}

def test_keys(provider, kind, url, naziv):
    log(f"\n  ▶ {naziv}")
    keys = KEYS.get(provider, [])
    if not keys:
        log("    ❌ nema ključeva")
        record(provider, naziv, None, 0, None, None, False, None, None, "nema ključeva")
        return
    t0 = time.time()
    alive = 0
    for k in keys:
        pace(provider, 1)
        r = _http('GET', url, _list_headers(kind, k), None, 30)
        LAST_CALL[provider] = time.time()
        st = r['status']
        if st == 200:
            alive += 1
            log(f"    ✅ ključ {kid(k)} radi")
        else:
            log(f"    ❌ ključ {kid(k)} HTTP {st}: {r['text'][:140]!r}")
            low = r['text'].lower()
            if st == 401 or (st in (400, 403) and ('api key' in low or 'api_key' in low or 'unauthorized' in low)):
                block_key(provider, k, '*', INF, f'ključ ne radi (HTTP {st})')
    dt = time.time() - t0
    log(f"    ključeva koji rade: {alive}/{len(keys)}")
    ok = alive == len(keys)
    record(provider, naziv, 200 if ok else 1, dt, None, None, False, None, None,
           None if ok else f"{alive}/{len(keys)} ključeva radi")

def test_models(provider, kind, url, wanted, naziv):
    log(f"\n  ▶ {naziv}")
    pace(provider, 1)
    t0 = time.time()
    result, key, error = _call_with_retry(
        provider,
        lambda k: _http('GET', url, _list_headers(kind, k), None, 30),
        model='__models__', max_retries=3, base_pause=5,
    )
    dt = time.time() - t0
    if not (result and result.get('status') == 200):
        log_failure(error, dt, result)
        record(provider, naziv, (result or {}).get('status'), dt, key, None, False, None, None, error)
        return
    data = result['data'] or {}
    if kind == 'gemini':
        ids = {m.get('name', '').split('/', 1)[-1]: m for m in data.get('models', [])}
    else:
        ids = {m.get('id'): m for m in data.get('data', []) if m.get('id')}
    log(f"    ✅ HTTP 200 | {dt:.1f}s | ključ {kid(key)} | modela: {len(ids)}")
    checks = []
    for w in wanted:
        found = w in ids
        checks.append((f"model {w!r} postoji", found))
        if found and kind == 'gemini':
            methods = ids[w].get('supportedGenerationMethods')
            log(f"      metode: {methods}")
        if not found:
            close = difflib.get_close_matches(w, list(ids), n=6, cutoff=0.5)
            log(f"    ⚠️ model {w!r} NE POSTOJI. Slični: {close}")
    log_checks(checks)
    record(provider, naziv, 200, dt, key, checks)

def test_or_key():
    provider = 'OPENROUTER'
    naziv = "OpenRouter info o ključevima / limitima"
    log(f"\n  ▶ {naziv}")
    t0 = time.time()
    bad = 0
    for k in KEYS[provider]:
        pace(provider, 1)
        r = _http('GET', OR_KEY_URL, _list_headers('bearer', k), None, 30)
        LAST_CALL[provider] = time.time()
        if r['status'] == 200:
            dd = (r['data'] or {}).get('data', r['data']) or {}
            sel = {x: dd.get(x) for x in ('label', 'limit', 'limit_remaining', 'usage',
                                          'is_free_tier', 'rate_limit') if x in dd}
            log(f"    ✅ ključ {kid(k)}: {sel}")
        else:
            bad += 1
            log(f"    ❌ ključ {kid(k)} HTTP {r['status']}: {r['text'][:140]!r}")
            if r['status'] == 401:
                block_key(provider, k, '*', INF, 'ključ ne radi (HTTP 401)')
    dt = time.time() - t0
    record(provider, naziv, 200 if bad == 0 else 1, dt, None, None, False, None, None,
           None if bad == 0 else f"{bad} ključeva ne radi")

def section(title):
    log("\n" + "=" * 70)
    log(title)
    log("=" * 70)

# ═══════════════════════════════════════════════════════════════
# BURST
# ═══════════════════════════════════════════════════════════════
def run_burst(n, gap):
    section(f"BURST SONDA — {n} brzih poziva po provideru")
    tiny = {"maxOutputTokens": 8}
    tiny_nothink = {"maxOutputTokens": 8, "thinkingConfig": {"thinkingBudget": 0}}
    targets = [
        ('GEMINI', GEMINI_MODEL, lambda k: call_gemini(k, GEMINI_MODEL, G("Reci OK", gen=tiny_nothink), 30)),
        ('GEMMA', GEMMA_MODEL, lambda k: call_gemini(k, GEMMA_MODEL, G("Reci OK", gen=tiny), 30)),
        ('GROQ', GROQ_MODEL, lambda k: call_openai(k, GROQ_URL, O(GROQ_MODEL, "Reci OK", max_tokens=8, reasoning_effort="none"), 30)),
        ('NVIDIA', NV_MODEL, lambda k: call_openai(k, NV_URL, O(NV_MODEL, "Reci OK", max_tokens=8), 60)),
        ('MISTRAL', MI_MODEL, lambda k: call_openai(k, MI_URL, O(MI_MODEL, "Reci OK", max_tokens=8), 30)),
        ('OPENROUTER', OR_MODEL, lambda k: call_openai(k, OR_URL, O(OR_MODEL, "Reci OK", max_tokens=8), 30)),
    ]
    for provider, model, fn in targets:
        if not want(provider):
            continue
        key = get_next_key(provider, scope=model)
        if key is None:
            log(f"\n  ▶ {provider}: nema slobodnog ključa")
            continue
        log(f"\n  ▶ {provider} / {model} | ključ {kid(key)}")
        ok = 0
        stop = None
        last_hdr = {}
        t0 = time.time()
        for i in range(n):
            r = fn(key)
            LAST_CALL[provider] = time.time()
            if r.get('headers'):
                last_hdr = r['headers']
            if r['status'] == 200:
                ok += 1
            else:
                stop = r
                break
            if gap > 0:
                time.sleep(gap)
        dt = time.time() - t0
        if stop is None:
            rpm = ok / dt * 60 if dt > 0 else 0
            log(f"    ✅ svih {ok}/{n} prošlo u {dt:.1f}s (~{rpm:.0f} RPM)")
            note = f"{ok}/{n} bez 429 (~{rpm:.0f} RPM)"
        elif stop['status'] == 429:
            kind, secs, quota = classify_429(stop['text'], stop.get('headers'))
            log(f"    🚫 429 nakon {ok} u {dt:.1f}s ({'dnevni' if kind == 'daily' else 'minutni'}, ~{secs:.0f}s)")
            if quota:
                log(f"       kvota: {quota}")
            log(f"       tijelo: {stop['text'][:300]!r}")
            block_key(provider, key, model, INF if kind == 'daily' else secs, 'burst sonda 429')
            note = f"429 nakon {ok} poziva ({kind})"
        else:
            log(f"    ❌ HTTP {stop['status']} nakon {ok}: {stop['text'][:200]!r}")
            note = f"HTTP {stop['status']} nakon {ok}"
        if last_hdr:
            log(f"    limiti (headeri): {last_hdr}")
        RESULTS.append({'provider': provider, 'test': f"burst x{n}", 'verdict': 'INFO',
                        'status': 200 if stop is None else stop['status'],
                        'seconds': round(dt, 2), 'key': kid(key), 'reasoning_on': None,
                        'tag': 'burst', 'note': note})

# ═══════════════════════════════════════════════════════════════
# SVI TESTOVI
# ═══════════════════════════════════════════════════════════════
def run_all():
    T0 = {"thinkingConfig": {"thinkingBudget": 0}}
    TMIN = {"thinkingConfig": {"thinkingLevel": "minimal"}}

    # ── GEMINI ──
    if want('GEMINI'):
        section("GEMINI 3.5 FLASH LITE — reasoning off")
        M = GEMINI_MODEL
        test_keys('GEMINI', 'gemini', GEMINI_LIST_URL, "provjera svih Gemini ključeva")
        test_models('GEMINI', 'gemini', GEMINI_LIST_URL,
                    [GEMINI_MODEL] + ([GEMMA_MODEL] if want('GEMMA') else []),
                    "provjera da modeli postoje (Gemini API)")

        test_gemini(M, "baseline", G("Reci OK"), 'GEMINI')
        test_gemini(M, "thinkingLevel=minimal",
                    G("Reci OK", gen=TMIN), 'GEMINI', expect_no_reasoning=True)
        test_gemini(M, "thinkingBudget=0",
                    G("Reci OK", gen=T0), 'GEMINI', expect_no_reasoning=True)
        test_gemini(M, "json + thinkingBudget=0",
                    G(JSON_PROMPT, gen={"responseMimeType": "application/json",
                                        "thinkingConfig": {"thinkingBudget": 0}}),
                    'GEMINI', expect_json=True, expect_no_reasoning=True)
        test_gemini(M, "systemInstruction + thinkingBudget=0",
                    G("Reci OK", system=SYS_PROMPT, gen=T0), 'GEMINI', expect_no_reasoning=True)
        test_gemini(M, "json + thinkingLevel=minimal",
                    G(JSON_PROMPT, gen={"responseMimeType": "application/json", **TMIN}),
                    'GEMINI', expect_json=True, expect_no_reasoning=True)
        test_gemini(M, "kombinirano (produkcija): system + json + thinkingLevel=minimal + temp + maxOutputTokens",
                    G(JSON_PROMPT, system=SYS_PROMPT,
                      gen={"responseMimeType": "application/json", "temperature": 0.3,
                           "maxOutputTokens": 2048, **TMIN}),
                    'GEMINI', expect_json=True, expect_no_reasoning=True)
        test_gemini(M, "diakritika (UTF-8) + thinkingBudget=0",
                    G(UTF8_PROMPT, gen=T0), 'GEMINI', expect_text=UTF8_TXT, expect_no_reasoning=True)
        test_gemini(M, "dugačak prompt (~3000) + thinkingBudget=0",
                    G("Test. " * 500, gen={"temperature": 0.3, "maxOutputTokens": 2048,
                                           "thinkingConfig": {"thinkingBudget": 0}}),
                    'GEMINI', expect_no_reasoning=True)
        test_gemini(M, "includeThoughts=true + thinkingBudget=1024 (provjera detekcije reasoning-a)",
                    G("Koliko je 17 * 23? Odgovori samo brojem.",
                      gen={"thinkingConfig": {"includeThoughts": True, "thinkingBudget": 1024}}),
                    'GEMINI', info_only=True)

    # ── GEMMA ──
    if want('GEMMA'):
        section("GEMMA 26B — bez thinkingConfig")
        M = GEMMA_MODEL
        if not want('GEMINI'):
            test_models('GEMMA', 'gemini', GEMINI_LIST_URL, [GEMMA_MODEL], "provjera da Gemma model postoji")

        test_gemini(M, "Gemma baseline", G("Reci OK"), 'GEMMA')
        test_gemini(M, "Gemma temp=0.3",
                    G("Reci OK", gen={"temperature": 0.3, "maxOutputTokens": 2048}), 'GEMMA')
        test_gemini(M, "Gemma dugačak prompt",
                    G("Test. " * 500, gen={"temperature": 0.3, "maxOutputTokens": 2048}), 'GEMMA')
        test_gemini(M, "Gemma systemInstruction",
                    G("Reci OK", system=SYS_PROMPT, gen={"maxOutputTokens": 2048}), 'GEMMA')
        test_gemini(M, "Gemma JSON mod (responseMimeType)",
                    G(JSON_PROMPT, gen={"responseMimeType": "application/json", "maxOutputTokens": 2048}),
                    'GEMMA', expect_json=True)
        test_gemini(M, "Gemma JSON samo kroz prompt (bez responseMimeType)",
                    G('Vrati isključivo validan JSON, bez ikakvog drugog teksta: {"ok": true}',
                      gen={"maxOutputTokens": 2048}),
                    'GEMMA', expect_json=True)
        test_gemini(M, "Gemma diakritika (UTF-8)",
                    G(UTF8_PROMPT, gen={"maxOutputTokens": 2048}), 'GEMMA', expect_text=UTF8_TXT)
        test_gemini(M, "Gemma + thinkingBudget=0 (provjera tvrdnje)",
                    G("Reci OK", gen={"thinkingConfig": {"thinkingBudget": 0}}), 'GEMMA', info_only=True)

    # ── GROQ ──
    if want('GROQ'):
        section("GROQ — reasoning off")
        test_keys('GROQ', 'bearer', GROQ_LIST_URL, "provjera svih Groq ključeva")
        test_models('GROQ', 'bearer', GROQ_LIST_URL, [GROQ_MODEL], "provjera da Groq model postoji")

        test_openai('GROQ', GROQ_URL, O(GROQ_MODEL, "Reci OK"), "Groq baseline")
        test_openai('GROQ', GROQ_URL, O(GROQ_MODEL, "Reci OK", reasoning_effort="none"),
                    "Groq reasoning_effort=none", expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL, O(GROQ_MODEL, "Reci OK", reasoning_format="hidden"),
                    "Groq reasoning_format=hidden", expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL, O(GROQ_MODEL, "Reci OK", include_reasoning=False),
                    "Groq include_reasoning=false", expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL, O(GROQ_MODEL, "/no_think Reci OK"),
                    "Groq '/no_think' u promptu", expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL,
                    O(GROQ_MODEL, "Reci OK", system=SYS_PROMPT, reasoning_effort="none"),
                    "Groq system + reasoning_effort=none", expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL,
                    O(GROQ_MODEL, JSON_PROMPT, response_format={"type": "json_object"}),
                    "Groq json_object (bez gašenja reasoninga)", expect_json=True)
        test_openai('GROQ', GROQ_URL,
                    O(GROQ_MODEL, JSON_PROMPT, system=SYS_PROMPT,
                      response_format={"type": "json_object"}, reasoning_effort="none"),
                    "Groq kombinirano (produkcija)", expect_json=True, expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL,
                    O(GROQ_MODEL, UTF8_PROMPT, reasoning_effort="none", max_tokens=400),
                    "Groq diakritika (UTF-8)", expect_text=UTF8_TXT, expect_no_reasoning=True)
        test_openai('GROQ', GROQ_URL,
                    O(GROQ_MODEL, "Test. " * 500, reasoning_effort="none", max_tokens=400),
                    "Groq dugačak prompt", expect_no_reasoning=True)

    # ── NVIDIA ──
    if want('NVIDIA'):
        section("NVIDIA — reasoning off")
        test_keys('NVIDIA', 'bearer', NV_LIST_URL, "provjera svih NVIDIA ključeva")
        test_models('NVIDIA', 'bearer', NV_LIST_URL, [NV_MODEL], "provjera da NVIDIA model postoji")

        test_openai('NVIDIA', NV_URL, O(NV_MODEL, "Reci OK"), "NVIDIA baseline", timeout=120)
        test_openai('NVIDIA', NV_URL, O(NV_MODEL, "Reci OK", system="detailed thinking off"),
                    "NVIDIA 'detailed thinking off'", timeout=120, expect_no_reasoning=True)
        test_openai('NVIDIA', NV_URL,
                    O(NV_MODEL, "Reci OK", chat_template_kwargs={"enable_thinking": False}),
                    "NVIDIA chat_template_kwargs enable_thinking=false",
                    timeout=120, expect_no_reasoning=True)
        test_openai('NVIDIA', NV_URL,
                    O(NV_MODEL, "Reci OK", chat_template_kwargs={"thinking": False}),
                    "NVIDIA chat_template_kwargs thinking=false",
                    timeout=120, expect_no_reasoning=True)
        test_openai('NVIDIA', NV_URL, O(NV_MODEL, "Reci OK", system="/no_think"),
                    "NVIDIA '/no_think' u system poruci", timeout=120, expect_no_reasoning=True)
        test_openai('NVIDIA', NV_URL,
                    O(NV_MODEL, JSON_PROMPT, system="detailed thinking off",
                      response_format={"type": "json_object"}),
                    "NVIDIA system + json_object", timeout=120, expect_json=True, expect_no_reasoning=True)
        test_openai('NVIDIA', NV_URL,
                    O(NV_MODEL, UTF8_PROMPT, system="detailed thinking off", max_tokens=400),
                    "NVIDIA diakritika (UTF-8)", timeout=120,
                    expect_text=UTF8_TXT, expect_no_reasoning=True)

    # ── MISTRAL ──
    if want('MISTRAL'):
        section("MISTRAL")
        test_keys('MISTRAL', 'bearer', MI_LIST_URL, "provjera svih Mistral ključeva")
        test_models('MISTRAL', 'bearer', MI_LIST_URL, [MI_MODEL], "provjera da Mistral model postoji")

        test_openai('MISTRAL', MI_URL, O(MI_MODEL, "Reci OK"), "Mistral baseline")
        test_openai('MISTRAL', MI_URL, O(MI_MODEL, "Reci OK", system=SYS_PROMPT),
                    "Mistral system poruka")
        test_openai('MISTRAL', MI_URL,
                    O(MI_MODEL, JSON_PROMPT, system=SYS_PROMPT, response_format={"type": "json_object"}),
                    "Mistral system + json_object", expect_json=True)
        test_openai('MISTRAL', MI_URL, O(MI_MODEL, UTF8_PROMPT, max_tokens=400),
                    "Mistral diakritika (UTF-8)", expect_text=UTF8_TXT)
        test_openai('MISTRAL', MI_URL, O(MI_MODEL, "Test. " * 500, max_tokens=400),
                    "Mistral dugačak prompt")

    # ── OPENROUTER ──
    if want('OPENROUTER'):
        section("OPENROUTER")
        test_or_key()
        test_models('OPENROUTER', 'bearer', OR_LIST_URL, [OR_MODEL], "provjera da OpenRouter model postoji")

        test_openai('OPENROUTER', OR_URL, O(OR_MODEL, "Reci OK"), "OpenRouter baseline")
        test_openai('OPENROUTER', OR_URL, O(OR_MODEL, "Reci OK", system=SYS_PROMPT),
                    "OpenRouter system poruka")
        test_openai('OPENROUTER', OR_URL,
                    O(OR_MODEL, JSON_PROMPT, system=SYS_PROMPT, response_format={"type": "json_object"}),
                    "OpenRouter system + json_object", expect_json=True)
        test_openai('OPENROUTER', OR_URL, O(OR_MODEL, UTF8_PROMPT, max_tokens=400),
                    "OpenRouter diakritika (UTF-8)", expect_text=UTF8_TXT)

# ═══════════════════════════════════════════════════════════════
# SAŽETAK
# ═══════════════════════════════════════════════════════════════
def print_summary():
    section("SAŽETAK — rezultati testova")
    icons = {'PASS': '✅', 'FAIL': '❌', 'INFO': 'ℹ️'}
    per = defaultdict(lambda: {'PASS': 0, 'FAIL': 0, 'INFO': 0})
    for r in RESULTS:
        per[r['provider']][r['verdict']] += 1
        extra = f" — {r['note']}" if r.get('note') else ''
        log(f"  {icons[r['verdict']]} {r['provider']:<10} {r['test']} ({r['seconds']:.1f}s){extra}")
    log()
    log("Po provideru (PASS / FAIL / INFO):")
    for prov in ALL_PROVIDERS:
        if prov in per:
            p = per[prov]
            log(f"  {prov}: {p['PASS']} / {p['FAIL']} / {p['INFO']}")

    by = defaultdict(list)
    for r in RESULTS:
        if r.get('tag') == 'reasoning_off':
            by[r['provider']].append(r)
    if by:
        log("\nGAŠENJE REASONINGA — što radi:")
        for prov, rs in by.items():
            radi = [r['test'] for r in rs if r['reasoning_on'] is False]
            nece = [r['test'] for r in rs if r['reasoning_on'] is True]
            greska = [r['test'] for r in rs if r['reasoning_on'] is None]
            log(f"  {prov}:")
            log(f"    ✅ reasoning isključen: {radi or '—'}")
            log(f"    ⚠️ reasoning i dalje radi: {nece or '—'}")
            log(f"    ❌ greška/nepodržano: {greska or '—'}")

    section("SAŽETAK — blokirani ključevi")
    log(f"Ukupno blokiranih ključeva: {len(BLOCKED_KEYS)}")
    for k in BLOCKED_KEYS:
        log(f"  🚫 ...{k[-8:]}")
    for (ns, k, sc), b in BLOCKS.items():
        until = 'do kraja testa' if b['until'] == INF else f"još ~{max(0, b['until'] - time.time()):.0f}s"
        log(f"     {ns} {kid(k)} [{sc}] — {b['reason']} ({until})")
    log()
    log("Ključevi po provideru koji su ostali:")
    for prov, keys in KEYS.items():
        dostupni = [k for k in keys if k not in BLOCKED_KEYS]
        log(f"  {prov}: {len(dostupni)}/{len(keys)} dostupno")

def save_json():
    base = os.path.splitext(OUT_PATH)[0] if OUT_PATH else os.path.join('/tmp', OUT_NAME)
    path = base + '.json'
    try:
        blocks = [{'provider': ns, 'key': kid(k), 'scope': sc, 'reason': b['reason'],
                   'permanent': b['until'] == INF} for (ns, k, sc), b in BLOCKS.items()]
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'time': datetime.now().isoformat(timespec='seconds'),
                       'results': RESULTS, 'blocks': blocks}, fh, ensure_ascii=False, indent=2)
        return path
    except Exception as e:
        log(f"⚠️ JSON nije sačuvan: {e}")
        return None

def main():
    log("=" * 70)
    log("KOMPLETNI TEST v4 — retry + rotacija + burst + provjere ključeva/modela/limita")
    log("=" * 70)
    log(f"Pokrenuto: {datetime.now():%Y-%m-%d %H:%M:%S} | provideri: {', '.join(sorted(ONLY)) or 'svi'} | burst: {args.burst}")
    log(f"Ključevi: GEMINI={len(KEYS['GEMINI'])}, GEMMA={len(KEYS['GEMMA'])}, GROQ={len(KEYS['GROQ'])}, NVIDIA={len(KEYS['NVIDIA'])}, MISTRAL={len(KEYS['MISTRAL'])}, OPENROUTER={len(KEYS['OPENROUTER'])}")
    unknown = ONLY - set(ALL_PROVIDERS)
    if unknown:
        log(f"⚠️ nepoznati provideri u --only: {sorted(unknown)}")
    if not any(KEYS.values()):
        log("❌ Nema nijednog ključa u dev_api.json")
        return
    try:
        run_all()
        if args.burst > 0:
            run_burst(args.burst, args.burst_gap)
    except KeyboardInterrupt:
        log("\n⛔ Prekinuto (Ctrl+C) — slijedi sažetak.")
    except Exception:
        log("\n💥 Neočekivana greška:\n" + traceback.format_exc())
    finally:
        print_summary()
        jp = save_json()
        if OUT_PATH:
            log(f"\n📄 Sačuvano: {OUT_PATH}")
        if jp:
            log(f"📄 JSON izvještaj: {jp}")
        if OUT_FH:
            try:
                OUT_FH.close()
            except Exception:
                pass

if __name__ == '__main__':
    main()
