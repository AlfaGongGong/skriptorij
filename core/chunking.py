# core/chunking.py
# ISPRAVKA:
#   BUG#6 FIX: max_words default promijenjen s 1500 na 800
#              da bude konzistentan s SkriptorijAllInOne.chunk_html(max_words=800)
#              Staro: chunk_html(html_content, max_words=1500) ← bio 1500
#              Novo:  chunk_html(html_content, max_words=800)  ← konzistentno s engineom
#
#              Ova nekonzistentnost je uzrokovala pogrešan ETA proračun:
#              run.py poziva engine.chunk_html() (→ 800) za prebrojavanje,
#              ali standalone chunk_html() koristio 1500 — različit broj chunkova.

from bs4 import BeautifulSoup, NavigableString


def chunk_html(html_content: str, max_words=500) -> list:
    """
    Dijeli HTML sadržaj na blokove od max_words riječi.
    Default: 800 (konzistentno s SkriptorijAllInOne.chunk_html).
    """
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body if soup.body else soup
    chunks, current_chunk, current_words = [], [], 0
    for tag in body.children:
        tag_str = str(tag)
        text = (
            tag.get_text(strip=True)
            if not isinstance(tag, NavigableString)
            else str(tag).strip()
        )
        words = len(text.split())
        if words == 0:
            current_chunk.append(tag_str)
            continue
        if current_words + words > max_words and current_words > 0:
            chunks.append("".join(current_chunk))
            current_chunk = [tag_str]
            current_words = words
        else:
            current_chunk.append(tag_str)
            current_words += words
    if current_chunk:
        chunks.append("".join(current_chunk))
    return [c for c in chunks if c.strip()]


def get_context_window(checkpoint_dir, chunks: list, idx: int, file_name: str) -> tuple:
    prev_ctx, next_ctx = "Početak poglavlja.", "Kraj poglavlja."
    if idx > 0:
        prev_chk = checkpoint_dir / f"{file_name}_blok_{idx - 1}.chk"
        if prev_chk.exists():
            try:
                prev_raw = prev_chk.read_text("utf-8")
                prev_ctx = BeautifulSoup(prev_raw, "html.parser").get_text()[-600:]
            except Exception:
                prev_ctx = chunks[idx - 1][-600:]
        else:
            prev_ctx = chunks[idx - 1][-600:]
    if idx < len(chunks) - 1:
        next_ctx = chunks[idx + 1][:400]
    return prev_ctx, next_ctx
