import json, time, urllib.request, urllib.error, sys
from datetime import datetime, timezone
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
                    "client_spoc_name, client_spoc_email, list_of_entities, is_active, "
                    "created_at, updated_at FROM clients_client WHERE client_id=%s", (cid,))
        row = cur.fetchone()
        if not row:
            return None
        keys = ["client_id","client_name","client_short_name","client_industries",
                "client_spoc_name","client_spoc_email","list_of_entities","is_active",
                "created_at","updated_at"]
        return dict(zip(keys, row))

def db_count():
    with psycopg.connect(**DB) as conn:
        return conn.cursor().execute("SELECT COUNT(*) FROM clients_client").fetchone()[0]

results = []
def expect(tid, desc, expected, actual, extra=""):
    ok = expected == actual
    results.append({"id": tid, "desc": desc, "expected": expected, "actual": actual, "pass": ok})
    print(("PASS " if ok else "FAIL ") + f"[{tid}] {desc} | expected: {expected} | actual: {actual}" + (f" | {extra}" if extra and not ok else ""))

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

# R1: KNOWN DEFECT re-check — POST without client_short_name
st, body = req("POST", "/clients/", {"client_name": "TEST-ECHO Ltd",
    "client_spoc_name": "Echo Test", "client_spoc_email": "echo@test.test"})
expect("R1", "POST without client_short_name -> 201 (plan: optional)", 201, st,
       f"body={str(body)[:300]}")

# R3: POST with short_name given but industries/entities omitted
st, body = req("POST", "/clients/", {"client_name": "TEST-FOXTROT Ltd",
    "client_short_name": "FXT", "client_spoc_name": "Fox Test",
    "client_spoc_email": "fox@test.test"})
idF = body.get("client_id") if isinstance(body, dict) and st == 201 else None
rowF = db_row(idF) if idF else None
ok = st == 201 and rowF and rowF["client_industries"] == [] and rowF["list_of_entities"] == []
expect("R3", "POST omitting only list fields -> 201 + DB defaults []", "201 + DB industries=[] entities=[]",
       f"{st} db={json.dumps(rowF, default=str, sort_keys=True) if rowF else None}")

# R9: JSON null for list fields -> coerced to []
st, body = req("POST", "/clients/", full("TEST-GOLF Ltd", client_industries=None, list_of_entities=None))
idG = body.get("client_id") if isinstance(body, dict) and st == 201 else None
rowG = db_row(idG) if idG else None
expect("R9", "POST null list fields -> coerced [] per plan", "201 + DB [] []",
       f"{st} db={json.dumps(rowG, default=str, sort_keys=True) if rowG else None}")

# R6: whitespace stripping
st, body = req("POST", "/clients/", full("  TEST-HOTEL Ltd  ", client_spoc_name="  H S  ", client_spoc_email=" h@hotel.test "))
idH = body.get("client_id") if isinstance(body, dict) and st == 201 else None
rowH = db_row(idH) if idH else None
ok = st == 201 and rowH and rowH["client_name"] == "TEST-HOTEL Ltd" and rowH["client_spoc_name"] == "H S"
expect("R6", "POST strips surrounding whitespace", "201 + DB stripped name/spoc",
       f"{st} name={rowH['client_name'] if rowH else None} spoc={rowH['client_spoc_name'] if rowH else None}")

# R8: client_name > 255 chars -> 400
st, body = req("POST", "/clients/", full("X" * 256))
expect("R8", "POST client_name 256 chars -> 400 (max_length)", 400, st, f"body={str(body)[:200]}")

# R4: real collision target — create TEST-INDIA Ltd then try PUTting another onto it
st, body = req("POST", "/clients/", full("TEST-INDIA Ltd"))
idI = body.get("client_id") if isinstance(body, dict) and st == 201 else None
st, body = req("POST", "/clients/", full("TEST-JULIET Ltd", client_spoc_email="j@juliet.test"))
idJ = body.get("client_id") if isinstance(body, dict) and st == 201 else None
st, body = req("PUT", f"/clients/{idJ}/", full("test-india ltd", client_spoc_email="j@juliet.test"))
rowJ = db_row(idJ) if idJ else None
expect("R4", "PUT rename onto existing other client (case-variant) -> 409 + DB unchanged", "409",
       st, f"body={str(body)[:300]} db_name={rowJ['client_name'] if rowJ else None}")

# R4b: exact-case rename onto other -> 409
st, body = req("PUT", f"/clients/{idJ}/", full("TEST-INDIA Ltd", client_spoc_email="j@juliet.test"))
expect("R4b", "PUT rename exact other name -> 409", 409, st, f"body={str(body)[:200]}")

# R5: own-name case-variant still 200
st, body = req("PUT", f"/clients/{idJ}/", full("TEST-JULIET ltd", client_spoc_email="j@juliet.test"))
expect("R5", "PUT own name case-variant -> 200", 200, st, f"body={str(body)[:200]}")

# R11: GET detail matches DB exactly for one client
st, body = req("GET", f"/clients/{idI}/")
rowI = db_row(idI)
ok = st == 200 and body and body["client_name"] == rowI["client_name"] \
     and body["client_industries"] == rowI["client_industries"] \
     and body["is_active"] == rowI["is_active"]
expect("R11", "GET detail JSON matches DB row", "API == DB", "API=" + json.dumps(body, sort_keys=True) + " DB=" + json.dumps(rowI, default=str, sort_keys=True))

# cleanup: soft-delete every active TEST- row via the API
with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT client_id FROM clients_client WHERE client_name LIKE 'TEST-%' AND is_active")
    active_ids = [r[0] for r in cur.fetchall()]
deleted = []
for cid in active_ids:
    st, body = req("DELETE", f"/clients/{cid}/")
    deleted.append((cid, st))
with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_active THEN 1 ELSE 0 END) FROM clients_client WHERE client_name LIKE 'TEST-%'")
    total, act = cur.fetchone()
expect("CL1", "cleanup soft-deletes all TEST rows via API", f"{len(active_ids)} x 204",
       str(deleted))
expect("CL2", "DB: all TEST rows present, none active", f"total={total} active=0",
       f"total={total} active={act}")

print()
fails = [r for r in results if not r["pass"]]
print(f"ROUND2 TOTAL: {len(results)} checks, {len(results)-len(fails)} passed, {len(fails)} failed")
json.dump({"timestamp": datetime.now(timezone.utc).isoformat(), "results": results},
          open(r"C:\Users\LT-IS-07\AppData\Local\Temp\opencode\api_results_round2.json", "w"), indent=1)
sys.exit(1 if fails else 0)
