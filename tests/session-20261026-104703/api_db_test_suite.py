"""Live API + DB persistence verification for the clients CRUD API.

Runs every endpoint against the live dev server with valid data (plus the
expected error outputs from plan section 4), then verifies each write by
querying the PostgreSQL `cnk` database directly.
"""
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
            body = raw.decode(errors="replace")
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
def record(tid, desc, expected, actual, ok, extra=""):
    results.append({"id": tid, "desc": desc, "expected": expected,
                    "actual": actual, "pass": bool(ok), "extra": extra})
    print(("PASS " if ok else "FAIL ") + f"[{tid}] {desc}: expected {expected}, got {actual}" + (f" | {extra}" if extra and not ok else ""))

def expect(tid, desc, expected, actual, extra=""):
    record(tid, desc, expected, actual, expected == actual, extra)

# ---- wait for server ----
for _ in range(30):
    try:
        req("GET", "/clients/"); break
    except Exception:
        time.sleep(0.5)

full = lambda name, **kw: {
    "client_name": name,
    "client_short_name": "ACME",
    "client_industries": ["Manufacturing", "FMCG"],
    "client_spoc_name": "Priya Sharma",
    "client_spoc_email": "priya@acme.test",
    "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"], **kw}

start_count = db_count()
print(f"DB rows before suite: {start_count}")

# T01 create valid full payload
st, body = req("POST", "/clients/", full("TEST-ALPHA Ltd"))
idA = body.get("client_id") if isinstance(body, dict) else None
ok = st == 201 and isinstance(idA, int) and body.get("is_active") is True \
     and body.get("created_at") and body.get("updated_at")
expect("T01", "POST valid full payload -> 201 + full JSON", "201 + client_id/is_active/created_at/updated_at", f"{st} client_id={idA}", "client_id must be int, is_active true, timestamps set")
rowA = db_row(idA)
ok2 = rowA and rowA["client_name"] == "TEST-ALPHA Ltd" and rowA["client_short_name"] == "ACME" \
      and rowA["client_industries"] == ["Manufacturing", "FMCG"] \
      and rowA["client_spoc_name"] == "Priya Sharma" and rowA["client_spoc_email"] == "priya@acme.test" \
      and rowA["list_of_entities"] == ["Acme Pvt Ltd", "Acme LLP"] and rowA["is_active"] is True
expect("T01b", "DB row matches created payload", "all fields + is_active=true", "row=" + json.dumps(rowA, default=str, sort_keys=True), "DB persistence mismatch")

# T02 duplicate exact name
st, body = req("POST", "/clients/", full("TEST-ALPHA Ltd"))
expect("T02", "POST duplicate exact name -> 409", 409, st, f"body={body}")
expect("T02b", "409 did not add a row", db_count(), start_count + 1)

# T03 duplicate case-variant
st, body = req("POST", "/clients/", full("TEST-ACME LTD"))
expect("T03", "POST case-variant duplicate -> 409", 409, st, f"body={body}")
expect("T03b", "409 did not add a row", db_count(), start_count + 1)

# T04 create with only required keys (optionals omitted)
st, body = req("POST", "/clients/", {"client_name": "TEST-BETA Ltd",
    "client_spoc_name": "Ravi Kumar", "client_spoc_email": "ravi@beta.test"})
idB = body.get("client_id") if isinstance(body, dict) else None
expect("T04", "POST with only required keys -> 201", 201, st, f"body={body}")
rowB = db_row(idB)
ok = rowB and rowB["client_short_name"] == "" and rowB["client_industries"] == [] \
     and rowB["list_of_entities"] == [] and rowB["is_active"] is True
expect("T04b", "DB defaults for omitted optionals", "short='', industries=[], entities=[], active", json.dumps(rowB, default=str, sort_keys=True))

# T05-T10 invalid creates
st, body = req("POST", "/clients/", full("TEST-E1", _drop := "client_name") if False else
               {k: v for k, v in full("TEST-E1").items() if k != "client_name"})
expect("T05", "POST missing client_name -> 400", 400, st, f"body={body}")
st, body = req("POST", "/clients/", {k: v for k, v in full("TEST-E2").items() if k != "client_spoc_email"})
expect("T06", "POST missing client_spoc_email -> 400", 400, st, f"body={body}")
st, body = req("POST", "/clients/", full("TEST-E3", client_spoc_email="not-an-email"))
expect("T07", "POST invalid email -> 400", 400, st, f"body={body}")
st, body = req("POST", "/clients/", full("TEST-E4", client_industries="Manufacturing"))
expect("T08", "POST industries as string -> 400", 400, st, f"body={body}")
st, body = req("POST", "/clients/", full("TEST-E5", client_industries=["Mfg", 42]))
expect("T09", "POST industries with non-string member -> 400", 400, st, f"body={body}")
st, body = req("POST", "/clients/", full("TEST-E6", list_of_entities="Acme"))
expect("T10", "POST list_of_entities as string -> 400", 400, st, f"body={body}")
expect("T05b", "invalid creates added no rows", db_count(), start_count + 3)

# T11 read-only fields ignored on create
st, body = req("POST", "/clients/", full("TEST-DELTA Ltd", client_id=999, is_active=False,
                                         created_at="2000-01-01T00:00:00Z", updated_at="2000-01-01T00:00:00Z"))
idD = body.get("client_id") if isinstance(body, dict) else None
rowD = db_row(idD)
ok = st == 201 and idD != 999 and rowD and rowD["is_active"] is True \
     and rowD["created_at"].year == 2026
expect("T11", "POST with injected read-only fields ignored", "201, own id, active, server timestamps",
       f"{st} id={idD} active={rowD['is_active'] if rowD else None} created={rowD['created_at'] if rowD else None}")

# T12 list: active only, newest first
st, body = req("GET", "/clients/")
names = [c["client_name"] for c in body] if isinstance(body, list) else []
ok = st == 200 and names == ["TEST-DELTA Ltd", "TEST-BETA Ltd", "TEST-ALPHA Ltd"]  # newest first
expect("T12", "GET list active-only newest-first", "200 [DELTA,BETA,ALPHA]", f"{st} {names}")

# T13 retrieve active
st, body = req("GET", f"/clients/{idA}/")
keys = sorted(body.keys()) if isinstance(body, dict) else []
expect("T13", "GET active client -> 200 all 10 fields", "200, 10 keys", f"{st} {len(keys)} keys", f"keys={keys}")

# T15 unknown id / T16 non-numeric
st, body = req("GET", "/clients/999999/")
expect("T15", "GET unknown id -> 404", 404, st, f"body={body}")
st, body = req("GET", "/clients/abc/")
expect("T16", "GET non-numeric id -> 404", 404, st, f"body={body}")

# T17 full PUT changes values
st, body = req("POST", "/clients/", full("TEST-GAMMA Ltd", client_spoc_email="g@gamma.test"))
idC = body.get("client_id") if isinstance(body, dict) else None
rowC0 = db_row(idC)
st, body = req("PUT", f"/clients/{idC}/", full("TEST-GAMMA Corp", client_short_name="GMMA",
               client_industries=["IT"], client_spoc_email="new@gamma.test",
               list_of_entities=["Gamma LLP"]))
rowC1 = db_row(idC)
ok = st == 200 and rowC1 and rowC1["client_name"] == "TEST-GAMMA Corp" \
     and rowC1["client_short_name"] == "GMMA" and rowC1["client_industries"] == ["IT"] \
     and rowC1["client_spoc_email"] == "new@gamma.test" and rowC1["list_of_entities"] == ["Gamma LLP"] \
     and rowC1["updated_at"] > rowC1["created_at"] and rowC1["updated_at"] > rowC0["updated_at"]
expect("T17", "PUT full payload -> 200 + DB updated", "200 + all changed fields in DB + updated_at advanced",
       f"{st} row=" + json.dumps({k: rowC1[k] for k in ['client_name','client_short_name','client_industries','client_spoc_email','list_of_entities']}, default=str, sort_keys=True) if rowC1 else str(st))

# T18 PUT missing one key -> 400, DB unchanged
p = full("TEST-GAMMA Corp"); p.pop("list_of_entities")
st, body = req("PUT", f"/clients/{idC}/", p)
rowC2 = db_row(idC)
expect("T18", "PUT missing list_of_entities -> 400 + DB unchanged", "400 + name still TEST-GAMMA Corp",
       f"{st} name={rowC2['client_name'] if rowC2 else None}")

# T19 PUT rename to other client's name (case-variant) -> 409
st, body = req("PUT", f"/clients/{idC}/", full("test-beta ltd"))
expect("T19", "PUT rename to other's name case-variant -> 409", 409, st, f"body={body}")

# T20 PUT own name case-variant -> 200 (self-exclusion)
st, body = req("PUT", f"/clients/{idC}/", full("TEST-GAMMA ltd"))
expect("T20", "PUT own name case-variant -> 200", 200, st, f"body={body}")

# T21 PUT with read-only fields injected -> ignored
st, body = req("PUT", f"/clients/{idC}/", full("TEST-GAMMA Ltd", client_id=999, is_active=False))
rowC3 = db_row(idC)
ok = st == 200 and rowC3 and rowC3["client_id"] == idC and rowC3["is_active"] is True
expect("T21", "PUT ignores injected client_id/is_active", "200, DB id unchanged + still active",
       f"{st} id={rowC3['client_id'] if rowC3 else None} active={rowC3['is_active'] if rowC3 else None}")

# T23 PATCH -> 405
st, body = req("PATCH", f"/clients/{idC}/", {"client_short_name": "X"})
expect("T23", "PATCH -> 405", 405, st, f"body={body}")

# T24 DELETE -> 204 empty body + soft delete in DB
st, body = req("DELETE", f"/clients/{idA}/")
rowA2 = db_row(idA)
ok = st == 204 and body is None and rowA2 and rowA2["is_active"] is False \
     and rowA2["updated_at"] > rowA2["created_at"]
expect("T24", "DELETE -> 204 empty + DB is_active=false, updated_at refreshed",
       "204, body empty, DB row kept with is_active=false", f"{st} body={body} db_active={rowA2['is_active'] if rowA2 else None} upd={rowA2['updated_at'] if rowA2 else None} created={rowA2['created_at'] if rowA2 else None}")

# T25 deleted client invisible/immutable via API
st, body = req("GET", f"/clients/{idA}/")
expect("T25a", "GET deleted id -> 404", 404, st)
p = full("TEST-ALPHA Ltd")
st, body = req("PUT", f"/clients/{idA}/", p)
expect("T25b", "PUT deleted id -> 404", 404, st)
st, body = req("GET", "/clients/")
names = [c["client_name"] for c in body] if isinstance(body, list) else []
expect("T25c", "list excludes deleted", "[TEST-GAMMA Ltd,TEST-BETA Ltd,TEST-DELTA Ltd]", str(names))

# T26 delete again / unknown
st, body = req("DELETE", f"/clients/{idA}/")
expect("T26a", "DELETE already-deleted -> 404", 404, st)
st, body = req("DELETE", "/clients/999999/")
expect("T26b", "DELETE unknown -> 404", 404, st)

# T27 final DB reconciliation
n = db_count()
with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT client_id, client_name, is_active FROM clients_client WHERE client_name LIKE 'TEST-%' ORDER BY client_id")
    rows = cur.fetchall()
active = [r[0] for r in rows if r[2]]
expect("T27", "DB final state reconciles with API", "4 TEST rows (3 active, ALPHA inactive), API listed 3",
       f"rows={rows} API_list={names}")

print()
fails = [r for r in results if not r["pass"]]
print(f"TOTAL: {len(results)} checks, {len(results)-len(fails)} passed, {len(fails)} failed")
json.dump({"timestamp": datetime.now(timezone.utc).isoformat(),
           "base_url": BASE, "results": results},
          open(r"C:\Users\LT-IS-07\AppData\Local\Temp\opencode\api_results.json", "w"), indent=1)
sys.exit(1 if fails else 0)
