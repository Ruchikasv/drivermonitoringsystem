"""
Probe local PostgreSQL service connection.
"""
import psycopg

passwords = ["postgres", "admin", "root", "password", "1234", "123456", "Ruchika", "ruchika", ""]
ports = [5432, 5433]

success = False
for port in ports:
    for pwd in passwords:
        try:
            conn = psycopg.connect(
                f"postgresql://postgres:{pwd}@localhost:{port}/postgres",
                connect_timeout=2
            )
            print(f"[SUCCESS] Connected to PostgreSQL on port {port} with password: '{pwd}'")
            conn.close()
            success = True
            break
        except Exception as e:
            # print(f"[FAIL] port {port}, pwd '{pwd}': {e}")
            pass
    if success:
        break

if not success:
    print("[FAIL] Could not connect with common default passwords. Testing Windows authentication / trust...")
    try:
        conn = psycopg.connect("postgresql://localhost:5432/postgres", connect_timeout=2)
        print("[SUCCESS] Connected to PostgreSQL with local SSPI/default auth")
        conn.close()
        success = True
    except Exception as e:
        print(f"[FAIL] Direct connect error: {e}")
