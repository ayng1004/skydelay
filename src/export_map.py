import duckdb, pandas as pd, joblib, json, os

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")
OUT = os.path.join(BASE, "web", "data")
FEATURES = ["airline", "origin", "dest", "route", "orig_hour", "month", "day_of_week", "dep_hour",
            "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"]

def main():
    os.makedirs(OUT, exist_ok=True)
    model = joblib.load(os.path.join(MODELS, "model.joblib"))
    meta = json.load(open(os.path.join(MODELS, "meta.json")))
    con = duckdb.connect(DB, read_only=True)
    routes = con.execute("""
        SELECT o.origin, o.dest, o.n, o.distance, o.crs_elapsed, o.dep_hour, o.airline,
               a1.lat AS olat, a1.lon AS olon, a2.lat AS dlat, a2.lon AS dlon, a1.city AS ocity, a2.city AS dcity,
               wc.prcp, wc.snow, wc.wspd, wc.tavg
        FROM (
            SELECT origin, dest, count(*) AS n, round(avg(distance)) AS distance,
                   round(avg(crs_elapsed)) AS crs_elapsed,
                   cast(median(dep_hour) AS INT) AS dep_hour, mode(airline) AS airline
            FROM flights WHERE cancelled=0 AND diverted=0 AND crs_elapsed IS NOT NULL
            GROUP BY origin, dest HAVING count(*) > 800
        ) o
        JOIN airports a1 ON o.origin=a1.iata
        JOIN airports a2 ON o.dest=a2.iata
        LEFT JOIN weather_clim wc ON o.origin=wc.iata AND wc.month=7
        ORDER BY o.n DESC LIMIT 700
    """).df()

    X = routes[["airline", "origin", "dest", "dep_hour", "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"]].copy()
    X["month"] = 7; X["day_of_week"] = 4
    X["route"] = routes.origin + "_" + routes.dest
    X["orig_hour"] = routes.origin + "_" + routes.dep_hour.astype(str)
    for c in ["prcp", "snow"]: X[c] = X[c].fillna(0)
    for c in ["wspd", "tavg"]: X[c] = X[c].fillna(X[c].median())
    routes["risk"] = model.predict_proba(X[FEATURES])[:, 1].round(3)

    cols = ["origin", "dest", "ocity", "dcity", "olat", "olon", "dlat", "dlon", "distance", "crs_elapsed", "airline", "n", "risk"]
    json.dump(routes[cols].round(3).to_dict(orient="records"), open(os.path.join(OUT, "routes.json"), "w"))
    ap = json.load(open(os.path.join(MODELS, "airport_clusters.json")))
    json.dump(ap, open(os.path.join(OUT, "airports.json"), "w"))
    keep = set(meta["airports"])
    ac = con.execute("SELECT iata, city, lat, lon FROM airports").df()
    cities = {r.iata: r.city for r in ac.itertuples() if r.iata in keep}
    coords = {r.iata: [round(r.lon, 3), round(r.lat, 3)] for r in ac.itertuples() if r.iata in keep}
    json.dump({"airlines": meta["airlines"], "airports": meta["airports"], "cities": cities, "coords": coords},
              open(os.path.join(OUT, "meta.json"), "w"))

    clim = con.execute("SELECT iata, month, prcp, snow, wspd, tavg FROM weather_clim").df()
    cd = {f"{r.iata}_{int(r.month)}": [round(r.prcp, 2), round(r.snow, 2), round(r.wspd, 2), round(r.tavg, 2)] for r in clim.itertuples()}
    json.dump(cd, open(os.path.join(MODELS, "weather_clim.json"), "w"))
    con.close()
    print(f"Export OK -> {len(routes)} routes, {len(ap)} aeroports, {len(cd)} climatologies")

if __name__ == "__main__":
    main()
