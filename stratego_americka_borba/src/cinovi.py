# Definicija činova
class Cin:
    def __init__(self, ime, funkcija, figura):
        self.ime = ime
        self.funkcija = funkcija
        self.figura = figura

    def __str__(self):
        return f"{self.ime} - {self.funkcija} - {self.figura}"