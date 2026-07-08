#!/usr/bin/env python3
"""
coding_proxy.py — OpenAI-kompatibilan /v1/chat/completions iznad Booklyfi flote.

Koristi FleetManager.get_best_key() + network.http_client.api_call() — isti
ključevi/rotacija/quota koje već koristi glavni pipeline. Ne dira BCS
lektorske/prevodilačke rute niti ijedan postojeći fajl.

Pokretanje (MORA iz root-a projekta zbog dev_api.json/api_state.json i
config./network. importa):

    cd /storage/emulated/0/termux/Skriptorij
    python3 coding_proxy.py
"""

import json
import logging
import sys
import time
import uuid
from pathlib import Path

from flask import Flask, Response, jsonify, request

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from api_fleet import FleetManager
from network.http_client import api_call
from config.ai_config import MODEL_MAP

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("coding_proxy")

PORT = 8811

# Redoslijed pokušaja. MISTRAL zadnji namjerno — 1 RPM na free tier
# (min_gap_s=62.0 u profilu), praktično neupotrebljiv za interaktivni rad,
# ali ostaje kao krajnji fallback ako je sve ostalo u cooldownu.
PROVIDER_CHAIN = ["GEMINI", "GROQ", "CEREBRAS", "GITHUB", "MISTRAL"]

CODING_SYSTEM_PROMPT = (
    "Ti si precizan coding asistent. Odgovaraj sažeto i direktno, s ispravnim "
    "kodom. Kad daješ kod, koristi markdown code block s naznačenim jezikom. "
    "Ne objašnjavaj očigledno. Ako kontekst nije dovoljan, postavi kratko "
    "pitanje umjesto nagađanja."
)

app = Flask(__name__)
fleet = FleetManager()  # čita dev_api.json / api_state.json iz cwd-a


def _messages_to_system_and_user(messages: list) -> tuple[str, str]:
    """
    api_call() prima jedan system string i jedan user string, ne punu
    listu poruka. System poruke se spajaju u system string; ostatak
    historije (user/assistant) se serijalizuje u jedan user string tako
    da model i dalje vidi kontekst prethodnih razmjena.
    """
    system_parts = []
    convo_parts = []

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):
            # Continue ponekad šalje content kao listu blokova {"type":"text",...}
            content = "\n".join(
                b.get("text", "") for b in content if isinstance(b, dict)
            )
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            convo_parts.append(f"[ASISTENT]\n{content}")
        else:
            convo_parts.append(f"[KORISNIK]\n{content}")

    system = "\n\n".join(p for p in system_parts if p) or CODING_SYSTEM_PROMPT
    user = "\n\n".join(convo_parts) if convo_parts else ""
    return system, user


def _call_fleet(system: str, user: str) -> tuple[str | None, str | None]:
    for provider in PROVIDER_CHAIN:
        keys_in_fleet = fleet.fleet.get(provider, [])
        if not keys_in_fleet:
            continue

        model = MODEL_MAP.get(provider)
        if not model:
            continue

        attempts = min(len(keys_in_fleet), 3)
        for _ in range(attempts):
            key = fleet.get_best_key(provider)
            if not key:
                break

            logger.info("[coding_proxy] pokušaj: %s (...%s)", provider, key[-4:])
            result = api_call(
                provider=provider,
                model=model,
                api_key=key,
                system=system,
                user=user,
                temperature=0.3,
                max_tokens=4096,
                timeout=90,
            )
            if result:
                return result, f"{provider}-{model}"

        logger.warning(
            "[coding_proxy] %s iscrpljen, prelazim na sljedeći provider", provider
        )

    return None, None


@app.route("/v1/models", methods=["GET"])
def list_models():
    return jsonify(
        {
            "object": "list",
            "data": [
                {"id": "booklyfi-fleet", "object": "model", "owned_by": "booklyfi"}
            ],
        }
    )


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    payload = request.get_json(force=True, silent=True) or {}
    messages = payload.get("messages", [])
    stream = bool(payload.get("stream", False))

    if not messages:
        return jsonify({"error": {"message": "messages je prazan"}}), 400

    system, user = _messages_to_system_and_user(messages)
    if not user:
        return jsonify({"error": {"message": "nema korisničkog sadržaja"}}), 400

    t0 = time.time()
    content, used = _call_fleet(system, user)
    elapsed = time.time() - t0

    if not content:
        logger.error("[coding_proxy] SVI provajderi iscrpljeni (%.1fs)", elapsed)
        return (
            jsonify(
                {
                    "error": {
                        "message": "Svi provajderi u floti su trenutno iscrpljeni ili nedostupni. Pokušaj za par minuta."
                    }
                }
            ),
            503,
        )

    logger.info(
        "[coding_proxy] OK preko %s (%.1fs, %d znakova)", used, elapsed, len(content)
    )

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if stream:

        def _sse():
            chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": used,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": content},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            done_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": used,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return Response(_sse(), mimetype="text/event-stream")

    return jsonify(
        {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": used,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )


if __name__ == "__main__":
    active = [p for p in PROVIDER_CHAIN if fleet.fleet.get(p)]
    logger.info(
        "[coding_proxy] Aktivni provajderi: %s",
        ", ".join(active) or "NIJEDAN — provjeri dev_api.json",
    )
    app.run(host="0.0.0.0", port=PORT, threaded=True)
