# BOOKLYFI — KONTEKST PROJEKTA v7 (2026-11-03)
Lokacija: /root/skriptorij (proot Ubuntu)
Server: BOOKLYFI_HOST=0.0.0.0 python3 main.py (http://127.0.0.1:8080)

---

## POSTULATI RADA (MORANJE P1-P19)
P1 Git umesto .bak.
P2 Jedna izmena, ast.parse + py_compile, pa test.
P3 Zabranjeni obrasci (re.sub za kod, sed -i bez prikaza).
P4 Obavezan STARO/NOVO pre primene (čekaj "da").
P5 Dijagnostika pre fixa (grep -n, sed -n, bez pretpostavki).
P6 Greška se poništava (git checkout), ne popravlja.
P7 Backup pre AI sesije.
P8 Kontekst ažuriran pre sesije.
P9 AI ne dira van zahteva.
P10 AI-jev "OK" nije dokaz, korisnik pokreće.
P11 Integritet podataka prvo (provera pre upisa).
P12 Modeli se ne hardkodiraju (model_discovery).
P13 Raspodela opterećenja (kratki=GROQ, dugi=GEMINI).
P14 Otpornost (circuit breaker, quota na disk).
P15 live_audit kao JSON, ne HTML.
P16 Output sa clear + tee + tools/out.sh.
P17 Dijagnostika → STARO/NOVO → ast.parse → test → audit.
P18 REPO GUARD u svakoj skripti.
**P19 — Overdiagnose sindrom:** Max 2 prolaza dijagnostike. Jedna skripta sa svim odgovorima. Direktan odgovor na direktno pitanje. Ne ponavljaj ono što je već provereno.

---

## TRENUTNO STANJE (2026-11-03)
- **Faza:** Finalizacija TWOC prevoda.
- **TWOC:** 99% gotov. `.chk` fajlovi su čisti od navodnika, duplikata, `NEPREVEDENO`.
- **UI:** Potpuno redizajniran (Zen Mode). Glavni fokus na Human Timeline.
- **Zadnji HEAD:** `c218bbc` (UI Spinner/Stuck logika), pre toga `11ae2d0`, `7b9d1b4`, `70c7414` (lint).

### Commitovani fixevi (Stabilno, ne dirati bez STARO/NOVO)
- **UI:** `c218bbc` (Spinner), `2b39ff4` (Zen mode), `75bcb81` (Timeline).
- **Navodnici:** `0abb65e`, `84e151c`, `8e13df6` (ascii->typographic).
- **Overlap:** `a592839`, `744dce9` (fuzzy overlap).
- **Lint:** `70c7414` (kuka u pipeline).
- **_ocisti_ai_markere:** (U toku, sprecava brisanje "naravno").

---

## STRUKTURA PROJEKTA
(Standardna struktura ostaje ista: main.py, run.py, app.py, api/routes/, core/, processing/, epub/, network/, analysis/, data/).
- `core/lint_hr.py` — novi modul za lint pravila.
- `core/text_utils.py` — `_ocisti_ai_markere` (AI uvodi), `_navodnici_u_tekstu`.
- `epub/styler.py` — `_skrati_overlap_fuzzy`.

---

## PIPELINE I UI
### UI — Human Timeline
- `main.js`: `updateHumanTimeline` (deduplikacija, spinner), `_checkTimelineStuck` (alert ako AI ne odgovori >25s).
- `style.css`: `.human-timeline`, `.zen-toggle-bar`.
- Zen Mode: Sakriva `.stats-grid`, `.card-pipeline`, `#audit-log` iza jednog dugmeta.

### Stilizacija
- `styler.py`: `_dijalog` (ne vraća tipografske u ascii), `_skrati_overlap_fuzzy` (čuva `<p>` strukturu).

---

## SLEDEĆI KORACI (Prioritet)
1. **Provera `chk_zarez_fix` outputa:** Da li su `,,` i `, .` obrisani iz `.chk`.
2. **Apply `_ocisti_ai_markere` fix:** Da se "naravno" sačuva u dijalogu za buduće blokove.
3. **Kapija nad EPUB-om (`epub_gate.py`):** Claude pravi skriptu za finalnu proveru.
4. **Rebuild:** Kada je sve čisto, puštamo `styler` i pravimo finalni EPUB.

## NE DIRATI
- Commitovane fajlove iz tabele gore.
- `_FROZEN_TWOC/`.
- `data/kalkovi_karantena.db` (checkout pre commita).
- Kanon u MoonReader-u (Claude radi sync u repo).
