# epub/styling.py
_EPUB_PAPER_CSS = "body { background: #f4ede0; } p { line-height: 1.85; }"
def _inject_epub_global_css(soup):
    style = soup.new_tag("style")
    style.string = _EPUB_PAPER_CSS
    if soup.head: soup.head.append(style)
