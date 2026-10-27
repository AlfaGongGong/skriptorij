#!/usr/bin/env python3
"""
Booklyfi pipeline audit v2 — hvata SVE: greške, upozorenja, pucanja, konflikte.

Faze:
 0  okruženje (python, disk, RAM, paketi)
 S  statička analiza projekta (sintaksa, duplikati def/class, goli except,
    progutani izuzeci, neriješeni importi, nepostojeća imena u `from x import y`,
    pyflakes ako postoji)
 I  import svakog modula u zasebnom procesu (import-time greške, cirkularni
    importi, warning-i)
 1  analiza ulaznog EPUB-a
 4  svaki mod u ZASEBNOM procesu (hvata segfault/OOM/timeout/hang) + hvata:
    izuzetke, log_callback poruke, logging zapise, warnings, stdout/stderr,
    RAM/vrijeme, promjenu ulaza
 5  duboka validacija izlaza (ZIP, mimetype, OPF, manifest/spine, XML parser,
    duplikati id, mrtvi linkovi/sidra/slike, CSS klase, NCX, mojibake, ...)
 6  poređenje ulaz↔izlaz (gubitak teksta, slike, spine, metadata) i mod↔mod
 8  idempotentnost (stilizacija već stilizovanog EPUB-a ne smije dupliciti)
 9  sažetak SVIH FAIL/WARN + JSON izvještaj; exit code 1 ako ima FAIL

Upotreba: python3 tools/pipeline_audit.py [putanja_do.epub]
Env: AUDIT_TIMEOUT=900  AUDIT_IDEM=1  AUDIT_SKIP_IMPORTS=0
"""
import sys, os, re, ast, json, time, shutil, signal, hashlib, zipfile, platform
import traceback, datetime, subprocess, importlib.util, posixpath, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# ═════════════ WORKER (zaseban proces; mora prije otvaranja loga) ═════════════
def worker(mode, epub, result_path):
    import logging, warnings, faulthandler, resource
    faulthandler.enable()
    res = {"mode": mode, "callback": [], "records": [], "warnings": [],
           "exception": None, "result": None, "maxrss_mb": 0, "secs": 0}

    class H(logging.Handler):
        def emit(self, r):
            try:
                res["records"].append([r.levelname, r.name, r.getMessage()[:1500]])
            except Exception:
                pass
    logging.getLogger().addHandler(H())
    logging.getLogger().setLevel(logging.DEBUG)

    def cb(msg, a="info"):
        res["callback"].append([str(a), str(msg)[:1500]])

    t0 = time.time()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            from epub.manager import EpubStylerManager
            m = EpubStylerManager(epub_path=Path(epub), log_callback=cb)
            if not hasattr(m, "stilizuj"):
                raise AttributeError("EpubStylerManager nema metodu 'stilizuj'")
            res["result"] = m.stilizuj()
        except BaseException as e:
            res["exception"] = {"type": type(e).__name__, "msg": str(e),
                                "tb": traceback.format_exc()}
        for x in w:
            res["warnings"].append(f"{x.category.__name__}: {x.message} ({x.filename}:{x.lineno})")
    res["secs"] = round(time.time() - t0, 2)
    try:
        res["maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        pass
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(res, f, default=str, ensure_ascii=False)

if len(sys.argv) >= 5 and sys.argv[1] == "--worker":
    worker(sys.argv[2], sys.argv[3], sys.argv[4])
    sys.exit(0)

# ═════════════ Konfiguracija ═════════════
try:
    DOWNLOAD = Path("/storage/emulated/0/Download")
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
    (DOWNLOAD / ".w").write_text("x"); (DOWNLOAD / ".w").unlink()
except Exception:
    DOWNLOAD = ROOT / "audit_out"
    DOWNLOAD.mkdir(parents=True, exist_ok=True)
LOG = DOWNLOAD / "pipeline_audit_full.log"
JSON_REPORT = DOWNLOAD / "pipeline_audit_full.json"

EPUB_CANDIDATES = [
    Path("/storage/emulated/0/Books/MoonReader/booklyfi/PREVEDENO_A_Death_--_Stephen_King_--_101_--_Simon_and_Schuster_--_f4ffe438ff1a54c8a52081ee9a586b59_--_Anna_s_Archive.epub"),
    Path("/storage/emulated/0/Download/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO.epub"),
    Path("/storage/emulated/0/Books/MoonReader/STYLED/Joe_Abercrombie_The_Trouble_With_Peace_PREVEDENO_STYLED.epub"),
]
MODES = ["default"]  # jedan mod
TIMEOUT = int(os.environ.get("AUDIT_TIMEOUT", "900"))
DO_IDEM = os.environ.get("AUDIT_IDEM", "1") == "1"
SKIP_IMPORTS = os.environ.get("AUDIT_SKIP_IMPORTS", "0") == "1"

# Nivo audita: quick | medium | full
LEVEL = "full"
if "--level" in sys.argv:
    _i = sys.argv.index("--level")
    if _i + 1 < len(sys.argv):
        LEVEL = sys.argv[_i + 1]
        del sys.argv[_i:_i + 2]
if LEVEL not in ("quick", "medium", "full"):
    print(f"Nepoznat --level: {LEVEL} (dozvoljeno: quick|medium|full)")
    sys.exit(2)

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", "backups",
             "backup", "audit_out", "build", "dist", "site-packages"}

# ═════════════ Log ═════════════
_log_fh = open(LOG, "w", encoding="utf-8")
FINDINGS = []
COUNTS = Counter()

def _write(level, phase, msg, tb=None):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] [{phase}] {msg}\n"
    print(line, end="")
    _log_fh.write(line)
    if tb:
        _log_fh.write(tb + "\n" + "-" * 60 + "\n")
    _log_fh.flush()
    COUNTS[level] += 1
    if level in ("FAIL", "WARN"):
        FINDINGS.append((level, phase, msg.split("\n")[0][:400]))

def INFO(p, m): _write("INFO", p, m)
def OK(p, m): _write("OK", p, m)
def WARN(p, m): _write("WARN", p, m)
def FAIL(p, m, tb=None): _write("FAIL", p, m, tb)
def SKIP(p, m): _write("SKIP", p, m)

def _excepthook(t, v, tb):
    FAIL("AUDIT", f"neuhvaćen izuzetak u samom auditu: {t.__name__}: {v}",
         "".join(traceback.format_exception(t, v, tb)))
sys.excepthook = _excepthook

# ═════════════ Pomoćne ═════════════
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def ln(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""

def resolve(base_dir, href):
    href = urllib.parse.unquote(href.split("#")[0].split("?")[0])
    return posixpath.normpath(posixpath.join(base_dir, href)) if href else ""

def tail(text, n=40):
    return "\n".join(text.strip().splitlines()[-n:])

# ═════════════ FAZA 0: okruženje ═════════════
def phase_env():
    INFO("0_ENV", f"python {sys.version.split()[0]} | {platform.platform()} | root={ROOT}")
    try:
        du = shutil.disk_usage(DOWNLOAD)
        free = du.free // (1 << 20)
        (WARN if free < 300 else INFO)("0_ENV", f"slobodan disk: {free} MB")
    except Exception as e:
        WARN("0_ENV", f"disk_usage: {e}")
    try:
        for l in open("/proc/meminfo"):
            if l.startswith("MemAvailable"):
                mb = int(l.split()[1]) // 1024
                (WARN if mb < 500 else INFO)("0_ENV", f"slobodan RAM: {mb} MB")
    except Exception:
        pass
    for pkg in ("bs4", "lxml", "ebooklib", "pyflakes", "requests", "flask"):
        try:
            ok = importlib.util.find_spec(pkg) is not None
        except Exception:
            ok = False
        INFO("0_ENV", f"paket {pkg}: {'da' if ok else 'NE'}")

# ═════════════ FAZA S: statička analiza ═════════════
def project_files():
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if re.search(r"\.(bak|orig)|\.bak_|_backup", p.name):
            continue
        yield p

def modname(p):
    parts = list(p.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)

def top_names(body, acc=None):
    acc = acc if acc is not None else {"names": set(), "star": False}
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            acc["names"].add(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tg = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in tg:
                for x in ast.walk(t):
                    if isinstance(x, ast.Name):
                        acc["names"].add(x.id)
        elif isinstance(n, ast.Import):
            for a in n.names:
                acc["names"].add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                if a.name == "*":
                    acc["star"] = True
                else:
                    acc["names"].add(a.asname or a.name)
        elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            for fld in ("body", "orelse", "finalbody"):
                top_names(getattr(n, fld, []) or [], acc)
            for h in getattr(n, "handlers", []) or []:
                top_names(h.body, acc)
    return acc

def phase_static():
    INFO("S_STATIC", "statička analiza projekta...")
    files = list(project_files())
    INFO("S_STATIC", f"{len(files)} .py fajlova")
    local = {modname(p): p for p in files}
    local_roots = {m.split(".")[0] for m in local if m}
    trees, names_of = {}, {}

    for p in files:
        rel = p.relative_to(ROOT)
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            FAIL("S_STATIC", f"{rel}: nije UTF-8: {e}")
            src = p.read_text(encoding="utf-8", errors="replace")
        if "\x00" in src:
            FAIL("S_STATIC", f"{rel}: sadrži NUL bajtove")
        try:
            tree = ast.parse(src, str(rel))
            compile(src, str(rel), "exec")
        except SyntaxError as e:
            FAIL("S_STATIC", f"{rel}:{e.lineno}: SyntaxError: {e.msg}")
            continue
        except Exception as e:
            FAIL("S_STATIC", f"{rel}: compile: {type(e).__name__}: {e}")
            continue
        trees[p] = tree
        names_of[modname(p)] = top_names(tree.body)
        if "\t" in src and re.search(r"^ +\S", src, re.M) and re.search(r"^\t+\S", src, re.M):
            WARN("S_STATIC", f"{rel}: miješa tabove i razmake u uvlačenju")

    for p, tree in trees.items():
        rel = p.relative_to(ROOT)
        # try-blokovi koji hvataju ImportError → opcioni importi
        opt_ranges = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Try):
                for h in n.handlers:
                    t = ast.dump(h.type) if h.type is not None else "bare"
                    if h.type is None or "ImportError" in t or "ModuleNotFoundError" in t or "'Exception'" in t:
                        opt_ranges.append((n.body[0].lineno, n.body[-1].end_lineno))
        def optional(line):
            return any(a <= line <= b for a, b in opt_ranges)

        # duplikati def/class u istom scope-u
        def dups(body, scope):
            seen = {}
            for n in body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if n.decorator_list:
                        continue
                    if n.name in seen:
                        WARN("S_STATIC", f"{rel}:{n.lineno}: '{n.name}' redefinisan u {scope} (prvi put red {seen[n.name]}) — konflikt/mrtav kod")
                    seen[n.name] = n.lineno
                if isinstance(n, ast.ClassDef):
                    dups(n.body, f"klasi {n.name}")
        dups(tree.body, "modulu")

        pkg = modname(p).split(".")
        if p.name != "__init__.py":
            pkg = pkg[:-1]

        for n in ast.walk(tree):
            if isinstance(n, ast.ExceptHandler):
                if n.type is None:
                    WARN("S_STATIC", f"{rel}:{n.lineno}: goli 'except:' (hvata i KeyboardInterrupt/SystemExit)")
                if all(isinstance(b, (ast.Pass, ast.Continue)) for b in n.body):
                    WARN("S_STATIC", f"{rel}:{n.lineno}: izuzetak se tiho guta (except ... pass) — greške nestaju")
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("eval", "exec"):
                WARN("S_STATIC", f"{rel}:{n.lineno}: {n.func.id}() poziv")
            elif isinstance(n, ast.FunctionDef):
                for d in n.args.defaults + [x for x in n.args.kw_defaults if x]:
                    if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                        WARN("S_STATIC", f"{rel}:{n.lineno}: mutabilni default argument u '{n.name}'")
            elif isinstance(n, ast.Import):
                for a in n.names:
                    top = a.name.split(".")[0]
                    if top in local_roots:
                        continue
                    try:
                        found = importlib.util.find_spec(top) is not None
                    except Exception:
                        found = False
                    if not found:
                        (INFO if optional(n.lineno) else FAIL)(
                            "S_STATIC", f"{rel}:{n.lineno}: import '{a.name}' se ne može riješiti" +
                            (" (opcioni, u try)" if optional(n.lineno) else ""))
            elif isinstance(n, ast.ImportFrom):
                if n.level > 0:
                    base = pkg[:len(pkg) - (n.level - 1)] if n.level - 1 <= len(pkg) else None
                    if base is None:
                        FAIL("S_STATIC", f"{rel}:{n.lineno}: relativni import izlazi iz projekta")
                        continue
                    target = ".".join(base + (n.module.split(".") if n.module else []))
                else:
                    target = n.module or ""
                top = target.split(".")[0] if target else ""
                if top in local_roots or n.level > 0:
                    if target not in local:
                        sub_ok = any(m.startswith(target + ".") for m in local)
                        if not sub_ok:
                            (INFO if optional(n.lineno) else FAIL)(
                                "S_STATIC", f"{rel}:{n.lineno}: lokalni modul '{target}' ne postoji")
                        continue
                    info = names_of.get(target)
                    if not info or info["star"]:
                        continue
                    for a in n.names:
                        if a.name == "*":
                            continue
                        if a.name not in info["names"] and f"{target}.{a.name}" not in local:
                            (INFO if optional(n.lineno) else FAIL)(
                                "S_STATIC", f"{rel}:{n.lineno}: '{a.name}' ne postoji u modulu '{target}'")
                elif top:
                    try:
                        found = importlib.util.find_spec(top) is not None
                    except Exception:
                        found = False
                    if not found:
                        (INFO if optional(n.lineno) else FAIL)(
                            "S_STATIC", f"{rel}:{n.lineno}: import iz '{target}' se ne može riješiti" +
                            (" (opcioni)" if optional(n.lineno) else ""))

    # pyflakes
    if files:
        try:
            r = subprocess.run([sys.executable, "-m", "pyflakes"] + [str(p) for p in files],
                               capture_output=True, text=True, timeout=300)
            if "No module named pyflakes" in r.stderr:
                SKIP("S_STATIC", "pyflakes nije instaliran (pip install pyflakes --break-system-packages)")
            else:
                n_unused = 0
                for l in (r.stdout + r.stderr).splitlines():
                    if not l.strip():
                        continue
                    l = l.replace(str(ROOT) + "/", "")
                    if "imported but unused" in l or "assigned to but never used" in l:
                        n_unused += 1
                    elif "undefined name" in l or "syntax error" in l.lower() or "invalid syntax" in l:
                        FAIL("S_PYFLAKES", l)
                    else:
                        WARN("S_PYFLAKES", l)
                INFO("S_PYFLAKES", f"neiskorištenih importa/varijabli: {n_unused} (ne prijavljujem pojedinačno)")
        except Exception as e:
            WARN("S_PYFLAKES", f"pyflakes pao: {e}")
    return local

# ═════════════ FAZA I: import svakog modula (zaseban proces) ═════════════
def phase_imports(local):
    if SKIP_IMPORTS:
        SKIP("I_IMPORT", "preskočeno (AUDIT_SKIP_IMPORTS=1)")
        return
    INFO("I_IMPORT", "importujem svaki lokalni modul u zasebnom procesu...")
    code = "import sys,importlib; sys.path.insert(0,'.'); importlib.import_module(sys.argv[1])"
    for mod, p in sorted(local.items()):
        rel = p.relative_to(ROOT)
        if not mod or rel.parts[0] in ("tools", "tests", "test", "scripts") or p.name == "__main__.py":
            continue
        try:
            r = subprocess.run([sys.executable, "-X", "faulthandler", "-W", "default", "-c", code, mod],
                               capture_output=True, text=True, timeout=120, cwd=ROOT)
        except subprocess.TimeoutExpired:
            FAIL("I_IMPORT", f"{mod}: import visi >120s (blokira pri importu)")
            continue
        err = r.stderr
        if r.returncode != 0:
            tag = "CIRKULARNI IMPORT" if "partially initialized" in err or "circular" in err.lower() else "import pao"
            FAIL("I_IMPORT", f"{mod}: {tag} (rc={r.returncode})", tail(err))
        else:
            ws = [l for l in err.splitlines() if "Warning" in l]
            for w in ws[:5]:
                WARN("I_IMPORT", f"{mod}: {w.strip()[:300]}")
            if not ws:
                OK("I_IMPORT", mod)

# ═════════════ EPUB analiza ═════════════
BLOCK = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "section", "blockquote", "pre", "hr"}
MOJI = re.compile(r"Ã.|Ä[\x80-\xbf]|Å[\x80-\xbf]|â€|Â\xa0")

def analyze_epub(path, tag):
    m = {"exists": path.exists(), "size": 0, "n_xhtml": 0, "n_css": 0, "n_img": 0, "n_opf": 0, "n_ncx": 0,
         "galley_rw": 0, "section": 0, "ascii_quote": 0, "em_crtica": 0, "dropcap_ref": 0, "dropcap_img": 0,
         "dropcap_span": 0, "display_inline": 0, "display_block": 0, "css_display_inline": 0,
         "booklyfi_class": 0, "h1_count": 0, "p_count": 0, "words": 0, "spine": 0, "invalid_xml": 0,
         "mojibake": 0, "fffd": 0, "dead_links": 0, "dead_anchors": 0, "dead_imgs": 0, "dup_ids": 0,
         "nested_p": 0, "block_in_p": 0, "empty_docs": 0,
         "has_naslovna": False, "has_impresum": False, "has_toc_xhtml": False, "has_ncx": False,
         "title": None, "lang": None, "images": [], "undefined_bf": [], "unused_bf": []}
    if not m["exists"]:
        FAIL(tag, f"fajl ne postoji: {path}")
        return m
    m["size"] = path.stat().st_size
    if m["size"] == 0:
        FAIL(tag, "fajl je prazan (0 B)")
        return m
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        FAIL(tag, f"BAD ZIP: {e}")
        return m
    try:
      with z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        nameset = set(names)
        for n, c in Counter(names).items():
            if c > 1:
                FAIL(tag, f"duplikat unosa u ZIP-u: {n}")
        try:
            bad = z.testzip()
            if bad:
                FAIL(tag, f"CRC greška u ZIP unosu: {bad}")
        except Exception as e:
            FAIL(tag, f"testzip: {type(e).__name__}: {e}")
        if not infos or infos[0].filename != "mimetype":
            FAIL(tag, "'mimetype' nije prvi unos u ZIP-u")
        else:
            if infos[0].compress_type != zipfile.ZIP_STORED:
                FAIL(tag, "'mimetype' je komprimiran (mora biti STORED)")
            if z.read("mimetype").strip() != b"application/epub+zip":
                FAIL(tag, "'mimetype' ima pogrešan sadržaj")

        for n in names:
            low = n.lower()
            if n.endswith("/"):
                continue
            if low.endswith(".opf"): m["n_opf"] += 1
            elif low.endswith(".ncx"): m["n_ncx"] += 1; m["has_ncx"] = True
            elif low.endswith(".css"): m["n_css"] += 1
            elif low.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")): m["n_img"] += 1
            elif low.endswith((".xhtml", ".html", ".htm")): m["n_xhtml"] += 1
            if "naslovna" in low or "titlepage" in low or "cover" in low: m["has_naslovna"] = True
            if "impresum" in low or "copyright" in low: m["has_impresum"] = True
            if low.endswith(("toc.xhtml", "nav.xhtml")): m["has_toc_xhtml"] = True
            if info_size_zero(z, n):
                WARN(tag, f"prazan fajl u arhivi: {n}")
        m["images"] = sorted(posixpath.basename(n) for n in names
                             if n.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp")))

        # container + OPF
        opf_path = None
        try:
            c = ET.fromstring(z.read("META-INF/container.xml"))
            rf = [e for e in c.iter() if ln(e.tag) == "rootfile"]
            opf_path = rf[0].get("full-path") if rf else None
        except KeyError:
            FAIL(tag, "nema META-INF/container.xml")
        except ET.ParseError as e:
            FAIL(tag, f"container.xml nevalidan: {e}")
        if opf_path and opf_path not in nameset:
            FAIL(tag, f"OPF iz container.xml ne postoji: {opf_path}")
            opf_path = None
        manifest, spine, opf_dir = {}, [], ""
        if opf_path:
            opf_dir = posixpath.dirname(opf_path)
            try:
                opf = ET.fromstring(z.read(opf_path))
            except ET.ParseError as e:
                FAIL(tag, f"OPF nevalidan XML: {e}")
                opf = None
            if opf is not None:
                idc = Counter()
                for it in opf.iter():
                    t = ln(it.tag)
                    if t == "item":
                        iid, href = it.get("id"), it.get("href")
                        idc[iid] += 1
                        full = resolve(opf_dir, href) if href else None
                        manifest[iid] = {"href": full, "type": it.get("media-type"), "props": it.get("properties", "")}
                        if full and full not in nameset:
                            FAIL(tag, f"manifest stavka bez fajla: {href}")
                    elif t == "itemref":
                        spine.append(it.get("idref"))
                    elif t == "title" and m["title"] is None:
                        m["title"] = (it.text or "").strip()
                    elif t == "language" and m["lang"] is None:
                        m["lang"] = (it.text or "").strip()
                for k, v in idc.items():
                    if v > 1:
                        FAIL(tag, f"duplikat manifest id: {k}")
                for r in spine:
                    if r not in manifest:
                        FAIL(tag, f"spine idref bez manifest stavke: {r}")
                m["spine"] = len(spine)
                if not spine: FAIL(tag, "spine je prazan")
                if not m["title"]: WARN(tag, "OPF nema dc:title")
                if not m["lang"]: WARN(tag, "OPF nema dc:language")
                mh = {v["href"] for v in manifest.values() if v["href"]}
                for n in names:
                    if n.endswith("/") or n == "mimetype" or n.startswith("META-INF/") or n == opf_path:
                        continue
                    if n not in mh:
                        WARN(tag, f"fajl u arhivi nije u manifestu (siroče): {n}")

        # XHTML dokumenti
        docs_ids, html_blob, all_text_blob = {}, [], []
        links = []   # (src_doc, href)
        used_bf = set()
        for n in names:
            if not n.lower().endswith((".xhtml", ".html", ".htm")):
                continue
            try:
                raw = z.read(n)
            except Exception as e:
                FAIL(tag, f"ne mogu čitati {n}: {e}")
                continue
            text = raw.decode("utf-8", "replace")
            html_blob.append(text)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as e:
                m["invalid_xml"] += 1
                FAIL(tag, f"XML nevalidan: {n}: {e}")
                continue
            parent = {c: p for p in root.iter() for c in p}
            ids, doc_dir = Counter(), posixpath.dirname(n)
            for el in root.iter():
                t = ln(el.tag)
                if el.get("id"):
                    ids[el.get("id")] += 1
                cls = el.get("class", "")
                for tok in cls.split():
                    if tok.startswith("booklyfi-"):
                        used_bf.add(tok)
                        m["booklyfi_class"] += 1
                    if "galley-rw" in tok:
                        m["galley_rw"] += 1
                if t == "section": m["section"] += 1
                elif t == "h1": m["h1_count"] += 1
                elif t == "p":
                    m["p_count"] += 1
                    a = parent.get(el)
                    while a is not None:
                        if ln(a.tag) == "p":
                            m["nested_p"] += 1
                            WARN(tag, f"ugniježđen <p> u {n}")
                            break
                        a = parent.get(a)
                if t in BLOCK and t != "p" and ln(parent.get(el).tag if parent.get(el) is not None else "") == "p":
                    m["block_in_p"] += 1
                    WARN(tag, f"<{t}> unutar <p> u {n} (nevalidan XHTML)")
                if "dropcap" in cls:
                    if t == "img": m["dropcap_img"] += 1
                    elif t == "span": m["dropcap_span"] += 1
                if t == "span" and "font-size:1px" in (el.get("style") or "").replace(" ", ""):
                    m["dropcap_span"] += 1
                if t in ("a", "link") and el.get("href"):
                    links.append((n, el.get("href"), t))
                if t in ("img", "image", "script", "source"):
                    src = el.get("src") or el.get("{http://www.w3.org/1999/xlink}href") or el.get("href")
                    if src and not re.match(r"^(data:|https?:|//)", src):
                        tgt = resolve(doc_dir, src)
                        if tgt not in nameset:
                            m["dead_imgs"] += 1
                            FAIL(tag, f"slika/resurs ne postoji: {src} (iz {n})")
                    elif src and src.startswith(("http:", "https:", "//")):
                        WARN(tag, f"vanjski resurs u EPUB-u: {src[:100]} ({n})")
            for k, v in ids.items():
                if v > 1:
                    m["dup_ids"] += 1
                    FAIL(tag, f"duplikat id='{k}' u {n}")
            docs_ids[n] = set(ids)
            # F0.5: broji samo <body> tekst (ne <style>, <title>, CSS)
            _body_el = next((el for el in root.iter() if ln(el.tag) == "body"), None)
            txt = "".join(_body_el.itertext()) if _body_el is not None else "".join(root.itertext())
            all_text_blob.append(txt)
            words = len(re.findall(r"\w+", txt))
            if words == 0 and not root.findall(".//{*}img") and not root.findall(".//{*}svg"):
                m["empty_docs"] += 1
                WARN(tag, f"dokument bez teksta i slika: {n}")
            m["ascii_quote"] += txt.count('"')
            m["em_crtica"] += txt.count("\u2014")
            m["fffd"] += txt.count("\ufffd")
            mj = MOJI.findall(txt)
            if mj:
                m["mojibake"] += len(mj)
                FAIL(tag, f"mojibake ({len(mj)}x) u {n}: {mj[:3]}")
        blob = "\n".join(html_blob)
        m["words"] = len(re.findall(r"\w+", "".join(all_text_blob)))
        m["dropcap_ref"] = blob.count("booklyfi-dropcap")
        m["display_inline"] = blob.count("display:inline") + blob.count("display: inline")
        m["display_block"] = blob.count("display:block") + blob.count("display: block")
        m["galley_rw"] += blob.count("galley-rw") - m["galley_rw"] if blob.count("galley-rw") > m["galley_rw"] else 0
        if m["fffd"]: WARN(tag, f"{m['fffd']}x U+FFFD (oštećeni znakovi)")

        # CSS
        css_defined = set()
        for n in names:
            if not n.lower().endswith(".css"):
                continue
            css = z.read(n).decode("utf-8", "replace")
            if css.count("{") != css.count("}"):
                FAIL(tag, f"CSS neuravnotežene zagrade {{}}: {n} ({css.count('{')} vs {css.count('}')})")
            if css.count("/*") != css.count("*/"):
                FAIL(tag, f"CSS neuravnotežen komentar: {n}")
            css_defined |= set(re.findall(r"\.(booklyfi-[A-Za-z0-9_-]+)", css))
            m["css_display_inline"] += len(re.findall(r"display\s*:\s*inline\b", css))
            m["galley_rw"] += css.count("galley-rw")
            for u in re.findall(r"url\(['\"]?([^)'\"]+)", css):
                if not u.startswith(("data:", "http")):
                    if resolve(posixpath.dirname(n), u) not in nameset:
                        FAIL(tag, f"CSS url() ne postoji: {u} ({n})")
        m["undefined_bf"] = sorted(used_bf - css_defined)
        m["unused_bf"] = sorted(css_defined - used_bf)
        if m["undefined_bf"]:
            WARN(tag, f"klase u XHTML-u bez CSS definicije: {m['undefined_bf'][:10]}")
        if m["unused_bf"]:
            INFO(tag, f"CSS klase koje se nigdje ne koriste: {m['unused_bf'][:10]}")

        # linkovi i sidra
        for src, href, t in links:
            if re.match(r"^(https?:|mailto:|tel:|data:|javascript:)", href):
                continue
            tgt = resolve(posixpath.dirname(src), href) if href.split("#")[0] else src
            frag = href.split("#", 1)[1] if "#" in href else ""
            if tgt not in nameset:
                m["dead_links"] += 1
                FAIL(tag, f"mrtav link: {href} (iz {src})")
            elif frag and tgt in docs_ids and urllib.parse.unquote(frag) not in docs_ids[tgt]:
                m["dead_anchors"] += 1
                WARN(tag, f"mrtvo sidro: {href} (iz {src})")

        # NCX
        for n in names:
            if n.lower().endswith(".ncx"):
                try:
                    nx = ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    FAIL(tag, f"NCX nevalidan: {e}")
                    continue
                pts = [e for e in nx.iter() if ln(e.tag) == "navPoint"]
                if not pts: WARN(tag, f"NCX nema navPoint stavki: {n}")
                for e in nx.iter():
                    if ln(e.tag) == "content" and e.get("src"):
                        tgt = resolve(posixpath.dirname(n), e.get("src"))
                        fr = e.get("src").split("#")[1] if "#" in e.get("src") else ""
                        if tgt not in nameset:
                            m["dead_links"] += 1
                            FAIL(tag, f"NCX pokazuje na nepostojeći fajl: {e.get('src')}")
                        elif fr and tgt in docs_ids and fr not in docs_ids[tgt]:
                            m["dead_anchors"] += 1
                            WARN(tag, f"NCX mrtvo sidro: {e.get('src')}")
    except Exception as e:
        FAIL(tag, f"analiza EPUB-a pala: {type(e).__name__}: {e}", traceback.format_exc())
    return m

def info_size_zero(z, n):
    try:
        i = z.getinfo(n)
        return i.file_size == 0 and not n.endswith("/") and not n.lower().endswith(("mimetype",))
    except Exception:
        return False

SCALAR = (int, float, str, bool, type(None))

def report_metrics(tag, a):
    OK(tag, f"xhtml={a['n_xhtml']} css={a['n_css']} img={a['n_img']} opf={a['n_opf']} ncx={a['n_ncx']} spine={a['spine']} riječi={a['words']}")
    INFO(tag, f"galley-rw={a['galley_rw']} section={a['section']} ascii_quote={a['ascii_quote']} em_crtica={a['em_crtica']} h1={a['h1_count']} p={a['p_count']}")
    INFO(tag, f"dropcap_ref={a['dropcap_ref']} dropcap_img={a['dropcap_img']} dropcap_span={a['dropcap_span']} display_inline(html)={a['display_inline']} display_inline(css)={a['css_display_inline']} display_block={a['display_block']} booklyfi_class={a['booklyfi_class']}")
    INFO(tag, f"naslovna={a['has_naslovna']} impresum={a['has_impresum']} toc_xhtml={a['has_toc_xhtml']} ncx={a['has_ncx']} title={a['title']!r} lang={a['lang']!r}")

def check_output(tag, a):
    if a["galley_rw"] > 0: FAIL(tag, f"galley-rw={a['galley_rw']} (treba 0)")
    if a["section"] > 0: WARN(tag, f"section={a['section']} (treba 0)")
    if a["ascii_quote"] > 500: WARN(tag, f"ascii_quote={a['ascii_quote']} (>500)")
    elif a["ascii_quote"] > 0: INFO(tag, f"ascii_quote={a['ascii_quote']}")
    if a["dropcap_img"] == 0 and a["dropcap_span"] == 0: WARN(tag, "nema dropcap (ni img ni span)")
    if a["display_inline"] > 0: FAIL(tag, f"display:inline u XHTML={a['display_inline']} (treba 0)")
    if a["display_block"] == 0 and (a["dropcap_img"] or a["dropcap_ref"]): WARN(tag, "display:block=0 ali postoji dropcap")
    if a["booklyfi_class"] == 0: WARN(tag, "nema nijedne booklyfi-* klase u XHTML-u")
    if not a["has_ncx"] and not a["has_toc_xhtml"]: FAIL(tag, "nema ni NCX ni nav/toc.xhtml")
    if not a["has_naslovna"]: WARN(tag, "nema naslovne")
    if not a["has_impresum"]: WARN(tag, "nema impresuma")

# ═════════════ Pokretanje moda u zasebnom procesu ═════════════
def run_mode(mode, epub, phase, label):
    rpath = DOWNLOAD / f"pipeline_audit_{label}_{mode}.result.json"
    if rpath.exists(): rpath.unlink()
    sha_before = sha256_file(epub)
    t0 = time.time()
    INFO(phase, f"start (timeout {TIMEOUT}s)...")
    try:
        r = subprocess.run([sys.executable, "-X", "faulthandler", "-W", "default", str(Path(__file__).resolve()),
                            "--worker", mode, str(epub), str(rpath)],
                           capture_output=True, text=True, timeout=TIMEOUT, cwd=ROOT)
    except subprocess.TimeoutExpired as e:
        FAIL(phase, f"TIMEOUT >{TIMEOUT}s (visi/beskonačna petlja)")
        return None
    dt = time.time() - t0
    rawlog = DOWNLOAD / f"pipeline_audit_{label}_{mode}.raw.log"
    out_txt = r.stdout + "\n--- STDERR ---\n" + r.stderr
    if r.returncode != 0:
        if r.returncode < 0:
            try: sn = signal.Signals(-r.returncode).name
            except Exception: sn = str(-r.returncode)
            FAIL(phase, f"proces ubijen signalom {sn} (SIGSEGV=segfault, SIGKILL=najvjerovatnije OOM)", tail(r.stderr))
        else:
            FAIL(phase, f"proces završio sa rc={r.returncode}", tail(r.stderr))
    if "Traceback (most recent call last)" in out_txt:
        WARN(phase, "u stdout/stderr ima Traceback (možda uhvaćen i progutan unutar pipeline-a)")
    for l in out_txt.splitlines():
        if re.search(r"\b(Warning|WARNING)\b", l):
            WARN(phase, f"stderr/stdout: {l.strip()[:300]}")
    if not rpath.exists():
        FAIL(phase, "worker nije napisao rezultat (pao prije kraja)")
        rawlog.write_text(out_txt, encoding="utf-8")
        return None
    res = json.loads(rpath.read_text(encoding="utf-8"))
    with open(rawlog, "w", encoding="utf-8") as f:
        f.write("=== CALLBACK ===\n" + "\n".join(f"[{a}] {m}" for a, m in res["callback"]))
        f.write("\n=== LOGGING ===\n" + "\n".join(f"[{l}] {n}: {m}" for l, n, m in res["records"]))
        f.write("\n=== WARNINGS ===\n" + "\n".join(res["warnings"]))
        f.write("\n=== STDOUT/STDERR ===\n" + out_txt)
    if res["exception"]:
        e = res["exception"]
        FAIL(phase, f"{e['type']}: {e['msg']}", e["tb"])
    for w in res["warnings"][:20]:
        WARN(phase, f"warnings: {w[:300]}")
    kw = re.compile(r"error|greška|greska|exception|traceback|failed|neuspj|timeout|nije pronađen|not found|nedostaje|warning|upozorenje|skip|preskoč", re.I)
    for a, msg in res["callback"]:
        if a.lower() in ("error", "err", "fail", "critical"):
            FAIL(phase, f"callback[{a}]: {msg[:300]}")
        elif a.lower() in ("warn", "warning") or kw.search(msg):
            WARN(phase, f"callback[{a}]: {msg[:300]}")
    for lvl, name, msg in res["records"]:
        if lvl in ("ERROR", "CRITICAL"): FAIL(phase, f"log {name}: {msg[:300]}")
        elif lvl == "WARNING": WARN(phase, f"log {name}: {msg[:300]}")
    mb = res.get("maxrss_mb", 0)
    (WARN if mb > 1024 else INFO)(phase, f"vrijeme={dt:.1f}s RAM vrh={mb} MB | callback={len(res['callback'])} log={len(res['records'])} (sve u {rawlog.name})")
    if sha256_file(epub) != sha_before:
        FAIL(phase, "ULAZNI EPUB JE MODIFICIRAN tokom stilizacije (treba ostati netaknut)")
    rs = res["result"]
    if not isinstance(rs, dict):
        FAIL(phase, f"stilizuj vratio {type(rs).__name__}, ne dict: {str(rs)[:200]}")
        return None
    for k in ("errors", "warnings", "failed", "skipped"):
        v = rs.get(k)
        if v:
            (FAIL if k in ("errors", "failed") else WARN)(phase, f"rezultat['{k}']: {str(v)[:400]}")
    if not rs.get("ok"):
        FAIL(phase, f"ok=False: {rs.get('error', '?')}")
        return None
    out = rs.get("output") or rs.get("epub_path") or rs.get("path")
    if not out:
        FAIL(phase, f"nema 'output'/'epub_path'/'path' u rezultatu: {list(rs.keys())}")
        return None
    out = Path(out)
    if not out.exists():
        FAIL(phase, f"output ne postoji: {out}")
        return None
    if out.resolve() == Path(epub).resolve():
        FAIL(phase, "izlaz = ulaz (pregazio originalni fajl)")
    elif sha256_file(out) == sha_before:
        WARN(phase, "izlaz je bajt-po-bajt identičan ulazu (stilizacija ništa nije promijenila)")
    OK(phase, f"{out.name} ({out.stat().st_size:,} B)")
    return out

def epubcheck(tag, out):
    exe = shutil.which("epubcheck")
    if not exe:
        return
    try:
        r = subprocess.run([exe, str(out)], capture_output=True, text=True, timeout=300)
        for l in (r.stdout + r.stderr).splitlines():
            if l.startswith(("FATAL", "ERROR")): FAIL(tag + "_EPUBCHECK", l[:300])
            elif l.startswith("WARNING"): WARN(tag + "_EPUBCHECK", l[:300])
    except Exception as e:
        WARN(tag + "_EPUBCHECK", f"pao: {e}")

def diff_dicts(a, b, label, phase):
    for k in a:
        if not isinstance(a[k], SCALAR):
            continue
        if a[k] != b.get(k):
            WARN(phase, f"{label} razlika: {k}: {a[k]} vs {b.get(k)}")

# ═════════════ MAIN ═════════════
def main():
    INFO("START", f"Booklyfi pipeline audit v2 — {datetime.datetime.now()}")
    INFO("START", f"Log: {LOG}")
    phase_env()
    local = phase_static()
    phase_imports(local)

    if LEVEL == "quick":
        INFO("9_SUMMARY", "LEVEL=quick — preskačem EPUB (samo S_STATIC + I_IMPORT)")
        return

    # FAZA 0: test EPUB
    test_epub = Path(sys.argv[1]) if len(sys.argv) > 1 else next((c for c in EPUB_CANDIDATES if c.exists()), None)
    if not test_epub or not test_epub.exists():
        FAIL("0_TestEPUB", f"nema test EPUB-a: {[str(c) for c in EPUB_CANDIDATES]}")
        return
    OK("0_TestEPUB", f"{test_epub.name} ({test_epub.stat().st_size:,} B)")

    inp = analyze_epub(test_epub, "1_INPUT")
    report_metrics("1_INPUT", inp)

    # FAZA 4: modovi
    modes_to_run = MODES  # jedan mod
    INFO("4_RUN", f"LEVEL={LEVEL}, modovi: {modes_to_run}")
    outputs = {}
    for mode in modes_to_run:
        out = run_mode(mode, test_epub, f"4_RUN_{mode.upper()}", "pass1")
        if out:
            outputs[mode] = out

    # FAZA 5: analiza izlaza
    analyses = {}
    for mode, out in outputs.items():
        tag = f"5_{mode.upper()}"
        a = analyze_epub(out, tag)
        analyses[mode] = a
        report_metrics(tag, a)
        check_output(tag, a)
        epubcheck(tag, out)

        # FAZA 6a: ulaz ↔ izlaz
        t6 = f"6_IN_OUT_{mode.upper()}"
        if inp["words"]:
            ratio = a["words"] / inp["words"]
            lvl = FAIL if (ratio < 0.95 or ratio > 1.05) else WARN if (ratio < 0.99 or ratio > 1.01) else INFO
            lvl(t6, f"broj riječi izlaz/ulaz = {ratio:.4f} ({a['words']} / {inp['words']})")
        if a["spine"] != inp["spine"]: WARN(t6, f"spine: {inp['spine']} → {a['spine']}")
        lost = set(inp["images"]) - set(a["images"])
        if lost: FAIL(t6, f"izgubljene slike: {sorted(lost)[:10]}")
        if inp["title"] != a["title"]: WARN(t6, f"dc:title: {inp['title']!r} → {a['title']!r}")
        if inp["lang"] != a["lang"]: WARN(t6, f"dc:language: {inp['lang']!r} → {a['lang']!r}")
        if a["dead_links"] > inp["dead_links"]: FAIL(t6, f"mrtvi linkovi: {inp['dead_links']} → {a['dead_links']}")
        if a["dead_anchors"] > inp["dead_anchors"]: WARN(t6, f"mrtva sidra: {inp['dead_anchors']} → {a['dead_anchors']}")
        if a["invalid_xml"] > inp["invalid_xml"]: FAIL(t6, f"nevalidni XHTML: {inp['invalid_xml']} → {a['invalid_xml']}")

    # FAZA 6b: mod ↔ mod
    INFO("6_COMPARE", "upoređujem modove...")
    done = list(analyses)
    if len(done) < 2:
        INFO("6_COMPARE", f"jedan mod — nema sta porediti")
    else:
        for other in done[1:]:
            INFO("6_COMPARE", f"{done[0]} vs {other}:")
            diff_dicts(analyses[done[0]], analyses[other], f"{done[0]}->{other}", "6_COMPARE")

    # FAZA 8: idempotentnost (samo full)
    if LEVEL != "full":
        SKIP("8_IDEM", f"LEVEL={LEVEL} — idempotentnost se testira samo na full")
    elif DO_IDEM:
        tmpdir = DOWNLOAD / "audit_idem"
        tmpdir.mkdir(exist_ok=True)
        for mode, out in outputs.items():
            ph = f"8_IDEM_{mode.upper()}"
            cp = tmpdir / f"idem_{mode}.epub"
            shutil.copy2(out, cp)
            out2 = run_mode(mode, cp, ph, "idem")
            if not out2:
                continue
            a2 = analyze_epub(out2, ph)
            a1 = analyses[mode]
            for k in ("booklyfi_class", "dropcap_ref", "dropcap_img", "dropcap_span", "section", "galley_rw", "n_css", "n_xhtml", "n_img"):
                if a2[k] != a1[k]:
                    (FAIL if a2[k] > a1[k] and k in ("booklyfi_class", "dropcap_img", "dropcap_span", "dropcap_ref") else WARN)(
                        ph, f"nije idempotentno: {k}: {a1[k]} → {a2[k]} nakon 2. prolaza")
            if a2["words"] != a1["words"]:
                WARN(ph, f"riječi nakon 2. prolaza: {a1['words']} → {a2['words']}")
            check_output(ph, a2)
    else:
        SKIP("8_IDEM", "isključeno (AUDIT_IDEM=0)")

    # SAŽETAK
    INFO("9_SUMMARY", "=" * 60)
    INFO("9_SUMMARY", f"Ulaz: {test_epub.name}")
    INFO("9_SUMMARY", f"Modovi završili: {done}")
    INFO("9_SUMMARY", f"Modovi pali: {[m for m in MODES if m not in outputs]}")

main()

# ═════════════ Završni izvještaj ═════════════
_log_fh.write("\n" + "=" * 70 + "\nSVI NALAZI (FAIL + WARN), grupisano\n" + "=" * 70 + "\n")
grp = Counter((l, p, m) for l, p, m in FINDINGS)
for (l, p, m), c in sorted(grp.items(), key=lambda x: (x[0][0] != "FAIL", x[0][1])):
    line = f"[{l}] [{p}] {m}" + (f"  (x{c})" if c > 1 else "")
    _log_fh.write(line + "\n")
    print(line)
summary = (f"\nUKUPNO: FAIL={COUNTS['FAIL']} WARN={COUNTS['WARN']} OK={COUNTS['OK']} "
           f"INFO={COUNTS['INFO']} SKIP={COUNTS['SKIP']}")
print(summary)
_log_fh.write(summary + "\n")
_log_fh.close()
JSON_REPORT.write_text(json.dumps({
    "counts": dict(COUNTS),
    "findings": [{"level": l, "phase": p, "msg": m} for l, p, m in FINDINGS]
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f">>> Log: {LOG}\n>>> JSON: {JSON_REPORT}\n>>> Sirovi logovi modova: {DOWNLOAD}/pipeline_audit_*_*.raw.log")
sys.exit(1 if COUNTS["FAIL"] else 0)
