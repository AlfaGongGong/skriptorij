import re, shutil
path = "/storage/emulated/0/termux/Skriptorij/app.py"
shutil.copy(path, path + ".bak_aidelete")
src = open(path, encoding="utf-8").read()

# Nađi POST handler za review/chunk i dodaj DELETE odmah iza
old = '''    @app.route("/api/review/chunk/<path:stem>", methods=["POST"])
    def api_review_chunk_post(stem):'''

new = '''    @app.route("/api/review/chunk/<path:stem>", methods=["DELETE"])
    def api_review_chunk_delete(stem):
        """Briše .chk fajl za dati stem — koristi se za AI re-obradu jednog bloka."""
        try:
            chk_path = _find_chk_path(stem)
            if chk_path is None or not chk_path.exists():
                return jsonify({"ok": True, "note": "Fajl već ne postoji"}), 200
            chk_path.unlink()
            return jsonify({"ok": True, "deleted": str(chk_path)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/review/chunk/<path:stem>", methods=["POST"])
    def api_review_chunk_post(stem):'''

print("Pronađen:", old in src)
if old in src:
    src = src.replace(old, new)
    open(path, "w", encoding="utf-8").write(src)
    print("app.py OK — DELETE endpoint dodan")
else:
    # Pokušaj naći gdje je POST definiran
    idx = src.find("api_review_chunk_post")
    print("Kontekst:", repr(src[max(0,idx-100):idx+50]))