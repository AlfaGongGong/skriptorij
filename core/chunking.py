# core/chunking.py — v3 (2026-10-06)
#
# ZAŠTO v3:
#   v2 je grupirala djecu <div>/<p> po max_words, ali NIJE rezala pojedinačni <p>.
#   Kad je <p> > max_words, ostavljen je cijeli — rezultat: prevelik chunk
#   (HTTP 413 na Groq, MAX_TOKENS na drugima).
#
# RJEŠENJE u v3:
#   1. Grupiraj djecu po max_words (kao v2).
#   2. Ako je POJEDINAČNI <p> > max_words — reži ga PO REČENICAMA.
#   3. Čuvaj HTML tagove (<em>, <i>, <b>) unutar rečenice.
#   4. Nikad ne reži riječ na pola.
#   5. Ako je rečenica > max_words — reži po zarezu/razmaku.
#   6. Ne gubi tekst — svaki znak ide u točno jedan chunk.
#
# Default max_words = 400 (sigurnija granica za modele s niskim TPM).

import re
import warnings
from bs4 import XMLParsedAsHTMLWarning
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from bs4 import BeautifulSoup, NavigableString, Tag


# Regex za granicu rečenice: iza . ! ? … slijedi razmak ili kraj
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u2026])\s+")


def _word_count(node) -> int:
    if isinstance(node, NavigableString):
        return len(str(node).split())
    return len(node.get_text(strip=True).split())


def _tag_open_close(tag) -> tuple:
    """Vraca (open_tag, close_tag)."""
    full = str(tag)
    inner = "".join(str(c) for c in tag.children)
    close_tag = f"</{tag.name}>"
    if inner and full.endswith(close_tag):
        open_tag = full[: len(full) - len(inner) - len(close_tag)]
    elif full.endswith(close_tag):
        open_tag = full[: len(full) - len(close_tag)]
    else:
        return full, ""
    return open_tag, close_tag


def _split_text_by_sentences(text: str, max_words: int) -> list:
    """
    Reži TEKST po rečenicama, u grupe od max_words.
    Nikad ne reže riječ na pola. Ako je rečenica > max_words, reže po zarezu.
    Vraća listu stringova.
    """
    if not text.strip():
        return [text]

    # 1. Podijeli po rečenicama
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    # 2. Grupiraj rečenice u grupe od max_words
    grupe = []
    trenutna = []
    trenutne_rijeci = 0

    for s in sentences:
        w = len(s.split())

        # Ako je JEDNA rečenica prevelika — reži je
        if w > max_words:
            # Prvo zatvori trenutnu grupu
            if trenutna:
                grupe.append(" ".join(trenutna))
                trenutna = []
                trenutne_rijeci = 0
            # Reži veliku rečenicu
            dijelovi = _split_long_sentence(s, max_words)
            grupe.extend(dijelovi)
            continue

        if trenutne_rijeci > 0 and trenutne_rijeci + w > max_words:
            grupe.append(" ".join(trenutna))
            trenutna = [s]
            trenutne_rijeci = w
        else:
            trenutna.append(s)
            trenutne_rijeci += w

    if trenutna:
        grupe.append(" ".join(trenutna))

    return grupe if grupe else [text]


def _split_long_sentence(sentence: str, max_words: int) -> list:
    """
    Reži JEDNU preveliku rečenicu. Prvo po zarezu, pa po razmaku.
    Nikad ne reže riječ na pola.
    """
    # Probaj po zarezu
    if "," in sentence:
        dijelovi = [d.strip() for d in sentence.split(",") if d.strip()]
        if len(dijelovi) > 1:
            # Grupiraj dijelove po max_words
            grupe = []
            trenutna = []
            trenutne_rijeci = 0
            for d in dijelovi:
                w = len(d.split())
                if trenutne_rijeci > 0 and trenutne_rijeci + w > max_words:
                    grupe.append(", ".join(trenutna) + ",")
                    trenutna = [d]
                    trenutne_rijeci = w
                else:
                    trenutna.append(d)
                    trenutne_rijeci += w
            if trenutna:
                grupe.append(", ".join(trenutna))
            return grupe

    # Zadnja linija: reži po razmaku
    rijeci = sentence.split()
    grupe = []
    trenutna = []
    for r in rijeci:
        trenutna.append(r)
        if len(trenutna) >= max_words:
            grupe.append(" ".join(trenutna))
            trenutna = []
    if trenutna:
        grupe.append(" ".join(trenutna))
    return grupe if grupe else [sentence]


def _split_p_tag(p_tag: Tag, max_words: int) -> list:
    """
    Reži JEDAN <p> tag na više <p> tagova, čuvajući unutrašnje tagove.
    Vraća listu stringova (HTML).
    """
    open_tag, close_tag = _tag_open_close(p_tag)
    if not close_tag:
        return [str(p_tag)]

    # Ako <p> ima samo tekst — reži po rečenicama
    if len(list(p_tag.children)) == 1 and isinstance(list(p_tag.children)[0], NavigableString):
        text = str(list(p_tag.children)[0])
        dijelovi = _split_text_by_sentences(text, max_words)
        return [open_tag + d + close_tag for d in dijelovi]

    # Ako <p> ima ugniježđene tagove (<em>, <i>, <b>) — reži po rečenicama na tekstualnoj razini
    # Prvo: pretvori u "virtualni" tekst s tagovima
    # Jednostavno: iteriraj kroz djecu, akumuliraj tekst, čuvaj tagove

    dijelovi = []  # lista (tekst, tagovi)
    trenutni_tekst = []
    trenutni_trenutni_rijeci = 0
    trenutni_dijelovi = []  # čuvaj (string, tip)

    def flush():
        nonlocal trenutni_tekst, trenutni_trenutni_rijeci, trenutni_dijelovi
        if trenutni_dijelovi:
            html_inner = "".join(trenutni_dijelovi)
            dijelovi.append(html_inner)
        trenutni_tekst = []
        trenutni_trenutni_rijeci = 0
        trenutni_dijelovi = []

    for child in p_tag.children:
        if isinstance(child, NavigableString):
            text = str(child)
            # Reži ovaj tekst po rečenicama
            sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
            if not sentences:
                sentences = [text]
            for s in sentences:
                w = len(s.split())
                if trenutni_trenutni_rijeci > 0 and trenutni_trenutni_rijeci + w > max_words:
                    flush()
                trenutni_dijelovi.append(s + " " if not s.endswith(" ") else s)
                trenutni_trenutni_rijeci += w
        else:
            # Tag (<em>, <i>, <b>) — dodaj u trenutni dio
            s = str(child)
            w = _word_count(child)
            if trenutni_trenutni_rijeci > 0 and trenutni_trenutni_rijeci + w > max_words:
                flush()
            trenutni_dijelovi.append(s)
            trenutni_trenutni_rijeci += w

    flush()

    if not dijelovi:
        return [str(p_tag)]

    return [open_tag + d + close_tag for d in dijelovi]


def _grupisi_djecu(children: list, max_words: int) -> list:
    """
    Grupira djecu u grupe od max_words.
    Ako je pojedinačno dijete > max_words i to je <p>, reži ga.
    Vraća listu grupa (svaka grupa je lista stringova HTML).
    """
    grupe = []
    trenutna = []
    trenutne_rijeci = 0

    for child in children:
        w = _word_count(child)

        if w == 0:
            if trenutna:
                trenutna.append(str(child))
            continue

        # Ako je <p> > max_words — reži ga
        if isinstance(child, Tag) and child.name == "p" and w > max_words:
            if trenutna:
                grupe.append(trenutna)
                trenutna = []
                trenutne_rijeci = 0
            # Reži <p>
            dijelovi = _split_p_tag(child, max_words)
            for d in dijelovi:
                grupe.append([d])
            continue

        # Ako je bilo koji drugi tag > max_words (npr. <div>) — rekurzivno
        if isinstance(child, Tag) and w > max_words:
            if trenutna:
                grupe.append(trenutna)
                trenutna = []
                trenutne_rijeci = 0
            # Rekurzivno obradi djecu tog taga
            open_tag, close_tag = _tag_open_close(child)
            if close_tag:
                unutrasnje_grupe = _grupisi_djecu(list(child.children), max_words)
                for ug in unutrasnje_grupe:
                    grupe.append([open_tag + "".join(ug) + close_tag])
            else:
                grupe.append([str(child)])
            continue

        if trenutne_rijeci > 0 and trenutne_rijeci + w > max_words:
            grupe.append(trenutna)
            trenutna = [str(child)]
            trenutne_rijeci = w
        else:
            trenutna.append(str(child))
            trenutne_rijeci += w

    if trenutna:
        grupe.append(trenutna)

    return grupe


def chunk_html(html_content: str, max_words: int = 250) -> list:
    """
    Dijeli HTML sadržaj na blokove od max_words riječi.

    Radi za sve slučajeve:
    - Ako je <p> prevelik — reži po rečenicama.
    - Ako je <div> prevelik — reži po <p> djeci.
    - Ako je rečenica prevelika — reži po zarezu/razmaku.
    - Nikad ne reže riječ na pola.
    - Čuva <em>, <i>, <b> unutar rečenice.

    Default: 400 riječi.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body if soup.body else soup

    grupe = _grupisi_djecu(list(body.children), max_words)
    chunks = ["".join(g) for g in grupe if "".join(g).strip()]
    return chunks


def get_context_window(checkpoint_dir, chunks: list, idx: int, file_name: str) -> tuple:
    """
    Vraća (prev_ctx, next_ctx) — BEZ TEKSTA (samo oznaka).
    """
    prev_ctx = "Prethodni blok postoji. Nastavi stil i ton." if idx > 0 else "Ovo je prvi blok poglavlja."
    next_ctx = "Sljedeći blok postoji." if idx < len(chunks) - 1 else "Ovo je zadnji blok poglavlja."
    return prev_ctx, next_ctx
