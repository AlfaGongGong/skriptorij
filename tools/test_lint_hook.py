import sys, tempfile, json, pathlib, types
sys.path.insert(0, "/root/skriptorij")
import processing.pipeline as pl
import core.lint_hr as lh
pl._get_karantena_detektor = lambda: None
pl._get_rod_detektor = lambda: None
pl.kalkovi_engine = None
tmp = pathlib.Path(tempfile.mkdtemp())
S = types.SimpleNamespace(log=lambda *a, **k: None, checkpoint_dir=tmp,
                          book_path="/tmp/Test_Lint.epub", morfo_validator=None,
                          book_context=None)
ulaz = "<p>Vick je,, imala. Skarling\u2019s Chair, . Kraj.</p>"
out = pl._primijeni_kalkove_i_validator(S, ulaz, "part0001.html", 7)
assert ",," not in out and "Vick je, imala" in out, out
assert "Skarling\u2019s Chair, ." in out, out
lines = (tmp / "lint_flags.jsonl").read_text(encoding="utf-8").strip().split("\n")
assert len(lines) == 1, lines
rec = json.loads(lines[0])
assert rec["blok"] == "part0001.html_blok_7", rec
assert rec["flag"].get("zarez_tocka_ispalo_nesto") == 1, rec
assert rec["flag"].get("engleski_posvojni_oblik") == 1, rec
orig = lh.lint_blok
def _boom(s):
    raise RuntimeError("test")
lh.lint_blok = _boom
out2 = pl._primijeni_kalkove_i_validator(S, ulaz, "part0001.html", 8)
lh.lint_blok = orig
assert ",," in out2, "pad lintera mora ostaviti tekst netaknut"
print("test kuke: VERDIKT: OK")
