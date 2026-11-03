import ast, sys
P = "processing/pipeline.py"
STARO = r'''            logging.debug(f"[pipeline] Rod detektor greška (blok {chunk_idx}): {e}")

    return finalno
'''
NOVO = r'''            logging.debug(f"[pipeline] Rod detektor greška (blok {chunk_idx}): {e}")

    # Korak 12: lint_hr — sigurni popravci oblika + oznake (fail-safe, bez AI)
    try:
        from core.lint_hr import lint_blok as _lint_blok

        _lint_out, _lint_r = _lint_blok(finalno)
        if _lint_out and len(_lint_out.strip()) > 10:
            finalno = _lint_out
        _lint_fix = _lint_r.get("fix", {})
        _lint_flag = _lint_r.get("flag", {})
        if _lint_fix or _lint_flag:
            self.log(
                f"[{file_name}] Blok {chunk_idx}: lint_hr fix={_lint_fix} flag={_lint_flag}",
                "tech",
            )
        _lint_dir = getattr(self, "checkpoint_dir", None)
        if _lint_flag and _lint_dir:
            import json as _json_lint

            with open(_lint_dir / "lint_flags.jsonl", "a", encoding="utf-8") as _lf:
                _lf.write(
                    _json_lint.dumps(
                        {"blok": f"{file_name}_blok_{chunk_idx}", "flag": _lint_flag},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except Exception as _lint_err:
        logging.warning(f"[pipeline] lint_hr greška (blok {chunk_idx}): {_lint_err}")

    return finalno
'''
src = open(P, encoding="utf-8", newline="").read()
n = src.count(STARO)
print("STARO pojavljivanja =", n)
if n != 1:
    sys.exit("FAIL: STARO mora biti tacno 1x, nista nije mijenjano")
out = src.replace(STARO, NOVO)
ast.parse(out)
with open(P, "w", encoding="utf-8", newline="") as h:
    h.write(out)
print("upisano")
