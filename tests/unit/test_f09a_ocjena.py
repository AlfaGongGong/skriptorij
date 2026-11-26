import asyncio

import core.quality as Q

PROZA = (
    "Ana je tiho prošla kroz sobu i sjela uz prozor. Vani je padala kiša, a ulica je bila prazna. "
    "Sjetila se razgovora od jučer i nije znala što bi mu odgovorila. Na stolu je stajala hladna kava. "
    "Netko je dolje zalupio vratima, pa se trgnula iz misli. Ustala je, uzela šal i izašla na stubište. "
    "Zrak je mirisao na vlažno drvo i stari kamen. Pred zgradom je čekao stari prijatelj s kišobranom. "
    "Nasmijao se kad ju je ugledao i rekao da je kasnila. Krenuli su zajedno prema trgu, ne govoreći mnogo. "
    "U kafiću na uglu bilo je toplo i bučno, pa su sjeli u najdalji kut. Naručili su čaj i kolače."
)


def _pokreni(fn, **kw):
    meta = {}
    s = asyncio.run(Q._scoruj_kvalitetu(PROZA, fn, 0, "f.html", tip_ocjenjivanja="prevod", meta_out=meta, **kw))
    return s, meta


def test_paratekst_samo_kratko_ili_na_pocetku():
    assert Q._je_nonprose_blok("<p>Copyright 2020. All rights reserved.</p>") is True
    dugo = PROZA + " Na kraju je spomenula index u knjizi i kazalo."
    assert Q._je_nonprose_blok("<p>" + dugo + "</p>") is False


def test_zarez_u_ocjeni():
    async def fn(prompt, idx, uloga=None, filename=None):
        return '{"ocjena": "9,2"}', "GROQ"
    _, meta = _pokreni(fn)
    assert meta.get("ai") == 9.2, meta


def test_bez_ai_najvise_osam():
    async def fn(prompt, idx, uloga=None, filename=None):
        return None, "GROQ"
    s, meta = _pokreni(fn)
    assert s <= 8.0, s
    assert meta.get("status") == "heur_only"


def test_izvornik_ide_u_prompt_a_bez_njega_nema_tacnosti():
    uhv = {}
    async def fn(prompt, idx, uloga=None, filename=None):
        uhv["p"] = prompt
        return '{"ocjena": 9.0}', "GROQ"
    _pokreni(fn, izvornik="<p>She walked across the room.</p>")
    assert "IZVORNIK (EN" in uhv["p"] and "ISJECAK" in uhv["p"]
    _pokreni(fn)
    assert "IZVORNIK NIJE DOSTUPAN" in uhv["p"]


def test_tri_isjecka():
    dugo = "a" * 3000
    r = Q._isjecak(dugo)
    assert r.count("[...]") == 2 and len(r) < 1300
    assert Q._isjecak("kratko") == "kratko"
