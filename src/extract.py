import os, sys, zipfile, urllib.request

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
BTS_URL = "https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{y}_{m}.zip"
INNER = "On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_{y}_{m}.csv"
AIRPORTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"

def telecharge(url, dest):
    print("  ...", url.split('/')[-1])
    urllib.request.urlretrieve(url, dest)

def extrait_mois(y, m):
    out = os.path.join(RAW, f"bts_{y}_{m:02d}.csv")
    if os.path.exists(out):
        print(f"{y}-{m:02d} deja present"); return
    zpath = os.path.join(RAW, f"bts_{y}_{m}.zip")
    telecharge(BTS_URL.format(y=y, m=m), zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extract(INNER.format(y=y, m=m), RAW)
    os.replace(os.path.join(RAW, INNER.format(y=y, m=m)), out)
    os.remove(zpath)
    print(f"  -> bts_{y}_{m:02d}.csv")

if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    annee = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    m1 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    m2 = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    if not os.path.exists(os.path.join(RAW, "airports.dat")):
        telecharge(AIRPORTS_URL, os.path.join(RAW, "airports.dat"))
    for m in range(m1, m2 + 1):
        extrait_mois(annee, m)
    print("Extraction terminee.")
