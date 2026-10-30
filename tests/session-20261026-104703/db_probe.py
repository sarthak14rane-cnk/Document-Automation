import psycopg

conn = psycopg.connect(
    dbname="cnk", user="postgres", password="4cAnZanSDJ08lUQr",
    host="127.0.0.1", port=2478, connect_timeout=5,
)
cur = conn.cursor()

cur.execute("SELECT current_database()")
print("connected to:", cur.fetchone()[0])

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print("tables:", tables)

if "clients_client" in tables:
    cur.execute("SELECT COUNT(*) FROM clients_client")
    print("clients_client rows:", cur.fetchone()[0])
    cur.execute("SELECT conname FROM pg_constraint WHERE conrelid='clients_client'::regclass ORDER BY conname")
    print("constraints:", [r[0] for r in cur.fetchall()])
    cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='clients_client' ORDER BY ordinal_position")
    for name, dtype, nullable in cur.fetchall():
        print(f"  {name}: {dtype} (null={nullable})")
else:
    print("clients_client MISSING")

conn.close()
