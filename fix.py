# pokreni jednokratno u Python-u ili Termux-u
from api_fleet import FleetManager
fm = FleetManager()
fm.revive_all("GEMINI")
fm.flush_now()