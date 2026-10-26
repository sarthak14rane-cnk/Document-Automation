# Environment & gotchas — PostgreSQL, .env, logging

## .env (USER-OWNED — never edit it)
Location: `src/document_generator/.env`. Read via `python-dotenv` in `backend/settings.py`.
Actual keys (note: POSTGRES_* prefix, NOT DB_*):
```
POSTGRES_HOST=localhost
POSTGRES_PORT=2478
POSTGRES_USER=doc_user
POSTGRES_PASSWORD=1422
POSTGRES_DB=django_db
```
`.env.example` (committable template) lives beside it.

## CRITICAL: IPv6/IPv4 host stall
PostgreSQL listens **only on IPv4 `127.0.0.1:2478`**, but `localhost` resolves to **IPv6 `::1` first**.
This made every DB request take ~130 seconds. Fixed in `settings.py` (NOT in .env):
```python
'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1').replace('localhost', '127.0.0.1'),
'OPTIONS': {'connect_timeout': 5},
```
Requests went from 130,694ms to 70-240ms. If DB feels slow, check this first.

## Middleware class-path gotcha
Django `MIDDLEWARE` entries must be `module.ClassName`, not snake_case:
- WRONG: `'backend.middleware.loguru_request_logger'`
- RIGHT: `'backend.middleware.LoguruRequestLoggerMiddleware'`
A wrong path fails only at WSGI load (`runserver`), NOT at `manage.py check`. To catch it:
`uv run python -c "... from django.core.wsgi import get_wsgi_application; get_wsgi_application()"`

## Logging
- loguru file sink: `src/document_generator/logs/app.log`, rotation `10 MB`, retention `4 weeks`, set up in `backend/logging_setup.py` (called from settings).
- `backend/middleware.py` logs every request: method, path, status, duration, **request body** (user explicitly chose to include bodies — contains PII, accepted risk).
- Business events logged as `CLIENT_CREATED` / `CLIENT_UPDATED` / `CLIENT_DEACTIVATED`.
- `logs/` and `.env` are git-ignored.

## KNOWN BLOCKER: unit tests cannot run
`manage.py test clients` fails: `permission denied to create database`.
`doc_user` lacks CREATEDB. Fix (requires a PostgreSQL superuser):
```sql
ALTER ROLE doc_user CREATEDB;
```
Then `uv run python manage.py test clients` (creates/drops scratch `test_django_db`; dev DB untouched).
Until then, validation was done via a live-server smoke test instead.