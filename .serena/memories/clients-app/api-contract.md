# clients app — API contract (implemented & smoke-tested 23/23)

Routes: `/clients/` and `/clients/{client_id}/` — **trailing slashes required** (SimpleRouter default).

| Method | Path | Success | Errors |
|---|---|---|---|
| POST | /clients/ | 201 + full JSON | 400 validation, 409 duplicate name |
| GET | /clients/ | 200 array, active only, newest first | — |
| GET | /clients/{id}/ | 200 + full JSON | 404 unknown OR inactive |
| PUT | /clients/{id}/ | 200 + full JSON | 400, 404, 409 |
| PATCH | /clients/{id}/ | — | **405 (intentionally disabled)** |
| DELETE | /clients/{id}/ | 204 empty body (soft delete) | 404 |

## Rules
- **PUT = full update, ALL business keys required.** Implemented with a separate `UpdateClientSerializer`; `ClientViewSet.get_serializer_class()` switches on `action == "update"`.
- **Active-only on every endpoint**: `get_queryset()` returns `Client.objects.filter(is_active=True)`, so an inactive id behaves like a nonexistent one (404) for read/update/delete alike.
- **Soft delete**: `destroy()` sets `is_active=False` then `save()` — must NOT use `QuerySet.update()` or `updated_at` won't refresh.
- **Case-insensitive duplicate name -> 409** via `clients/exceptions.py:Conflict(APIException)` with `status_code=409`; raised from serializer `validate()`. Check runs against ALL rows (soft-deleted names still block re-registration); update excludes own pk.
- `client_id` is `BigAutoField(primary_key=True)` — auto-generated, read-only. `is_active`, `created_at`, `updated_at` also read-only.
- `client_industries` and `list_of_entities` are `JSONField(default=list)` — must be arrays of strings. Explicit `null` IS accepted and coerced to `[]` (both serializers `allow_null` via `extra_kwargs`; `_validate_string_list` coerces `None → []`) — verified on create and PUT.

## Runtime-verified 2026-10-26 (live server + direct SQL on cnk) — defects
- ~~D1~~ **RESOLVED 2026-10-26**: `ClientSerializer` declares `client_short_name = CharField(required=False, allow_blank=True, default="")` — omitted key now stores `""`. Serializer-only, no migration.
- ~~D2~~ **RESOLVED 2026-10-26**: both serializers set `allow_null: True` via `extra_kwargs` for `client_industries`/`list_of_entities`; `_validate_string_list` coerces `None → []`. Works on create AND PUT.
- Everything else verified correct: 201/409(exact+case-variant, create AND update, self-excluded on update)/400/404(unknown+inactive+non-numeric)/405/204, active-only newest-first, PUT all-keys-required, soft delete + updated_at refresh, whitespace stripping (name/spoc/email), 256-char name → 400, empty lists OK, soft-deleted names still block re-registration. Full details: tests/session-20261026-104703/RESULTS.md

## Key files
- `clients/models.py` — Client model + `UniqueConstraint(Func(F("client_name"), function="LOWER"))`
- `clients/serializers.py` — `ClientSerializer` (create) + `UpdateClientSerializer` (PUT)
- `clients/views.py` — `ClientViewSet` (`http_method_names` excludes "patch")
- `clients/urls.py` — SimpleRouter, `basename="client"`
- `clients/exceptions.py` — `Conflict`
- `clients/tests.py` — 22-test suite (runnable; 21 pass, 1 test-only failure, see `mem:clients-app/environment`)