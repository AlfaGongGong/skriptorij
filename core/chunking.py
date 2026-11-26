# core/chunking.py — v4 (F04, 2026-11-26)
#
# v3 -> v4 (audit R7-4..R7-9, R7-25):
#   - broj rijeci: get_text(" ", strip=True) (oznake oko svake rijeci vise ne spajaju rijeci)
#   - <img>, <hr>, <a id> i komentari na pocetku bloka se vise ne gube
#   - tekst se escapea (&, <, >) pri slaganju bloka, komentari se pisu kao komentari
#   - nema umetnutog razmaka usred rijeci uz inline oznake (<i>stig</i>la)
#   - zarez-rez cuva razmake ("1,000" ostaje) i dio veci od limita se dijeli po rijecima
#   - rijecenica veca od limita unutar <p> s oznakama se dijeli po rijecima
#   - jedan zadani limit: MAX_WORDS_DEFAULT = 500 (kao produkcija)
#   - sigurnosna mreza ne uklanja oznake ako blok ima img/hr/id
#   - provjera sacuvanosti nakon chunk_html (rijeci, img, hr, id) baca ChunkingError

import re
import warnings

from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

MAX_WORDS_DEFAULT = 500


class ChunkingError(ValueError):
    """Chunking je izgubio ili promijenio sadrzaj (rijeci, img, hr, id)."""


# Granica recenice: iza . ! ? … slijedi razmak ili kraj
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u2026])\s+")
# Isto, ali razmak ostaje uz sljedeci dio (nista se ne gubi)
_SENTENCE_KEEP = re.compile(r"(?<=[.!?\u2026])(?=\s)")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _html(node) -> str:
    """HTML cvora: obican tekst se escapea, komentar ostaje komentar, tag kao str(tag)."""
    if isinstance(node, NavigableString):
        return node.output_ready(formatter="minimal")
    return str(node)


def _word_count(node) -> int:
    if isinstance(node, Comment):
        return 0
    if isinstance(node, NavigableString):
        return len(str(node).split())
    return len(node.get_text(" ", strip=True).split())


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


def _split_po_rijecima(text: str, max_words: int) -> list:
    rijeci = text.split()
    grupe = [" ".join(rijeci[i : i + max_words]) for i in range(0, len(rijeci), max_words)]
    return grupe if grupe else [text]


def _split_long_sentence(sentence: str, max_words: int) -> list:
    """
    Rezi JEDNU preveliku recenicu: prvo iza zareza (zarez i razmak ostaju uz prethodni dio,
    "1,000" se ne dira), a dio koji je i sam veci od limita po rijecima.
    """
    dijelovi = [d for d in re.split(r"(?<=,)\s+", sentence.strip()) if d]
    grupe, tren, br = [], [], 0
    for d in dijelovi:
        w = len(d.split())
        if w > max_words:
            if tren:
                grupe.append(" ".join(tren))
                tren, br = [], 0
            grupe.extend(_split_po_rijecima(d, max_words))
            continue
        if tren and br + w > max_words:
            grupe.append(" ".join(tren))
            tren, br = [d], w
        else:
            tren.append(d)
            br += w
    if tren:
        grupe.append(" ".join(tren))
    return grupe if grupe else [sentence]


def _split_text_by_sentences(text: str, max_words: int) -> list:
    """
    Rezi TEKST po recenicama u grupe od najvise max_words rijeci (cisti tekst, bez escapea).
    Nikad ne rezi rijec na pola.
    """
    if not text.strip():
        return [text]

    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    grupe, trenutna, trenutne_rijeci = [], [], 0
    for s in sentences:
        w = len(s.split())
        if w > max_words:
            if trenutna:
                grupe.append(" ".join(trenutna))
                trenutna, trenutne_rijeci = [], 0
            grupe.extend(_split_long_sentence(s, max_words))
            continue
        if trenutne_rijeci > 0 and trenutne_rijeci + w > max_words:
            grupe.append(" ".join(trenutna))
            trenutna, trenutne_rijeci = [s], w
        else:
            trenutna.append(s)
            trenutne_rijeci += w
    if trenutna:
        grupe.append(" ".join(trenutna))
    return grupe if grupe else [text]


def _split_p_tag(p_tag: Tag, max_words: int) -> list:
    """Rezi JEDAN <p> na vise <p> (HTML stringovi), cuvajuci unutarnje oznake."""
    open_tag, close_tag = _tag_open_close(p_tag)
    if not close_tag:
        return [str(p_tag)]

    djeca = list(p_tag.children)
    if len(djeca) == 1 and type(djeca[0]) is NavigableString:
        dijelovi = _split_text_by_sentences(str(djeca[0]), max_words)
        return [open_tag + _esc(d) + close_tag for d in dijelovi]

    dijelovi = []
    tren = []
    br = 0

    def flush():
        nonlocal tren, br
        if tren:
            dijelovi.append("".join(tren))
        tren, br = [], 0

    for child in djeca:
        if isinstance(child, NavigableString):
            if type(child) is not NavigableString:  # komentar, CDATA...
                tren.append(_html(child))
                continue
            text = str(child)
            dijelovi_s = [s for s in _SENTENCE_KEEP.split(text) if s != ""] or [text]
            for s in dijelovi_s:
                w = len(s.split())
                if w > max_words:
                    lead = s[: len(s) - len(s.lstrip())]
                    trail = s[len(s.rstrip()) :]
                    dp = _split_long_sentence(s.strip(), max_words)
                    for i, d in enumerate(dp):
                        wd = len(d.split())
                        if br > 0 and br + wd > max_words:
                            flush()
                        txt = (lead if i == 0 else "") + d + (trail if i == len(dp) - 1 else "")
                        tren.append(_esc(txt))
                        br += wd
                        if i < len(dp) - 1:
                            flush()
                    continue
                if br > 0 and br + w > max_words:
                    flush()
                tren.append(_esc(s))
                br += w
        else:
            s = str(child)
            w = _word_count(child)
            if isinstance(child, Tag) and w > max_words:
                flush()
                dijelovi.extend(_split_p_tag(child, max_words))
                continue
            if br > 0 and br + w > max_words:
                flush()
            tren.append(s)
            br += w

    flush()
    if not dijelovi:
        return [str(p_tag)]
    return [open_tag + d + close_tag for d in dijelovi]


def _grupisi_djecu(children: list, max_words: int) -> list:
    """
    Grupira djecu u grupe od najvise max_words rijeci. Dijete bez rijeci (img, hr, <a id>,
    komentar) se UVIJEK zadrzava (na pocetku se prilijepi prvoj sljedecoj grupi).
    Vraca listu grupa (svaka grupa je lista HTML stringova).
    """
    grupe = []
    trenutna = []
    br = 0

    for child in children:
        w = _word_count(child)

        if w == 0:
            # samo prazan obican tekst na pocetku grupe se baca (razmaci izmedju blokova)
            if trenutna or type(child) is not NavigableString:
                trenutna.append(_html(child))
            continue

        if w > max_words and (isinstance(child, Tag) or type(child) is NavigableString):
            pre = []
            if trenutna:
                if br > 0:
                    grupe.append(trenutna)
                else:
                    pre = trenutna
                trenutna, br = [], 0

            if isinstance(child, Tag):
                if child.name == "p":
                    dijelovi = _split_p_tag(child, max_words)
                else:
                    open_tag, close_tag = _tag_open_close(child)
                    if close_tag:
                        dijelovi = [
                            open_tag + "".join(ug) + close_tag
                            for ug in _grupisi_djecu(list(child.children), max_words)
                        ]
                    else:
                        dijelovi = [str(child)]
            else:
                dijelovi = [
                    "<p>" + _esc(d.strip()) + "</p>"
                    for d in _split_text_by_sentences(str(child), max_words)
                ]

            if pre:
                if dijelovi:
                    dijelovi[0] = "".join(pre) + dijelovi[0]
                else:
                    dijelovi = ["".join(pre)]
            for d in dijelovi:
                grupe.append([d])
            continue

        if br > 0 and br + w > max_words:
            grupe.append(trenutna)
            trenutna = [_html(child)]
            br = w
        else:
            trenutna.append(_html(child))
            br += w

    if trenutna:
        grupe.append(trenutna)
    return grupe


def _spoji_bez_rijeci(chunks: list) -> list:
    """F04b: blok bez ijedne rijeci (samo <img>/<hr>/<a id>) se spaja sa susjednim blokom,
    jer AI takav blok ne moze prevesti (zavrsi kao [[NEPREVEDENO: blok N]])."""
    izlaz, pred = [], ""
    for c in chunks:
        if not BeautifulSoup(c, "html.parser").get_text(" ", strip=True).split():
            if izlaz:
                izlaz[-1] += c
            else:
                pred += c
            continue
        izlaz.append(pred + c)
        pred = ""
    if pred:
        izlaz.append(pred)
    return izlaz


def _otisak(html_content: str) -> tuple:
    """(broj rijeci, broj img, broj hr, skup id-ova) tijela dokumenta."""
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body if soup.body else soup
    rijeci = len(body.get_text(" ", strip=True).split())
    ids = {str(t.get("id")) for t in body.find_all(attrs={"id": True})}
    return rijeci, len(body.find_all("img")), len(body.find_all("hr")), ids


def _provjeri_sacuvanost(ulaz: str, chunkovi: list) -> None:
    """R7-25: nakon rezanja ne smije nestati ni promijeniti se rijec, img, hr ni id."""
    a = _otisak(ulaz)
    b = _otisak("".join(chunkovi))
    greske = []
    if a[0] != b[0]:
        greske.append("rijeci %d -> %d" % (a[0], b[0]))
    if a[1] != b[1]:
        greske.append("img %d -> %d" % (a[1], b[1]))
    if a[2] != b[2]:
        greske.append("hr %d -> %d" % (a[2], b[2]))
    if a[3] != b[3]:
        greske.append("id nedostaje: %s" % sorted(a[3] - b[3])[:5])
    if greske:
        raise ChunkingError("chunk_html nije sacuvao sadrzaj: " + "; ".join(greske))


def chunk_html(html_content: str, max_words: int = MAX_WORDS_DEFAULT) -> list:
    """
    Dijeli HTML na blokove od najvise max_words rijeci (zadano MAX_WORDS_DEFAULT = 500).
    Veliki <p> se rezi po recenicama, veliki <div> po djeci, velika recenica po zarezu/rijecima.
    Cuva inline oznake, img/hr/sidra; nikad ne rezi rijec. Baca ChunkingError ako se sadrzaj promijeni.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body if soup.body else soup

    grupe = _grupisi_djecu(list(body.children), max_words)
    chunks = ["".join(g) for g in grupe if "".join(g).strip()]
    chunks = _spoji_bez_rijeci(chunks)
    gotovi = []
    for c in chunks:
        gotovi.extend(_sigurno_rezi(c, max_words))
    _provjeri_sacuvanost(html_content, gotovi)
    return gotovi


def _sigurno_rezi(chunk: str, max_words: int) -> list:
    """Zadnja mreza: blok i nakon svega > 2*max_words rijeci se rezi po tekstu.
    Ako blok ima img/hr/id, NE dira se (oznake bi se izgubile); bolje velik blok nego izgubljen sadrzaj."""
    try:
        soup = BeautifulSoup(chunk, "html.parser")
        tekst = soup.get_text("\n")
    except Exception:
        return [chunk]
    if len(tekst.split()) <= max_words * 2:
        return [chunk]
    if soup.find(["img", "hr"]) or soup.find(attrs={"id": True}):
        return [chunk]
    odlomci = [o.strip() for o in re.split(r"\n+", tekst) if o.strip()]
    dijelovi = []
    for o in odlomci:
        if len(o.split()) > max_words:
            dijelovi.extend(_split_text_by_sentences(o, max_words))
        else:
            dijelovi.append(o)
    izlaz, tren, br = [], [], 0
    for d in dijelovi:
        w = len(d.split())
        if tren and br + w > max_words:
            izlaz.append("".join("<p>" + _esc(x) + "</p>" for x in tren))
            tren, br = [], 0
        tren.append(d)
        br += w
    if tren:
        izlaz.append("".join("<p>" + _esc(x) + "</p>" for x in tren))
    return izlaz or [chunk]


def get_context_window(checkpoint_dir, chunks: list, idx: int, file_name: str) -> tuple:
    """
    Vraća (prev_ctx, next_ctx): zadnje 2 rečenice prethodnog bloka i
    prva rečenica sljedećeg bloka (plain EN). Placeholder ako nema.
    """
    prev_ctx = "Ovo je prvi blok poglavlja."
    next_ctx = "Ovo je zadnji blok poglavlja."

    if idx > 0 and idx - 1 < len(chunks):
        try:
            prev_text = BeautifulSoup(chunks[idx - 1], "html.parser").get_text(" ")
            prev_text = re.sub(r"\s+", " ", prev_text).strip()
            if prev_text:
                tail = " ".join(_SENTENCE_SPLIT.split(prev_text)[-2:]).strip()
                if tail:
                    prev_ctx = tail[-300:]
        except Exception:
            prev_ctx = "Prethodni blok postoji. Nastavi stil i ton."

    if idx < len(chunks) - 1:
        try:
            next_text = BeautifulSoup(chunks[idx + 1], "html.parser").get_text(" ")
            next_text = re.sub(r"\s+", " ", next_text).strip()
            if next_text:
                head = _SENTENCE_SPLIT.split(next_text)[0].strip()
                if head:
                    next_ctx = head[:250]
        except Exception:
            next_ctx = "Sljedeći blok postoji."

    return prev_ctx, next_ctx
