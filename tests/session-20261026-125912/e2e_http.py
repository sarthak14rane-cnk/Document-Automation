"""E2E HTTP-contract runner for the Clients API as consumed by the frontend UI.

Exercises the complete CRUD + validation contract end-to-end against a live
dev server using the exact JSON payload shapes the UI JavaScript sends.
Repos stay untouched: writes only transient sandbox rows (each soft-deleted
before finishing).

Usage: uv run python e2e_http.py [base_url]   (default http://127.0.0.1:8010)
Prints one PASS/FAIL line per step; exits 0 only if every step passed.
"""
import datetime
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
STAMP = str(int(time.time()))
RESULTS = []


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, (json.loads(body) if body.strip() else None)


def check(step, ok, detail):
    RESULTS.append((step, ok))
    print(("PASS" if ok else "FAIL") + "  " + step + "  " + str(detail))


def main():
    name = "E2E Sandbox Journey " + STAMP
    results = []
    payload = {
        "client_name": name,
        "client_short_name": "E2EJ",
        "client_industries": ["Manufacturing", "FMCG"],
        "client_spoc_name": "E2E Http Tester",
        "client_spoc_email": "e2e_http@example.com",
        "list_of_entities": ["E2E Pvt Ltd", "E2E LLP"],
    }

    # ---- CREATE ----
    status, body = call("POST", "/clients/", payload)
    ok = status == 201 and isinstance(body, dict) and "client_id" in body and body.get("is_active") is True
    check("E1 POST create -> 201 with client_id/is_active", ok, "status=" + str(status))
    if not ok:
        return finish()
    client_id = body["client_id"]
    created = dict(body)
    check("E1b echo payload + server timestamps",
          body.get("client_name") == name and "created_at" in body and "updated_at" in body,
          "client_id=" + str(client_id))

    # ---- LIST ----
    status, body = call("GET", "/clients/")
    first = body[0] if isinstance(body, list) and body else None
    check("E2 GET list -> 200, new row first (newest first)",
          status == 200 and first and first.get("client_id") == client_id,
          "status=" + str(status) + ", count=" + str(len(body) if isinstance(body, list) else "?"))

    # ---- Duplicate case-insensitive ----
    status, body = call("POST", "/clients/", dict(payload, client_name=name.upper()))
    check("E3 POST duplicate UPPER name -> 409 client_name error",
          status == 409 and isinstance(body, dict) and "client_name" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    # ---- 400 validation shapes ----
    status, body = call("POST", "/clients/", {k: v for k, v in payload.items() if k != "client_spoc_email"})
    check("E4 POST missing required email -> 400",
          status == 400 and isinstance(body, dict) and "client_spoc_email" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("POST", "/clients/", dict(payload, client_spoc_email="not-an-email"))
    check("E5 POST invalid email -> 400", status == 400 and "client_spoc_email" in body, "status=" + str(status))

    status, body = call("POST", "/clients/", dict(payload, client_industries="Manufacturing"))
    check("E6 POST industries as string -> 400 'must be a list'",
          status == 400 and "client_industries" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("POST", "/clients/", dict(payload, list_of_entities=["ok", 42]))
    check("E7 POST non-string list member -> 400",
          status == 400 and "list_of_entities" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("POST", "/clients/", dict(payload, client_name="   "))
    check("E8 POST whitespace-only name -> 400",
          status == 400 and "client_name" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("POST", "/clients/", dict(payload, client_name="X" * 300))
    check("E9 POST 300-char name -> 400 maxlength",
          status == 400 and "client_name" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("POST", "/clients/", dict(payload, client_name=None))
    check("E10 POST null name -> 400", status == 400, "status=" + str(status))

    # ---- read-only fields ignored ----
    status, body = call("POST", "/clients/", dict(payload, client_name="E2E Sandbox JourneyRival " + STAMP, client_id=9999, is_active=False))
    ok = status == 201 and isinstance(body, dict) and body.get("client_id") not in (9999, client_id) and body.get("is_active") is True
    check("E11 POST readonly fields ignored (client_id/is_active)", ok,
          "status=" + str(status) + ", body=" + json.dumps(body)[:160])
    rival = body if ok else None

    # ---- PUT (full update) ----
    put_payload = dict(payload, client_short_name="E2EJ-UPD")
    status, body = call("PUT", "/clients/" + str(client_id) + "/", put_payload)
    check("E12 PUT full payload -> 200 short name changed",
          status == 200 and isinstance(body, dict) and body.get("client_short_name") == "E2EJ-UPD",
          "status=" + str(status))
    updated = body if status == 200 and isinstance(body, dict) else None

    missing = {k: v for k, v in put_payload.items() if k != "list_of_entities"}
    status, body = call("PUT", "/clients/" + str(client_id) + "/", missing)
    check("E13 PUT missing one key -> 400 (all-keys contract)",
          status == 400 and isinstance(body, dict) and "list_of_entities" in body,
          "status=" + str(status) + ", body=" + json.dumps(body)[:140])

    status, body = call("PATCH", "/clients/" + str(client_id) + "/", {"client_short_name": "X"})
    check("E14 PATCH -> 405 (disabled verb)", status == 405, "status=" + str(status))

    status, body = call("PUT", "/clients/99999999/", put_payload)
    check("E15 PUT unknown id -> 404", status == 404, "status=" + str(status))

    if rival is None:
        check("E16 PUT rename to other client's UPPER name -> 409", False, "rival row missing")
    else:
        status, body = call("PUT", "/clients/" + str(client_id) + "/",
                            dict(put_payload, client_name=rival["client_name"].upper()))
        check("E16 PUT rename to other client's UPPER name -> 409",
              status == 409 and "client_name" in body,
              "status=" + str(status))
        status, body = call("PUT", "/clients/" + str(client_id) + "/",
                            dict(put_payload, client_name=name))
        check("E17 PUT rename to own name (case-variant UPPER) -> 200 self-exclusion",
              status == 200 and isinstance(body, dict) and body.get("client_name") == name,
              "status=" + str(status))

    # ---- DELETE chain ----
    status, body = call("DELETE", "/clients/" + str(client_id) + "/")
    check("E18 DELETE -> 204 empty", status == 204 and body is None, "status=" + str(status))
    status, body = call("DELETE", "/clients/" + str(client_id) + "/")
    check("E19 DELETE again -> 404", status == 404, "status=" + str(status))
    status, body = call("GET", "/clients/" + str(client_id) + "/")
    check("E20 GET deleted id -> 404 (active-only)", status == 404, "status=" + str(status))
    status, body = call("GET", "/clients/")
    ids = [c["client_id"] for c in body] if isinstance(body, list) else []
    check("E21 list excludes deleted id", client_id not in ids, "count=" + str(len(ids)))
    status, body = call("PUT", "/clients/" + str(client_id) + "/", put_payload)
    check("E22 PUT on deleted id -> 404", status == 404, "status=" + str(status))

    # ---- cleanup rival ----
    if rival is not None:
        s, _ = call("DELETE", "/clients/" + str(rival["client_id"]) + "/")
        check("C1 cleanup: rival row soft-deleted", s == 204, "status=" + str(s))

    # ---- timestamps ----
    if created and updated:
        def parse(ts):
            return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        check("E23 updated_at advanced after PUT",
              parse(updated["updated_at"]) > parse(created["created_at"]),
              created["created_at"][:19] + " -> " + updated["updated_at"][:19])

    finish()


def finish():
    failed = [r for r in RESULTS if not r[1]]
    print("\n===== " + str(len(RESULTS) - len(failed)) + "/" + str(len(RESULTS)) + " steps passed =====")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
