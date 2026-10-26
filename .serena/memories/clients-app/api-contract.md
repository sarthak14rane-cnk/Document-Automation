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
- `client_industries` and `list_of_entities` are `JSONField(default=list)` — must be arrays of strings; `None` coerced to `[]`.

## Key files
- `clients/models.py` — Client model + `UniqueConstraint(Func(F("client_name"), function="LOWER"))`
- `clients/serializers.py` — `ClientSerializer` (create) + `UpdateClientSerializer` (PUT)
- `clients/views.py` — `ClientViewSet` (`http_method_names` excludes "patch")
- `clients/urls.py` — SimpleRouter, `basename="client"`
- `clients/exceptions.py` — `Conflict`
- `clients/tests.py` — 20-test suite (not yet runnable, see `mem:clients-app/environment`)