# SkyDelay, prédiction des retards de vols aériens

Projet Data Science M1. Chaîne complète depuis la collecte de données massives jusqu'à une interface de démonstration, autour d'une question simple : ce vol va-t-il arriver en retard, et de combien ?

## Le problème

Aux États-Unis, environ un vol sur cinq arrive avec plus de 15 minutes de retard. On cherche à estimer ce risque au moment de la réservation, en n'utilisant que des informations connues avant le décollage : compagnie, aéroports de départ et d'arrivée, date, heure, et météo prévue au départ. Le retard est un phénomène en partie aléatoire, ce qui en fait un vrai problème d'apprentissage, contrairement à une quantité calculable par formule.

## Les données

- **Vols** : US Bureau of Transportation Statistics, jeu On-Time Performance, tous les vols intérieurs de 2024, un fichier par mois. Environ **7 millions de vols**, 110 colonnes brutes, plusieurs Go. Source : https://www.transtats.bts.gov/
- **Aéroports** : coordonnées géographiques depuis OpenFlights, pour la carte. Source : https://openflights.org/data.html
- **Météo** : relevés quotidiens par aéroport (pluie, neige, vent, température) via Meteostat pour l'entraînement, et prévisions Open-Meteo pour les prédictions à venir. Sources : https://meteostat.net/ et https://open-meteo.com/

## Architecture

```
data/raw          fichiers bruts téléchargés (ignorés par git)
data/processed    base DuckDB (flights.duckdb, ignorée par git)
src/              pipeline : extract, transform, weather, train, train_reg,
                  train_dayof, unsupervised, export_map, export_day, gen_static
models/           modèles entraînés et métadonnées
api/              API FastAPI qui sert les modèles
web/              interface carte (deck.gl et MapLibre) et onglet projet
notebooks/        3 notebooks de recherche (exploration, EDA, modélisation)
```

## Stockage : pourquoi SQL (DuckDB)

Les données sont très structurées, avec un schéma fixe, et l'usage principal est analytique : agrégations sur des millions de lignes (retard moyen par aéroport, par heure, par compagnie). Une base **SQL colonnaire** est le bon choix. DuckDB charge les 7 millions de vols en une douzaine de secondes, sans serveur à installer, et exécute les agrégations très rapidement. Une base NoSQL n'apporterait rien ici : pas de documents imbriqués, pas de schéma variable. Des index sont créés sur les aéroports pour accélérer les requêtes de la carte.

## Pipeline ETL

1. **Extraction** : téléchargement des fichiers mensuels BTS, des aéroports et de la météo.
2. **Transformation** : sélection des colonnes utiles, typage, création de variables (heure de départ, route, retard de l'avion précédent, congestion, état du réseau) et jointure météo, le tout en SQL dans DuckDB. On retire les vols annulés ou déroutés.
3. **Chargement** : écriture dans les tables `flights`, `airports`, `weather` de la base.

Un point important a orienté tout le projet : éviter la **fuite de données**. Le retard au départ est corrélé à 0,97 avec le retard à l'arrivée, mais on ne le connaît pas au moment de réserver. On a donc gardé uniquement les variables disponibles avant le vol.

## Analyse exploratoire

Les trois notebooks documentent la démarche pas à pas :
- `01_exploration_donnees` : découverte du jeu brut, choix de la cible, mise en évidence de la fuite de données.
- `02_eda_visualisations` : distribution des retards, effet de l'heure (de 9 % le matin à 30 % en soirée), du jour, du mois, de la compagnie, corrélations.
- `03_modelisation` : comparaison des modèles, courbe ROC, importance des variables, clustering.

## Modélisation

Classification supervisée du retard de 15 minutes ou plus, comparée sur un découpage temporel (entraînement janvier à octobre, test novembre-décembre, pour ne jamais prédire le passé avec le futur).

Les scores AUC obtenus : 0,50 pour la référence qui prédit toujours à l'heure, 0,56 pour la régression logistique, 0,65 pour le gradient boosting avec météo, et 0,80 pour le gradient boosting du jour du vol.

On évalue en AUC car l'accuracy est trompeuse quand 80 % des vols sont à l'heure. On distingue deux scénarios. À la réservation, on ne connaît que le trajet et l'horaire, le modèle atteint 0,65. Le jour du vol, on ajoute trois variables calculées sur nos propres données et connues avant le départ : le retard de l'avion précédent (effet domino, via le numéro d'appareil), la congestion et le temps d'escale, et l'état du réseau (taux de retard au départ de l'aéroport dans les deux heures précédentes). L'AUC monte à 0,80 et l'erreur en minutes descend de 20,0 à 16,0. C'est le principe des services du marché comme Google Flights ou FlightAware.

Une régression prédit aussi le nombre de minutes de retard, sur la médiane (le retard typique) plutôt que la moyenne gonflée par les cas extrêmes, ce qui donne une prévision lisible.

En non supervisé, un clustering KMeans regroupe les aéroports par profil (volume, taux de retard, distance) et une détection d'anomalies (IsolationForest) repère les aéroports atypiques. Ces groupes colorent les points de la carte.

Les variables catégorielles à forte cardinalité (route, aéroport par heure) sont encodées par la cible (TargetEncoder), ce qui évite l'explosion du nombre de colonnes.

## Limite assumée

Même le meilleur modèle, à 0,80, ne devine pas tout. Sans la météo minute par minute ni l'état réel du trafic le jour même, une partie du retard reste imprévisible, et c'est vrai pour tout le monde, Google compris. Le modèle capte la part structurelle du retard, pas les aléas comme une panne ou un arrêt au sol. Un modèle bien calibré donne d'ailleurs un risque modéré à la plupart des vols, dont la majorité arrivent effectivement à l'heure : la calibration est vérifiée dans le notebook et sur la carte.

## Interface

Une application web (deck.gl et MapLibre) avec deux vues. La carte rejoue une vraie journée de 2024 : chaque avion vole à son horaire réel, coloré par son retard, avec trois affichages comparables (prédiction à la réservation, prédiction du jour du vol, retard réel observé). On peut mettre en pause, changer de journée, cliquer un avion, et prédire un vol de son choix qui s'affiche alors sur la carte avec ses facteurs. Un onglet raconte la démarche. L'API FastAPI charge les modèles et va chercher la vraie météo prévue du jour choisi.

## Lancer le projet

```bash
pip install -r requirements.txt

python src/extract.py 2024 1 12
python src/transform.py
python src/weather.py

python src/train.py
python src/train_reg.py
python src/train_dayof.py
python src/unsupervised.py

python src/export_map.py
python src/gen_static.py

python -m uvicorn api.main:app --port 8000
python -m http.server 8080 --directory web
```

Puis ouvrir http://localhost:8080.

## Déploiement

Le frontend se déploie sur Vercel et l'API sur Render, avec redéploiement automatique à chaque push. 

## Outils

Python, DuckDB, pandas, scikit-learn, FastAPI, deck.gl, MapLibre.
