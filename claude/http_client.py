# network/http_client.py
import asyncio
import random
import requests
import time
from utils.logging import add_audit

async def _async_http_post(self, url, headers, json_payload, prov, prov_upper, key, attempt=1):
    try:
        try:
            _timeout_ctx = asyncio.timeout(120)
        except AttributeError:
            import contextlib
            _timeout_ctx = contextlib.asynccontextmanager(lambda: (yield))()
        async with _timeout_ctx:
            resp = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                json=json_payload,
                timeout=90,
                verify=False,
            )
        try:
            self.fleet.analyze_response(prov, key, resp.status_code, resp.headers)
        except Exception:
            pass

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code in (429, 425):
            retry_after = resp.headers.get('Retry-After')
            wait = float(retry_after) if retry_after else min(2 ** attempt, 60)
            self.log(f"[{prov_upper}] HTTP 429 — čekam {wait:.0f}s", "warning")
            await asyncio.sleep(wait)
            if attempt < 3:
                return await _async_http_post(self, url, headers, json_payload, prov, prov_upper, key, attempt+1)
            return None
        elif resp.status_code in (401, 403, 402, 412):
            return None
        else:
            return None
    except Exception as e:
        self.log(f"[{prov_upper}] Mrežna greška: {str(e)[:100]}", "error")
        return None

async def _call_single_provider(self, prov_upper, model, sys_content, user_prompt, opt_temp, max_tokens=1200):
    # HUMAN-LIKE JITTER pre svakog zahteva
    await asyncio.sleep(random.uniform(0.5, 2.5))

    key = self.fleet.get_best_key(prov_upper)
    if not key:
        return None, None

    headers = {"Content-Type": "application/json"}
    if prov_upper == "GEMMA":
        messages = [{"role": "user", "content": user_prompt}]
    else:
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_prompt}
        ]

    payload = {
        "model": model,
        "temperature": opt_temp,
        "max_tokens": max_tokens,
        "messages": messages
    }

    from network.provider_urls import get_url
    url = get_url(prov_upper)
    headers["Authorization"] = f"Bearer {key}"

    data = await _async_http_post(self, url, headers, payload, prov_upper, prov_upper, key)
    if not data:
        return None, None

    if "choices" in data:
        return data["choices"][0]["message"]["content"].strip(), f"{prov_upper}-{model}"
    return None, None
