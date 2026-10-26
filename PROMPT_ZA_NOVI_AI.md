# Booklyfi handoff — 2026-10-26

## Projekat
Python/Flask EPUB prevodilac i stilizator. /root/skriptorij/. Server 127.0.0.1:8080.

## Pravila
- P1 git commit prije svake izmjene
- P2 jedna izmjena po bloku, ast.parse ili compile poslije
- P3 zabranjeni re.sub za kod, sed -i, find/replace
- P4 STARO/NOVO prije primene, korisnik kaze da ili ne
- P5 dijagnostika prije fixa
- P6 greska se ponistava (git checkout), ne popravlja
- P7 backup: tar czf /storage/emulated/0/Download/skriptorij_DATUM.tar.gz .
- P9 ne diraj nista van zahtjeva
- P10 korisnik pokrece i vidi, sintaksa nije dokaz
- P11 integritet podataka prvo
- P16 clear + tee u /tmp/blok_HHMMSS.log

## Struktura
- main.py Flask 127.0.0.1:8080
- run.py batch, _auto_stilizuj na kraju
- app.py 2098 redaka, 33 rute (kandidat za blueprinte)
- api/routes/ blueprinti
- processing/pipeline.py + workers + retro
- epub/styler.py 1924 redaka — glavna stilizacija
- network/http_client.py 1705
- static/js/main.js 3867
- static/css/style.css 3487

## Pipeline
- run.py -> _auto_stilizuj -> run_epub_styler (auto)
- UI mode=standard -> run_epub_styler
- UI mode=booklyfi -> stil_ai.py legacy, NIJE default

## Radi
- Prevod, lektura, stilizacija
- Dropcaps 33 od 79, ostali pocinju emcrticom ili kratkim p
- Vijenac, TOC, naslovna, impresum
- Orphan navodnici -> emcrtica
- Atomic write (kljucevi, quality_scores)
- 146 except-pass -> logger
- _ukloni_duplikate_p 80c prefix

## Ne radi
- Dijalog u lekturi spojen u jedan p (_razdvoji_dijalog_p uklonjen, stetio naraciji)
- Batch D-J (frontend, mobilni, UX, pristupacnost, refaktor)

## Kriticne funkcije u epub/styler.py
1. _ukloni_sve — unwrap section i div.galley-rw, brise booklyfi klase
2. _normalizuj — div u p, h4-h6 u h3
3. _dijalog — orphan navodnici 1-6
4. _dodaj_naslov — split TOC naslov od prve recenice
5. _dodaj_dropcap — prvi p posle h1, PNG 4em display block, skriveno slovo font-size 1px
6. _ukloni_duplikate_p — brise ponovljene p po 80c prefix

## Na sta paziti
1. main.py: _host prije try bloka, inace NameError pri startu
2. from __future__ poslije svih importa, ast.parse to ne hvata, samo compile i import
3. _ukloni_duplikate_p prije _dodaj_dropcap
4. _razdvoji_dijalog_p nikad vracati
5. Dva run_epub_styler 641 i 1328, Python koristi zadnju
6. keys.py koristi atomic_write_json, ne open w plus json.dump

## Test
- python3 tools/test_dropcap_naracija.py
- python3 tools/provjeri_dijalog.py
- python3 tools/finalna_provjera.py

## Regeneracija
from api_fleet import get_active_fleet
from epub.styler import run_epub_styler
run_epub_styler(epub_path=PREVEDENO, fleet=get_active_fleet(), output_path=STYLED, log_callback=print, options={})

## Sljedeci batch-evi
D frontend, E mobilni, F UX, G pristupacnost, J odrzavanje, H app.py blueprints, I duplirana stilizacija

## Korisnik
Bosanski. Direktno, bez uljepsavanja. Voli brojeve ne pretpostavke. Prethodni AI imao 13 gresaka: awk bug, shell quoting, izmisljena imena, ast.parse umjesto compile. NIKAD ne pretpostavljaj. Otvori fajl, nadji funkciju, pokazi STARO NOVO, sacekaj da.
