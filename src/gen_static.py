import os, json, duckdb
import export_day

BASE = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(BASE, "web", "data")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")

DAYS = [f"2024-{m:02d}-15" for m in range(1, 13)]

def main():
    os.makedirs(os.path.join(OUT, "days"), exist_ok=True)
    for d in DAYS:
        export_day.main(d, out=f"days/{d}.json")
    json.dump(DAYS, open(os.path.join(OUT, "days.json"), "w"))
    export_day.main("2024-07-15", out="day.json")
    con = duckdb.connect(DB, read_only=True)
    coords = {r[0]: [round(r[1], 4), round(r[2], 4)] for r in con.execute("SELECT iata, lat, lon FROM airports").fetchall()}
    con.close()
    json.dump(coords, open(os.path.join(BASE, "models", "coords.json"), "w"))
    print(f"OK : {len(DAYS)} journees + coords ({len(coords)} aeroports)")

if __name__ == "__main__":
    main()
