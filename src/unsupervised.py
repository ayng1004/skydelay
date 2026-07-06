import duckdb, os, json
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
MODELS = os.path.join(BASE, "models")
FEATS = ["n_flights", "delay_rate", "avg_delay", "cancel_rate", "avg_distance"]

def profils_aeroports(db=DB):
    con = duckdb.connect(db, read_only=True)
    df = con.execute("""
        SELECT f.origin AS iata, count(*) AS n_flights,
               avg(f.arr_del15) AS delay_rate,
               avg(CASE WHEN f.cancelled=0 THEN f.arr_delay END) AS avg_delay,
               avg(f.cancelled) AS cancel_rate,
               avg(f.distance) AS avg_distance,
               a.name, a.lat, a.lon
        FROM flights f LEFT JOIN airports a ON f.origin = a.iata
        GROUP BY f.origin, a.name, a.lat, a.lon
        HAVING count(*) > 5000
    """).df()
    con.close(); return df

def main(db=DB, k=4):
    os.makedirs(MODELS, exist_ok=True)
    df = profils_aeroports(db)
    X = StandardScaler().fit_transform(df[FEATS])

    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
    df["cluster"] = km.labels_
    print(f"{len(df)} aeroports | silhouette (k={k}) = {silhouette_score(X, km.labels_):.3f}")
    print("\nProfil moyen par cluster :")
    print(df.groupby("cluster")[FEATS].mean().round(2).to_string())

    iso = IsolationForest(contamination=0.05, random_state=0).fit(X)
    df["anomalie"] = (iso.predict(X) == -1).astype(int)
    print("\nAeroports anormaux :", df[df.anomalie == 1].iata.tolist())

    df.to_csv(os.path.join(MODELS, "airport_clusters.csv"), index=False)
    carte = df.dropna(subset=["lat", "lon"]).round(3)
    json.dump(carte.to_dict(orient="records"), open(os.path.join(MODELS, "airport_clusters.json"), "w"), indent=1)
    print("\nSauvegarde -> models/airport_clusters.{csv,json}")
    return df

if __name__ == "__main__":
    main()
