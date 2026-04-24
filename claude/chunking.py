# core/chunking.py
from bs4 import BeautifulSoup, NavigableString

def chunk_html(html_content: str, max_words=800) -> list:
    soup = BeautifulSoup(html_content, "html.parser")
    body = soup.body if soup.body else soup
    chunks, current_chunk, current_words = [], [], 0
    for tag in body.children:
        tag_str = str(tag)
        text = tag.get_text(strip=True) if not isinstance(tag, NavigableString) else str(tag).strip()
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
            except:
                prev_ctx = chunks[idx - 1][-600:]
        else:
            prev_ctx = chunks[idx - 1][-600:]
    if idx < len(chunks) - 1:
        next_ctx = chunks[idx + 1][:400]
    return prev_ctx, next_ctx
