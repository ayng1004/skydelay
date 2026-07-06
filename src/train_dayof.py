import duckdb, pandas as pd, time, joblib, os, json, gc
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import TargetEncoder
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score, mean_absolute_error

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")
CAT = ["airline", "origin", "dest", "route", "orig_hour"]
EXTRA = ["prev_arr_delay", "dep_congestion", "turnaround", "airport_state"]
NUM = ["month", "day_of_week", "dep_hour", "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"] + EXTRA
FEATURES = CAT + NUM
REG_CAT = ["airline", "origin", "dest"]
REG_FEATURES = REG_CAT + ["month", "day_of_week", "dep_hour", "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"] + EXTRA

def load(where, n=None):
    con = duckdb.connect(DB, read_only=True)
    samp = f"USING SAMPLE {n} ROWS" if n else ""
    df = con.execute(f"""SELECT f.airline, f.origin, f.dest, f.month, f.day_of_week, f.dep_hour, f.distance, f.crs_elapsed,
        f.prev_arr_delay, f.dep_congestion, f.turnaround, f.airport_state, w.prcp, w.snow, w.wspd, w.tavg, f.arr_del15, f.arr_delay
        FROM flights f LEFT JOIN weather w ON f.origin=w.iata AND f.flight_date=w.date
        WHERE {where} AND f.cancelled=0 AND f.diverted=0 AND f.arr_del15 IS NOT NULL AND f.crs_elapsed IS NOT NULL {samp}""").df()
    con.close()
    df["route"] = df.origin + "_" + df.dest
    df["orig_hour"] = df.origin + "_" + df.dep_hour.astype(str)
    for c in ["prcp", "snow"]: df[c] = df[c].fillna(0)
    for c in ["wspd", "tavg"]: df[c] = df[c].fillna(df[c].median())
    return df

def main():
    os.makedirs(MODELS, exist_ok=True)
    tr = load("f.flight_date < '2024-11-01'"); te = load("f.flight_date >= '2024-11-01'")
    thr = float(tr.arr_del15.mean())
    print(f"Train {len(tr):,} | Test {len(te):,}")
    clf = Pipeline([("prep", ColumnTransformer([("cat", TargetEncoder(), CAT)], remainder="passthrough")),
                    ("clf", HistGradientBoostingClassifier(learning_rate=0.1, max_iter=300, random_state=0))])
    t = time.time(); clf.fit(tr[FEATURES], tr.arr_del15); dt = time.time()-t
    proba = clf.predict_proba(te[FEATURES])[:, 1]
    auc = roc_auc_score(te.arr_del15, proba)
    res = {"modele": "Jour du vol (avec propagation)", "AUC": round(float(auc), 4),
           "PR_AUC": round(float(average_precision_score(te.arr_del15, proba)), 4),
           "F1": round(float(f1_score(te.arr_del15, (proba >= thr).astype(int))), 4), "t_train_s": round(dt, 1)}
    print("Classifieur jour du vol :", res)
    print(f"Calibration : predit {proba.mean():.3f} vs reel {te.arr_del15.mean():.3f}")
    joblib.dump(clf, os.path.join(MODELS, "model_dayof.joblib"))
    del tr, te, clf, proba; gc.collect()

    trs = load("f.flight_date < '2024-11-01'", 400000); tes = load("f.flight_date >= '2024-11-01'", 150000)
    reg = Pipeline([("prep", ColumnTransformer([("cat", TargetEncoder(), REG_CAT)], remainder="passthrough")),
                    ("reg", HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.1, max_iter=300, random_state=0))])
    ytr = trs.arr_delay.clip(-30, 240)
    t = time.time(); reg.fit(trs[REG_FEATURES], ytr); dtr = time.time()-t
    mae = mean_absolute_error(tes.arr_delay.clip(-30, 240), reg.predict(tes[REG_FEATURES]))
    print(f"Regresseur jour du vol : MAE {mae:.1f} min | train {dtr:.0f}s")
    joblib.dump(reg, os.path.join(MODELS, "model_dayof_reg.joblib"))

    meta = json.load(open(os.path.join(MODELS, "meta.json")))
    meta["dayof_features"] = FEATURES
    meta["dayof_reg_features"] = REG_FEATURES
    meta["dayof"] = res
    meta["dayof_regression"] = {"MAE_min": round(float(mae), 2)}
    json.dump(meta, open(os.path.join(MODELS, "meta.json"), "w"), indent=2)
    print("Modeles jour du vol sauvegardes.")

if __name__ == "__main__":
    main()
