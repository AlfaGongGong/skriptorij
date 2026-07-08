from .igra import Igra
from .igrači import Igrač
from .pravila_igre import PravilaIgre

# Kreiraj igru
igra = Igra()

# Dodaj igrače
igra.dodaj_igrača(Igrač('John', 'Amerikanci'))
igra.dodaj_igrača(Igrač('Jane', 'Englezi'))

# Prikaži pravila igre
print(igra.prikaži_pravila())