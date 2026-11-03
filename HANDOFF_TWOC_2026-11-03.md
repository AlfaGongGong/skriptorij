# HANDOFF v7 — TWOC, 2026-11-03
Repo: /root/skriptorij. Dopuna uz KONTEKST.md v6 (ne zamjenjuje ga; pravila P1-P19 ostaju na snazi).

## Povuceno u ovoj sesiji (ne ponavljati)
- "EPUB je zastario jer je mtime 30.10." — netacno: styler cuva stari mtime, a sadrzaj se mijenja.
- "Packager dodaje ASCII navodnike" — netacno: packager.py:340-370 radi ispravno (U ima ~1274).
- "7 poglavlja fali u EPUB-u" — styler ih namjerno brise (cover/slika/copyright/TOC/marketing: part0167-0170, 0172, 0243, 0246).
- Hipoteze: styler bira drugi _skr_ folder; _ocisti_chk vraca ASCII — obje pale (postoji jedan _skr_ folder; _ocisti_chk ne dira navodnike).

## Uzroci nadjeni i popravljeni
1. Navodnici u STYLED (ASCII 6622 -> 79): epub/styler.py _dijalog primjenjivao je DIJALOG_TIPOGRAFIJA (core/kalkovi/dijalog.py) koji je tipografske navodnike vracao u ASCII ". Sada preskace pravila ciji replace sadrzi ". (dijalog.py NIJE mijenjan.)
2. Siroce zatvarac u odlomku s crticom: core/text_utils.py _navodnici_u_tekstu (commit 0abb65e) + poziv iza _dijalog u styleru (84e151c). Odlomaka s crticom i orphan zatvaracem: 146 -> 1.
3. Judge -> Sutkinja po padezima u .chk (159 izmjena, 0 preostalo). Kanon (knjiga/jezik/termini) nema unos za Judge/Sutkinja.
4. Adua padezi u .chk (25 izmjena; 7 nominativa ostaje namjerno).
5. Dupliranje: model ponovo prevede kraj prethodnog bloka. styler.py: _skrati_overlap_fuzzy (>=0.85 na razini odlomaka; prvo fuzzy, pa egzaktni _skrati_overlap koji vraca goli tekst i slijeva odlomke). Ponovljenih recenica 77 -> 10; najduzi odlomak part0179 452 -> 114 (a592839, 744dce9).
   Pravi uzrok je u generiranju: 37 od 382 granica blokova ima preklapanje (134 odlomka). Fix u core/chunking.py je za Claudettu; ovo samo zaobilazi pri sastavljanju.

## Stanje STYLED
STYLED/Joe_Abercrombie_The_Wisdom_of_Crowds_PREVEDENO_STYLED.epub: html 76, p 6023, ASCII " 79, orphan 1, Judge 0, NEPREVEDENO 0, ",," 10, grupa dupliranja 10.
Samo mjereno, nije citano — korisnik provjerava u Moon+: part0207 (oko "Pucnula je prstima"), part0236 (navodnici), part0223 (Sutkinja), part0179/0198 (odlomci).

## Otvoreno
- 10 grupa dupliranja: part0222 [51,55],[52,57]; part0198 [81,88]; part0220 [30,34],[33,39]; part0208 [82,87],[83,89]; part0240 [91,98]. Uzrok nepoznat (preklapanje koje ne sezee do kraja bloka, ili petlja u bloku). Ako ne smeta citanju — prihvatiti.
- ",," (10), ", ." (9), cirilicno "o" u "kompromisa" (part0210), ~50 vise otvorenih nego zatvorenih navodnika (npr. "Mozda„"): jednokratna skripta nad .chk (dry-run pa apply, kao Judge).
- .chk mijesa "Sutkinja"/"sutkinja"; odluka o kanonu.
- Claudetta: core/chunking.py granice blokova.

## Rebuild bez AI (~30 s)
e = SkriptorijAllInOne("/storage/emulated/0/Download/The_Wisdom_of_Crowds.epub", "V10_TURBO", {}, {}); e.generate_ncx(); e.finalize(); zatim EpubStylerManager(epub_path=output_file).stilizuj().
Styler cita tekst poglavlja direktno iz .chk (styler.py ~1215-1330), pa je izmjena .chk odmah vidljiva; booklyfi/...PREVEDENO.epub je samo medukorak.
NE puštati run.py AUTO-RETRO: petlja run.py:492-510 ignorira BOOKLYFI_ONLY_FILES.

## Backupi (Download)
twoc_rebuild_bak_*, twoc_pre_final_*, twoc_styled_prev_*, twoc_styled_prije_*, twoc_chk_bak_* (Judge), twoc_chk_bak_adua2_*.
Skripte u tools/: judge_fix2.sh, adua_dup2.sh, styler_orphan_fix.sh, overlap_redoslijed.sh.

## Za asistenta
P19: bez novih dijagnostika; jedna skripta, STARO/NOVO, test, auto-povrat. Server: python main.py (BOOKLYFI_HOST=0.0.0.0 po potrebi).

## Git (zadnjih 15)
    744dce9 fix: styler fuzzy overlap prije egzaktnog (cuva odlomke)
    6ed38af prije: fuzzy overlap prije egzaktnog
    a592839 fix: styler fuzzy overlap blokova (_skrati_overlap_fuzzy)
    124448f prije: adua padezi + fuzzy overlap u styleru
    84e151c fix: styler uklanja siroce zatvarace u odlomku s crticom
    c6835fd prije: styler siroce zatvarac u odlomku s crticom
    8e13df6 fix: styler _dijalog ne vraca tipografske navodnike u ASCII
    5672a1a prije: styler _dijalog ne vraca tipografske navodnike u ASCII
    0abb65e fix: orphan zatvarac u odlomku s crticom (_navodnici_u_tekstu)
    a58db14 prije: orphan zatvarac u odlomku s crticom
    634799d feat: /tts/gemini proxy endpoint za TTS Server
    df9714a data: few_shot_abercombie +126 parova (T1 cleanup aftermath)
    e438a30 docs: KONTEKST.md v6 — stanje 2026-11-02, P19, TWOC 98%
    5631e46 fix: _navodnici_u_tekstu — ASCII " u „...” po pasusu
    d431891 feat: quality_status.json — stvarno AI-ocenjeno vs heuristicki fallback
