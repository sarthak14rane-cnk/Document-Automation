import psycopg
conn = psycopg.connect(dbname="cnk", user="postgres", password="4cAnZanSDJ08lUQr", host="127.0.0.1", port=2478, connect_timeout=5)
cur = conn.cursor()
cur.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename='clients_client'")
for name, defn in cur.fetchall():
    print("INDEX:", name, "->", defn)
cur.execute("SELECT conname, contype FROM pg_constraint WHERE conrelid='clients_client'::regclass")
print("constraints:", cur.fetchall())
cur.execute("SELECT name, applied FROM django_migrations WHERE app='clients'")
print("client migrations:", cur.fetchall())
conn.close()
