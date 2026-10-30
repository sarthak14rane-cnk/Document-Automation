# Clients Module — Frontend UI (Django Templates + Vanilla JS)

## 1. Objective

Build the first frontend of the Document Automation tool: a **Clients module UI**.

Requested outcome (user):

- **No login/authentication flow** for this iteration.
- **Simple navbar + footer** shared by all pages.
- The **navbar contains a "Clients" option** that opens the clients page.
- The **clients page lists all active clients** from the database showing **`client_name`, `client_short_name`, `client_spoc_name`**.
- Each row has **Edit** and **Delete** buttons; delete asks for confirmation (user choice).
- **One "Add Client" option** leads to an add form taking **all fields required for client registration**.

Final outcome: three server-rendered pages (clients list, add client, edit client) served by the same Django project, consuming the already-built and validated Clients CRUD API (`docs/plan-clients-app-crud.md`; backend confirmed complete — live smoked 23/23).

Decisions confirmed with the user this session:
- **Stack:** Django templates + vanilla JS (`fetch` → existing DRF API). No Node toolchain, no CORS, no build step.
- **Styling:** Bootstrap 5 **vendored into `static/`** (offline-safe), plus a small custom stylesheet.
- **Delete flow:** native browser confirm dialog before the soft delete.

## 2. Context

### Existing architecture (confirmed from repository)

- Django project at `src/document_generator/` (settings module `backend.settings`, `DEBUG=True`, Python 3.12, `uv`-managed). Deps (`pyproject.toml`): Django 6.1.2, DRF, psycopg 3, loguru, python-dotenv — **no frontend packages exist; none are needed** for the chosen stack.
- **Backend API (implemented, validated) — the frontend's only contract:**
  - `GET /clients/` → `200` JSON array of **active** clients, newest first (`Meta.ordering = ["-created_at"]`).
  - `POST /clients/` → `201` (duplicate case-insensitive name → `409`; validation → `400`).
  - `GET /clients/{client_id}/` → `200` (inactive or unknown → `404`).
  - `PUT /clients/{client_id}/` → full update; **ALL 6 business keys required** (400 if any missing; 409 dup; 404 inactive/unknown). `PATCH` → `405`.
  - `DELETE /clients/{client_id}/` → soft delete `is_active=False`, `204` (404 inactive/unknown).
  - JSON object shape (every client, from `clients/serializers.py`): `client_id`, `client_name`, `client_short_name`, `client_industries` (list of strings), `client_spoc_name`, `client_spoc_email`, `list_of_entities` (list of strings), `is_active`, `created_at`, `updated_at`.
  - Error shapes (DRF default): `400` → `{"field": ["msg"]}`; `404/405/409` → `{"detail": "..."}`. Views: `src/document_generator/clients/views.py` (`ClientViewSet`, `AllowAny`, `http_method_names = ["get","post","put","delete"]`, `lookup_field="client_id"`, `lookup_value_regex="[0-9]+"`).
- **URL wiring (`backend/urls.py`):** exactly `admin/` and `clients/` (DRF `SimpleRouter` with prefix `""`). No root route exists yet.
- **No frontend exists:** zero `.html` files, no templates dir, no static dir, no JS anywhere; `TEMPLATES` uses `APP_DIRS: True` with empty `DIRS` (`backend/settings.py` lines 71–84). `'django.contrib.staticfiles'` **is** installed and `STATIC_URL = 'static/'` (line 144) — in `DEBUG` mode `runserver` serves static files from app `static/` directories automatically, so **no new static settings are required**.
- **`INSTALLED_APPS`** (settings lines 46–56): `django.contrib.*` ×6, `clients`, `template_master`, `rest_framework`. `template_master` is out of scope.
- **No `REST_FRAMEWORK` settings block exists** — DRF defaults (`SessionAuthentication` + `BasicAuthentication`) are active while viewsets declare `AllowAny`.

### Constraints discovered

1. **URL-space sharing:** the user-facing pages must share the `/clients/` namespace with the DRF API without moving the API. This is safe *only* because the router detail pattern matches **numeric ids only** (`lookup_value_regex = r"[0-9]+"`): `/clients/add/` and `/clients/{id}/edit/` fall through the API include to the frontend include (which must be registered **after** it — see §3.4).
2. **CSRF trap (real, found via code inspection):** DRF's `SessionAuthentication` enforces CSRF on POST/PUT/DELETE **when a session-authenticated user is present** — e.g. if the developer has logged into Django admin (`/admin/`) in the same browser, the `sessionid` cookie makes JS `fetch()` calls fail with `403` even though the endpoints are `AllowAny`. Since the user explicitly wants **no authentication**, the correct minimal fix is to set DRF `DEFAULT_AUTHENTICATION_CLASSES = []` (one settings block) so every API request is anonymous and CSRF is never enforced. Alternative (rejected as more moving parts): add `django.template.context_processors.csrf`, embed tokens in templates, send `X-CSRFToken` headers.
3. **XSS surface (new, introduced by this task):** the list JS will inject user-entered strings (`client_name` etc.) into the DOM. The implementation must build elements with `textContent` (never `innerHTML` string concatenation) — see Security.
4. **PII logging (pre-existing, accepted):** `backend/middleware.py` logs request bodies (SPOC names/emails) to the rotated `logs/app.log`; frontend POST/PUT bodies will be logged the same way. No change requested.

### Confirmed external fact (web research)

- Current stable Bootstrap 5 line is **5.3.8** (Bootstrap 6 exists only as `6.0.0-alpha.x`). Official dist files: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css` and `https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js` (jsDelivr/cdnjs/g bootstrap docs show 5.3.8 as latest 5.x patch). MIT-licensed — vendoring is permitted.

### Assumptions (stated, not confirmed)

- The **clients list page doubles as the home page** (served at `/`), with the navbar "Clients" link pointing to `/`. The user asked for a navbar option that "opens the clients page"; with only one module UI so far, a distinct landing page would be an empty shell. Trivially changeable later.
- List columns are exactly the three requested; other fields (email, industries, entities, email, timestamps) are visible on the edit page via prefill and remain accessible through the DRF API.
- `client_industries` / `list_of_entities` are edited as **comma-separated text inputs** (no tag widget); empty lists stay `[]`. Backend already coerces `null → []` and validates list-of-strings.
- No pagination/search (tiny data volume; consistent with the API decision "no filters/pagination this iteration").
- Delete stays a **soft delete** (API contract); UI will not offer "restore deleted clients".

### Dependencies / blockers

1. PostgreSQL reachable with the existing `src/document_generator/.env`, and the `clients_client` table already migrated (true today — the app is in use with live data; verified by the prior session's smoke tests and the defect-fix record in `docs/plan-clients-app-crud.md` §6).
2. One-time **internet access for the executor** to download the two Bootstrap files (only step needing the network; after that, fully offline-capable).
3. No new Python dependencies; `manage.py test` needs the (already resolved) `CREATEDB` privilege for `doc_user` to run the test DB.

**No blockers.**

## 3. What / Why / How to Build

### 3.1 Create the `frontend` Django app (`src/document_generator/frontend/`)

- **What:** A lightweight, template-only Django app — the home for *all* future UI modules (template_master UI will land here later too).
- **Why:** Follows the existing app pattern (`clients`, `template_master`) and gives templates/static/tests a single place; keeps Django URLs to one new `include`.
- **How:** Standard app skeleton created by hand inside `src/document_generator/`:
  - `frontend/__init__.py` (empty)
  - `frontend/apps.py`:
    ```python
    from django.apps import AppConfig

    class FrontendConfig(AppConfig):
        default_auto_field = "django.db.models.BigAutoField"
        name = "frontend"
    ```
  - No `models.py` (template-only app; nothing to migrate). `admin.py` not needed.

### 3.2 Register the app — `backend/settings.py`

- **What:** `INSTALLED_APPS` **append** `'frontend'` (order irrelevant; place after `'clients'`).
- **Why:** Django discovers `frontend/templates/**` (APP_DIRS) and `frontend/static/**` (staticfiles) only when the app is installed.
- **How:** One list item. Nothing else in settings changes for templates or static (confirmed: `APP_DIRS: True`, `STATUS`/`STATIC_URL` already present; `runserver` serves app static dirs under `DEBUG`).
- **Also add** (same file, see §3.7 for why):
  ```python
  REST_FRAMEWORK = {
      # No authentication this iteration (user decision). Empty list = every
      # DRF request is anonymous; SessionAuthentication (default) would enforce
      # CSRF on POST/PUT/DELETE whenever an /admin/ session cookie exists in
      # the browser, breaking unauthenticated JS calls.
      'DEFAULT_AUTHENTICATION_CLASSES': [],
  }
  ```

### 3.3 Frontend views — `frontend/views.py` (create)

- **What:** Two `TemplateView` subclasses; rendering only, **no DB queries** (all data flows through the DRF API from JS).
  ```python
  from django.views.generic import TemplateView

  class ClientsListView(TemplateView):
      """GET / — active-clients table; rows fetched from GET /clients/ by JS."""
      template_name = "frontend/clients_list.html"

  class ClientFormView(TemplateView):
      """GET /clients/add/  -> create mode; GET /clients/{id}/edit/ -> edit mode."""
      template_name = "frontend/client_form.html"

      def get_context_data(self, **kwargs):
          ctx = super().get_context_data(**kwargs)
          client_id = self.kwargs.get("client_id")        # from URL converter
          ctx["mode"] = "edit" if client_id else "create"
          ctx["client_id"] = client_id
          return ctx
  ```
- **Why:** Minimal server logic; one shared form template driven by `mode`. No `db.sqlite3`/ORM coupling in the UI layer.
- **How:** As above. Edit prefill happens client-side via `GET /clients/{id}/` — keeps views stateless and avoids re-serializing model internals.

### 3.4 URLs — `frontend/urls.py` (create) + `backend/urls.py` (append)

- **What:** Page routes; API routes stay untouched.
  ```python
  # frontend/urls.py
  from django.urls import path
  from .views import ClientsListView, ClientFormView

  urlpatterns = [
      path("", ClientsListView.as_view(), name="clients-list-page"),
      path("clients/add/", ClientFormView.as_view(), name="client-add-page"),
      path(
          "clients/<int:client_id>/edit/",
          ClientFormView.as_view(),
          name="client-edit-page",
      ),
  ]
  ```
  ```python
  # backend/urls.py — append as the LAST entry of urlpatterns
  path("", include("frontend.urls")),
  ```
- **Why these exact URLs:** `/clients/` (API list) and `/clients/{numeric}/` (API detail) already exist. Page URLs merge into the same namespace:
  - `/clients/add/` → router detail pattern requires `[0-9]+` → no API match → falls through to the frontend include (**this fall-through works only because the frontend include is listed after the API include** — the ordering is a hard requirement, not a preference).
  - `/clients/{id}/edit/` → trailing `/edit/` never matches the anchored API detail regex → same fall-through.
- **How:** Exactly as above; `urlpatterns` order in `backend/urls.py` (project root) ends up: `admin/`, `clients/` (API), `""` (pages).

### 3.5 Templates — `frontend/templates/frontend/` (create directory + 3 files)

**`base.html`** — navbar + footer skeleton (both pages extend this; sidebar deliberately not built since only one module exists):

- `<head>`: `<meta charset>`, `<meta viewport>`, `{% static %}`-referenced `<link>` to `frontend/vendor/bootstrap/bootstrap.min.css`, then `frontend/css/styles.css` (custom tweaks load second), `<title>{% block title %}Document Automation{% endblock %}</title>`.
- `<body class="d-flex flex-column min-vh-100">` — standard Bootstrap pattern so the footer sticks to the bottom on short pages.
- Navbar (`<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">`): brand "Document Automation" (→ `/`); a single nav item **"Clients"** (`{% url 'clients-list-page' %}`, `{{ request.resolver_match.url_name }}`-based `active` class is optional polish). With `navbar-expand-lg` the small-screen hamburger requires the Bootstrap JS bundle — include it (vendored) at end of body.
- Content block `{% block content %}{% endblock %}` inside a `<main class="container">`.
- Footer: `<footer class="footer mt-auto py-3 bg-light border-top">` → `<div class="container text-muted small">© 2026 Document Automation — internal tool</div>`.
- `{% block scripts %}{% endblock %}`.

**`clients_list.html`** — the clients page:

- Page header row: `<h1>Clients</h1>` + `<a class="btn btn-primary" href="{% url 'client-add-page' %}">+ Add Client</a>` (the single "add" option, user-required).
- `<div id="clients-error" class="alert alert-danger d-none"></div>` — fetch/render error banner.
- `<table class="table table-striped table-hover align-middle">` with `<thead>`: **Client Name | Short Name | SPOC Name | Actions**; `<tbody id="clients-tbody">` initially containing a loading row ("Loading clients…").
- `data-*` hooks on `<body>`/`<table>` are unnecessary here — this page has no server-side data. The page JS (`clients.js`) depends on the two element ids above only.

**`client_form.html`** — add + edit form (mode-aware, driven by `{{ mode }}` and `{{ client_id }}`):

- Title: `Add New Client` / `Edit Client` (RequestContext `mode`).
- `<form id="client-form" novalidate method="post" action="#">` — submission is intercepted by JS; `action` is a no-op.
- Fields (all business fields, satisfying "all required fields for client registration"; `*` = HTML `required`):
  | Bootstrap field | `name` | Backend constraint | Notes |
  | --- | --- | --- | --- |
  | Client Name * | `client_name` | required (255) | duplicate name → server 409 |
  | Short Name | `client_short_name` | optional (100) | must still be **sent** on edit (PUT all-keys rule) |
  | Industries | `client_industries` | optional list of strings | text input, comma-separated |
  | SPOC Name * | `client_spoc_name` | required (255) | |
  | SPOC Email * | `client_spoc_email` | required, valid email (254) | `<input type="email">` |
  | Entities | `list_of_entities` | optional list of strings | text input, comma-separated |
- Each field: `<div class="mb-3">` + `<label>` + input + `<div class="invalid-feedback" data-error-for="…"></div>` target for server-side messages.
- Top banner `<div id="form-error" class="alert alert-danger d-none">` for global errors (404 prefill failure, unexpected 500, malformed response).
- Buttons: `Save Client` (submit) + `Cancel` (plain link → `/`).
- Mode hand-off to JS: put the data directly on the form element itself (keeps `base.html` generic):
  `<form id="client-form" novalidate method="post" action="#" data-mode="{{ mode }}" data-client-id="{{ client_id|default_if_none:'' }}">`
  — `client_form.js` reads these two attributes (§3.6).

### 3.6 Static assets — `frontend/static/frontend/` (create directory tree + files)

```
frontend/static/frontend/
├── vendor/bootstrap/bootstrap.min.css        # downloaded once from jsdelivr@5.3.8
├── vendor/bootstrap/bootstrap.bundle.min.js  # downloaded once from jsdelivr@5.3.8
├── css/styles.css                            # small custom sheet (~30 lines)
└── js/clients.js                             # list page logic
└── js/client_form.js                         # add/edit form logic
```

- **Vendoring step (executor):** download the two official 5.3.8 dist files (URLs in §2 Confirmed external fact) into `vendor/bootstrap/` and **commit them** (they're project source now, not build artifacts — keep them out of any ignore list). No SRI/integrity attributes needed for local files.
- **`styles.css`** (intentionally minimal — "keep simple"): small sticky-footer helpers if any, `.table-column-actions { width: 1%; white-space: nowrap; }` so Edit/Delete buttons don't stretch, optional max-width for the form.

**`js/clients.js` (list page — load with `defer`):**

1. `fetch("/clients/", { headers: { Accept: "application/json" } })` → on 200, array of client objects.
2. Render one `<tr>` per client with cells: `client_name`; `client_short_name` (show `—` when blank); `client_spoc_name`; Actions cell with:
   - **Edit** → `<a class="btn btn-sm btn-outline-primary" href="/clients/{client_id}/edit/">Edit</a>`
   - **Delete** → `<button class="btn btn-sm btn-outline-danger">Delete</button>` with `data-client-id`.
3. **XSS rule (hard requirement):** build every row/cell via `document.createElement` + `element.textContent = value`. Never assign user-derived strings through `innerHTML` (`client_name` is user input; attackers could type `<script>` payloads).
4. Delete click → `confirm("Delete this client? The client will be deactivated.")`; if declined → no-op. If accepted:
   `fetch("/clients/{client_id}/", { method: "DELETE" })` →
   - `204` → remove row from DOM (or re-fetch the list — re-fetch is simpler and self-consistent);
   - `404` (client already inactive/unknown) → alert message + re-fetch list;
   - other/error → show `#clients-error` banner.
5. Empty list (API returns `[]`) → single full-width row: "No clients yet — add your first client."
6. List render failure (network/500/404-nonJSON) → banner with generic message + `console.error` (server side already logged the request in `logs/app.log`).

**`js/client_form.js` (add + edit — load with `defer`):**

1. Read `mode` / `client_id` from the `<form>` `data-*` attributes (§3.5).
2. **Edit prefill:** on load, `fetch("/clients/" + client_id + "/")` → 200 → populate the six inputs (lists joined with `", "`); `404` → show `#form-error`: "Client not found or no longer active." + hide/disable the form (row was deleted elsewhere; detail is 404 for inactive ids — API contract).
3. **Submit handler** (`event.preventDefault()`):
   - Client-side HTML5 `checkValidity()` first (required fields, email format, maxlength mirrors server limits).
   - Parse `client_industries` / `list_of_entities`: split on commas, trim items, drop empties → arrays.
   - Build payload with **all six keys always sent** (empty strings/arrays are valid — this satisfies the `UpdateClientSerializer` "every key required" PUT contract and keeps add/edit payloads symmetrical):
     ```json
     { "client_name": "...", "client_short_name": "...", "client_industries": ["..."],
       "client_spoc_name": "...", "client_spoc_email": "...", "list_of_entities": ["..."] }
     ```
   - `Content-Type: application/json`; mode create → `POST /clients/`; mode edit → `PUT /clients/{client_id}/`.
   - Success (`201`/`200`) → `window.location.href = "/"` (back to the list).
   - **Failure mapping (DRF shapes, per `clients/serializers.py`):** JSON `{"field": ["msg", ...]}` → put first message into the matching `.invalid-feedback[data-error-for=field]` + `is-invalid` class; unknown-field keys or single-key `{"detail": "..."}` and any non-JSON/network error → `#form-error` banner. Special-case `409`: message lands under `client_name` ("A client with this name (case-insensitive) already exists.").
4. No confirmation on Save; no PATCH anywhere (API 405s it by design).

### 3.7 Auth/CSRF settings change — `backend/settings.py` (already covered §3.2)

- **What:** add the `REST_FRAMEWORK` block with empty `DEFAULT_AUTHENTICATION_CLASSES`.
- **Why:** without it, an `/admin/` session cookie in the browser triggers DRF CSRF enforcement on the JS POST/PUT/DELETE calls → random 403s that look like a frontend bug. With it, all requests are anonymous — exactly matching "no login/authentication flow for now" and the existing `AllowAny` viewset. One-block, reversible change; must be re-visited when authentication lands (recorded in Compatibility).

## 4. Technical Specification

### Architecture changes

- First UI layer: new `frontend` app (pure presentation — templates + static + views + URL wiring). Existing apps/models unchanged apart from the optional-to-users settings registration and the DRF auth-defaults block. No new packages, no build pipeline.

### Data flow

```
Browser page (/  /clients/add/  /clients/{id}/edit/)
  → Django TemplateView (render shell only, no DB)
  → vanilla JS fetch (same-origin, no CSRF token needed once auth classes are [])
      GET/POST /clients/          GET/PUT/DELETE /clients/{client_id}/
  → existing DRF pipeline: LoguruRequestLoggerMiddleware → urls → ClientViewSet
    → ClientSerializer/UpdateClientSerializer (dup-check 409, list coercion)
  → PostgreSQL clients_client
```
Server-side render knows nothing about client data; JS owns all data binding.

### API changes

**None.** Backend endpoints, payloads, status codes, and serializers are untouched. The only backend-surface delta is the `REST_FRAMEWORK` auth-defaults block (behavior of the endpoints themselves unchanged).

### Database/schema changes

`Not applicable.` (No models in the frontend app; no migrations.)

### Backend changes

1. `src/document_generator/backend/settings.py` — `INSTALLED_APPS` += `'frontend'`; new `REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": []}` block.
2. `src/document_generator/backend/urls.py` — final entry `path("", include("frontend.urls"))` (after `admin/` and `clients/`).

### Frontend changes (the core of this plan)

- New app tree under `src/document_generator/frontend/`: `__init__.py`, `apps.py`, `views.py`, `urls.py`, `tests.py`, `templates/frontend/{base.html, clients_list.html, client_form.html}`, `static/frontend/{css/styles.css, js/clients.js, js/client_form.js, vendor/bootstrap/{bootstrap.min.css, bootstrap.bundle.min.js}}`.
- Page inventory:

| Page | URL | File | JS | Actions |
| --- | --- | --- | --- | --- |
| Clients list (home) | `/` | `frontend/clients_list.html` | `clients.js` | table fetch/render; row Delete (confirm → soft delete); row Edit link |
| Add client | `/clients/add/` | `frontend/client_form.html` | `client_form.js` | POST submit, server-error display, cancel |
| Edit client | `/clients/{client_id}/edit/` | `frontend/client_form.html` | `client_form.js` | prefill via GET; PUT all-keys submit, server-error display, cancel |

### Configuration changes

- Only the settings entries listed in Backend changes. `.env`, `STATIC_URL`, `TEMPLATES`, middleware — **no changes**.

### Security considerations

- **No authentication/authorization this iteration** (user's explicit choice; codified by `DEFAULT_AUTHENTICATION_CLASSES = []`). Anyone who can reach the server can create/edit/deactivate clients through UI or API. Accepted and intentionally documented; the future auth pass must revisit both the viewsets and this settings block together.
- **CSRF:** with auth classes empty, DRF performs no CSRF verification on API calls, which is what makes the plain-`fetch` flow work. This is only acceptable *because* no credentials/cookies authorize anything — removing the guard once authentication exists without implementing token/CSRF handling would be a vulnerability (see Compatibility).
- **Stored-XSS via client fields (new surface introduced by this task):** `client_name` etc. are user-typed strings rendered into the table. Executor must insert values with `textContent` only; `innerHTML` with interpolated values is forbidden. (Form inputs are safe by nature — user typing into their own form is fine; the table is the injection display vector.)
- **Bootstrap provenance:** download the vendored files from the official jsdelivr release (URL pinned in §2) — not from third-party mirrors; no SRI needed once local, but the pinned URL is auditable.
- **No secrets** involved (no new `.env` keys).

### Error handling

- **List page:** fetch/render failures → red alert banner; delete 404 → message + refresh (handles "deactivated elsewhere"); delete 204 → row refreshes.
- **Form page:** DRF `{"field": [...]}` → inline field messages; `{"detail": ...}` / unexpected status / non-JSON → banner; prefill 404 → "Client not found or no longer active." (matches API contract for inactive ids); client-side `checkValidity()` guards before any network call.
- Server-side errors are already fully logged by `LoguruRequestLoggerMiddleware`; the JS `console.error` is for the dev console only.

### Validation

- Client-side: HTML5 `required`, `type="email"`, `maxlength` mirroring the model (255/100/255/254).
- Server-side (authoritative, unchanged): non-blank name/spoc-name, valid email, list-of-strings coercion, case-insensitive duplicate-name check (409), PUT all-keys presence.

### Performance considerations

- Tiny data volume; single fetch per page load; no pagination intentionally. Vendored Bootstrap (~230 KB CSS+JS) served once and browser-cached — no CDN dependency at runtime.

### Compatibility considerations

- **URL ordering fragility (document, keep):** page routes share the `/clients/` prefix with the API and rely on (a) numeric-only `lookup_value_regex` and (b) the frontend `include` being appended **after** the API include. If either changes (e.g. router prefix moves under `/api/`), page URLs collide/shift — the future "move API under `/api/`" cleanup, if any, must update `frontend/urls.py` and the JS constants together.
- **Auth-forward compatibility:** when authentication is introduced, this plan's `DEFAULT_AUTHENTICATION_CLASSES = []` must be replaced (Session/Token), **and** the frontend fetch calls must gain credential/CSRF handling — flagging now so the frontend design isn't mistaken for auth-ready.
- Django 6.1 / DRF 3.18 / Bootstrap 5.3.8 / evergreen browsers — no version-risky surface; `TemplateView`/<int:>/fetch are long-stable primitives.
- DRF still serves `GET /clients/` as JSON at its URL; devs hitting `/clients/` directly see the API, users use `/` — no regression against existing behavior (smoke-tested previously).

### Testing strategy

**Automated — `frontend/tests.py` (create; page-level smoke tests, no DB writes):**
1. `GET /` → 200, uses `frontend/clients_list.html`, contains "Clients", an "Add Client" link to `/clients/add/`, and "SPOC Name" column header.
2. `GET /clients/add/` → 200, `frontend/client_form.html`, title "Add New Client", six inputs with the canonical names.
3. `GET /clients/1/edit/` → 200, same template, title "Edit Client" (template renders in edit mode even without a row — prefill is JS-side).
4. Assert `{{ mode }}` plumbing: edit page form tag carries `data-mode="edit"` / `data-client-id="1";` create page `data-mode="create"`.

**Automated — regression:** existing suite `uv run python manage.py test clients` must still pass unchanged (22 tests), proving API URLs were not shadowed.

**Manual matrix (runserver + browser, PostgreSQL live):**
5. `/` with data → rows show name/shortname(spoc)/spoc-name; blank short name renders `—`.
6. `/` empty DB (or after deleting all) → "No clients yet…" empty state.
7. Add flow: all fields → save → redirects to `/`, new row visible (newest first), `logs/app.log` shows `CLIENT_CREATED` + REQ line.
8. Add flow: duplicate name (case-variant of an existing) → inline client_name error, no navigation (409 path).
9. Add flow: missing required field → blocked client-side; invalid email → blocked client-side (plus server would 400).
10. Edit flow: open → fields prefilled from API GET; change short name only → save → back to list, change visible, `updated_at` advanced.
11. Edit of an id deleted in another tab/session → "Client not found or no longer active."
12. Delete: confirm dialog on click; Cancel → row untouched; OK → row disappears, DB row has `is_active=false` (via admin or psql), list refresh consistent.
13. Delete already-inactive id (two tabs) → 404 message + list refresh, no crash.
14. Admin-cookie regression: log into `/admin/` in the same browser, then create/edit/delete via the UI → must succeed (validates the empty auth-classes change) where before it would have 403'd on CSRF.
15. Offline styling sanity: with no internet, pages still fully styled (vendored Bootstrap did its job).

### Deployment considerations

- Dev-only posture unchanged; pages served by the same `uv run python manage.py runserver`. Vendored assets are committed source — no CDN, no Node, no build step in any environment. For any future non-DEBUG deployment, `collectstatic` needs `STATIC_ROOT`+`STATICFILES_DIRS` additions — out of scope, noted for the auth/hardening pass.

## 5. Change Template

| File | Change Type | Proposed Change | Reason |
| :--- | :--- | :--- | :--- |
| `src/document_generator/frontend/__init__.py` | Create | Empty package marker | New app |
| `src/document_generator/frontend/apps.py` | Create | `FrontendConfig(name="frontend")` | App registration |
| `src/document_generator/frontend/views.py` | Create | `ClientsListView` + `ClientFormView` (TemplateViews; context `mode`/`client_id`) | §3.3 — page rendering, no DB access |
| `src/document_generator/frontend/urls.py` | Create | `""` → list page; `clients/add/`; `clients/<int:client_id>/edit/` (§3.4) | Client-page routing |
| `src/document_generator/backend/urls.py` | Modify | Append `path("", include("frontend.urls"))` as last entry | Expose pages; fall-through after API include (§3.4) |
| `src/document_generator/backend/settings.py` | Modify | `INSTALLED_APPS` += `'frontend'`; add `REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": []}` | App discovery; CSRF-free anonymous API access (§3.2/§3.7) |
| `src/document_generator/frontend/templates/frontend/base.html` | Create | Navbar (brand + "Clients" link) / footer / blocks / vendored-Bootstrap links, sticky-footer body classes | Shared chrome (navbar/footer requirement) |
| `src/document_generator/frontend/templates/frontend/clients_list.html` | Create | Clients table shell (Name/Short Name/SPOC Name/Actions), Add Client button, error-alert, empty state | The clients page |
| `src/document_generator/frontend/templates/frontend/client_form.html` | Create | Mode-aware form: six fields, inline error slots, banner, Save/Cancel | Add + edit pages |
| `src/document_generator/frontend/static/frontend/vendor/bootstrap/bootstrap.min.css` | Create | Download official Bootstrap 5.3.8 dist CSS (jsdelivr URL in §2) and commit | Styling (user choice: vendored) |
| `src/document_generator/frontend/static/frontend/vendor/bootstrap/bootstrap.bundle.min.js` | Create | Download official Bootstrap 5.3.8 bundle JS and commit | Navbar collapse on mobile |
| `src/document_generator/frontend/static/frontend/css/styles.css` | Create | Minimal custom rules (actions-column width, form width, footer helpers) | Small layout polish |
| `src/document_generator/frontend/static/frontend/js/clients.js` | Create | List fetch/render (textContent-only), Edit links, Delete + confirm + soft-delete call, error banners | Clients-page behavior |
| `src/document_generator/frontend/static/frontend/js/client_form.js` | Create | Edit prefill (GET), all-keys POST/PUT submit, DRF error mapping (field inline / detail banner), redirect on success | Form behavior |
| `src/document_generator/frontend/tests.py` | Create | Page smoke tests + mode plumbing assertions (§4 Testing items 1–4) | Lock in page behavior |

**Explicitly out of scope:** `template_master/*`; any API/serializer/model/migration change; login/auth UI; pagination/search; "restore deleted clients" UI; separate landing page; moving API routes under `/api/`; `robots.txt`/favicon polish; `STATIC_ROOT`/production static config.

## 6. To-Do Matrix

| File / Change | Proposed Action | Executed | Tested | Deployed |
| :--- | :--- | :---: | :---: | :---: |
| `src/document_generator/frontend/__init__.py` | Create empty package | [x] | [x] | [ ] |
| `src/document_generator/frontend/apps.py` | Create `FrontendConfig` | [x] | [x] | [ ] |
| `src/document_generator/frontend/views.py` | Create `ClientsListView` + `ClientFormView` | [x] | [x] | [ ] |
| `src/document_generator/frontend/urls.py` | Create page routes per §3.4 | [x] | [x] | [ ] |
| `src/document_generator/backend/urls.py` | Append frontend include (last) | [x] | [x] | [ ] |
| `src/document_generator/backend/settings.py` | `INSTALLED_APPS` += `frontend`; add `REST_FRAMEWORK` auth-defaults block | [x] | [x] | [ ] |
| `src/document_generator/frontend/templates/frontend/base.html` | Create navbar/footer skeleton | [x] | [x] | [ ] |
| `src/document_generator/frontend/templates/frontend/clients_list.html` | Create clients table page | [x] | [x] | [ ] |
| `src/document_generator/frontend/templates/frontend/client_form.html` | Create mode-aware form page | [x] | [x] | [ ] |
| `src/document_generator/frontend/static/frontend/vendor/bootstrap/bootstrap.min.css` | Download + commit Bootstrap 5.3.8 CSS | [x] | [x] | [ ] |
| `src/document_generator/frontend/static/frontend/vendor/bootstrap/bootstrap.bundle.min.js` | Download + commit Bootstrap 5.3.8 bundle JS | [x] | [x] | [ ] |
| `src/document_generator/frontend/static/frontend/css/styles.css` | Create minimal custom stylesheet | [x] | [x] | [ ] |
| `src/document_generator/frontend/static/frontend/js/clients.js` | Create list-page JS | [x] | [x] | [ ] |
| `src/document_generator/frontend/static/frontend/js/client_form.js` | Create form-page JS | [x] | [x] | [ ] |
| `src/document_generator/frontend/tests.py` | Create page smoke tests | [x] | [x] | [ ] |
| (regression) `src/document_generator/clients/tests.py` | Do NOT modify; re-run `uv run python manage.py test clients` after wiring | [x] | [ ] | [ ] |

**Validation note (post-execution):**
- `uv run python manage.py check` — clean.
- `uv run python manage.py test frontend` — **10/10 pass** (page routes, templates, all six form fields, mode/data plumbing).
- `uv run python manage.py test clients` (regression) — 22 tests: 21 pass, 1 fail — the failure is the **pre-existing, documented** `test_create_readonly_fields_ignored` hardcoded `client_id == 1` assertion (plan-clients-app-crud.md §6 defect-fix record; file untouched by this task). All URL-behavior tests pass → API routes were not shadowed by the page include.
- Live `runserver` + Playwright browser verification: all pages/static serve 200 (incl. vendored Bootstrap 5.3.8); manual-matrix items verified in a real browser — **5** (row render + blank short name → `—`), **6** (empty state), **7** (add → 201 → redirect → row + `CLIENT_CREATED` logged), **8** (duplicate → inline 409 field error, no navigation), **9** (client-side required/email blocking), **10** (edit prefill → PUT all-keys → list updated, `CLIENT_UPDATED` logged), **11** (edit of soft-deleted id → "Client not found or no longer active." + form disabled), **12** (delete dialog: accept → 204 → row removed; cancel → row untouched; DB `is_active=false` confirmed via API 404).
- Manual-matrix items **not** exercised this run: **13** (delete of an already-inactive id — branch exists, guards via API 404 contract), **14** (admin-cookie regression — root-caused by the new empty auth-classes setting), **15** (fully-offline styling — vendored assets served locally, but browser ran with internet). Sandbox rows used for browser tests were soft-deleted after each flow; no active test data remains.

### Second independent verification session (2026-10-26, Tester agent, `tests/session-20261026-125912/`)

- Unit suites re-run: `test frontend` **10/10 pass**; `test clients` **21/22** (identical documented pre-existing fail, file untouched — regression row stays `[ ]`).
- **HTTP-contract E2E `e2e_http.py`: 25/25 pass** against live runserver (create 201/echo, list-first, dup-409, missing-key/invalid-email/list-type/member-type/blank/300-char/null 400s, readonly-fields ignored on create, PUT full 200 + missing-key 400 + PATCH 405 + unknown-id 404 + self-exclusion 200, DELETE 204→404 chain, GET-detail 404, list exclusion, PUT-on-deleted 404, `updated_at` advance).
- Browser matrix items completed via Playwright MCP: **7** (form attrs `maxlength=255/100/255/254`, novalidate, Cancel→`/`; typed 300 chars truncates to 255 client-side; valid create → redirect → row; DB row all six fields + timestamps verified), **8** (case-variant duplicate → inline 409 message, no navigation), **9** (blank submit → 3 inline errors + 0 network; invalid email → blocked + 0 network; server-400 blank + tooLong messages mapped inline via UI), **10** (prefill exact all-six; PUT 200; list shows `E2EA-UPD`; DB `updated_at` advanced), **11** re-verified earlier run, **12** (exact dialog text "Delete this client? The client will be deactivated." captured; accept → row gone + empty state; DB `is_active=false`, `updated_at` advanced; data otherwise preserved), **13** (two-tab stale delete → DELETE 404 + exact banner captured via MutationObserver timeline), **14** (disposable superuser login → `sessionid` cookie set → UI create + delete succeed with no 403 → superuser removed, 0 superusers left), **15** (grep: zero external `http(s)` refs in templates/static; network resource list: only the 4 same-origin static assets; computed `navbar` bg `rgb(33, 37, 41)` proving vendored CSS applies).
- XSS security probe: `<img onerror>`/`<script>`/`<b>` in name/SPOC stored raw, rendered as text via `textContent`-built rows — 0 injected `img`/`script` elements, no dialogs; row soft-deleted after.
- DB: every E2E-sandbox row `is_active=false` (finalstate: 0 active in sweep); rejected payloads (blank/tooLong/ws-named/duplicate) verified never inserted; DB has 0 superusers.
- Findings (report-only, no fixes made): **O1** `/favicon.ico` auto-request 404 (no favicon in template — favicon polish explicitly out of scope; cosmetic console noise); **O2** nested DRF list-type error shape `{"field": {"field": msg}}` would render "[object Object]" in `applyApiErrors` — unreachable through the normal UI (form always sends arrays); future polish; **O3** the 404-branch banner displays for a measured 86 ms then `hideError()` blanks it during the auto-refresh — matrix item 13 works but the message is effectively transient/invisible to users; consider a persistent notification in a later pass.

## 7. Sources

Repository evidence:
- `docs/plan-clients-app-crud.md` — implemented backend contract, decisions, validation record (23/23 smoke, 22 unit tests, defect fixes D1/D2)
- `src/document_generator/clients/views.py`, `clients/serializers.py`, `clients/urls.py`, `clients/models.py` — exact API/JSON shapes, `AllowAny`, numeric `lookup_value_regex`, PUT all-keys rule
- `src/document_generator/backend/urls.py`, `backend/settings.py` — current routing, `INSTALLED_APPS`, `TEMPLATES` (APP_DIRS), `STATIC_URL`, middleware, DB
- `pyproject.toml` — dependency inventory (no frontend stack present)
- `.gitignore` — current ignore entries (no changes needed)

External documentation (web research actually used this session):
- Bootstrap 5.3 current-stable version + official dist file URLs (jsDelivr / cdnjs / getbootstrap.com download page) — https://getbootstrap.com/docs/5.3/getting-started/download/ , https://www.jsdelivr.com/package/npm/bootstrap , https://cdnjs.com/libraries/bootstrap (confirmed 5.3.8 stable; Bootstrap 6 present only as 6.0.0-alpha)

## 8. Summary

A first frontend lands for the Clients module: three server-rendered pages inside a new lightweight `frontend` Django app — clients list (home, at `/`) showing every active client's name, short name, and SPOC name with per-row Edit/Delete (Delete confirms, then soft-deletes via the existing API) and a single Add Client button; plus an add/edit form page covering all six registration fields, prefilling on edit and submitting all-keys PUT (matching the backend's PUT contract) or POST. Bootstrap 5.3.8 is vendored into static for offline-capable styling; the list page renders data with `textContent`-built DOM (no XSS). The backend API is untouched; the only backend deltas are registering the new app and clearing DRF default auth classes so anonymous JS calls are never CSRF-blocked (the admin-session-cookie 403 trap). Regressions are guarded by the untouched 22-test API suite plus new page-level tests and a 15-point manual matrix.

**Expected end state:** `uv run python manage.py runserver` → `/` shows the styled clients page (navbar + footer) driven by live PostgreSQL data; add/edit/delete all work end-to-end without login; both the API suite and the new page tests pass.

**Major dependencies:** existing running PostgreSQL + migrated `clients_client` (in place); one-time internet download of Bootstrap by the executor; no new Python/JS dependencies.

**Major risks/blockers:** none blocking. Forward-compatibility flags documented: (1) page/API URL-space sharing depends on include ordering + numeric-only lookup regex — any future API-prefix move must update `frontend/urls.py` + JS constants together; (2) empty DRF auth classes must be revisited (together with frontend fetch handling) when the deferred authentication pass lands.
