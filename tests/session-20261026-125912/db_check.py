"""Read-only PostgreSQL row verification for the Clients frontend E2E session.

Verifies every UI-driven change actually landed in the database with the
expected column state. Uses psycopg with credentials from
src/document_generator/.env (same values Django settings reads).

Usage:
  uv run python db_check.py created    --name "NAME" --short "S" --spoc "P" --email "e@x" --industries "A, B" --entities "X, Y"
  uv run python db_check.py updated    --name "NAME" [same args]
  uv run python db_check.py deleted    --name "NAME"
  uv run python db_check.py notcreated --name "NAME"
  uv run python db_check.py caselock   --name "NAME"
  uv run python db_check.py finalstate --prefix "E2E Sandbox"

Exit code 0 = all assertions passed.
"""
import argparse
import json
import os
import sys

import psycopg
from dotenv import load_dotenv

BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "document_generator")
load_dotenv(os.path.join(BASE_DIR, ".env"))


def connect():
    return psycopg.connect(
        dbname=os.getenv("POSTGRES_DB", "django_db"),
        user=os.getenv("POSTGRES_USER", "doc_user"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        host=os.getenv("POSTGRES_HOST", "127.0.0.1").replace("localhost", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        connect_timeout=5,
    )


def split_list(s):
    return [p.strip() for p in (s or "").split(",") if p.strip()]


def fetch_rows_dict(name):
    with connect() as conn:
        cur = conn.execute(
            "SELECT client_id, client_name, client_short_name, client_industries,"
            " client_spoc_name, client_spoc_email, list_of_entities, is_active,"
            " created_at, updated_at FROM clients_client WHERE client_name = %s",
            (name,),
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def dump(rows):
    out = []
    for r in rows:
        out.append({
            "client_id": r["client_id"],
            "short_name": r["client_short_name"],
            "industries": r["client_industries"],
            "spoc_name": r["client_spoc_name"],
            "spoc_email": r["client_spoc_email"],
            "entities": r["list_of_entities"],
            "is_active": r["is_active"],
            "created_at": r["created_at"].isoformat(),
            "updated_at": r["updated_at"].isoformat(),
        })
    return json.dumps(out, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--short", default=None)
    ap.add_argument("--spoc", default=None)
    ap.add_argument("--email", default=None)
    ap.add_argument("--industries", default="")
    ap.add_argument("--entities", default="")
    args = ap.parse_args()

    failures = []

    if args.stage in ("created", "updated"):
        rows = fetch_rows_dict(args.name)
        if len(rows) != 1:
            failures.append("expected exactly 1 row for %r, got %d" % (args.name, len(rows)))
        else:
            r = rows[0]
            if args.stage == "created" and r["is_active"] is not True:
                failures.append("row is not active on creation (is_active=%r)" % r["is_active"])
            if args.stage == "updated" and r["updated_at"] <= r["created_at"]:
                failures.append("updated_at did not advance past created_at")
            if args.short is not None and r["client_short_name"] != args.short:
                failures.append("short_name=%r != %r" % (r["client_short_name"], args.short))
            if args.spoc is not None and r["client_spoc_name"] != args.spoc:
                failures.append("spoc_name=%r != %r" % (r["client_spoc_name"], args.spoc))
            if args.email is not None and r["client_spoc_email"] != args.email:
                failures.append("spoc_email=%r != %r" % (r["client_spoc_email"], args.email))
            lists = {"industries": split_list(args.industries), "entities": split_list(args.entities)}
            if list(r["client_industries"] or []) != lists["industries"]:
                failures.append("industries=%r != %r" % (r["client_industries"], lists["industries"]))
            if list(r["list_of_entities"] or []) != lists["entities"]:
                failures.append("entities=%r != %r" % (r["list_of_entities"], lists["entities"]))
    elif args.stage == "deleted":
        rows = fetch_rows_dict(args.name)
        if len(rows) != 1:
            failures.append("expected exactly 1 row for %r, got %d" % (args.name, len(rows)))
        else:
            r = rows[0]
            if r["is_active"] is not False:
                failures.append("is_active=%r expected False" % r["is_active"])
            if r["updated_at"] <= r["created_at"]:
                failures.append("updated_at did not advance on deactivation")
    elif args.stage == "notcreated":
        rows = fetch_rows_dict(args.name)
        if rows:
            failures.append("row(s) unexpectedly exist: " + dump(rows))
    elif args.stage == "caselock":
        with connect() as conn:
            cur = conn.execute(
                "SELECT count(*) FROM clients_client WHERE LOWER(client_name) = LOWER(%s)",
                (args.name,),
            )
            (count,) = cur.fetchone()
        if count != 1:
            failures.append("case-insensitive row count for %r = %d, expected 1" % (args.name, count))
    elif args.stage == "finalstate":
        if not args.prefix:
            failures.append("--prefix required")
        with connect() as conn:
            cur = conn.execute("SELECT is_active, count(*) FROM clients_client GROUP BY is_active")
            counts = {bool(row[0]): int(row[1]) for row in cur.fetchall()}
            cur = conn.execute(
                "SELECT count(*) FROM clients_client WHERE client_name LIKE %s AND is_active",
                (args.prefix + "%",),
            )
            sandbox_active = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT count(*) FROM clients_client WHERE client_name LIKE %s",
                (args.prefix + "%",),
            )
            sandbox_total = cur.fetchone()[0]
        if sandbox_active != 0:
            failures.append("%d sandbox rows still ACTIVE (expected all soft-deleted)" % sandbox_active)
        print(json.dumps({"sandbox_total": sandbox_total, "sandbox_active": sandbox_active}))
        print(json.dumps({"active_total_in_db": counts.get(True, 0), "inactive_total_in_db": counts.get(False, 0)}))
    else:
        failures.append("unknown stage " + str(args.stage))

    if args.name and args.stage in ("created", "updated", "deleted", "notcreated", "caselock"):
        rows = fetch_rows_dict(args.name) if args.stage != "caselock" else []
        if args.stage != "caselock":
            print(dump(rows))
        else:
            print("(caselock detail: %s rows matched ci)" % len(fetch_rows_dict(args.name)))

    if failures:
        for f in failures:
            print("FAIL: " + f)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
