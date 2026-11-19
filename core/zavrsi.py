"""zavrsi (P2.6e): odluke s kartica revizije -> .chk -> slozeni EPUB -> kapija.

Tok: (1) zadnje odluke 'prevedi_ponovo' s novim prijevodom postaju ispravke,
(2) apply_overlay.primijeni ih upisuje u .chk (backup izmijenjenih .chk u
BOOKLYFI_ISPRAVCI/backup_zavrsi_*), (3) tools/rebuild_knjiga.py slaze EPUB u zasebnom
procesu, (4) provjera da se novi tekst nalazi u EPUB-u, (5) epub_gate, epub_fix,
audit_epub --gate, epubcheck.
Mijenja samo .chk (s backupom) i STYLED EPUB (stari se kopira u Download/styled_bak_*).
Rollback: kopiraj .chk iz backup_zavrsi_* nazad i ponovi rebuild.
CLI: python -m core.zavrsi <knjiga> [izvorni.epub] [--dry]
"""
import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / ".logs"
STATUS_FILE = LOGS / "zavrsi_status.json"
ISPRAVCI = Path("/storage/emulated/0/Download/BOOKLYFI_ISPRAVCI")
STYLED_DIR = Path("/storage/emulated/0/Books/MoonReader/STYLED")
KANON = Path("/storage/emulated/0/Books/MoonReader/kanon")
DOWNLOAD = Path("/storage/emulated/0/Download")
EPUBCHECK = Path("/usr/share/java/epubcheck.jar")

_BLOK = re.compile(r"^(.+\.x?html)_blok_(\d+)(?:\.chk)?$")
_LOCK = threading.Lock()
STATUS = {"stanje": "nema"}


def _vrijeme():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _py():
    v = REPO / "venv" / "bin" / "python3"
    return str(v) if v.exists() else sys.executable


def _overlay():
    p = REPO / "tools" / "apply_overlay.py"
    spec = importlib.util.spec_from_file_location("apply_overlay_zavrsi", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ispravke_iz_odluka(knjiga):
    """(ispravke za apply_overlay, preskoceno) iz zadnjih odluka 'prevedi_ponovo' s novim prijevodom."""
    from core import odluke as _od
    out, pres = [], []
    for z in _od.za_primjenu(knjiga):
        kl = z.get("kljuc")
        blok = str(z.get("blok", "")).strip()
        hr = str(z.get("hr", "")).strip()
        novo = str(z.get("novo", "")).strip()
        m = _BLOK.match(blok)
        if not m:
            pres.append({"id": kl, "razlog": f"blok neprepoznat: {blok!r}"})
        elif not hr or not novo or hr == novo:
            pres.append({"id": kl, "razlog": "prazan ili identican fragment"})
        else:
            out.append({"id": kl, "fajl": m.group(1), "blok": int(m.group(2)),
                        "staro": hr, "novo": novo})
    return out, pres


def primijeni_odluke(knjiga, ck, bdir=None, dry=False, log=print):
    """Upisuje odluke u .chk. Vraca (rezultat {ok,vec,fail}, ispravke, preskoceno)."""
    ispravke, pres = ispravke_iz_odluka(knjiga)
    log(f"Odluka za primjenu: {len(ispravke)}, preskoceno: {len(pres)}")
    for p in pres:
        log(f"  PRESKOCENO {p['id']}: {p['razlog']}")
    if ispravke:
        st = _overlay().primijeni(ck, ispravke, strict=False, bdir=bdir, dry=dry, log=log)
    else:
        st = {"ok": 0, "vec": 0, "fail": 0}
    return st, ispravke, pres


def _rx_fragment(s):
    rijeci = str(s).split()
    if not rijeci:
        return None
    return re.compile(r"(?:\s|<[^>]*>)+".join(re.escape(r) for r in rijeci))


def primijeni_u_html(ck, ispravke, bdir=None, log=print, dry=False):
    """P2.8: finalize pakira HTML iz work_dir-a (ne .chk), pa se ispravke upisuju i tamo.
    Fragment mora pogoditi tocno 1x (tolerira tagove i entitete izmedju rijeci).
    Vraca {ok, vec, fail}. Idempotentno."""
    wd = Path(ck).parent
    st = {"ok": 0, "vec": 0, "fail": 0}
    for isp in ispravke:
        oid = isp.get("id") or "?"
        fajl = isp.get("fajl")
        staro = str(isp.get("staro", ""))
        novo = str(isp.get("novo", ""))
        p = next((c for c in (wd / "text" / fajl, wd / fajl) if c.is_file()), None)
        if p is None:
            nadjeni = [x for x in wd.rglob(fajl) if "checkpoints" not in x.parts]
            p = nadjeni[0] if nadjeni else None
        if p is None:
            log(f"  HTML WARN {oid}: nema {fajl} u {wd.name}")
            st["fail"] += 1
            continue
        try:
            t = p.read_text("utf-8")
        except Exception as e:
            log(f"  HTML WARN {oid}: nije citljivo {p.name}: {e!r}")
            st["fail"] += 1
            continue
        novo_h = html.escape(novo, quote=False)
        pogodak = None
        for var in (staro, html.escape(staro, quote=False)):
            if var and t.count(var) == 1:
                i = t.find(var)
                pogodak = (i, i + len(var))
                break
        if pogodak is None:
            for var in (staro, html.escape(staro, quote=False)):
                rx = _rx_fragment(var)
                if rx is None:
                    continue
                m = list(rx.finditer(t))
                if len(m) == 1:
                    pogodak = (m[0].start(), m[0].end())
                    break
        if pogodak is None:
            if novo_h in t or novo in t:
                log(f"  HTML VEC {oid}: {p.name}")
                st["vec"] += 1
            else:
                log(f"  HTML WARN {oid}: staro nije nadjeno tocno 1x u {p.name}")
                st["fail"] += 1
            continue
        if not dry:
            if bdir:
                Path(bdir).mkdir(parents=True, exist_ok=True)
                b = Path(bdir) / ("html_" + p.name)
                if not b.exists():
                    b.write_bytes(p.read_bytes())
            p.write_text(t[:pogodak[0]] + novo_h + t[pogodak[1]:], encoding="utf-8")
        log(f"  HTML OK{' (dry)' if dry else ''} {oid}: {p.name}")
        st["ok"] += 1
    return st


def provjeri_u_epubu(epub, ispravke):
    """Nalazi li se 'novo' svake ispravke u tekstu EPUB-a (razmaci/velika slova normalizirani)."""
    def n(s):
        return re.sub(r"\s+", " ", str(s or "")).strip().lower()
    dijelovi = []
    with zipfile.ZipFile(epub) as z:
        for ime in z.namelist():
            if ime.lower().endswith((".html", ".xhtml", ".htm")):
                raw = z.read(ime).decode("utf-8", "ignore")
                dijelovi.append(html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    t = n(" ".join(dijelovi))
    nije = [i.get("id") for i in ispravke if n(i["novo"]) not in t]
    return {"novo_u_epubu": len(ispravke) - len(nije), "nije_nadjeno": nije}


def _spremi(st):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        from utils.file_utils import atomic_write_text as _awt

        _awt(STATUS_FILE, json.dumps(st, ensure_ascii=False, indent=1))
    except Exception as e:
        print("[zavrsi] status nije spremljen:", repr(e))


def status():
    if STATUS.get("stanje") != "nema":
        return dict(STATUS)
    try:
        if STATUS_FILE.exists():
            d = json.loads(STATUS_FILE.read_text("utf-8"))
            if d.get("stanje") == "tece" and not _LOCK.locked():
                d["stanje"] = "prekinuto"
            return d
    except Exception as e:
        print("[zavrsi] status nečitljiv:", repr(e))
    return dict(STATUS)


def _cmd(cmd, log, timeout=None):
    cmd = [str(c) for c in cmd]
    log("$ " + " ".join(cmd))
    try:
        r = subprocess.run(cmd, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        log("  TIMEOUT")
        return 124, ""
    except OSError as e:
        log("  NE MOGU POKRENUTI: " + repr(e))
        return 127, ""
    out = r.stdout or ""
    linije = out.splitlines()
    if len(linije) > 120:
        log(f"  ... ({len(linije) - 120} redaka izostavljeno) ...")
    for ln in linije[-120:]:
        log("  " + ln)
    log(f"  rc={r.returncode}")
    return r.returncode, out


def _backup_styled(knjiga, ts, log):
    if not STYLED_DIR.exists():
        return None
    nm = knjiga.lower()
    c = [f for f in STYLED_DIR.glob("*_STYLED.epub") if nm in f.name.lower()]
    if not c:
        tok = [t for t in nm.split("_") if t]
        c = [f for f in STYLED_DIR.glob("*_STYLED.epub") if tok and all(t in f.name.lower() for t in tok)]
    if not c:
        log("Nema starog STYLED EPUB-a za backup.")
        return None
    f = max(c, key=lambda x: x.stat().st_mtime)
    dst = DOWNLOAD / f"styled_bak_{knjiga}_{ts}.epub"
    shutil.copy2(f, dst)
    log(f"Backup STYLED: {f.name} -> {dst.name}")
    return str(dst)


def pokreni(knjiga, izvor, ck, dry=False):
    """Cijeli tok. dry=True samo broji ispravke (ne mijenja nista). Vraca dict stanja."""
    ck = Path(ck)
    ts = time.strftime("%Y%m%d_%H%M%S")
    LOGS.mkdir(parents=True, exist_ok=True)
    lf = LOGS / f"zavrsi_{knjiga}_{ts}{'_dry' if dry else ''}.log"
    rep = []
    st = {"stanje": "tece", "knjiga": knjiga, "dry": dry, "poceo": _vrijeme(),
          "log_fajl": str(lf), "korak": "start"}

    def log(msg):
        ln = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print("[zavrsi]", ln)
        with lf.open("a", encoding="utf-8") as f:
            f.write(ln + "\n")
        rep.append(ln)

    def upd(**kw):
        st.update(kw)
        st["log_rep"] = rep[-25:]
        if not dry:
            STATUS.clear()
            STATUS.update(st)
            _spremi(st)

    try:
        upd(korak="ispravke")
        bdir = None if dry else ISPRAVCI / f"backup_zavrsi_{knjiga}_{ts}"
        rez, ispravke, pres = primijeni_odluke(knjiga, ck, bdir, dry, log)
        upd(ispravke=rez, ukupno=len(ispravke), preskoceno=pres,
            backup_chk=str(bdir) if bdir else None)
        if dry:
            upd(stanje="dry", korak="gotovo", zavrsio=_vrijeme())
            return st
        try:
            upd(html=primijeni_u_html(ck, ispravke, bdir, log))
        except Exception as e:
            log("Primjena u HTML nije uspjela: " + repr(e))
            upd(html={"greska": repr(e)})
        if rez.get("fail"):
            log(f"UPOZORENJE: {rez['fail']} ispravki nije primijenjeno (vidi gore); nastavljam s ostalima.")

        upd(korak="backup_epub")
        upd(backup_epub=_backup_styled(knjiga, ts, log))

        upd(korak="rebuild")
        rc, out = _cmd([_py(), "tools/rebuild_knjiga.py", izvor, knjiga], log, timeout=7200)
        styled = ""
        for ln in out.splitlines():
            if ln.startswith("STYLED="):
                styled = ln[len("STYLED="):].strip()
        if rc != 0 or not styled or not Path(styled).is_file():
            upd(stanje="pao", greska=f"rebuild rc={rc}, styled={styled!r}", zavrsio=_vrijeme())
            return st
        upd(styled=styled)

        kap = {}
        upd(korak="epub_gate")
        kap["epub_gate"], _ = _cmd([_py(), "tools/epub_gate.py", styled], log, timeout=900)

        upd(korak="epub_fix")
        tmp = styled + ".fixed.tmp"
        kap["epub_fix"], _ = _cmd([_py(), "tools/epub_fix.py", styled, tmp], log, timeout=900)
        if kap["epub_fix"] == 0 and Path(tmp).exists():
            os.replace(tmp, styled)
        elif Path(tmp).exists():
            Path(tmp).unlink()

        upd(korak="popravci")
        try:
            from core import epub_popravci
            pst = epub_popravci.popravi(styled)
            log("Popravci nasljedjenih gresaka: " + json.dumps(pst, ensure_ascii=False))
            upd(popravci=pst)
        except Exception as e:
            log("Popravci nisu uspjeli: " + repr(e))

        upd(korak="provjera")
        prov_nije = []
        try:
            upd(provjera=provjeri_u_epubu(styled, ispravke))
            log("Provjera novog teksta u EPUB-u: " + json.dumps(st["provjera"], ensure_ascii=False))
            prov_nije = list(st["provjera"].get("nije_nadjeno") or [])
        except Exception as e:
            log("Provjera nije uspjela: " + repr(e))
            upd(provjera={"greska": repr(e)})
            prov_nije = ["provjera_pala"]

        upd(korak="audit")
        cmd = [_py(), "tools/audit_epub.py", "--izvor", izvor]
        g = KANON / f"{knjiga}.json"
        if g.exists():
            cmd += ["--glosar", g]
        cmd += ["--chk", ck, "--gate", styled]
        kap["audit"], _ = _cmd(cmd, log, timeout=3600)

        upd(korak="epubcheck")
        if shutil.which("java") and EPUBCHECK.exists():
            kap["epubcheck"], _ = _cmd(["java", "-jar", EPUBCHECK, styled], log, timeout=900)
        else:
            kap["epubcheck"] = None
            log("epubcheck nije dostupan - preskoceno.")

        ok = (kap["epub_gate"] == 0 and kap["epub_fix"] == 0 and kap["audit"] == 0
              and kap["epubcheck"] in (0, None) and not prov_nije)
        if prov_nije:
            log("UPOZORENJE: novi tekst NIJE u EPUB-u za: " + ", ".join(map(str, prov_nije)))
        upd(kapija=kap, kapija_ok=ok, stanje="gotovo" if ok else "gotovo_s_nalazima",
            korak="gotovo", zavrsio=_vrijeme())
    except Exception as e:
        import traceback
        log("GRESKA: " + repr(e))
        log(traceback.format_exc()[-600:])
        upd(stanje="pao", greska=repr(e), zavrsio=_vrijeme())
    return st


def zapocni(knjiga, izvor, ck):
    """Pokrece pokreni() u pozadinskoj niti. False ako je vec jedan tok u tijeku."""
    if not _LOCK.acquire(blocking=False):
        return False

    def _posao():
        try:
            pokreni(knjiga, izvor, ck)
        finally:
            _LOCK.release()

    threading.Thread(target=_posao, daemon=True).start()
    return True


def _cli(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    dry = "--dry" in argv
    if not args:
        print("Upotreba: python -m core.zavrsi <knjiga> [izvorni.epub] [--dry]")
        return 1
    sys.path.insert(0, str(REPO))
    from config.settings import CHECKPOINT_BASE_DIR
    knjiga = args[0]
    izvor = Path(args[1]) if len(args) > 1 else None
    ck = Path(CHECKPOINT_BASE_DIR) / f"_skr_{knjiga}" / "checkpoints"
    if not ck.exists():
        print("Nema checkpoint foldera:", ck)
        return 1
    if not dry and (izvor is None or not izvor.is_file()):
        print("Za pun tok treba izvorni EPUB kao 2. argument.")
        return 1
    st = pokreni(knjiga, izvor, ck, dry=dry)
    print(json.dumps({k: v for k, v in st.items() if k != "log_rep"}, ensure_ascii=False, indent=1))
    return 0 if st.get("stanje") in ("dry", "gotovo") else 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv))
