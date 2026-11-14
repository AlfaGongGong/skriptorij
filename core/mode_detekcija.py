"""L22: odredjivanje moda knjige (PREVOD / LEKTURA) iz EN izvora (checkpoints/izvor_en/*.en).

Zasto: pri nastavku sesije HTML u work_dir je vec preveden pa detekcija na njemu daje LEKTURA
za englesku knjigu (King of Thorns, Prince of Thorns spremljeni kao LEKTURA). Kopija EN izvora
(P2.20) je jedini pouzdan uzorak.
"""
import re
from pathlib import Path

HR_DIJAKRITIKA_PRAG = 0.003
EN_PRAG_LEKTURA = 0.05   # EN stop-word udio ispod kojeg je tekst vjerojatno vec HR (engleska proza ~0.09-0.15)


def odluci_mode(hr_ratio: float, en_ratio: float) -> str:
    if hr_ratio > HR_DIJAKRITIKA_PRAG:
        return "LEKTURA"
    if en_ratio < EN_PRAG_LEKTURA:
        return "LEKTURA"
    return "PREVOD"


def mode_iz_izvora_en(checkpoint_dir, n_files: int = 8):
    """'PREVOD' | 'LEKTURA' iz EN izvora, ili None ako izvora nema / nije citljiv."""
    try:
        from core.text_utils import _HR_DIACRITICALS, _detektuj_en_ostatke

        fajlovi = sorted((Path(checkpoint_dir) / "izvor_en").glob("*.en"))
        if not fajlovi:
            return None
        start = int(len(fajlovi) * 0.10) if len(fajlovi) > n_files else 0
        korak = max(1, (len(fajlovi) - start) // n_files)
        uzorak = fajlovi[start::korak][:n_files] or fajlovi[:n_files]
        tekst = ""
        for f in uzorak:
            sirovi = f.read_text("utf-8", errors="ignore")
            tekst += re.sub(r"<[^>]+>", " ", sirovi)[:5000] + "\n"
        if len(tekst.strip()) < 500:
            return None
        hr = sum(1 for c in tekst if c in _HR_DIACRITICALS) / max(1, len(tekst))
        return odluci_mode(hr, _detektuj_en_ostatke(tekst))
    except Exception:
        return None
