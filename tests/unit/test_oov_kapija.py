from core.oov_kapija import provjeri

EN_TXT = ("<p>The shutters gave without warning. They flew back and I found that I was standing "
          "high above the execution yard, drenched in moonlight. I spun around and found nothing. "
          "He said that they would not be there when you came back from the river, but it was "
          "what it was and we had been told.</p>") * 2
HR_TXT = ("<p>Ivan je jučer otišao u grad i kupio kruh, mlijeko i sir za večeru. Kad se vratio kući, "
          "žena ga je čekala pred vratima i pitala gdje je bio toliko dugo. Rekao joj je da je sreo "
          "starog prijatelja koji mu je ispričao dugu priču o svom životu i svojoj djeci. Zatim su "
          "zajedno sjeli za stol i mirno večerali dok je vani padala kiša.</p>")


def test_engleski_odbijen():
    assert provjeri(EN_TXT)["odbij"]


def test_hrvatski_prolazi():
    assert not provjeri(HR_TXT)["odbij"]


def test_sha_komentar_se_ignorira():
    assert not provjeri("<!-- chunk_sha:v2:GEMINI::aadc72cb10c9e108 -->" + HR_TXT)["odbij"]


def test_neprevedeno_marker_prolazi():
    assert not provjeri("NEPREVEDENO " + EN_TXT)["odbij"]
