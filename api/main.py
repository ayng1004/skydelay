import os, json, joblib, pandas as pd, urllib.request, urllib.parse, datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

BASE = os.path.join(os.path.dirname(__file__), "..")
COORDS = json.load(open(os.path.join(BASE, "models", "coords.json")))
_wcache = {}

def fetch_weather(lat, lon, date):
    key = (round(lat, 1), round(lon, 1), date)
    if key in _wcache: return _wcache[key]
    try:
        d = datetime.date.fromisoformat(date)
        archive = d < datetime.date.today() - datetime.timedelta(days=5)
        base = "https://archive-api.open-meteo.com/v1/archive" if archive else "https://api.open-meteo.com/v1/forecast"
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": date, "end_date": date,
            "daily": "precipitation_sum,snowfall_sum,windspeed_10m_max,temperature_2m_mean", "timezone": "auto"})
        with urllib.request.urlopen(f"{base}?{q}", timeout=6) as r:
            dd = json.load(r)["daily"]
        w = [dd["precipitation_sum"][0] or 0, (dd["snowfall_sum"][0] or 0) * 10,
             dd["windspeed_10m_max"][0] or 15, dd["temperature_2m_mean"][0] or 15]
        _wcache[key] = w
        return w
    except Exception:
        return None
model = joblib.load(os.path.join(BASE, "models", "model.joblib"))
reg = joblib.load(os.path.join(BASE, "models", "model_reg.joblib"))
do_clf = joblib.load(os.path.join(BASE, "models", "model_dayof.joblib"))
do_reg = joblib.load(os.path.join(BASE, "models", "model_dayof_reg.joblib"))
meta = json.load(open(os.path.join(BASE, "models", "meta.json")))
clim = json.load(open(os.path.join(BASE, "models", "weather_clim.json")))
routes = json.load(open(os.path.join(BASE, "web", "data", "routes.json")))
route_idx = {(r["origin"], r["dest"]): r for r in routes}
_v = list(clim.values())
CLIM_DEF = [round(sum(x[i] for x in _v) / len(_v), 2) for i in range(4)] if _v else [0, 0, 15, 15]

app = FastAPI(title="Flight Delay API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Vol(BaseModel):
    airline: str
    origin: str
    dest: str
    month: int = 7
    day_of_week: int = 4
    dep_hour: int = 8
    distance: int | None = None
    crs_elapsed: int | None = None
    prev_arr_delay: int | None = None
    date: str | None = None

@app.get("/health")
def health():
    return {"status": "ok", "routes": len(routes)}

@app.get("/meta")
def get_meta():
    return {"airlines": meta["airlines"], "airports": meta["airports"]}

@app.get("/routes")
def get_routes():
    return routes

@app.post("/predict")
def predict(v: Vol):
    r = route_idx.get((v.origin, v.dest))
    d = v.distance if v.distance is not None else (r["distance"] if r else 800)
    e = v.crs_elapsed if v.crs_elapsed is not None else (r["crs_elapsed"] if r else 120)
    meteo_source = "typique"
    w = None
    if v.date and v.origin in COORDS:
        lat, lon = COORDS[v.origin]
        w = fetch_weather(lat, lon, v.date)
        if w: meteo_source = "réelle"
    if not w: w = clim.get(f"{v.origin}_{v.month}", CLIM_DEF)
    row = {"airline": v.airline, "origin": v.origin, "dest": v.dest,
           "route": f"{v.origin}_{v.dest}", "orig_hour": f"{v.origin}_{v.dep_hour}",
           "month": v.month, "day_of_week": v.day_of_week, "dep_hour": v.dep_hour,
           "distance": d, "crs_elapsed": e, "prcp": w[0], "snow": w[1], "wspd": w[2], "tavg": w[3],
           "dep_congestion": 20, "turnaround": 50, "airport_state": 0.2}
    X = pd.DataFrame([row])
    facteurs = []
    if w[1] > 1: facteurs.append(("Neige au départ", "fort"))
    elif w[0] > 8: facteurs.append(("Pluie au départ", "moyen"))
    if w[2] > 30: facteurs.append(("Vent fort", "moyen"))
    if v.dep_hour >= 17: facteurs.append(("Départ en soirée", "moyen"))
    elif v.dep_hour <= 8: facteurs.append(("Départ tôt le matin", "faible"))
    if v.prev_arr_delay is not None:
        X["prev_arr_delay"] = v.prev_arr_delay
        p = float(do_clf.predict_proba(X[meta["dayof_features"]])[:, 1][0])
        mins = int(round(float(do_reg.predict(X[meta["dayof_reg_features"]])[0])))
        mode = "jour du vol"
        if v.prev_arr_delay >= 30: facteurs.insert(0, (f"Avion précédent en retard de {v.prev_arr_delay} min", "fort"))
        elif v.prev_arr_delay >= 15: facteurs.insert(0, (f"Avion précédent un peu en retard", "moyen"))
        else: facteurs.insert(0, ("Avion précédent à l'heure", "faible"))
    else:
        p = float(model.predict_proba(X[meta["features"]])[:, 1][0])
        mins = int(round(float(reg.predict(X[meta["reg_features"]])[0])))
        mode = "réservation"
    if not facteurs: facteurs.append(("Conditions favorables", "faible"))
    meteo = {"prcp": round(w[0], 1), "snow": round(w[1], 1), "wspd": round(w[2], 1), "tavg": round(w[3], 1)}
    return {"proba_retard": round(p, 3), "retard_minutes": mins, "mode": mode, "distance": d, "crs_elapsed": e,
            "meteo": meteo, "meteo_source": meteo_source, "facteurs": facteurs}
