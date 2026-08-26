import psycopg

for user in ["postgres", "Ruchika_TejasRaju"]:
    try:
        conn = psycopg.connect(f"postgresql://{user}@localhost:5434/postgres", connect_timeout=3)
        row = conn.execute("SELECT version()").fetchone()
        print(f"[SUCCESS] Connected to PostgreSQL 17 as user '{user}'! Version: {row[0]}")
        conn.close()
        break
    except Exception as e:
        print(f"[INFO] Connecting as '{user}' failed: {e}")
