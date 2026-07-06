import duckdb, pandas as pd, numpy as np, time, joblib, os, json
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, TargetEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import roc_auc_score, average_precision_score, f1_score, confusion_matrix

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")

CAT = ["airline", "origin", "dest", "route", "orig_hour"]
CAT_OH = ["airline", "origin", "dest"]
NUM = ["month", "day_of_week", "dep_hour", "distance", "crs_elapsed", "prcp", "snow", "wspd", "tavg"]
FEATURES = CAT + NUM
TARGET = "arr_del15"

def charge(db=DB):
    con = duckdb.connect(db, read_only=True)
    df = con.execute("""SELECT f.airline, f.origin, f.dest, f.month, f.day_of_week, f.dep_hour, f.distance, f.crs_elapsed,
        w.prcp, w.snow, w.wspd, w.tavg, f.arr_del15, f.arr_delay, f.flight_date
        FROM flights f LEFT JOIN weather w ON f.origin=w.iata AND f.flight_date=w.date
        WHERE f.cancelled=0 AND f.diverted=0 AND f.arr_del15 IS NOT NULL AND f.arr_delay IS NOT NULL AND f.crs_elapsed IS NOT NULL""").df()
    con.close()
    df["route"] = df.origin + "_" + df.dest
    df["orig_hour"] = df.origin + "_" + df.dep_hour.astype(str)
    for c in ["prcp", "snow"]: df[c] = df[c].fillna(0)
    for c in ["wspd", "tavg"]: df[c] = df[c].fillna(df[c].median())
    return df

def evalue(nom, y, proba, seuil=0.5, t=None):
    pred = (proba >= seuil).astype(int)
    r = {"modele": nom, "AUC": round(roc_auc_score(y, proba), 4), "PR_AUC": round(average_precision_score(y, proba), 4),
         "F1": round(f1_score(y, pred), 4), "accuracy": round(float((pred == y).mean()), 4)}
    if t is not None: r["t_train_s"] = round(t, 1)
    return r

def main(db=DB):
    os.makedirs(MODELS, exist_ok=True)
    df = charge(db)
    airlines = sorted(df.airline.unique().tolist()); airports = sorted(set(df.origin.unique()) | set(df.dest.unique()))
    train = df[df.flight_date < "2024-11-01"]; test = df[df.flight_date >= "2024-11-01"]
    Xtr, ytr = train[FEATURES].copy(), train[TARGET].copy(); Xte, yte = test[FEATURES].copy(), test[TARGET].copy()
    del df, train, test
    thr = float(ytr.mean())
    print(f"Train {len(Xtr):,} | Test {len(Xte):,} | taux retard train={thr:.3f} (= seuil de decision)")
    res = []

    dum = DummyClassifier(strategy="most_frequent").fit(Xtr, ytr)
    res.append(evalue("Dummy (majoritaire)", yte, dum.predict_proba(Xte)[:, 1], seuil=thr))

    lr = Pipeline([("prep", ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CAT_OH)], remainder="drop")),
                   ("clf", LogisticRegression(max_iter=300))])
    t = time.time(); lr.fit(Xtr[CAT_OH], ytr); res.append(evalue("Regression logistique", yte, lr.predict_proba(Xte[CAT_OH])[:, 1], seuil=thr, t=time.time()-t))
    del lr

    hgb = Pipeline([("prep", ColumnTransformer([("cat", TargetEncoder(), CAT)], remainder="passthrough")),
                    ("clf", HistGradientBoostingClassifier(learning_rate=0.1, max_iter=300, random_state=0))])
    t = time.time(); hgb.fit(Xtr, ytr); t_hgb = time.time()-t
    proba = hgb.predict_proba(Xte)[:, 1]
    res.append(evalue("HistGradientBoosting", yte, proba, seuil=thr, t=t_hgb))

    tab = pd.DataFrame(res)
    print("\n=== Comparaison (test = nov-dec 2024, seuil = taux de base) ===")
    print(tab.to_string(index=False))
    print(f"\nCalibration HGB : proba predite moyenne {proba.mean():.3f} vs retard reel {yte.mean():.3f}")
    print("Matrice de confusion HGB :\n", confusion_matrix(yte, (proba >= thr).astype(int)))

    joblib.dump(hgb, os.path.join(MODELS, "model.joblib"))
    meta = {"features": FEATURES, "cat": CAT, "num": NUM, "airlines": airlines, "airports": airports,
            "base_rate": round(float(ytr.mean()), 4), "resultats": res}
    json.dump(meta, open(os.path.join(MODELS, "meta.json"), "w"), indent=2)
    tab.to_csv(os.path.join(MODELS, "resultats.csv"), index=False)
    print("\nClassifieur + meta sauvegardes. Lancez src/train_reg.py pour la regression.")
    return tab

if __name__ == "__main__":
    main()
