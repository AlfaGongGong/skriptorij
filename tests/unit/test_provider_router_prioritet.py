from network.provider_router import ProviderRouterV2


def _prvi(r, uloga):
    rk = r.get_ranked_models(uloga)
    return rk[0][2].provider if rk else None


def _router(kj):
    r = ProviderRouterV2(kj)
    for prov in ("gemini", "groq"):
        r.set_health_score(prov, 1.0)
    return r


def test_jezik_gemini_prvi_provjere_groq_prvi():
    r = _router({"GEMINI": ["x"], "GROQ": ["x"], "GEMMA": ["x"]})
    assert _prvi(r, "PREVODILAC") == "gemini"
    assert _prvi(r, "LEKTOR") == "gemini"
    assert _prvi(r, "SCORER") == "groq"
    assert _prvi(r, "VERIFIER") == "groq"


def test_samo_jedan_provider_radi():
    assert _prvi(_router({"GEMINI": ["x"]}), "PREVODILAC") == "gemini"
    assert _prvi(_router({"GROQ": ["x"]}), "PREVODILAC") == "groq"


def test_los_provider_ide_na_kraj():
    r = _router({"GEMINI": ["x"], "GROQ": ["x"]})
    r.set_health_score("gemini", 0.3)
    assert _prvi(r, "PREVODILAC") == "groq"


def test_get_best_model_prati_prioritet():
    r = _router({"GEMINI": ["x"], "GROQ": ["x"]})
    best = r.get_best_model("PREVODILAC")
    assert best is not None and best[0] == "gemini"
