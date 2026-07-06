import os, duckdb

BASE = os.path.join(os.path.dirname(__file__), "..")
DB = os.path.join(BASE, "data", "processed", "flights.duckdb")
RAW = os.path.join(BASE, "data", "raw")

def build(db_path=DB, pattern="bts_2024_*.csv"):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path): os.remove(db_path)
    con = duckdb.connect(db_path)
    glob = os.path.join(RAW, pattern).replace("\\", "/")
    con.execute(f"""
        CREATE TABLE flights AS
        WITH base AS (SELECT
            CAST(FlightDate AS DATE)                  AS flight_date,
            Month                                     AS month,
            DayOfWeek                                 AS day_of_week,
            CAST(CRSDepTime AS INTEGER) // 100 % 24   AS dep_hour,
            CAST(CRSDepTime AS INTEGER) // 100 * 60 + CAST(CRSDepTime AS INTEGER) % 100 AS dep_min,
            DepTimeBlk                                AS dep_block,
            Reporting_Airline                         AS airline,
            Tail_Number                               AS tail,
            Origin                                    AS origin,
            Dest                                      AS dest,
            CAST(Distance AS INTEGER)                 AS distance,
            CAST(CRSElapsedTime AS INTEGER)           AS crs_elapsed,
            CAST(Cancelled AS INTEGER)                AS cancelled,
            CAST(Diverted AS INTEGER)                 AS diverted,
            ArrDelay                                  AS arr_delay,
            CAST(ArrDel15 AS INTEGER)                 AS arr_del15,
            CAST(DepDel15 AS INTEGER)                 AS dep_del15
        FROM read_csv_auto('{glob}', ignore_errors=true))
        SELECT *,
            COALESCE(lag(arr_delay) OVER (PARTITION BY tail, flight_date ORDER BY dep_min), 0) AS prev_arr_delay,
            count(*) OVER (PARTITION BY origin, flight_date, dep_hour) AS dep_congestion,
            COALESCE(dep_min - lag(dep_min + COALESCE(crs_elapsed, 120)) OVER (
                PARTITION BY tail, flight_date ORDER BY dep_min), 240) AS turnaround
        FROM base
    """)
    con.execute("""
        CREATE TABLE flights2 AS
        WITH hr AS (
            SELECT origin, flight_date, dep_hour, avg(dep_del15) AS dep_rate
            FROM flights WHERE dep_del15 IS NOT NULL GROUP BY origin, flight_date, dep_hour),
        st AS (
            SELECT a.origin, a.flight_date, a.dep_hour, avg(b.dep_rate) AS airport_state
            FROM hr a JOIN hr b ON a.origin=b.origin AND a.flight_date=b.flight_date
                AND b.dep_hour BETWEEN a.dep_hour-2 AND a.dep_hour-1
            GROUP BY a.origin, a.flight_date, a.dep_hour)
        SELECT f.*, COALESCE(s.airport_state, 0.2) AS airport_state
        FROM flights f LEFT JOIN st s
            ON f.origin=s.origin AND f.flight_date=s.flight_date AND f.dep_hour=s.dep_hour
    """)
    con.execute("DROP TABLE flights"); con.execute("ALTER TABLE flights2 RENAME TO flights")
    n = con.execute("SELECT count(*) FROM flights").fetchone()[0]
    con.execute("CREATE INDEX idx_origin ON flights(origin)")
    con.execute("CREATE INDEX idx_dest ON flights(dest)")
    ap = os.path.join(RAW, "airports.dat").replace("\\", "/")
    con.execute(f"""
        CREATE TABLE airports AS SELECT
            column04 AS iata, column01 AS name, column02 AS city, column03 AS country,
            CAST(column06 AS DOUBLE) AS lat, CAST(column07 AS DOUBLE) AS lon
        FROM read_csv('{ap}', header=false, all_varchar=true)
        WHERE column04 <> '\\N' AND length(column04) = 3
    """)
    con.close()
    print(f"OK -> {db_path} | {n:,} vols")
    return n

if __name__ == "__main__":
    build()
