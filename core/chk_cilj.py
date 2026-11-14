"""L19: kamo review POST smije upisati ispravak bloka.

Packager spaja samo osnovne .chk (.prevod.chk i .lektura.chk preskace), pa se ispravak upisan
u njih tiho gubi. Zato se upis preusmjerava na osnovni .chk, uz ocuvano chunk_sha zaglavlje.
"""
import re
from pathlib import Path

_HDR = re.compile(r"^<!--\s*chunk_sha[^>]*-->\s*\n")
_SUFIKSI = (".lektura.chk", ".prevod.chk")


def cilj_za_upis(chk_path):
    p = Path(chk_path)
    for suf in _SUFIKSI:
        if p.name.endswith(suf):
            return p.with_name(p.name[: -len(suf)] + ".chk")
    return p


def sa_zaglavljem(izvor_path, novi_tekst):
    """Vraca novi_tekst s chunk_sha zaglavljem izvornog fajla (ako ga ima, a novi tekst nema svoje)."""
    if _HDR.match(novi_tekst):
        return novi_tekst
    try:
        m = _HDR.match(Path(izvor_path).read_text("utf-8", errors="ignore"))
    except Exception:
        m = None
    return (m.group(0) if m else "") + novi_tekst
