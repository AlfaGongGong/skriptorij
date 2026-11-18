"""L68: classla se u DinamickiDetektoru ne skida pri svakom startu i ne ponavlja bez mreze."""
import core.kalkovi.dinamicki_detektor as dd


class _FakeClassla:
    def __init__(self, download_pada=False):
        self.download_poziva = 0
        self.pipeline_poziva = 0
        self.download_pada = download_pada

    def download(self, *a, **k):
        self.download_poziva += 1
        if self.download_pada:
            raise OSError("nema mreze")

    def Pipeline(self, *a, **k):
        self.pipeline_poziva += 1
        return object()


def _pripremi(monkeypatch, tmp_path, fake):
    monkeypatch.setattr(dd, "BASE_DIR", tmp_path)
    monkeypatch.setattr(dd, "classla", fake, raising=False)
    monkeypatch.setattr(dd, "CLASSLA_DOSTUPAN", True)
    monkeypatch.setattr(dd, "_nlp", None)
    monkeypatch.setattr(dd, "_nlp_pokusano", False)


def test_modeli_vec_skinuti_nema_downloada(monkeypatch, tmp_path):
    (tmp_path / "data" / "classla_resources" / "hr").mkdir(parents=True)
    fake = _FakeClassla()
    _pripremi(monkeypatch, tmp_path, fake)
    assert dd._get_nlp() is not None
    assert fake.download_poziva == 0
    assert fake.pipeline_poziva == 1
    dd._get_nlp()
    assert fake.pipeline_poziva == 1, "nlp se mora kesirati"


def test_bez_mreze_jedan_pokusaj_pa_none(monkeypatch, tmp_path):
    fake = _FakeClassla(download_pada=True)
    _pripremi(monkeypatch, tmp_path, fake)
    assert dd._get_nlp() is None
    assert dd._get_nlp() is None
    assert dd._get_nlp() is None
    assert fake.download_poziva == 1, "download se ne smije ponavljati pri svakom pozivu"
