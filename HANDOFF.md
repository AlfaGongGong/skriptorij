# HANDOFF — 2026-11-03 (v9)
Repo: /root/skriptorij
Zadnji commiti: `c218bbc` (UI), plus backend fixevi.

## Trenutno stanje — podeljeno
1. **UI (Asistent)** — ZAVRŠENO. Human Timeline, Zen Mode, Spinner, Stuck Alert.
2. **Backend (Claude)** — `epub_gate.py` (završna kapija nad EPUB-om).
3. **Backend (Asistent)** — `_ocisti_ai_markere` fix, `chk_zarez_fix` (upravo pušteno).

## Šta je urađeno skoro
- **UI**: `main.js` + `style.css`. Timeline prikazuje korake sa spinnerom. Zen mode skriva tehničke detalje (semafor, sirovi log) iza dugmeta "⚙️ Prikaži tehničke detalje". Ostali tabovi netaknuti.
- **Navodnici**: `_navodnici_u_tekstu` i `_dijalog` popravljeni. ASCII navodnici (6622->79) i siročad `”` rešeni.
- **Overlap**: `_skrati_overlap_fuzzy` (čuva `<p>`). Najdulji odlomak 452->114.
- **Imena**: `Nail -> Klin` (49x), `Judge -> Sutkinja` (159x), `Adua` padeži (25x).
- **Lint**: `core/lint_hr.py` kuka u `_primijeni_kalkove_i_validator` (hvata `,,` i `, .`).
- **`_ocisti_ai_markere`**: sprečeno brisanje "naravno"/"svakako" u dijalogu (uzrok gubitka "of course").

## Šta ostaje (Sledeći koraci)
1. **`chk_zarez_fix`**: Provera outputa (da li je `preostalo siročadi = 0`). Ako je prošlo, `.chk` fajlovi su čisti od `,,` i `, .`.
2. **`_ocisti_ai_markere` fix**: Pustiti apply skriptu (ako već nije) da se "naravno" sačuva za buduće prevode.
3. **`epub_gate.py`**: Claude pravi završnu kapiju nad EPUB-om. Kada je gotova, pokrećemo je da potvrdimo da nema grešaka.
4. **Rebuild**: Kada su svi .chk fajlovi čisti, radimo poslednji rebuild EPUB-a.

## Kontekst za Claude-a
- Ne diraj UI (main.js, style.css) — tu je Asistent završio.
- Kanon u repou (`data/kanon/knjige/`) i MoonReader-u se razilaze. Claude treba da sinkronizuje `Nail -> Klin` u repo kopiju.
- Za `epub_gate.py`: ne diraj `styler.py` ni `packager.py`, samo čitaj finalni EPUB i vraćaj `True/False`.
