"""F03 DIO b: R9-27, R0-4, R0-6, R0-11, R0-12, R0-13, R0-18."""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_r9_27_overlay_u_core_i_omotac(tmp_path):
    from core import apply_overlay, zavrsi
    assert zavrsi._overlay() is apply_overlay
    ck = tmp_path / "ck"
    ck.mkdir()
    (ck / "a.html_blok_0.chk").write_text("Ona je rekla", encoding="utf-8")
    st = apply_overlay.primijeni(ck, [{"fajl": "a.html", "blok": 0, "staro": "je rekla", "novo": "rece"}], log=lambda m: None)
    assert st == {"ok": 1, "vec": 0, "fail": 0}
    assert (ck / "a.html_blok_0.chk").read_text("utf-8") == "Ona rece"
    r = subprocess.run([sys.executable, str(REPO / "tools" / "apply_overlay.py")], capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 1 and "Upotreba" in r.stdout


def test_r0_4_skrati_overlap_isto_ponasanje():
    from epub.styler import _skrati_overlap
    a = " ".join(f"r{i}" for i in range(30))
    b = " ".join(f"r{i}" for i in range(10, 30)) + " novi kraj"
    assert _skrati_overlap(a, b) == ("novi kraj", 20)
    assert _skrati_overlap("x y z", "a b c") == ("a b c", 0)


def test_r0_6_blockquote_vise_citata(tmp_path):
    from epub.ocisti import ocisti_epub
    epub = tmp_path / "k.epub"
    with zipfile.ZipFile(epub, "w") as z:
        z.writestr("c.xhtml", "<html><body><blockquote>Prvi tekst</blockquote><blockquote>Drugi tekst</blockquote></body></html>")
    ocisti_epub(epub)
    t = zipfile.ZipFile(epub).read("c.xhtml").decode("utf-8")
    assert "<blockquote><p>Prvi tekst</p></blockquote>" in t and "<blockquote><p>Drugi tekst</p></blockquote>" in t


def test_r0_11_nema_nekoristenih_uvoza_u_kodu_aplikacije():
    if not shutil.which("ruff"):
        pytest.skip("ruff nije instaliran")
    dat = ["core/sidro.py", "epub/packager.py", "epub/styler.py", "main.py", "processing/pipeline.py", "run.py", "core/zavrsi.py"]
    r = subprocess.run(["ruff", "check", "--select", "F401,F841", "--output-format", "concise", *dat],
                       capture_output=True, text=True, cwd=REPO)
    nalazi = [ln for ln in r.stdout.splitlines() if "F401" in ln or "F841" in ln]
    assert all("_spoji_chk_u_html" in ln for ln in nalazi), nalazi  # taj uvoz namjerno ostaje (R0-11 NALAZI)


def test_r0_12_raise_from():
    import app
    p = REPO / "tmp_f03b_cfg.json"
    p.write_text("{nije json", encoding="utf-8")
    try:
        with pytest.raises(app._KeysCfgError) as ei:
            app._keys_cfg_load(p)
        assert isinstance(ei.value.__cause__, ValueError)
    finally:
        p.unlink(missing_ok=True)


def test_r0_13_logs_nije_u_gitu():
    if not (REPO / ".git").exists() or not shutil.which("git"):
        pytest.skip("nema gita")
    r = subprocess.run(["git", "ls-files", ".logs"], capture_output=True, text=True, cwd=REPO)
    assert r.stdout.strip() == ""


def test_r0_18_pre_commit_hook_odbija_nedefinirano_ime(tmp_path):
    if not (shutil.which("ruff") and shutil.which("git") and shutil.which("bash")):
        pytest.skip("treba ruff, git i bash")
    d = tmp_path / "r"
    d.mkdir()
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    hook = REPO / "tools" / "git_hooks" / "pre-commit"

    def run(*a):
        try:
            return subprocess.run(a, cwd=d, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=60)
        except subprocess.TimeoutExpired:
            pytest.fail("istek vremena (60 s): %s" % (" ".join(a),))

    run("git", "init", "-q")
    (d / "ok.py").write_text("x = 1\n", encoding="utf-8")
    run("git", "add", "ok.py")
    assert run("bash", str(hook)).returncode == 0
    (d / "lose.py").write_text("print(nema_tog_imena)\n", encoding="utf-8")
    run("git", "add", "lose.py")
    r = run("bash", str(hook))
    assert r.returncode != 0 and "F821" in (r.stdout + r.stderr)
