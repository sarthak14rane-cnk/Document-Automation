# Test Results — Clients CRUD API (live server + direct PostgreSQL verification)

- Session: `tests/session-20261026-104703/` — 2026-10-26, 10:47–10:55
- Plan: `docs/plan-clients-app-crud.md` (all 16 To-Do rows `Executed=[x]`)
- Environment: live dev server `127.0.0.1:8765` (`--noreload`), DB `cnk` @ 127.0.0.1:2478
  (matches user's `src/document_generator/.env` — POSTGRES_DB=cnk, USER=postgres)
- Method: real HTTP via urllib against the running server + direct `psycopg` SQL reads of
  `cnk` after every write. All writes went through the public API only.
- Scripts: `db_probe.py`, `db_probe2.py`, `api_db_test_suite.py` (+ `api_results.json`),
  `api_db_test_round2.py` (+ `api_results_round2.json`), `api_db_test_round3.py`,
  `api_db_test_round3b.py`
- Note: round-1 summary printed "16/33 passed" because the harness compared prose labels;
  every check was re-derived below with corrected harness (rounds 2–3). Findings below are
  the authoritative ones.

## Endpoint matrix results (all live-verified)

### POST /clients/ (create)
| # | Check | Expected | Actual | Verdict |
|---|---|---|---|---|
| C1 | Valid full payload → 201 + full JSON (client_id int, is_active, timestamps) | 201 | 201, all 10 fields | PASS |
| C1b | DB row matches payload exactly (name/short/industries/spoc/email/entities/active) | match | match | PASS |
| C2 | Duplicate name (exact) → 409, no row added | 409 | 409, count unchanged | PASS |
| C3 | Duplicate name case-variant of **soft-deleted** name → 409 (soft-deleted names still block) | 409 | 409 `{"client_name": ["A client with this name (case-insensitive) already exists."]}` | PASS |
| C4 | Missing `client_name` → 400 | 400 | 400 | PASS |
| C5 | Missing `client_spoc_email` → 400 | 400 | 400 | PASS |
| C6 | Invalid email → 400 | 400 | 400 | PASS |
| C7 | `client_industries` as string → 400 | 400 | 400 | PASS |
| C8 | `client_industries` with non-string member → 400 | 400 | 400 | PASS |
| C9 | `list_of_entities` as string → 400 | 400 | 400 | PASS |
| C10 | Invalid creates add no rows | 0 | 0 | PASS |
| C11 | Injected `client_id`/`is_active`/`created_at` ignored; row active with server timestamps | 201 + server-owned | 201, id≠999, active, created 2026 | PASS |
| C12 | Payload with only the 3 required keys (`client_short_name` omitted) → 201 (plan: optional) | 201 | **500 IntegrityError** `null value in column "client_short_name"` | **FAIL — DEFECT D1** |
| C13 | `client_industries: null` / `list_of_entities: null` → coerced to `[]` (plan §3.4) | 201 with `[]` | **400** `{"client_industries": ["This field may not be null."], "list_of_entities": ["This field may not be null."]}` | **FAIL — DEFECT D2** |
| C14 | `client_short_name: ""` explicitly → 201, DB `''` | 201 | 201, DB `''` | PASS |
| C15 | Omitting only `client_industries`/`list_of_entities` (short given) → 201, DB `[]` | 201 | 201, DB `[]`/`[]` | PASS |
| C16 | Whitespace stripped on name/spoc_name/email before storage | stripped | DB: `TEST-HOTEL Ltd`, `H S`, `h@hotel.test` | PASS |
| C17 | `client_name` > 255 chars → 400 (max_length) | 400 | 400 | PASS |
| C18 | Empty arrays `[]` explicitly → 201 | 201 | 201 | PASS |

### GET /clients/ (list)
| # | Check | Verdict |
|---|---|---|
| L1 | 200, active-only, newest-first (verified with 3 active + 1 soft-deleted) | PASS |
| L2 | Soft-deleted rows never appear; all-inactive table → 200 `[]` | PASS |

### GET /clients/{id}/ (retrieve)
| # | Check | Verdict |
|---|---|---|
| R1 | Active id → 200 with exactly 10 fields | PASS |
| R2 | Response JSON equals DB row (every field cross-checked via SQL) | PASS |
| R3 | Unknown id → 404 | PASS |
| R4 | Non-numeric id (`/clients/abc/`) → 404 (no 500) | PASS |

### PUT /clients/{id}/ (full update)
| # | Check | Verdict |
|---|---|---|
| U1 | Full payload → 200; DB row shows ALL changed values; `updated_at` > `created_at` and advanced vs prior | PASS |
| U2 | Missing `list_of_entities` → 400 + DB unchanged | PASS |
| U3 | Missing `client_short_name` → 400 `"This field is required on full update."` | PASS |
| U4 | Missing `client_industries` → 400 `"This field is required on full update."` | PASS |
| U5 | Rename to another client's name (exact) → 409 + DB unchanged | PASS |
| U6 | Rename to another client's name (case-variant) → 409 + DB unchanged | PASS |
| U7 | Rename to own name case-variant → 200 (self-exclusion) | PASS |
| U8 | Injected `client_id=999`/`is_active=false` ignored; row keeps own id, stays active | PASS |
| U9 | PUT on soft-deleted id → 404 | PASS |

### PATCH /clients/{id}/
| P1 | Valid JSON PATCH → 405 (method disabled) | PASS |

### DELETE /clients/{id}/ (soft delete)
| # | Check | Verdict |
|---|---|---|
| D1 | → 204 with empty body; DB row retained with `is_active=false`; `updated_at` refreshed | PASS |
| D2 | After delete: GET → 404, PUT → 404, excluded from list | PASS |
| D3 | Re-DELETE → 404; DELETE unknown id → 404 | PASS |

## Direct database verification (PostgreSQL `cnk`, read-only SQL)
| # | Check | Verdict |
|---|---|---|
| DB1 | Schema: `clients_client` with all 10 columns, correct types (bigint PK identity, varchar, **jsonb** ×2, boolean, timestamptz ×2), all NOT NULL | PASS |
| DB2 | `unique_client_name_ci` functional **unique index** on `lower(client_name)` exists (Django implements Meta UniqueConstraint(Func(F, LOWER)) as index; verified via `pg_indexes` + `sqlmigrate`) | PASS |
| DB3 | Migration recorded: `django_migrations` has `clients.0001_initial` | PASS |
| DB4 | Create persists every field incl. exact JSONB array order/content | PASS |
| DB5 | Omitted optionals persisted as defaults (`''`, `[]`) — except D1 case | PASS |
| DB6 | PUT changes persisted; `updated_at` advances | PASS |
| DB7 | Soft delete: row retained, `is_active=false`, `updated_at` refreshed via `.save()` | PASS |
| DB8 | Final reconcile: 11 TEST rows, 0 active; API list `[]` — API state == DB state | PASS |

## Logging (plan §4 item 19)
`src/document_generator/logs/app.log` contains for this session: `REQ` lines with method,
path, status, duration and **request bodies** (incl. for POST/PUT/DELETE), plus
`CLIENT_CREATED` / `CLIENT_UPDATED` / `CLIENT_DEACTIVATED` business events. PASS.

## DEFECTS FOUND (2 real, 1 test-only)

### D1 — HIGH: POST /clients/ without `client_short_name` → HTTP 500
- Observed twice (client ids 3 and 6 rolled back):
  `psycopg.errors.NotNullViolation: null value in column "client_short_name"` —
  DEBUG=True HTML error page, not JSON.
- Plan §3.4 says `client_short_name` is **optional on create**; expected 201 with `""`.
- Root cause: model column is NOT NULL (`blank=True` is validation-only, no DB effect) and
  the create serializer does not supply `""` when the key is absent.
- Suggested fix location (executor): `clients/serializers.py` — give the field a default of
  `""` (e.g. `extra_kwargs` or an explicit declared field). No API schema/migration change.

### D2 — LOW: JSON `null` for `client_industries`/`list_of_entities` → 400 instead of coercion
- Actual: 400 `"This field may not be null."` per field.
- Plan §3.4 rule 1 specifies `None` → `[]` coercion; project memory also claims coercion.
  Decision needed from planner/user: implement coercion (allow_null=True + validate returns
  `[]`) or amend the plan to "null rejected with 400" (current behavior is defensible).

### D3 — TEST-ONLY (previously known): `clients/tests.py:101` asserts hardcoded `client_id == 1`
- Unit suite: 19/20 (run earlier this session, 0.94s). Postgres sequences don't roll back
  between test methods. App behavior is correct; the assertion should be `!= 999`/positive int.

## Left-behind state (disclosed)
- `cnk.clients_client` holds 11 rows named `TEST-*`, all `is_active=false`
  (ids 1,2,4,5,7,8,9,10,11,12,13 — gaps 3 and 6 are rolled-back failed inserts; id gaps are
  normal PostgreSQL identity behavior). All were soft-deleted through the API. No user tables
  (`emd_data`, `sales_data`, `tickets`) were touched; no direct SQL writes performed.
- Test rows can be physically removed with:
  `DELETE FROM clients_client WHERE client_name LIKE 'TEST-%';` (user's call — left intact).

## Verdict
Every endpoint behaves per plan for valid data and documented error cases, with correct
PostgreSQL persistence — **except D1 (500 on omitted optional field)** and the D2
plan/implementation mismatch. Logging requirement satisfied.
