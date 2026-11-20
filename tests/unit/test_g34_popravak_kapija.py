from core.popravak_kapija import prihvatljiv

EN = ("<p>The king rode north with 300 men and Harald.</p>"
      "<p>He did not look back at Aldric.</p><p>Night fell on the road.</p>")
HR = ("<p>Kralj je jahao na sjever s 300 ljudi i Haraldom.</p>"
      "<p>Nije se osvrnuo na Aldrica.</p><p>Noć je pala na put.</p>")


def test_ispravan_popravak_prolazi():
    ok, raz = prihvatljiv(EN, HR, HR)
    assert ok and raz == []


def test_zaglavlje_se_ignorira():
    ok, _ = prihvatljiv(EN, "<!-- chunk_sha: abc -->\n" + HR, HR)
    assert ok


def test_neprevedeno_odbijeno():
    ok, raz = prihvatljiv(EN, HR + "<p>[[NEPREVEDENO: blok 1]]</p>", HR)
    assert not ok and any("NEPREVEDENO" in r for r in raz)


def test_manje_odlomaka_odbijeno():
    ok, raz = prihvatljiv(EN, "<p>Kralj je jahao na sjever s 300 ljudi i Haraldom.</p>", HR)
    assert not ok and any("G3" in r for r in raz)


def test_engleski_tekst_odbijen():
    ok, raz = prihvatljiv(EN, EN, HR)
    assert not ok and any("engleski" in r for r in raz)


def test_prekinut_tekst_odbijen():
    ok, raz = prihvatljiv(EN, HR[:-12] + "</p>".replace("</p>", ""), HR)
    assert not ok


def test_nije_gore_od_starog():
    staro = HR.replace("300", "30")          # staro ima 1 G3 razlog (broj)
    ok, _ = prihvatljiv(EN, staro, staro)    # novo isto: nije gore
    assert ok
    gore = "<p>Kralj je jahao na sjever s 30 ljudi i Haraldom.</p>"   # broj + odlomci
    ok2, _ = prihvatljiv(EN, gore, staro)
    assert not ok2


def test_bez_starog_strogo():
    ok, _ = prihvatljiv(EN, HR.replace("300", "30"), None)
    assert not ok


def test_los_glosar_ne_ruši():
    ok, raz = prihvatljiv(EN, HR, HR, 123)
    assert isinstance(ok, bool) and isinstance(raz, list)


def test_prazno_odbijeno():
    ok, _ = prihvatljiv(EN, "   ", HR)
    assert not ok
