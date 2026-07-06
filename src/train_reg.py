import duckdb, pandas as pd, time, joblib, os, json
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import TargetEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")
CAT = ["airline", "origin", "dest"]
FEATURES = CAT + ["month", "day_of_week", "dep_hour", "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"]

def load(where, n):
    con = duckdb.connect(DB, read_only=True)
    df = con.execute(f"""SELECT f.airline, f.origin, f.dest, f.month, f.day_of_week, f.dep_hour, f.distance, f.crs_elapsed,
        w.prcp, w.snow, w.wspd, w.tavg, f.arr_delay
        FROM flights f LEFT JOIN weather w ON f.origin=w.iata AND f.flight_date=w.date
        WHERE {where} AND f.cancelled=0 AND f.diverted=0 AND f.arr_delay IS NOT NULL AND f.crs_elapsed IS NOT NULL
        USING SAMPLE {n} ROWS""").df()
    con.close()
    for c in ["prcp", "snow"]: df[c] = df[c].fillna(0)
    for c in ["wspd", "tavg"]: df[c] = df[c].fillna(df[c].median())
    df["y"] = df.arr_delay.clip(-30, 240)
    return df

def main():
    tr = load("f.flight_date < '2024-11-01'", 200000); te = load("f.flight_date >= '2024-11-01'", 80000)
    print(f"Train {len(tr):,} | Test {len(te):,}")
    reg = Pipeline([("prep", ColumnTransformer([("cat", TargetEncoder(), CAT)], remainder="passthrough")),
                    ("reg", HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.1, max_iter=300, random_state=0))])
    t = time.time(); reg.fit(tr[FEATURES], tr.y); dt = time.time()-t
    mae = mean_absolute_error(te.y, reg.predict(te[FEATURES]))
    print(f"HGB Regressor : MAE {mae:.1f} min | train {dt:.0f}s")
    joblib.dump(reg, os.path.join(MODELS, "model_reg.joblib"))
    meta = json.load(open(os.path.join(MODELS, "meta.json")))
    meta["reg_features"] = FEATURES
    meta["regression"] = {"modele": "HGB Regressor (minutes)", "MAE_min": round(float(mae), 2), "t_train_s": round(dt, 1)}
    json.dump(meta, open(os.path.join(MODELS, "meta.json"), "w"), indent=2)
    print("model_reg.joblib sauvegarde.")

if __name__ == "__main__":
    main()
