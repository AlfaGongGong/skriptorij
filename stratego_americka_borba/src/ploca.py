# Definicija ploče
class Ploca:
    def __init__(self, velicina):
        self.velicina = velicina
        self.polja = [[None for _ in range(velicina)] for _ in range(velicina)]

    def postavi_figuru(self, figura, x, y):
        self.polja[x][y] = figura

    def __str__(self):
        ploca_str = ""
        for red in self.polja:
            ploca_str += (
                " ".join([str(polje) if polje else "." for polje in red]) + "\n"
            )
        return ploca_str
