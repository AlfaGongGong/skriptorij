# Definicija igr3


from src.ploca import Ploca


class Igra:
    def __init__(self):
        self.ploca = Ploca(10)
        self.cinovi = []

    def dodaj_cin(self, cin):
        self.cinovi.append(cin)

    def __str__(self):
        return str(self.ploca)
