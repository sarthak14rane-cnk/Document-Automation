import json, urllib.request, urllib.error, sys
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
        cur.execute("SELECT client_id, client_name, client_short_name, client_industries, client_spoc_name, client_spoc_email, list_of_entities, is_active FROM clients_client WHERE client_id=%s", (cid,))
        row = cur.fetchone()
        if not row: return None
        keys = ["client_id","client_name","client_short_name","client_industries","client_spoc_name","client_spoc_email","list_of_entities","is_active"]
        return dict(zip(keys, row))

full = lambda name, **kw: {
    "client_name": name, "client_short_name": "ACME",
    "client_industries": ["Manufacturing", "FMCG"],
    "client_spoc_name": "Priya Sharma", "client_spoc_email": "priya@acme.test",
    "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"], **kw}

st, body = req("POST", "/clients/", full("TEST-KILO Ltd", client_industries=None, list_of_entities=None))
print("RR1 POST null list fields ->", st, "body:", json.dumps(body) if isinstance(body, dict) else str(body)[:300])

st, body = req("POST", "/clients/", {"client_name": "TEST-LIMA Ltd", "client_short_name": "",
    "client_spoc_name": "Lima Test", "client_spoc_email": "lima@test.test"})
idL = body.get("client_id") if isinstance(body, dict) and st == 201 else None
rowL = db_row(idL) if idL else None
print("RR2 POST short_name='' ->", st, "DB short_name:", repr(rowL["client_short_name"]) if rowL else None)
if idL:
    s2, _ = req("DELETE", f"/clients/{idL}/")
    print("RR2b cleanup delete ->", s2)

st, body = req("POST", "/clients/", full("TEST-MIKE Ltd", client_spoc_email="m@mike.test"))
idM = body.get("client_id") if isinstance(body, dict) and st == 201 else None
if idM:
    p = full("TEST-MIKE Ltd", client_spoc_email="m@mike.test"); p.pop("client_short_name")
    st2, body2 = req("PUT", f"/clients/{idM}/", p)
    p2 = full("TEST-MIKE Ltd", client_spoc_email="m@mike.test"); p2.pop("client_industries")
    st3, body3 = req("PUT", f"/clients/{idM}/", p2)
    print("RR3 PUT missing client_short_name ->", st2, "body:", json.dumps(body2) if isinstance(body2, dict) else str(body2)[:200])
    print("RR4 PUT missing client_industries ->", st3, "body:", json.dumps(body3) if isinstance(body3, dict) else str(body3)[:200])
    s4, _ = req("DELETE", f"/clients/{idM}/")
    print("RR3b cleanup delete ->", s4)

with psycopg.connect(**DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT client_spoc_email FROM clients_client WHERE client_id=8")
    print("RR5 DB email of row 8 (was sent padded):", repr(cur.fetchone()[0]))

st, body = req("GET", "/clients/")
print("RR6 GET list with only soft-deleted rows ->", st, "len:", len(body) if isinstance(body, list) else body)

st, body = req("GET", "/clients/")
names = [c["client_name"] for c in body] if isinstance(body, list) else []
print("RR7 list empty (all soft-deleted):", st, names)
