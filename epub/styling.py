
# epub/styling.py

_EPUB_PAPER_CSS = """\
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1em;
    line-height: 1.8;
    text-align: justify;
    color: #2c1a0e;
    background-color: #f5e6c8;
    margin: 3% 6%;
    padding: 0;
}

p {
    margin: 0;
    padding: 0;
    text-indent: 1.5em;
    orphans: 2;
    widows: 2;
}

p:first-child,
h1 + p,
h2 + p,
h3 + p {
    text-indent: 0;
}

h1 {
    font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    color: #800020;
    text-align: center;
    font-size: 2.2em;
    font-weight: normal;
    letter-spacing: 0.06em;
    margin: 4em 0 2em;
    padding: 0;
    page-break-before: always;
    line-height: 1.3;
}

h2 {
    font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    color: #800020;
    text-align: center;
    font-size: 1.5em;
    font-weight: normal;
    letter-spacing: 0.03em;
    margin: 0 0 1.8em;
    padding: 1.2em 0 0;
    page-break-before: always;
    line-height: 1.3;
}

h3 {
    font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    color: #800020;
    text-align: center;
    font-size: 1.15em;
    font-weight: normal;
    letter-spacing: 0.02em;
    margin: 0 0 1.2em;
    padding: 0.5em 0 0;
    line-height: 1.4;
}

span.dropcap {
    float: left;
    font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    font-size: 3.0em;
    line-height: 0.82;
    margin-right: 0.07em;
    margin-top: 0.06em;
    margin-bottom: 0;
    margin-left: 0;
    color: #800020;
    font-weight: bold;
}

blockquote {
    margin: 1em 2em;
    font-style: italic;
    color: #4a3728;
    border-left: 3px solid #c5a57a;
    padding-left: 1em;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}

a {
    color: #800020;
    text-decoration: none;
}

table {
    border-collapse: collapse;
    margin: 1em auto;
    font-size: 0.9em;
}

td, th {
    border: 1px solid #c5a57a;
    padding: 0.4em 0.8em;
}
"""


def _inject_epub_global_css(soup):
    # Remove any previously injected Booklyfi style block to avoid duplicates
    existing = soup.find("style", id="booklyfi-style")
    if existing:
        existing.decompose()

    style = soup.new_tag("style", id="booklyfi-style")
    style.string = _EPUB_PAPER_CSS
    if soup.head:
        soup.head.append(style)
    elif soup.html:
        head = soup.new_tag("head")
        head.append(style)
        soup.html.insert(0, head)
