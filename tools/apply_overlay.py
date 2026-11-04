import sys, json, re
from pathlib import Path

if len(sys.argv) < 3:
    print("Upotreba: apply_overlay.py <checkpoint_dir> <overlay_json>")
    sys.exit(1)

CK = Path(sys.argv[1])
OVR = Path(sys.argv[2])

if not OVR.exists():
    print(f"Overlay fajl {OVR} ne postoji. Preskacem.")
    sys.exit(0)

try:
    data = json.loads(OVR.read_text("utf-8"))
    ispravke = data.get("ispravke", [])
except Exception as e:
    print(f"Greska pri citanju {OVR}: {e}")
    sys.exit(1)

if not ispravke:
    sys.exit(0)

print(f"Primenjujem {len(ispravke)} ispravki iz overlay-a...")
count = 0
for isp in ispravke:
    fajl = isp.get("fajl")
    staro = isp.get("staro")
    novo = isp.get("novo")
    
    if not fajl or staro is None or novo is None:
        continue
        
    # Nadjemo .chk fajl
    ck_fajl = None
    for p in CK.glob(f"{fajl}_blok_*.chk"):
        if p.name.endswith((".prevod.chk", ".lektura.chk")): continue
        ck_fajl = p
        break
        
    if ck_fajl:
        t0 = ck_fajl.read_text("utf-8")
        if staro in t0:
            t = t0.replace(staro, novo, 1) # Menjamo samo prvo pojavljivanje
            ck_fajl.write_text(t, "utf-8")
            count += 1
            print(f"  OK: {ck_fajl.name} -> {staro[:20]}... u {novo[:20]}...")
        else:
            print(f"  WARN: {ck_fajl.name} ne sadrzi '{staro[:20]}...'")
    else:
        print(f"  WARN: Nema .chk fajla za {fajl}")

print(f"Primenjeno: {count} ispravki.")
