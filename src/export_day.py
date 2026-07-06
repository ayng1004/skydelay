import duckdb, pandas as pd, joblib, json, os, sys

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")
OUT = os.path.join(BASE, "web", "data")
FEATURES = ["airline", "origin", "dest", "route", "orig_hour", "month", "day_of_week", "dep_hour",
            "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"]

def model_pred_min(reg, X):
    return reg.predict(X).round().astype(int)

def main(date="2024-07-15", out="day.json"):
    meta = json.load(open(os.path.join(MODELS, "meta.json")))
    model = joblib.load(os.path.join(MODELS, "model.joblib"))
    reg = joblib.load(os.path.join(MODELS, "model_reg.joblib"))
    do_clf = joblib.load(os.path.join(MODELS, "model_dayof.joblib"))
    do_reg = joblib.load(os.path.join(MODELS, "model_dayof_reg.joblib"))
    reg_feat, do_feat, do_reg_feat = meta["reg_features"], meta["dayof_features"], meta["dayof_reg_features"]
    con = duckdb.connect(DB, read_only=True)
    df = con.execute(f"""
        SELECT f.origin, f.dest, f.airline, f.month, f.day_of_week, f.dep_hour, f.distance, f.crs_elapsed,
               f.dep_min, f.arr_del15, f.arr_delay, f.prev_arr_delay, f.dep_congestion, f.turnaround, f.airport_state,
               w.prcp, w.snow, w.wspd, w.tavg,
               a1.lon AS ox, a1.lat AS oy, a2.lon AS dx, a2.lat AS dy
        FROM flights f JOIN airports a1 ON f.origin=a1.iata JOIN airports a2 ON f.dest=a2.iata
             LEFT JOIN weather w ON f.origin=w.iata AND f.flight_date=w.date
        WHERE f.flight_date='{date}' AND f.cancelled=0 AND f.diverted=0
              AND f.crs_elapsed IS NOT NULL AND f.dep_min IS NOT NULL AND f.arr_del15 IS NOT NULL
    """).df()
    con.close()
    df["route"] = df.origin + "_" + df.dest
    df["orig_hour"] = df.origin + "_" + df.dep_hour.astype(str)
    for c in ["prcp", "snow"]: df[c] = df[c].fillna(0)
    for c in ["wspd", "tavg"]: df[c] = df[c].fillna(df[c].median())
    df["risk"] = model.predict_proba(df[FEATURES])[:, 1].round(3)
    df["pdelay"] = model_pred_min(reg, df[reg_feat])
    df["drisk"] = do_clf.predict_proba(df[do_feat])[:, 1].round(3)
    df["dpdelay"] = model_pred_min(do_reg, df[do_reg_feat])
    flights = [{"o": r.origin, "d": r.dest, "al": r.airline,
                "ox": round(r.ox, 2), "oy": round(r.oy, 2), "dx": round(r.dx, 2), "dy": round(r.dy, 2),
                "dep": int(r.dep_min), "dur": int(r.crs_elapsed), "risk": float(r.risk), "pdelay": int(r.pdelay),
                "drisk": float(r.drisk), "dpdelay": int(r.dpdelay), "prev": int(r.prev_arr_delay),
                "real": int(r.arr_del15), "delay": int(r.arr_delay)} for r in df.itertuples()]
    os.makedirs(OUT, exist_ok=True)
    json.dump({"date": date, "flights": flights}, open(os.path.join(OUT, out), "w"))
    print(f"{out} : {len(flights)} vols pour {date} | reel {df.arr_del15.mean():.1%} | booking {df.risk.mean():.1%} | jour {df.drisk.mean():.1%}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "2024-07-15")
