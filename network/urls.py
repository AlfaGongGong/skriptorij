# urls.py
# Automatski generisano iz skriptorij.py

import re
import json
import time
import random
import asyncio
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString
from api_fleet import FleetManager

# ===== URL GENERATORI =====
def _url_gemini_compat():
    return "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def _url_groq():
    return "https://api.groq.com/openai/v1/chat/completions"


def _url_samba():
    return "https://api.sambanova.ai/v1/chat/completions"


def _url_cerebras():
    return "https://api.cerebras.ai/v1/chat/completions"


def _url_mistral():
    return "https://api.mistral.ai/v1/chat/completions"


def _url_cohere():
    return "https://api.cohere.com/v2/chat"


def _url_openrouter():
    return "https://openrouter.ai/api/v1/chat/completions"


def _url_github():
    return "https://models.inference.ai.azure.com/chat/completions"


def _url_together():
    return "https://api.together.xyz/v1/chat/completions"


def _url_fireworks():
    return "https://api.fireworks.ai/inference/v1/chat/completions"


def _url_chutes():
    return "https://llm.chutes.ai/v1/chat/completions"


def _url_huggingface():
    return "https://router.huggingface.co/v1/chat/completions"


def _url_kluster():
    return "https://api.kluster.ai/v1/chat/completions"


def _url_gemma():
    return "https://api.together.xyz/v1/chat/completions"


def _url_daisy():
    return "http://www.daisy.org/z3986/2005/ncx/"

