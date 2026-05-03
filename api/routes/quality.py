
"""
Ruta za quality scores — DEPRECATED.
Sve quality_scores rute su sada u app.py direktno.
Ovaj blueprint je zadržan radi kompatibilnosti ali ne registruje /api/quality_scores
da ne bi overridao bogatiju implementaciju u app.py.
"""
from flask import Blueprint

bp = Blueprint("quality", __name__)

# /api/quality_scores je registrovan direktno u app.py create_app()
# Ne registruj ovdje da se izbjegne Flask route konflikt.



