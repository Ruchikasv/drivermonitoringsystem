"""
Inspect actual tables and columns in PostgreSQL.
"""
import psycopg

conn = psycopg.connect("postgresql://postgres@localhost:5434/postgres")
with conn.cursor() as cur:
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [r[0] for r in cur.fetchall()]
    print("[POSTGRESQL TABLES IN PUBLIC SCHEMA]:")
    for t in tables:
        cur.execute(f"""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = '{t}'
            ORDER BY ordinal_position;
        """)
        cols = cur.fetchall()
        print(f"  • {t} ({len(cols)} columns):")
        for c in cols:
            print(f"      - {c[0]}: {c[1]} (nullable={c[2]})")

conn.close()
