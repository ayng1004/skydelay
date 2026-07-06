import duckdb, pandas as pd, os, warnings
from datetime import datetime
from meteostat import Point, Daily
warnings.filterwarnings("ignore")

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")

def main():
    con = duckdb.connect(DB)
    aps = con.execute("SELECT iata, lat, lon FROM airports WHERE iata IN (SELECT DISTINCT origin FROM flights)").df()
    start, end = datetime(2024, 1, 1), datetime(2024, 12, 31)
    rows = []
    for i, r in aps.iterrows():
        try:
            d = Daily(Point(r.lat, r.lon), start, end).fetch()
        except Exception:
            d = None
        if d is None or d.empty:
            continue
        d = d.reset_index()[["time", "prcp", "snow", "wspd", "tavg"]]
        d["iata"] = r.iata
        rows.append(d)
        if i % 40 == 0:
            print(i, "/", len(aps), "aeroports")
    w = pd.concat(rows, ignore_index=True)
    w["date"] = pd.to_datetime(w["time"]).dt.date
    w = w[["iata", "date", "prcp", "snow", "wspd", "tavg"]]
    for c in ["prcp", "snow"]:
        w[c] = w[c].fillna(0)
    for c in ["wspd", "tavg"]:
        w[c] = w[c].fillna(w[c].median())
    con.execute("DROP TABLE IF EXISTS weather")
    con.execute("CREATE TABLE weather AS SELECT * FROM w")
    con.execute("DROP TABLE IF EXISTS weather_clim")
    con.execute("""CREATE TABLE weather_clim AS
        SELECT iata, month(date) AS month, avg(prcp) prcp, avg(snow) snow, avg(wspd) wspd, avg(tavg) tavg
        FROM weather GROUP BY iata, month(date)""")
    con.close()
    print("weather:", len(w), "lignes,", w.iata.nunique(), "aeroports")

if __name__ == "__main__":
    main()
