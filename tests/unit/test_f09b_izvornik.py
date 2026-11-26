import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _pozivi(rel):
    src = (ROOT / rel).read_text(encoding="utf-8")
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            f = n.func
            ime = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if ime == "_scoruj_kvalitetu":
                out.append({k.arg for k in n.keywords})
    return out


def test_pipeline_salje_izvornik():
    p = _pozivi("processing/pipeline.py")
    assert p and all("izvornik" in k for k in p)


def test_workers_salje_izvornik():
    p = _pozivi("processing/workers.py")
    assert p and all("izvornik" in k for k in p)


def test_retro_ne_salje_izvornik():
    p = _pozivi("processing/retro.py")
    assert p and all("izvornik" not in k for k in p)
