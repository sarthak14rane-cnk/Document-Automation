# Clients App — Complete CRUD API (PostgreSQL, Loguru)

## 1. Objective

Build full CRUD API endpoints for registering and managing clients in the existing `clients` Django app:

- A `clients` database table in **PostgreSQL** storing registered client data (name, short name, industries, SPOC details, entities, timestamps).
- Five JSON endpoints: create (with duplicate-name check), read-all (active clients), read-one by `client_id`, full update, and soft delete (`is_active` disabled).
- **All endpoints operate on active clients only** — an inactive `client_id` yields 404 for reads, updates, and deletes alike.
- A **single update verb** (`PUT`): the caller sends **all** keys (changed or not); the row is overwritten accordingly. `PATCH` is explicitly disabled.
- **Loguru-based operation logging**: a request/response middleware writing method, path, status, duration, and request bodies to one rotated log file (`logs/app.log`).

Decisions confirmed with the user (cumulative):
- **Framework:** Django REST Framework (new dependency).
- **`client_id`:** auto-generated primary key (users never send it on create).
- **Read-all:** simple list of active clients, no filters/pagination this iteration.
- **Duplicate check:** case-insensitive (`"Acme Ltd"` conflicts with `"ACME LTD"`).
- **Update semantics:** `PUT` = full payload update only; `PATCH` not supported.
- **Database:** PostgreSQL, credentials read from `src/document_generator/.env` via `python-dotenv` + `os.getenv` (user creates the `.env`; executor creates a `.env.example` template).
- **Logging:** loguru (already a dependency) file sink with size-based rotation; **request bodies are logged** (user's explicit choice — includes PII, see Security).

## 2. Context

Repo layout relevant to this task (all paths relative to repo root):

- Django project lives in `src/document_generator/`; settings module `backend.settings` (see `src/document_generator/manage.py` line 9). `BASE_DIR` (settings.py line 16) = `src/document_generator`.
- `src/document_generator/backend/settings.py` — currently SQLite (`db.sqlite3`), `INSTALLED_APPS` already contains `'clients'` and `'template_master'`; the `MIDDLEWARE` list is the standard 9-entry default; no `REST_FRAMEWORK` settings block; no dotenv/loguru wiring yet.
- `src/document_generator/backend/urls.py` — only `admin/` is wired; no `include()` yet.
- `src/document_generator/clients/` — created via `startapp`; `models.py`, `views.py`, `admin.py`, `tests.py` are defaults/empty; `urls.py` does not exist yet.
- `template_master` app exists but is **out of scope** for this plan.
- `pyproject.toml` — deps currently only `django>=6.1.2` and `loguru>=0.7.3`; managed with `uv` (`uv.lock` present, `.venv` = Python 3.12.13 + Django 6.1.2).
- Field-name note: the user wrote `client_industires` (typo); the model/API uses `client_industries`. Flagged before; user has not objected.

Confirmed facts
- `INSTALLED_APPS` already includes `'clients'` (done in previous session).
- `loguru` is already installed as a project dependency.
- The user will create `src/document_generator/.env` themselves containing DB credentials; settings must load it with `python-dotenv` + `os.getenv` (user-specified mechanism).

Doc research used (Context7 MCP — DRF, Django, Loguru), which informs the How below:
- DRF `ModelViewSet` provides `list/create/retrieve/update/partial_update/destroy`; `SimpleRouter` maps `GET|POST /clients/` and `GET|PUT|PATCH|DELETE /clients/{lookup}/` by default; trailing slashes kept.
- `serializer.is_valid(raise_exception=True)` → automatic HTTP 400 with field errors.
- Django base `View.http_method_names` allows disabling verbs (e.g. `'patch'`) — the standard way to remove a router-provided route's handler.
- Django `JSONField` is supported natively on PostgreSQL (no extension caveats, unlike SQLite).
- `DateTimeField(auto_now_add=True)` / (`auto_now=True`) cover `created_at`/`updated_at`; `auto_now` fires on `Model.save()`, **not** on `QuerySet.update()` (so soft delete must save the instance).
- Loguru `logger.add(sink, rotation=..., retention=..., catch=..., diagnose=...)`: string sizes like `"10 MB"` for rotation, human-friendly retention strings like `"4 weeks"`; `catch=True` prevents sink errors from propagating; `diagnose=False` recommended outside debugging (per docs guidance, to avoid variable-value leakage).

Assumptions
- No authentication on these endpoints this iteration (internal tool); `AllowAny` set explicitly so intent is visible, revisit later.
- `is_active` remains **app-managed** (not writable via API): created active; DELETE sets it false; reactivation-out-of-band only.
- A soft-deleted client's name still blocks re-registration (duplicate check runs against all rows, not just active ones).
- DELETE is idempotent-plus-404: deleting an already-inactive/unknown id returns 404 (consistent with the active-only rule).
- Loguru creates missing parent directories for the file sink; if the executor's environment doesn't, create `logs/` manually.
- Status code for "exists but inactive" is uniformly **404**, across every endpoint.

Blockers / dependencies (user-dependent, required before any runnable state)
1. `djangorestframework`, `psycopg[binary]`, `python-dotenv` are not installed yet (planned step 3.1).
2. **PostgreSQL server** must be reachable with credentials matching the `.env`.
3. **The target database must already exist** (`CREATE DATABASE document_generator;` or equivalent) — Django creates tables, not databases; `migrate` will fail without it.
4. The DB user in `.env` needs `CREATEDB` privilege for `manage.py test` (Django's test runner creates a `test_document_generator` database).
5. The user-created `.env` must exist at `src/document_generator/.env` before startinganything that touches the DB.

## 3. What / Why / How to Build

### 3.1 Dependencies: install DRF, psycopg, python-dotenv

- **What:** Add three dependencies.
- **Why:** DRF chosen by user; PostgreSQL driver required for the new DB backend (psycopg 3 is the current-generation driver and is preferred for modern Django releases over psycopg2); `python-dotenv` is the user-specified mechanism for reading `.env`.
- **How:** From repo root: `uv add djangorestframework "psycopg[binary]" python-dotenv` (updates `pyproject.toml` + `uv.lock`, syncs `.venv`).

### 3.2 Settings changes — `backend/settings.py`

- **What:** Five additions to `src/document_generator/backend/settings.py`.
- **Why:** Wire DRF, swap SQLite → PostgreSQL driven by `.env`, enable the loguru middleware, and initialize the file sink early.
- **How:**

```python
# 1) top of file, after BASE_DIR
from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')           # anchors to the .env the user creates
import os                                 # (os only needed if using getenv below)

# 2) INSTALLED_APPS — append
'rest_framework',

# 3) MIDDLEWARE — insert after CommonMiddleware (before auth/csrf is fine too)
'backend.middleware.loguru_request_logger',

# 4) Database — replace the SQLite block
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'document_generator'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# 5) near the top after load_dotenv()
from backend.logging_setup import setup_logging
setup_logging()                           # installs the rotated file sink once, early
```

Required `.env` keys (user-owned file; executor creates `.env.example` only):
```
DB_NAME=document_generator
DB_USER=postgres
DB_PASSWORD=<secret>
DB_HOST=localhost
DB_PORT=5432
```

### 3.3 Model — `Client` (unchanged by this revision)

- **What:** Create `Client` model in `src/document_generator/clients/models.py`.
- **Why:** The `clients` table the CRUD operates on.
- **How:**

```python
class Client(models.Model):
    client_id = models.BigAutoField(primary_key=True)          # auto-generated int PK, exposed as client_id
    client_name = models.CharField(max_length=255)
    client_short_name = models.CharField(max_length=100, blank=True)
    client_industries = models.JSONField(default=list, blank=True)  # list of text
    client_spoc_name = models.CharField(max_length=255)
    client_spoc_email = models.EmailField(max_length=254)
    list_of_entities = models.JSONField(default=list, blank=True)   # list of text
    is_active = models.BooleanField(default=True)              # app-managed, not directly writable
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)           # refreshed on every .save()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("client_name"), name="unique_client_name_ci"
            ),
        ]
        ordering = ["-created_at"]
```

- PostgreSQL supports functional/expression indexes natively, so the case-insensitive `Lower(...)` constraint is safe here (the SQLite verification caveat from the earlier revision is dropped).

### 3.4 Serializers — `ClientSerializer` (create) + `UpdateClientSerializer` (full update)

- **What:** Create `src/document_generator/clients/serializers.py`.
- **Why:** JSON validation, list-shape rules, and the case-insensitive duplicate-name business rule; the **two serializers encode the create-vs-update requiredness difference** (update = every key mandatory).
- **How:** Two `ModelSerializer` classes over the same model with `fields` covering `client_name, client_short_name, client_industries, client_spoc_name, client_spoc_email, list_of_entities` (both always include the read-only `client_id, is_active, created_at, updated_at` in output).

Shared rules (both serializers):
1. `validate_client_industries` / `validate_list_of_entities`: JSON list of strings; coerce `None`→`[]`; reject non-list or non-string members with a 400 field error.
2. Whitespace-strip `client_name`, `client_short_name`, `client_spoc_name`, `client_spoc_email`.
3. Read-only output fields: `client_id`, `is_active`, `created_at`, `updated_at`.
4. Uniqueness in `validate()`:
   - On **create** (`self.instance is None`): if `Client.objects.filter(client_name__iexact=candidate).exists()` → raise `Conflict` (§3.6).
   - On **update**: same query but `.exclude(pk=self.instance.pk)`.

Differences:
| | `ClientSerializer` (create) | `UpdateClientSerializer` (PUT) |
| --- | --- | --- |
| `client_name`, `client_spoc_name`, `client_spoc_email` | required | required |
| `client_short_name` | optional (`allow_blank=True`) | **required, `allow_blank=True`** (key must be sent, value may be empty) |
| `client_industries`, `list_of_entities` | optional, default `[]` | **required** (key must be sent; may be `[]`) |

### 3.5 View layer — `ClientViewSet`

- **What:** Create `src/document_generator/clients/views.py` with a `ModelViewSet`.
- **Why:** All five operations from one class; overrides only where the user's requirements diverge from defaults.
- **How:**

```python
from loguru import logger

class ClientViewSet(viewsets.ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [AllowAny]           # explicit this iteration (see Security)
    http_method_names = ["get", "post", "put", "delete"]   # NO 'patch' — user requirement
    lookup_field = "client_id"
    lookup_value_regex = r"[0-9]+"            # non-numeric ids → 404, not ValueError/500

    def get_queryset(self):
        # ACTIVE-ONLY precheck for every action (list/retrieve/update/destroy):
        # inactive or unknown ids fall through to 404.
        return Client.objects.filter(is_active=True)

    def get_serializer_class(self):
        # PUT must receive ALL keys; create keeps optional fields optional.
        return UpdateClientSerializer if self.action == "update" else ClientSerializer

    def perform_create(self, serializer):
        client = serializer.save()
        logger.info("CLIENT_CREATED client_id={} name={}", client.client_id, client.client_name)

    def perform_update(self, serializer):
        client = serializer.save()
        logger.info("CLIENT_UPDATED client_id={}", client.client_id)

    def destroy(self, request, *args, **kwargs):
        client = self.get_object()             # 404 if missing OR inactive
        client.is_active = False
        client.save()                          # auto_now refreshes updated_at
        logger.info("CLIENT_DEACTIVATED client_id={}", client.client_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
```

Behavior matrix:

| Endpoint | Effect |
| --- | --- |
| `POST /clients/` | Create active row; serializer dup-check → 409 possible |
| `GET /clients/` | All **active** clients, `-created_at` order (Meta.ordering) |
| `GET /clients/{id}/` | Active client details; inactive or unknown → 404 |
| `PUT /clients/{id}/` | **Full update, all keys required**; inactive or unknown → 404; dup-check excludes self |
| `DELETE /clients/{client_id}/` | Soft delete: `is_active=False` + `save()`; `204` empty body |

- Soft delete must never run inside `queryset.update()` — `auto_now` does not fire there (Django docs).

### 3.6 Duplicate-name conflict semantics (409)

- **What:** Duplicate create/update attempts return **409 Conflict**, not DRF's default 400.
- **Why:** The user asked for an explicit existence check; 409 communicates "resource exists" versus "payload invalid".
- **How:** Create `src/document_generator/clients/exceptions.py`:

```python
from rest_framework.exceptions import APIException

class Conflict(APIException):
    status_code = 409
    default_detail = "Client with the given name already exists."
    default_code = "client_name_conflict"
```

Raise `Conflict({"client_name": "A client with this name (case-insensitive) already exists."})` from the serializers' `validate()`. DRF's default exception handler respects `status_code`.

### 3.7 URLs

- **What:** Create `src/document_generator/clients/urls.py`; modify `src/document_generator/backend/urls.py`.
- **Why:** Wire the viewset with DRF SimpleRouter conventions (trailing slashes — matches `admin/` style).
- **How:**

```python
# clients/urls.py
from rest_framework.routers import SimpleRouter
from .views import ClientViewSet

router = SimpleRouter()
router.register("", ClientViewSet, basename="client")
urlpatterns = router.urls
```

```python
# backend/urls.py — add
from django.urls import include, path
urlpatterns += [path("clients/", include("clients.urls"))]
```

Routes produced (`patch` removed via `http_method_names`):
- `GET | POST /clients/` → `client-list`
- `GET | PUT | DELETE /clients/{client_id}/` → `client-detail` (`PATCH → 405`)

### 3.8 Admin registration (convenience, unchanged)

- **What:** Register `Client` in `src/document_generator/clients/admin.py`.
- **Why:** Cheap inspection aid; admin already enabled.
- **How:** `@admin.register(Client)`; `list_display = ("client_name", "client_short_name", "client_spoc_name", "client_spoc_email", "is_active", "created_at", "updated_at")`; `list_filter = ("is_active",)`; `search_fields = ("client_name", "client_short_name")`; `readonly_fields = ("created_at", "updated_at")`.

### 3.9 Migrations + PostgreSQL database

- **What:** Generate and apply the app's first migration **against PostgreSQL**.
- **Why:** Persist the `clients` table in the new backend.
- **Preconditions (user side):** `.env` present with valid DB_* values; PostgreSQL reachable; database exists (`CREATE DATABASE document_generator;`).
- **How:** From `src/document_generator/`:
  1. `uv run python manage.py check` (settings/Django sanity first)
  2. `uv run python manage.py makemigrations clients` → `clients/migrations/0001_initial.py` (name auto-assigned)
  3. `uv run python manage.py migrate` (creates tables in PostgreSQL)
- `db.sqlite3` becomes unused after this change (left on disk; untracked artifact — optional cleanup not in scope).

### 3.10 Loguru operation logging (middleware + setup)

- **What:** Two new project-level modules plus one middleware entry.
- **Why:** The user wants a single rotated log file capturing **all operations performed**, including request bodies.
- **How:**

`src/document_generator/backend/logging_setup.py` (create):
```python
from loguru import logger
from pathlib import Path

def setup_logging() -> None:
    """Install the rotated file sink exactly once."""
    log_path = Path(__file__).resolve().parent.parent / "logs" / "app.log"
    logger.add(
        str(log_path),
        level="INFO",
        rotation="10 MB",      # cut into timestamped archives when reached
        retention="4 weeks",   # per confirmed policy
        diagnose=False,        # don't leak variable values into traces
        catch=True,            # sink failures never break request handling
    )
```
- File is anchored at `BASE_DIR / logs / app.log` (independent of cwd). No console-sink changes (loguru's default stderr sink stays).

`src/document_generator/backend/middleware.py` (create):
```python
import time
from loguru import logger

class LoguruRequestLoggerMiddleware:
    def __init__(self, get_response): self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - started) * 1000
        body = getattr(request, "body", b"") or b""     # request bodies INCLUDED per user choice
        logger.info("REQ {} {} -> {} ({:.1f} ms) body={}",
                    request.method, request.get_full_path(), response.status_code,
                    duration_ms, body.decode("utf-8", errors="replace")[:2000])
        return response
```
- Facts: reading `request.body` in middleware is safe (Django caches it; DRF's parser reuses the cached value); truncated at 2000 chars so oversized payloads can't bloat the file; GET requests have empty bodies and log without one.
- Unexpected 5xx: DRF's exception handler produces a 500 response which this middleware logs like any other — an `ERROR`-level traceback line is added by logging inside the view dispatch? **No** — keep it simple: the middleware line with `status 500` plus DRF/Python's own error output on stderr is sufficient this iteration; a dedicated traceback sink is listed as a non-goal.
- Registration: `settings.MIDDLEWARE` gets `'backend.middleware.loguru_request_logger'` (class named `LoguruRequestLoggerMiddleware`); position after `CommonMiddleware`.

### 3.11 Tests

- **What:** Replace the stub in `src/document_generator/clients/tests.py` with API tests using DRF's `APIClient` (named routes via `reverse()`).
- **Why:** Lock in every documented behavior — now PostgreSQL-backed, PUT-only, active-only.
- **CRITICAL implementation note:** `manage.py test` runs against a scratch `test_document_generator` database it creates and drops itself (the dev DB is never touched); the `.env` DB user needs `CREATEDB` rights.

CRUD matrix (see Testing strategy §4 for the full list of assertions).

## 4. Technical Specification

### Architecture changes
- New DRF REST layer over PostgreSQL for the `clients` app; loguru middleware module at project level. Nothing else changes (`template_master`, existing auth/admin defaults untouched).

### Data flow
- `HTTP request → LoguruRequestLoggerMiddleware (logs method/path/status/duration/body) → URL router → ClientViewSet → ClientSerializer/UpdateClientSerializer (validate + case-insensitive dup check) → PostgreSQL`.
- All writes go through `Model.save()` (so `auto_now` refreshes `updated_at`); soft delete = field flip + save, never `QuerySet.update()`.

### API changes (new surface)

| Method | URL | Success | Errors |
| --- | --- | --- | --- |
| `POST /clients/` | Create | `201` + full JSON of created client | `400`, `409` (name exists, case-insensitive) |
| `GET /clients/` | List | `200` JSON array (active only, newest first) | — |
| `GET /clients/{client_id}/` | Retrieve | `200` + full JSON | `404` (unknown **or** inactive) |
| `PUT /clients/{client_id}/` | **Full update — ALL keys required** | `200` + full JSON | `400` (validation — includes missing keys), `404`, `409` |
| `PATCH /clients/{client_id}/` | — | **`405`** (method removed) | — |
| `DELETE /clients/{client_id}/` | Soft delete | `204`, empty body | `404` |

Create payload:
```json
{
  "client_name": "Acme Ltd",                     // required
  "client_short_name": "Acme",                   // optional
  "client_industries": ["Manufacturing", "FMCG"], // optional list[str]
  "client_spoc_name": "Priya Sharma",            // required
  "client_spoc_email": "priya@acme.com",         // required, valid email
  "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"]
}
```
Update (PUT) payload — **every key, always**:
```json
{
  "client_name": "Acme Ltd",
  "client_short_name": "Acme Corp",
  "client_industries": ["Manufacturing"],
  "client_spoc_name": "Priya Sharma",
  "client_spoc_email": "priya@acme.com",
  "list_of_entities": ["Acme Pvt Ltd", "Acme LLP"]
}
```
Responses always also include `client_id`, `is_active`, `created_at`, `updated_at` (ISO-8601). Error shape is DRF-default: `{"field": ["msg"]}` for 400; `{"detail": "..."}` for 404/405/409.

### Database/schema changes
- New table `clients_client` in PostgreSQL with columns §3.3 (JSON list columns native on PG). One migration under `clients/migrations/`.
- **Environment/config prerequisite:** user-provided `.env` + existing PostgreSQL database + account with table-creation rights; test runs additionally need `CREATEDB`.

### Backend changes
Files enumerated in the Change Template: `clients/*` (model/serializers/exceptions/views/urls/admin/tests/migration) plus `backend/settings.py`, `backend/urls.py`, `backend/middleware.py`, `backend/logging_setup.py`.

### Frontend changes
`Not applicable.` (JSON-only API this iteration.)

### Configuration changes
- `settings.py`: `rest_framework` app; `MIDDLEWARE` += loguru middleware; `DATABASES` → `django.db.backends.postgresql` with `os.getenv` values; `load_dotenv(BASE_DIR / '.env')`; `setup_logging()` call.
- `.env.example` created as the template; the real `.env` is user-owned and never committed.

### Security considerations
- **No authentication this iteration** (explicit `AllowAny`); authorization work deferred — endpoints are public on the dev server.
- **`.env` holds DB credentials:** must be git-ignored before first commit (`src/document_generator/.env`, `.env.example` is the only committable template). This is a hard requirement of this revision.
- **PII in logs (user-approved):** request bodies include SPOC names/emails; `client_industries`/entity names — written to `logs/app.log` and its rotated archives. Mitigations in place: `logs/` git-ignored, `diagnose=False` (no variable values inside printed web framework internals), bodies truncated to 2000 chars. Flagged so it's a conscious retention policy.
- CSRF middleware unchanged; DRF `SessionAuthentication` would enforce CSRF tokens for session-authenticated callers — anonymous POSTs are unaffected in the current unauthenticated configuration.
- Parameterized ORM everywhere; no raw SQL → no injection surface.
- Soft-deleted rows retain PII in PostgreSQL (acceptable for now; note for future retention policy).

### Error handling
Via DRF's default exception handler, plus middleware logging on top:
- `400` invalid payload (per-field messages from `is_valid(raise_exception=True)`, including "missing key" errors on PUT)
- `404` unknown or **inactive** id (queryset filter) and non-numeric id (via `lookup_value_regex`)
- `405` for `PATCH` (removed verb)
- `409` duplicate name (`Conflict`)
- Request/response logging continues even when a body is absent or un-decodable (`errors="replace"`); middleware wraps logging in try/except semantics only implicitly — DRF returns 500 responses which the middleware still logs (status included).

### Validation
- `client_name`/`client_spoc_name` non-blank; `client_spoc_email` valid format; `client_industries`/`list_of_entities` JSON arrays of strings (empty OK); `client_short_name` blank-OK but **the key must be present on PUT**; read-only server-owned fields (`client_id`, `is_active`, `created_at`, `updated_at`) ignored if sent.
- Cross-field: case-insensitive name uniqueness on create and update (self-excluded on update).

### Performance considerations
- Volume tiny; the only repeated indexed-ish scan is the `iexact` duplicate check — irrelevant at this scale, revisit before pagination/search ever lands.
- Loguru rotation bounds `logs/app.log` growth to ~10 MB per generation, retention prunes archives weekly (docs-envisioned behaviors §3.10).

### Compatibility considerations
- psycopg 3 + Django 6.1 on Python 3.12: supported pairing; `manage.py check` after the settings swap is the cheap early verification.
- DRF and Django versions selected by `uv add` will be current; no `asgiref`/`channels` involved (WSGI dev server).
- Loguru already a dependency; no version bump expected.

### Testing strategy

`src/document_generator/clients/tests.py` — DRF `APIClient` tests runner `uv run python manage.py test clients` (needs PG `CREATEDB` rights):

Create (POST /clients/)
1. Valid payload → `201`; body uses `client_id` (not `id`); `is_active == True`; `created_at`/`updated_at` set.
2. Duplicate name (exact) → `409`; different case (`"ACME LTD"` vs `"acme ltd"`) → `409`.
3. Missing `client_name` / `client_spoc_email` → `400` with field errors.
4. Invalid `client_spoc_email` → `400`.
5. `client_industries` as string (not list) → `400`; list with non-string member → `400`; empty list → OK.
6. Sent `client_id`/`is_active`/`created_at`/`updated_at` are ignored (read-only; row created active, server timestamps).

Read (GET)
7. After creating 2 and soft-deleting 1: `GET /clients/` returns only the active one, newest first.
8. `GET /clients/{id}/` for active id → `200` with all 10 fields.
9. Inactive id → `404`; unknown id → `404`; non-numeric (`/clients/abc/`) → `404`.

Update (PUT /clients/{client_id}/)
10. Full payload with one changed field → `200`; response row updated; `updated_at` > `created_at`.
11. **Missing any one key (e.g., omit `list_of_entities`) → `400`** ("send all keys" contract).
12. Rename to a name owned by another client (case-variant) → `409`; rename to own current name case-variant → `200` (self-exclusion).
13. Update an **inactive** client (whatever payload) → `404` (active-only precheck).
14. `PATCH /clients/{id}/` (even with valid full JSON) → `405`.
15. PUT payload containing `is_active`/`client_id` → ignored (read-only).

Delete (DELETE /clients/{client_id}/)
16. → `204` empty body; row still exists with `is_active=False` (ORM assertion).
17. Then: excluded from list; retrieve → `404`; **update** → `404`.
18. Second `DELETE` on same id → `404`; unknown id delete → `404`.

Logging (manual, not unit-asserted to stay non-brittle)
19. After `runserver` smoke tests (one request per endpoint, POST incl. body): confirm `logs/app.log` exists at `src/document_generator/logs/app.log`, contains REQ lines (method/path/status/duration/body for POST) and `CLIENT_CREATED/UPDATED/DEACTIVATED` lines; trigger a validation error (400) once and confirm it logged; leave a >10MB run only as an optional rotation sanity test (skip by default).

Database (manual)
20. After migrate: psql (or any PG client) `\dt` shows `clients_client`; a registered client via POST is SELECT-able from PostgreSQL; `db.sqlite3` is no longer touched by migrations.

### Deployment considerations
- Dev-only: `uv run` invocations; PostgreSQL reachable from `.env`; `logs/` auto-created on first log line (fallback: mkdir). No production hardening in scope.

## 5. Change Template

| File | Change Type | Proposed Change | Reason |
| :--- | :--- | :--- | :--- |
| `pyproject.toml` | Modify | Add `djangorestframework`, `psycopg[binary]`, `python-dotenv` (`uv add` — executor-run) | DRF framework, PostgreSQL driver, `.env` loading per user |
| `uv.lock` | Modify | Regenerated automatically by `uv add` | Lockfile consistency |
| `src/document_generator/backend/settings.py` | Modify | `load_dotenv` + `setup_logging()` at top; INSTALLED_APPS += `rest_framework`; MIDDLEWARE += `backend.middleware.loguru_request_logger`; `DATABASES` → PostgreSQL via `os.getenv(DB_*)` | §3.2 |
| `src/document_generator/backend/logging_setup.py` | Create | `setup_logging()` — rotated file sink (`logs/app.log`, `rotation="10 MB"`, `retention="4 weeks"`, `catch=True`, `diagnose=False`) | §3.10 |
| `src/document_generator/backend/middleware.py` | Create | `LoguruRequestLoggerMiddleware` — logs method/path/status/duration/request body (truncated) | §3.10 |
| `src/document_generator/backend/urls.py` | Modify | `path("clients/", include("clients.urls"))` | Expose CRUD routes |
| `src/document_generator/clients/models.py` | Modify | Add `Client` model per §3.3 (fields, case-insensitive unique constraint, ordering) | The `clients` table |
| `src/document_generator/clients/serializers.py` | Create | `ClientSerializer` (create) + `UpdateClientSerializer` (PUT, all keys required); shared list/strip validation + dup-name check | §3.4 |
| `src/document_generator/clients/exceptions.py` | Create | `Conflict(APIException)` with `status_code=409` | §3.6 |
| `src/document_generator/clients/views.py` | Modify | `ClientViewSet` per §3.5 (active-only queryset, PUT-only verbs, loguru INFO events, soft-delete `destroy`) | Endpoint behavior |
| `src/document_generator/clients/urls.py` | Create | `SimpleRouter` registration per §3.7 (`basename="client"`) | Route the viewset |
| `src/document_generator/clients/admin.py` | Modify | Register `Client` with list/filter/search/readonly per §3.8 | Inspection convenience |
| `src/document_generator/clients/migrations/0001_initial.py` | Create | Generated by `manage.py makemigrations clients` (name auto-assigned); applied by `migrate` into PostgreSQL | Schema creation |
| `src/document_generator/clients/tests.py` | Modify | Replace stub with the §4 Testing-strategy matrix | Lock in documented behavior |
| `src/document_generator/.env.example` | Create | Placeholder keys `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT` (no real secrets) | Template for the user's `.env` |
| `.gitignore` | Modify | Add entries: `src/document_generator/.env`, `logs/`, `db.sqlite3` | Secrets/artifacts must not be committed |

**Explicitly out of scope:** `src/document_generator/template_master/*`, any HTML/UI, authentication/authorization work, pagination/search filters, traceback sink for 5xx (documented non-goal), deleting `db.sqlite3`.

## 6. To-Do Matrix

| File / Change | Proposed Action | Executed | Tested | Deployed |
| :--- | :--- | :---: | :---: | :---: |
| `pyproject.toml` | `uv add djangorestframework "psycopg[binary]" python-dotenv` | [x] | [x] | [ ] |
| `uv.lock` | Regenerated by `uv add` | [x] | [x] | [ ] |
| `src/document_generator/backend/settings.py` | Apply §3.2 changes (dotenv, logging setup, INSTALLED_APPS, MIDDLEWARE, DATABASES) | [x] | [x] | [ ] |
| `src/document_generator/backend/logging_setup.py` | Create file-sink setup | [x] | [x] | [ ] |
| `src/document_generator/backend/middleware.py` | Create `LoguruRequestLoggerMiddleware` | [x] | [x] | [ ] |
| `src/document_generator/backend/urls.py` | Include `clients.urls` at `clients/` | [x] | [x] | [ ] |
| `src/document_generator/clients/models.py` | Add `Client` model per §3.3 | [x] | [x] | [ ] |
| `src/document_generator/clients/serializers.py` | Create both serializers per §3.4 | [x] | [x] | [ ] |
| `src/document_generator/clients/exceptions.py` | Create `Conflict` per §3.6 | [x] | [x] | [ ] |
| `src/document_generator/clients/views.py` | Add `ClientViewSet` per §3.5 | [x] | [x] | [ ] |
| `src/document_generator/clients/urls.py` | Create router config per §3.7 | [x] | [x] | [ ] |
| `src/document_generator/clients/admin.py` | Register `Client` per §3.8 | [x] | [ ] | [ ] |
| `src/document_generator/clients/migrations/0001_initial.py` | `makemigrations clients` + `migrate` per §3.9 | [x] | [x] | [ ] |
| `src/document_generator/clients/tests.py` | Write §4 test matrix | [x] | [ ] | [ ] |
| `src/document_generator/.env.example` | Create placeholder template | [x] | [ ] | [ ] |
| `.gitignore` | Add `.env`, `logs/`, `db.sqlite3` entries | [x] | [ ] | [ ] |

**Validation note (post-execution):** End-to-end smoke test against a live dev server passed **23/23 checks** covering every endpoint behavior in §4 (status codes 200/201/204/400/404/405/409, active-only filtering, PUT all-keys-required, case-insensitive dup, soft delete + `is_active=false` in DB, read-only field ignoring). Operation logging verified: `logs/app.log` recorded `REQ` lines with bodies and `CLIENT_CREATED/UPDATED/DEACTIVATED` events.

Two post-execution fixes applied during validation:
1. **Middleware path** — `settings.MIDDLEWARE` referenced `backend.middleware.loguru_request_logger` but the class is `LoguruRequestLoggerMiddleware`; corrected to the `module.ClassName` form (WSGI load previously failed with `ImproperlyConfigured`).
2. **DB host stall** — `POSTGRES_HOST=localhost` resolved to IPv6 `::1` first while Postgres listens only on IPv4 `127.0.0.1:2478`, making each request take ~130s. Normalised host to `127.0.0.1` in settings and added `connect_timeout: 5`. Requests now complete in 70–240ms.

Still outstanding: `manage.py test clients` (the 20-test unit suite) remains blocked on `doc_user` lacking `CREATEDB` — needs `ALTER ROLE doc_user CREATEDB;` run by a PostgreSQL superuser.

**Defect-fix record (2026-10-26, testing session `tests/session-20261026-104703/`):**
- Unit suite now RUNS (CREATEDB resolved; runs against scratch `test_cnk`). Current: 22 tests, 21 pass, 1 fail — the fail is `test_create_readonly_fields_ignored` asserting a hardcoded `client_id == 1` (Postgres sequences don't roll back between test methods; app behavior correct; assertion should be `!= 999`).
- **D1 FIXED** (was: POST without `client_short_name` → 500 IntegrityError): `ClientSerializer` now declares `client_short_name = CharField(required=False, allow_blank=True, default="")` — serializer-only, no migration (`makemigrations --check` clean). Regression test added.
- **D2 FIXED** (was: `null` for `client_industries`/`list_of_entities` → 400 instead of plan §3.4 `None → []` coercion): both serializers now set `allow_null: True` via `extra_kwargs`; the pre-existing `_validate_string_list` then coerces `None → []`. Regression tests added.
- Live re-verification (exact original defect payloads + DB row checks on `cnk`): all PASS; PUT key-presence (400) and non-string-member (400) guards unaffected. Details + scripts in `tests/session-20261026-104703/RESULTS.md`.

## 7. Sources

Repository evidence:
- `pyproject.toml` (deps + `uv` tooling)
- `src/document_generator/manage.py`, `backend/settings.py`, `backend/urls.py`
- `src/document_generator/clients/*` (startapp stubs; `models.py` confirmed empty)
- `src/document_generator/template_master/apps.py` (existence check; out of scope)

External documentation via Context7 MCP:
- Django REST Framework — serializers validation, `raise_exception=True`, partial updates & `self.instance`: https://www.django-rest-framework.org/api-guide/serializers/
- Django REST Framework — `ModelViewSet` actions: https://www.django-rest-framework.org/api-guide/viewsets/
- Django REST Framework — `SimpleRouter` URL patterns: https://www.django-rest-framework.org/api-guide/routers/
- Django REST Framework — exceptions/exception handler: https://www.django-rest-framework.org/api-guide/exceptions/
- Django 6.1 model field reference — `JSONField` on all backends (PostgreSQL native), `DateField.auto_now`/`auto_now_add` (incl. "not updated by `QuerySet.update()`"), unique constraints: https://docs.djangoproject.com/en/6.1/ref/models/fields/
- Django 6.1 model field reference — `save(update_fields=...)`: https://docs.djangoproject.com/en/6.1/ref/models/instances/
- Django 3.1 release notes — `models.JSONField` for all supported backends: https://docs.djangoproject.com/en/6.1/releases/3.1/
- Loguru — `logger.add()` file-sink config (`rotation`/`retention`/`compression`/`diagnose`/`catch`): https://loguru.readthedocs.io/en/stable/api/logger.html
- Loguru — overview (rotation examples by size/time, retention and compression): https://loguru.readthedocs.io/en/stable/overview.html

## 8. Summary

**What gets built:** A DRF-backed CRUD API over a new PostgreSQL `clients` table — auto `client_id` PK, case-insensitive duplicate-name protection (409), **PUT-only full updates (all keys required, PATCH disabled)**, **active-only enforcement on every endpoint**, soft delete via `is_active`, loguru request-log middleware (bodies included; bodies truncated to 2000 chars) writing to one rotated log file with self-anchored path and PII caveats, plus 18+ tests covering all those behaviors and 2 manual checks (log file + PostgreSQL data).

**End state:** `POST/GET /clients/` and `GET/PUT/DELETE /clients/{client_id}/` fully working on the local dev server against PostgreSQL, credentials read from `src/document_generator/.env` (git-ignored), every request/operation visible in `logs/app.log`, app registered in admin, test suite runnable via `manage.py test clients`.

**Major dependencies / blockers:**
1. Three new packages installed via `uv add` — first step.
2. **`src/document_generator/.env`** must exist with valid DB_* values — user-owned (only `.env.example` is ours).
3. PostgreSQL must be reachable and the database must already exist before `migrate` (Django creates tables, not databases); test runs need `CREATEDB` rights.
4. If `Lower(...)` functional unique constraint is rejected by the migration engine in some edge case, fallback = `unique=True` + the authoritative serializer `iexact` check (details §3.3). (Low risk on PostgreSQL.)

**Major risks:** none blocking. No authentication by design this iteration; PII lands in the log file by user choice (rotation + git-ignore used as the guardrails); duplicate-check race under high concurrency — acceptable internal-tool tradeoff, residual DB constraint is the safety net.

**Planned next after this:** wiring `template_master` (its own plan), then an auth/hardening pass over both apps.
