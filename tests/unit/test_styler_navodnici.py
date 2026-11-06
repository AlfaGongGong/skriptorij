from bs4 import BeautifulSoup

from epub.styler import _navodnici_popravi


def _t(html):
    s = BeautifulSoup(html, "html.parser")
    n = _navodnici_popravi(s)
    return n, s.get_text()


def test_a_izgubljen_zatvarajuci_prije_glagola():
    n, t = _t("<p>\u201eOv\u010detina, izustila je hvatajući zrak.</p>")
    assert n == 1
    assert t == "\u201eOv\u010detina\u201d, izustila je hvatajući zrak."


def test_a_drugi_navod_ostaje():
    n, t = _t("<p>\u201eDa, uzdahnuo je Klover, \u201ea pobjednik dobiva nagradu. Rani grob.\u201d</p>")
    assert n == 1
    assert t.startswith("\u201eDa\u201d, uzdahnuo je Klover, \u201ea pobjednik")


def test_a_cuva_em():
    s = BeautifulSoup("<p>\u201eProkleto <em>besmisleno</em>, prozbori Leo kroz zube.</p>", "html.parser")
    assert _navodnici_popravi(s) == 1
    assert s.find("em") is not None
    assert s.get_text() == "\u201eProkleto besmisleno\u201d, prozbori Leo kroz zube."


def test_b_crtica_umjesto_otvarajuceg():
    n, t = _t("<p>\u201eSamo radiš! Ali svejedno.\u201d Stand se nasmijao smijehom. \u2014 Više ovčetine za mene!\u201d Zatim je ošinuo uzde.</p>")
    assert n == 1
    assert "smijehom. \u201eVi\u0161e ov\u010detine za mene!\u201d Zatim" in t.replace("Više", "Vi\u0161e").replace("ovčetine", "ov\u010detine")


def test_b_ne_dira_pasus_koji_pocinje_crticom():
    n, t = _t("<p>\u2014 \u010cujem vas.\u201d</p>")
    assert n == 0
    assert t == "\u2014 \u010cujem vas.\u201d"


def test_c_razmak_crtica_navodnik():
    n, t = _t("<p>\u201eStao sam na stranu pobjednika \u2014 \u201d</p>")
    assert n == 1
    assert t.endswith("pobjednika \u2014\u201d")


def test_uravnotezen_ostaje():
    n, t = _t("<p>\u201eDobro\u201d, reče on.</p>")
    assert n == 0
    assert t == "\u201eDobro\u201d, reče on."


def test_idempotentno():
    s = BeautifulSoup("<p>\u201eOv\u010detina, izustila je.</p>", "html.parser")
    _navodnici_popravi(s)
    assert _navodnici_popravi(s) == 0


def test_c_balansirani_pasus_razmak_crtica_navodnik():
    n, t = _t("<p>\u201eReci mi\u201d, rekla je. \u201eNe mogu otići bez nje, ja \u2014 \u201d</p>")
    assert n >= 1
    assert "\u2014 \u201d" not in t
    assert t.endswith("ja \u2014\u201d")


def test_a_prosireni_glagoli():
    n, t = _t("<p>\u201ePodno\u0161ljivo\u2026, uspio je procikati.</p>")
    assert n == 1
    assert t == "\u201ePodno\u0161ljivo\u2026\u201d, uspio je procikati."


def test_a_prilog_prije_glagola():
    n, t = _t("<p>\u201eO ovome \u0107emo poslije, o\u0161tro odvrati Leo.</p>")
    assert n == 1
    assert t == "\u201eO ovome \u0107emo poslije\u201d, o\u0161tro odvrati Leo."


def test_d_rijec_u_navodnicima():
    n, t = _t("<p>Savine nije podnosila rije\u010d \u201edopu\u0161tenje. Vrije\u0111alo ju je. \u201eOn se ne\u0107e protiviti.\u201d</p>")
    assert n == 1
    assert "rije\u010d \u201edopu\u0161tenje\u201d." in t


def test_f_i_b_zavrsni_otvarajuci():
    n, t = _t("<p>Savine je zurila u njih. \u2014 Iskoristili ste me kao mamac. Mene i moju djecu \u2014 \u201e</p>")
    assert t == "Savine je zurila u njih. \u201eIskoristili ste me kao mamac. Mene i moju djecu \u2014\u201d"


def test_b_vise_crtica_umjesto_otvarajuceg():
    n, t = _t("<p>\u201eAli!\u201d rekao je. To nije rekao njoj. \u2014 Sada imamo priliku! Za novu Uniju.\u201d Netko je stajao. \u2014 Priliku\u2026 da stvari u\u010dinimo.\u201d</p>")
    assert n == 2
    assert "\u2014" not in t


def test_dup_par_brise_ponovljeni_par():
    from epub.styler import _ukloni_dup_par
    s = BeautifulSoup(
        "<div><p>\u2014 Rekla sam da nas se ne smije uznemiravati!</p>"
        "<p>\u2014 Ali rojalisti se pribli\u017eavaju Agriontu! \u2014 zacvilio je, skvr\u010div\u0161i se.</p>"
        "<p>\u2014 Pribli\u017eavaju se tko? \u2014 upita ona.</p>"
        "<p>\u201eMolim sud za strpljenje.\u201d</p>"
        "<p>\u201eAli rojalisti se pribli\u017eavaju Agriontu!\u201d zacvilio je, skvr\u010div\u0161i se.</p>"
        "<p>\u201ePribli\u017eavaju se tko?\u201d</p></div>", "html.parser")
    assert _ukloni_dup_par(s) == 2
    assert len(s.find_all("p")) == 4


def test_dup_par_ne_dira_kratke():
    from epub.styler import _ukloni_dup_par
    s = BeautifulSoup("<div><p>\u2014 Ne.</p><p>\u2014 Da.</p><p>\u2014 Ne.</p><p>\u2014 Da.</p></div>", "html.parser")
    assert _ukloni_dup_par(s) == 0


def test_g_dodaje_zatvarajuci_na_kraj():
    s = BeautifulSoup("<div><p>Rekao je. „Dat ću vam vremena, ali želim odgovor.</p><p>Krupan muškarac progovori: „Mladi Lave.”</p></div>", "html.parser")
    n = _navodnici_popravi(s)
    assert n == 1
    assert s.find("p").get_text().endswith("odgovor.”")


def test_g_ne_dira_navod_kroz_pasuse():
    s = BeautifulSoup("<div><p>„Koji su im sve uništili. Trebamo vojsku.</p><p>Moramo dobiti konce.”</p></div>", "html.parser")
    assert _navodnici_popravi(s) == 0
    assert s.find("p").get_text() == "„Koji su im sve uništili. Trebamo vojsku."


def test_i_nedostaje_otvarajuci_poslije_glagola():
    n, t = _t("<p>„Prokleto besmisleno”, prozbori Leo. Kad je želio biti poput njega. — Eto ti ga na”, promrmlja, moraš sam sebi biti heroj.”</p>")
    assert n == 2
    assert t == "„Prokleto besmisleno”, prozbori Leo. Kad je želio biti poput njega. „Eto ti ga na”, promrmlja, „moraš sam sebi biti heroj.”"


def test_crtica_navodnik_kraj():
    from epub.styler import _crtica_navodnik_kraj
    s = BeautifulSoup("<p>„Mislim, ja — ”</p>", "html.parser")
    assert _crtica_navodnik_kraj(s) == 1
    assert s.get_text() == "„Mislim, ja —”"
    assert _crtica_navodnik_kraj(s) == 0
