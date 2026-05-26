#!/usr/bin/env python3
"""
githubuj.py — Interaktivni meni za sve uobičajene Git/GitHub operacije.
Korišćenje: python githubuj.py [putanja_do_projekta]
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# ── Boje za terminal ───────────────────────────────────────────────────────────

C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"
C_ZELENA = "\033[92m"
C_ŽUTA   = "\033[93m"
C_CRVENA = "\033[91m"
C_PLAVA  = "\033[94m"
C_SIVA   = "\033[90m"
C_CYAN   = "\033[96m"

def bold(t):  return f"{C_BOLD}{t}{C_RESET}"
def zeleno(t): return f"{C_ZELENA}{t}{C_RESET}"
def žuto(t):   return f"{C_ŽUTA}{t}{C_RESET}"
def crveno(t): return f"{C_CRVENA}{t}{C_RESET}"
def plavo(t):  return f"{C_PLAVA}{t}{C_RESET}"
def sivo(t):   return f"{C_SIVA}{t}{C_RESET}"
def cyan(t):   return f"{C_CYAN}{t}{C_RESET}"

# ── Git helper ─────────────────────────────────────────────────────────────────

def git(args: list[str], cwd: Path = None, prikaži=True) -> tuple[int, str, str]:
    rezultat = subprocess.run(
        ["git"] + args,
        cwd=str(cwd or Path.cwd()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if prikaži:
        if rezultat.stdout.strip():
            print(rezultat.stdout.strip())
        if rezultat.stderr.strip():
            # git često šalje info na stderr (npr. "Switched to branch...")
            print(sivo(rezultat.stderr.strip()))
    return rezultat.returncode, rezultat.stdout.strip(), rezultat.stderr.strip()

def unos(poruka: str, podrazumevano: str = "") -> str:
    suffix = f" [{podrazumevano}]" if podrazumevano else ""
    try:
        vrednost = input(f"  {cyan('›')} {poruka}{suffix}: ").strip()
        return vrednost or podrazumevano
    except (EOFError, KeyboardInterrupt):
        print()
        return podrazumevano

def potvrdi(poruka: str) -> bool:
    odgovor = unos(f"{poruka} (d/n)", "d").lower()
    return odgovor in ("d", "da", "y", "yes")

def separator():
    print(sivo("─" * 60))

def naslov(tekst: str):
    print()
    separator()
    print(f"  {bold(tekst)}")
    separator()

def ok(poruka: str):
    print(zeleno(f"  ✅ {poruka}"))

def greška(poruka: str):
    print(crveno(f"  ❌ {poruka}"))

def info(poruka: str):
    print(žuto(f"  ℹ️  {poruka}"))

# ── Provjera git repoa ─────────────────────────────────────────────────────────

def provjeri_repo(root: Path) -> bool:
    kod, _, _ = git(["rev-parse", "--git-dir"], cwd=root, prikaži=False)
    return kod == 0

def trenutna_grana(root: Path) -> str:
    _, out, _ = git(["branch", "--show-current"], cwd=root, prikaži=False)
    return out or "HEAD odvojen"

def ima_uncommitted(root: Path) -> bool:
    _, out, _ = git(["status", "--porcelain"], cwd=root, prikaži=False)
    return bool(out.strip())

# ══════════════════════════════════════════════════════════════════════════════
# RADNJE
# ══════════════════════════════════════════════════════════════════════════════

def status(root: Path):
    naslov("STATUS REPOA")
    git(["status"], cwd=root)

def log(root: Path):
    naslov("ISTORIJA COMMITOVA")
    n = unos("Koliko commitova prikazati", "15")
    git(["log", f"-{n}", "--oneline", "--graph", "--decorate", "--all"], cwd=root)

def diff(root: Path):
    naslov("RAZLIKE (DIFF)")
    print("  1) Nestejdžovane promene")
    print("  2) Stejdžovane promene (--cached)")
    print("  3) Između dva commita / grane")
    izbor = unos("Izbor", "1")
    if izbor == "1":
        git(["diff"], cwd=root)
    elif izbor == "2":
        git(["diff", "--cached"], cwd=root)
    elif izbor == "3":
        od = unos("Od (commit/grana)", "HEAD~1")
        do = unos("Do (commit/grana)", "HEAD")
        git(["diff", od, do], cwd=root)

# ── Stejdžovanje i commit ──────────────────────────────────────────────────────

def dodaj_i_commit(root: Path):
    naslov("DODAJ I COMMIT")
    git(["status", "--short"], cwd=root)
    print()
    print("  1) Dodaj sve (git add -A)")
    print("  2) Dodaj interaktivno (git add -p)")
    print("  3) Dodaj specifičan fajl/pattern")
    izbor = unos("Šta dodati", "1")

    if izbor == "1":
        git(["add", "-A"], cwd=root)
    elif izbor == "2":
        os.system(f"git -C {root} add -p")
        return
    elif izbor == "3":
        pattern = unos("Fajl ili pattern (npr. *.py)")
        if pattern:
            git(["add", pattern], cwd=root)

    poruka = unos("Poruka commita")
    if not poruka:
        greška("Poruka ne može biti prazna.")
        return

    git(["commit", "-m", poruka], cwd=root)

def amend_commit(root: Path):
    naslov("IZMENI ZADNJI COMMIT (AMEND)")
    _, zadnji, _ = git(["log", "-1", "--oneline"], cwd=root, prikaži=False)
    info(f"Zadnji commit: {zadnji}")
    if not potvrdi("Izmeni zadnji commit?"):
        return
    nova_poruka = unos("Nova poruka (prazno = zadrži staru)")
    if nova_poruka:
        git(["commit", "--amend", "-m", nova_poruka], cwd=root)
    else:
        git(["commit", "--amend", "--no-edit"], cwd=root)

# ── Grane ─────────────────────────────────────────────────────────────────────

def grane(root: Path):
    naslov("UPRAVLJANJE GRANAMA")
    print("  1) Prikaži sve grane")
    print("  2) Napravi novu granu")
    print("  3) Prebaci se na granu")
    print("  4) Napravi i prebaci se")
    print("  5) Obriši granu (lokalnu)")
    print("  6) Obriši granu (udaljenu)")
    print("  7) Preimenuj granu")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["branch", "-a", "-vv"], cwd=root)
    elif izbor == "2":
        ime = unos("Ime nove grane")
        if ime: git(["branch", ime], cwd=root)
    elif izbor == "3":
        ime = unos("Na koju granu")
        if ime: git(["checkout", ime], cwd=root)
    elif izbor == "4":
        ime = unos("Ime nove grane")
        if ime: git(["checkout", "-b", ime], cwd=root)
    elif izbor == "5":
        git(["branch", "-a"], cwd=root)
        ime = unos("Obriši lokalnu granu")
        if ime and potvrdi(f"Obrisati '{ime}'?"):
            git(["branch", "-d", ime], cwd=root)
    elif izbor == "6":
        git(["branch", "-r"], cwd=root)
        remote = unos("Remote (npr. origin)")
        ime = unos("Ime grane na remoteu")
        if ime and potvrdi(f"Obrisati '{remote}/{ime}'?"):
            git(["push", remote, "--delete", ime], cwd=root)
    elif izbor == "7":
        staro = unos("Staro ime grane")
        novo = unos("Novo ime grane")
        if staro and novo:
            git(["branch", "-m", staro, novo], cwd=root)

# ── Push / Pull / Fetch ───────────────────────────────────────────────────────

def push(root: Path):
    naslov("PUSH NA REMOTE")
    grana = trenutna_grana(root)
    remote = unos("Remote", "origin")
    cilj = unos("Grana", grana)
    print()
    print("  1) Normalan push")
    print("  2) Push sa --set-upstream (prva objava grane)")
    print("  3) Force push (--force-with-lease) ⚠️")
    print("  4) Push tagova")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["push", remote, cilj], cwd=root)
    elif izbor == "2":
        git(["push", "--set-upstream", remote, cilj], cwd=root)
    elif izbor == "3":
        if potvrdi("⚠️  Force push može prepisati tuđi rad. Nastaviš?"):
            git(["push", "--force-with-lease", remote, cilj], cwd=root)
    elif izbor == "4":
        git(["push", remote, "--tags"], cwd=root)

def pull(root: Path):
    naslov("PULL SA REMOTEA")
    remote = unos("Remote", "origin")
    grana = unos("Grana", trenutna_grana(root))
    print()
    print("  1) Merge pull (podrazumevano)")
    print("  2) Rebase pull (--rebase)")
    izbor = unos("Izbor", "1")

    if izbor == "2":
        git(["pull", "--rebase", remote, grana], cwd=root)
    else:
        git(["pull", remote, grana], cwd=root)

def fetch(root: Path):
    naslov("FETCH")
    remote = unos("Remote (prazno = sve)", "")
    if remote:
        git(["fetch", remote, "--prune"], cwd=root)
    else:
        git(["fetch", "--all", "--prune"], cwd=root)

# ── Merge / Rebase / Cherry-pick ──────────────────────────────────────────────

def merge(root: Path):
    naslov("MERGE")
    git(["branch", "-a"], cwd=root)
    grana_iz = unos("Merge koje grane u trenutnu")
    if not grana_iz:
        return
    print()
    print("  1) Normalan merge")
    print("  2) --no-ff (uvek napravi merge commit)")
    print("  3) --squash (sažmi sve u jedan commit)")
    izbor = unos("Izbor", "1")

    if izbor == "2":
        git(["merge", "--no-ff", grana_iz], cwd=root)
    elif izbor == "3":
        git(["merge", "--squash", grana_iz], cwd=root)
        poruka = unos("Poruka squash commita")
        if poruka:
            git(["commit", "-m", poruka], cwd=root)
    else:
        git(["merge", grana_iz], cwd=root)

def rebase(root: Path):
    naslov("REBASE")
    print("  1) Rebase na granu/commit")
    print("  2) Interaktivni rebase (--interactive)")
    print("  3) Nastavi rebase (--continue)")
    print("  4) Prekini rebase (--abort)")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        cilj = unos("Rebase na (grana/commit)")
        if cilj: git(["rebase", cilj], cwd=root)
    elif izbor == "2":
        n = unos("Koliko poslednjih commitova", "3")
        os.system(f"git -C {root} rebase -i HEAD~{n}")
    elif izbor == "3":
        git(["rebase", "--continue"], cwd=root)
    elif izbor == "4":
        git(["rebase", "--abort"], cwd=root)

def cherry_pick(root: Path):
    naslov("CHERRY-PICK")
    sha = unos("SHA commita koji kopiraš")
    if sha:
        git(["cherry-pick", sha], cwd=root)

# ── Stash ─────────────────────────────────────────────────────────────────────

def stash(root: Path):
    naslov("STASH")
    print("  1) Stash (sačuvaj promene)")
    print("  2) Prikaži stash listu")
    print("  3) Primeni stash (pop)")
    print("  4) Primeni bez brisanja (apply)")
    print("  5) Obriši stash unos")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        poruka = unos("Opis staša (opcionalno)")
        if poruka:
            git(["stash", "push", "-m", poruka], cwd=root)
        else:
            git(["stash"], cwd=root)
    elif izbor == "2":
        git(["stash", "list"], cwd=root)
    elif izbor == "3":
        git(["stash", "pop"], cwd=root)
    elif izbor == "4":
        git(["stash", "list"], cwd=root)
        ref = unos("Koji stash (npr. stash@{0})", "stash@{0}")
        git(["stash", "apply", ref], cwd=root)
    elif izbor == "5":
        git(["stash", "list"], cwd=root)
        ref = unos("Koji stash obrisati", "stash@{0}")
        if potvrdi(f"Obrisati '{ref}'?"):
            git(["stash", "drop", ref], cwd=root)

# ── Reset / Revert ────────────────────────────────────────────────────────────

def reset_revert(root: Path):
    naslov("RESET / REVERT")
    print("  1) git reset --soft HEAD~N  (zadrži promene stejdžovane)")
    print("  2) git reset --mixed HEAD~N (zadrži promene nestejdžovane)")
    print("  3) git reset --hard HEAD~N  (⚠️  briše promene!)")
    print("  4) git revert <commit>      (siguran: napravi undo commit)")
    print("  5) Unstejdžuj fajl          (reset HEAD <fajl>)")
    izbor = unos("Izbor", "1")

    if izbor in ("1", "2", "3"):
        n = unos("Koliko commitova nazad", "1")
        tip = {"1": "--soft", "2": "--mixed", "3": "--hard"}[izbor]
        if izbor == "3" and not potvrdi("⚠️  Hard reset gubi promene zauvek. Nastaviš?"):
            return
        git(["reset", tip, f"HEAD~{n}"], cwd=root)
    elif izbor == "4":
        sha = unos("SHA commita koji revertaš")
        if sha: git(["revert", sha], cwd=root)
    elif izbor == "5":
        fajl = unos("Fajl za unstejdžovanje")
        if fajl: git(["reset", "HEAD", fajl], cwd=root)

# ── Tagovi ────────────────────────────────────────────────────────────────────

def tagovi(root: Path):
    naslov("TAGOVI")
    print("  1) Prikaži tagove")
    print("  2) Napravi lagan tag")
    print("  3) Napravi anotiran tag (-a)")
    print("  4) Obriši tag (lokalno)")
    print("  5) Push taga na remote")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["tag", "-l", "-n1"], cwd=root)
    elif izbor == "2":
        ime = unos("Ime taga (npr. v1.0.0)")
        if ime: git(["tag", ime], cwd=root)
    elif izbor == "3":
        ime = unos("Ime taga (npr. v1.0.0)")
        poruka = unos("Poruka taga")
        if ime and poruka:
            git(["tag", "-a", ime, "-m", poruka], cwd=root)
    elif izbor == "4":
        git(["tag", "-l"], cwd=root)
        ime = unos("Tag za brisanje")
        if ime and potvrdi(f"Obrisati tag '{ime}'?"):
            git(["tag", "-d", ime], cwd=root)
    elif izbor == "5":
        ime = unos("Ime taga")
        remote = unos("Remote", "origin")
        if ime: git(["push", remote, ime], cwd=root)

# ── Remote ────────────────────────────────────────────────────────────────────

def remoti(root: Path):
    naslov("REMOTI")
    print("  1) Prikaži remote")
    print("  2) Dodaj remote")
    print("  3) Ukloni remote")
    print("  4) Promeni URL remotea")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["remote", "-v"], cwd=root)
    elif izbor == "2":
        ime = unos("Ime remotea", "origin")
        url = unos("URL repoa")
        if url: git(["remote", "add", ime, url], cwd=root)
    elif izbor == "3":
        git(["remote", "-v"], cwd=root)
        ime = unos("Remote za uklanjanje")
        if ime and potvrdi(f"Ukloniti '{ime}'?"): git(["remote", "remove", ime], cwd=root)
    elif izbor == "4":
        git(["remote", "-v"], cwd=root)
        ime = unos("Remote", "origin")
        url = unos("Novi URL")
        if url: git(["remote", "set-url", ime, url], cwd=root)

# ── Init / Clone ──────────────────────────────────────────────────────────────

def init_clone(root: Path):
    naslov("INIT / CLONE")
    print("  1) Inicijalizuj novi repo (git init)")
    print("  2) Kloniraj repo (git clone)")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        putanja = unos("Putanja (prazno = trenutni dir)", str(root))
        git(["init", putanja] if putanja != str(root) else ["init"], cwd=root)
    elif izbor == "2":
        url = unos("URL repoa")
        odredište = unos("Odredišni direktorijum (prazno = automatski)", "")
        args = ["clone", url]
        if odredište:
            args.append(odredište)
        git(args, cwd=root.parent)

# ── Pretraga i čišćenje ───────────────────────────────────────────────────────

def pretraga(root: Path):
    naslov("PRETRAGA U ISTORIJI")
    print("  1) Traži po poruci commita")
    print("  2) Traži po sadržaju koda (git log -S)")
    print("  3) Ko je menjao fajl (git blame)")
    print("  4) Koji commit uveo bag (git bisect start)")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        termin = unos("Termin za pretragu")
        if termin: git(["log", "--all", "--oneline", f"--grep={termin}"], cwd=root)
    elif izbor == "2":
        termin = unos("Kod za pretragu")
        if termin: git(["log", "--all", "--oneline", f"-S{termin}"], cwd=root)
    elif izbor == "3":
        fajl = unos("Fajl za blame")
        if fajl: git(["blame", fajl], cwd=root)
    elif izbor == "4":
        info("Pokretanje bisecta... označi 'good'/'bad' commitove po uputstvima.")
        git(["bisect", "start"], cwd=root)
        dobar = unos("SHA poznatog dobrog commita")
        loš = unos("SHA lošeg commita (HEAD?)", "HEAD")
        if dobar:
            git(["bisect", "good", dobar], cwd=root)
            git(["bisect", "bad", loš], cwd=root)

def čišćenje(root: Path):
    naslov("ČIŠĆENJE")
    print("  1) Prikaži untracked fajlove (git clean -n)")
    print("  2) Obriši untracked fajlove (git clean -fd) ⚠️")
    print("  3) Prune obrisane remote grane")
    print("  4) Garbage collect (git gc)")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["clean", "-nd"], cwd=root)
    elif izbor == "2":
        git(["clean", "-nd"], cwd=root)
        if potvrdi("⚠️  Ovo trajno briše fajlove. Nastaviš?"):
            git(["clean", "-fd"], cwd=root)
    elif izbor == "3":
        git(["remote", "prune", "origin"], cwd=root)
    elif izbor == "4":
        git(["gc", "--aggressive", "--prune=now"], cwd=root)

# ── Konfiguracija ─────────────────────────────────────────────────────────────

def konfiguracija(root: Path):
    naslov("GIT KONFIGURACIJA")
    print("  1) Prikaži globalnu konfiguraciju")
    print("  2) Prikaži lokalnu konfiguraciju (repo)")
    print("  3) Postavi ime i email (globalno)")
    print("  4) Postavi default editor")
    print("  5) Prikaži aliase")
    print("  6) Dodaj alias")
    izbor = unos("Izbor", "1")

    if izbor == "1":
        git(["config", "--global", "--list"], cwd=root)
    elif izbor == "2":
        git(["config", "--local", "--list"], cwd=root)
    elif izbor == "3":
        ime = unos("Ime")
        email = unos("Email")
        if ime:  git(["config", "--global", "user.name", ime], cwd=root)
        if email: git(["config", "--global", "user.email", email], cwd=root)
    elif izbor == "4":
        editor = unos("Editor (nano, vim, code, ...)", "nano")
        git(["config", "--global", "core.editor", editor], cwd=root)
    elif izbor == "5":
        git(["config", "--global", "--get-regexp", "alias"], cwd=root)
    elif izbor == "6":
        ime = unos("Ime aliasa (bez 'git ')")
        komanda = unos("Git komanda (bez 'git ')")
        if ime and komanda:
            git(["config", "--global", f"alias.{ime}", komanda], cwd=root)
            ok(f"Alias: git {ime} → git {komanda}")

# ══════════════════════════════════════════════════════════════════════════════
# GLAVNI MENI
# ══════════════════════════════════════════════════════════════════════════════

MENI = [
    ("─── PREGLED ───────────────────────────────", None),
    ("Status repoa",           status),
    ("Log commitova",          log),
    ("Diff (razlike)",         diff),
    ("─── COMMITOVANJE ─────────────────────────", None),
    ("Dodaj fajlove i commit", dodaj_i_commit),
    ("Izmeni zadnji commit",   amend_commit),
    ("─── GRANE ────────────────────────────────", None),
    ("Upravljanje granama",    grane),
    ("Merge",                  merge),
    ("Rebase",                 rebase),
    ("Cherry-pick",            cherry_pick),
    ("─── REMOTE ───────────────────────────────", None),
    ("Push",                   push),
    ("Pull",                   pull),
    ("Fetch",                  fetch),
    ("Upravljanje remotima",   remoti),
    ("─── PONIŠTAVANJE ─────────────────────────", None),
    ("Reset / Revert",         reset_revert),
    ("Stash",                  stash),
    ("─── TAGOVI ───────────────────────────────", None),
    ("Tagovi",                 tagovi),
    ("─── OSTALO ───────────────────────────────", None),
    ("Pretraga istorije",      pretraga),
    ("Čišćenje radnog stabla", čišćenje),
    ("Init / Clone",           init_clone),
    ("Konfiguracija",          konfiguracija),
]

def prikaži_meni(root: Path):
    grana = trenutna_grana(root)
    izmene = "  " + žuto("● izmene") if ima_uncommitted(root) else ""
    print()
    print(bold("╔══════════════════════════════════════════╗"))
    print(bold("║           🐙  githubuj.py                ║"))
    print(bold("╚══════════════════════════════════════════╝"))
    print(f"  {sivo('Repo:')} {root.name}   {sivo('Grana:')} {plavo(grana)}{izmene}")
    print()

    broj = 0
    mapa: dict[str, callable] = {}

    for stavka, fn in MENI:
        if fn is None:
            print(f"  {sivo(stavka)}")
        else:
            broj += 1
            mapa[str(broj)] = fn
            print(f"  {cyan(str(broj).rjust(2))}) {stavka}")

    print()
    print(f"  {cyan(' 0')}) Izlaz")
    print()
    return mapa

def main():
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
    else:
        root = Path.cwd()

    if not root.is_dir():
        print(crveno(f"❌ '{root}' nije direktorijum."))
        sys.exit(1)

    # Ako repo ne postoji, ponudi init
    if not provjeri_repo(root):
        print(žuto(f"⚠️  '{root.name}' nije git repo."))
        if potvrdi("Inicijalizovati novi repo?"):
            git(["init"], cwd=root)
        else:
            sys.exit(0)

    while True:
        mapa = prikaži_meni(root)
        try:
            izbor = input(f"  {cyan('›')} Izbor: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if izbor == "0" or izbor.lower() in ("q", "quit", "exit", "izlaz"):
            print(zeleno("\n  Doviđenja! 👋\n"))
            break

        fn = mapa.get(izbor)
        if fn:
            try:
                fn(root)
            except KeyboardInterrupt:
                print()
                info("Akcija prekinuta.")
        else:
            greška(f"Nepoznat izbor: '{izbor}'")

        input(f"\n  {sivo('Pritisni Enter za povratak na meni...')}")

if __name__ == "__main__":
    main()
