path = "/storage/emulated/0/termux/Skriptorij/static/js/main.js"
import shutil, re
shutil.copy(path, path + ".bak_selectreview")

src = open(path, encoding="utf-8").read()

old = '''    // Init highlight editor ako još nije
    if (window._hlEditor) window._hlEditor.init();

    // Textarea: loading state
    if (window._hlEditor) window._hlEditor.applyText("⏳ Učitavam…");

    let text = "";
    try {
        const r = await fetch(
            `/api/review/chunk/${encodeURIComponent(item.stem || item.file)}`
        );
        const ct = r.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
            const d = await r.json();
            text = d.text !== undefined ? d.text : "";
        } else {
            text = await r.text();
        }
    } catch (e) {
        text = item.preview && item.preview !== "—" ? item.preview : "";
    }
    text = text.trim();

    // Popuni editor I pokreni highlight sken
    if (window._hlEditor) {
        window._hlEditor.applyText(text);
    } else {
        const ta = document.getElementById("review-text");
        if (ta) ta.value = text;
    }'''

new = '''    // Init highlight editor ako još nije — ali samo ako element postoji
    const _taCheck = document.getElementById("review-text") || document.getElementById("review-textarea");
    if (window._hlEditor && document.getElementById("review-text")) {
        window._hlEditor.init();
        window._hlEditor.applyText("⏳ Učitavam…");
    } else if (_taCheck) {
        _taCheck.value = "⏳ Učitavam…";
    }

    let text = "";
    try {
        const r = await fetch(
            `/api/review/chunk/${encodeURIComponent(item.stem || item.file)}`
        );
        const ct = r.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
            const d = await r.json();
            text = d.text !== undefined ? d.text : "";
        } else {
            text = await r.text();
        }
    } catch (e) {
        text = item.preview && item.preview !== "—" ? item.preview : "";
    }
    text = text.trim();

    // Popuni editor — koristi šta god postoji u DOM-u
    const _taFill = document.getElementById("review-text") || document.getElementById("review-textarea");
    if (window._hlEditor && document.getElementById("review-text")) {
        window._hlEditor.applyText(text);
    } else if (_taFill) {
        _taFill.value = text;
        _taFill.placeholder = text ? "" : "Upiši prijevod ovdje (blok je prazan)...";
    }'''

if old in src:
    src = src.replace(old, new)
    open(path, "w", encoding="utf-8").write(src)
    print("OK: _selectReviewInline ispravljen")
else:
    print("GREŠKA: stari kod nije pronađen")
    # Debug — pokazi kontekst
    idx = src.find("Init highlight editor")
    if idx >= 0:
        print("Nadjen na poziciji:", idx)
        print(repr(src[idx:idx+200]))
    raise SystemExit(1)
