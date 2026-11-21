"""K2e3: G3 imena ne hvata prevedene titule/epitete; negacije broje n't i s kovrcavim apostrofom."""
from core.strukturna_kapija import _imena, provjeri

EN_T = (
    "<p>He saw the Red Queen and her Silent Sister near the Black Fort, and the Norsemen waited.</p>"
    "<p>Later he spoke to the Emperor and to Grandmother about the Broken Empire.</p>"
)
HR_T = (
    "<p>Vidio je Crvenu kraljicu i njezinu \u0160utljivu sestru kraj Crne tvr\u0111ave, a sjevernjaci su \u010dekali.</p>"
    "<p>Poslije je razgovarao s carem i s bakom o Slomljenom carstvu.</p>"
)


def test_prevedene_titule_nisu_imena():
    assert _imena(EN_T.replace("<p>", " ").replace("</p>", " ")) == set()
    assert not any(r.startswith("imena") for r in provjeri(EN_T, HR_T))


def test_rijec_i_malim_slovom_u_tekstu_je_obicna():
    t = "The tall Gargoyle stared at Wulfric. Every gargoyle waits."
    assert _imena(t) == {"Wulfric"}


def test_pravo_ime_i_dalje_hvata():
    en = "<p>She met Katherine and Gareth near Rhodri.</p><p>Then they left.</p>"
    hr = "<p>Srela je nju i njega kraj onog.</p><p>Zatim su oti\u0161li.</p>"
    assert any(r.startswith("imena") for r in provjeri(en, hr))


EN_N = "<p>I don\u2019t know. He didn\u2019t come. We can\u2019t go. They won\u2019t stay.</p><p>Fine.</p>"


def test_negacije_kovrcavi_apostrof_ok():
    hr = "<p>Ne znam. Nije do\u0161ao. Ne mo\u017eemo i\u0107i. Ne\u0107e ostati.</p><p>Dobro.</p>"
    assert not any(r.startswith("negacije") for r in provjeri(EN_N, hr))


def test_negacije_kovrcavi_apostrof_nestale():
    hr = "<p>Znam. Do\u0161ao je. Mo\u017eemo i\u0107i. Ostat \u0107e.</p><p>Dobro.</p>"
    assert any(r.startswith("negacije") for r in provjeri(EN_N, hr))


def test_negacije_ravni_apostrof_i_dalje_radi():
    en = EN_N.replace("\u2019", "'")
    hr = "<p>Znam. Do\u0161ao je. Mo\u017eemo i\u0107i. Ostat \u0107e.</p><p>Dobro.</p>"
    assert any(r.startswith("negacije") for r in provjeri(en, hr))
