"""Re-test the exact D1/D2 defect payloads against the live server, then verify DB."""
import json, time, urllib.request, urllib.error
import psycopg

BASE = "http://127.0.0.1:8765"
DB = dict(dbname="cnk", user="postgres", password="4cAnZanSDJ08lUQr",
          host="127.0.0.1", port=2478, connect_timeout=5)

def req(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw.decode(errors="replace")[:200]
        return e.code, body

def db_row(cid):
    with psycopg.connect(**DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT client_id, client_name, client_short_name, client_industries, "
                    "client_spoc_email, list_of_entities, is_active FROM clients_client WHERE client_id=%s", (cid,))
        row = cur.fetchone()
        keys = ["client_id","client_name","client_short_name","client_industries",
                "client_spoc_email","list_of_entities","is_active"]
        return dict(zip(keys, row)) if row else None

for _ in range(20):
    try:
        req("GET", "/clients/"); break
    except Exception:
        time.sleep(0.5)

full = lambda name, **kw: {
    "client_name": name, "client_short_name": "ACME",
    "client_industries": ["Manufacturing", "FMCG"],
    "client_spoc_name": "Priya Sharma", "client_spoc_email": "priya@acme.test",
    "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"], **kw}

ok_all = True
def check(tid, desc, cond, detail):
    global ok_all
    if not cond: ok_all = False
    print(("PASS " if cond else "FAIL ") + f"[{tid}] {desc} | {detail}")

# D1: exactly the payload that used to 500
st, body = req("POST", "/clients/", {"client_name": "TEST-D1FIX Ltd",
    "client_spoc_name": "Ravi Kumar", "client_spoc_email": "ravi@beta.test"})
id1 = body.get("client_id") if isinstance(body, dict) and st == 201 else None
row = db_row(id1) if id1 else None
check("D1-retest", "POST without client_short_name -> 201 (was 500)", st == 201 and row
      and row["client_short_name"] == "" and row["client_industries"] == []
      and row["list_of_entities"] == [] and row["is_active"] is True,
      f"status={st} db={json.dumps(row, default=str, sort_keys=True)}")

# D2: exactly the payload that used to 400
st, body = req("POST", "/clients/", full("TEST-D2FIX Ltd", client_industries=None, list_of_entities=None))
id2 = body.get("client_id") if isinstance(body, dict) and st == 201 else None
row = db_row(id2) if id2 else None
check("D2-retest", "POST null list fields -> 201 coerced [] (was 400)", st == 201 and row
      and row["client_industries"] == [] and row["list_of_entities"] == [],
      f"status={st} db={json.dumps(row, default=str, sort_keys=True)}")

# D2 on PUT: key present with null value -> coerced, still 200
if id2:
    st, body = req("PUT", f"/clients/{id2}/", full("TEST-D2FIX Ltd", client_industries=None, list_of_entities=None))
    row = db_row(id2)
    check("D2-put", "PUT with null list values -> 200 coerced []", st == 200 and row
          and row["client_industries"] == [] and row["list_of_entities"] == [],
          f"status={st} db={json.dumps(row, default=str, sort_keys=True)}")

# regression guard: PUT still requires key presence; validation still rejects bad lists
st, _ = req("PUT", f"/clients/{id2}/", {k: v for k, v in full("TEST-D2FIX Ltd").items() if k != "list_of_entities"})
check("guard-put-required", "PUT missing list_of_entities still 400", st == 400, f"status={st}")
st, _ = req("POST", "/clients/", full("TEST-GUARD", client_industries=["Mfg", 42]))
check("guard-bad-member", "POST non-string member still 400", st == 400, f"status={st}")

# no duplicate rows created by guards/bad requests
with psycopg.connect(**DB) as conn:
    n = conn.cursor().execute("SELECT COUNT(*) FROM clients_client").fetchone()[0]
check("no-strays", "only the 2 fix-test rows exist", n == 2, f"count={n}")

# cleanup: soft-delete both via API
for cid in [id1, id2]:
    st, _ = req("DELETE", f"/clients/{cid}/")
    print(f"cleanup delete {cid} -> {st}")
with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_active THEN 1 ELSE 0 END) FROM clients_client")
    total, act = cur.fetchone()
check("cleanup", "rows kept, none active", act == 0, f"total={total} active={act}")

print()
print("ALL PASS" if ok_all else "SOME FAILED")
