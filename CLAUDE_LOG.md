CLAUDE LOG
Jedina memorija izmedju Claude acc. Novi zapisi na vrh, ispod ove linije.
[2026-10-21 15:40] Zadatak: Iteracija 1 — F3b quality_class + EKAVIZMI
Status: ZAVRSEN
Fajlovi kreirani: core/quality_class.py, tests/unit/test_quality_class.py
Fajlovi izmijenjeni: (nijedan)
Testovi: 8/8 (test_quality_class.py, pokrenuto u izolovanom okruzenju bez repoa; ostali testovi nisu pokretani)
Sljedeci korak: Iteracija 2 iz HANDOFF.md (Zadatak 2.1 static/js/metrics.js, 2.2 static/js/fleet.js trake kvota)
Napomene: Zadatak 1.1 zavrsen. Zadatak 1.2 (suziti \breci\b) PRESKOCEN odlukom korisnika:
u core/kalkovi/ekavizmi.py ne postoji \breci\b; na indeksu [149] je \breči\b → riječi
(pravi ekavizam), a "reci"/"reći" (glagol) ne okidaju nijedan obrazac. Test 2 iz specifikacije
("reći → ekavizam") je jezicki pogresan. Ako se lazni pozitiv ponovo pojavi, treba konkretan
primjer teksta (sumnja: _ekstrahuj_cist_tekst, dinamicki_lista ili kalkovi_da).
Otvoreno: core/metrics.py vec ima classify_metrics s drugim granicama (ekavizmi OK<=2.0,
REVIEW<=10.0, + TRUNCATED) — treba odluka koja klasifikacija ostaje prije povezivanja u pipeline.
[2026-10-21 15:00] Zadatak: Stilizator omnibus + Gemma thinking fix
Status: ZAVRSEN
Fajlovi kreirani: HANDOFF.md, CLAUDE_LOG.md
Fajlovi izmijenjeni: epub/styler.py, network/http_client.py
Testovi: 71/71 sinhronizovano (stilizator), 3/3 rucno (Gemma)
Sljedeci korak: Iteracija 1 iz HANDOFF.md (F3b quality_class + EKAVIZMI)
Napomene: Gemma 4 trosi 270 thoughts tokena. Fix: max(max_tokens, 2000).
Stilizator: 9 fixeva (A1, A1b, A2, A3, C, C2, D, E1, E2). Commit e59b621.

## [2026-10-22 08:55] Zadatak: Iteracija 2 — F3c-JS metrics.js + C5-JS fleet trake
- Status: ZAVRSEN
- Fajlovi kreirani: static/js/metrics.js
- Fajlovi izmijenjeni: static/js/ui/fleet.js, static/css/style.css, templates/index.html
- Testovi: node --check OK (metrics.js, fleet.js)
- Sljedeci korak: provjeri u UI, pa Iteracija 3
- Napomene: panel u #metrics-panel, cita GET /api/quality_scores (metrics + metrics_summary)

## [2026-10-22 09:05] Zadatak: Cleanup — metrics.js obrisan (F3d ostaje)
- Status: ZAVRSEN
- Fajlovi obrisani: static/js/metrics.js
- Fajlovi izmijenjeni: templates/index.html (uklonjen #metrics-panel + <script>), static/css/style.css (uklonjen .mx-*, ostao .fq-*)
- Testovi: node --check fleet.js OK; Flask restart; curl /api/quality_scores → {OK:413, REVIEW:19, REJECT:1, TRUNCATED:10}
- Sljedeci korak: Fleet kvote trake (fq-*) ostaju u dashboardu; F3d u Quality tabu pokriva metrike
- Napomene: Odluka korisnika — F3d (commit 7834453) je dovoljan prikaz metrika, novi metrics.js je bio duplikat istog izvora /api/quality_scores. Iteracija 3 iz HANDOFF.md je sljedeća (3-4 taba + kartica statusa).

## [2026-10-22 11:15] Zadatak: Blok 1 discovery filter + test 3 namespace
- Status: ZAVRSEN
- Fajlovi kreirani: (nijedan)
- Fajlovi izmijenjeni: network/model_discovery.py, network/provider_router.py
- Testovi: 84/84 passed (bio 83/1, baseline 48/11)
- Commit: 6b65936, 9cb1c8a
- Sljedeci korak: Blok 2 refaktor (model_profiles.py profil po provajderu)
- Napomene: Discovery filter prosiren (_GLOBAL_EXCLUDE audio/vision/reasoning/non-HR,
  MISTRAL filter voxtral/codestral/pixtral/magistral, GEMINI filter image/omni/exp).
  Rezultat: GROQ 1/1, MISTRAL 23/23 (jos visok), NVIDIA 63/63, OPENROUTER 17/17,
  GEMINI ~12/18. GEMMA nema endpoint (0 modela) — otvoreno.
  Test 3 fix: provider_router koristi prov_upper kao namespace (GEMINI/GEMMA razdvojeni).

## [2026-10-22 14:30] Zadatak: Moon+ replacements + styler &middot; fix
- Status: ZAVRSEN
- Fajlovi kreirani: core/replacements.py, tools/apply_replacements.py
- Fajlovi izmijenjeni: epub/styler.py (&middot; → &#183;)
- Testovi: parser 6/6, dry-run na A Little Hatred (266 pravila, 175 aktivirano, 4335 zamjena), EPUB otvoren u Moon+ Reader-u ✅
- Sljedeci korak: 503 dijagnostika (test 3, test 4) ili Faza 3 (learning iz fires)
- Napomene:
  - Moon+ replacement format: `\bSearch\b#->#Replace` (regex), `*Search#->#Replace` (literal)
  - apply_to_html koristi regex-based text node replacement (ne BeautifulSoup) — cuva XML deklaraciju i formatiranje
  - 3 sumnjiva pravila u korisnikovom fajlu: Uffrith→Afriθ, Meadow→medou, Oxelu→Okse (ostavljena, korisnik odlucio)
  - XML greske u originalu: text/part0066.html (JSON wrapper od prije) i booklyfi_001 (&middot;) — Moon+ tolerise, ali `&#183;` fix je ispravan


