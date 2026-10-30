import json, urllib.request, urllib.error
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

full = lambda name, **kw: {
    "client_name": name, "client_short_name": "ACME",
    "client_industries": ["Manufacturing", "FMCG"],
    "client_spoc_name": "Priya Sharma", "client_spoc_email": "priya@acme.test",
    "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"], **kw}

st, body = req("POST", "/clients/", full("TEST-NOVEMBER Ltd", client_industries=[], list_of_entities=[]))
print("RR8 POST empty lists ->", st, "client_id:", body.get("client_id") if isinstance(body, dict) else body)
if isinstance(body, dict) and st == 201:
    s, _ = req("DELETE", f"/clients/{body['client_id']}/")
    print("RR8b cleanup ->", s)

st, body = req("POST", "/clients/", full("TEST-ALPHA LTD"))
print("RR9 POST case-variant of SOFT-DELETED name ->", st, json.dumps(body) if isinstance(body, dict) else str(body)[:200], "(expect 409: soft-deleted names still block)")

with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN is_active THEN 1 ELSE 0 END), MIN(client_id), MAX(client_id) FROM clients_client")
    print("FINAL DB reconcile (total, active, min_id, max_id):", cur.fetchone())
