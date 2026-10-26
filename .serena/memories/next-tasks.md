# Next tasks

## 1. template_master app (NOT STARTED)
Skeleton exists at `src/document_generator/template_master/` (models.py/views.py/admin.py/tests.py are startapp defaults, `urls.py` missing, not routed in `backend/urls.py`).
Intended purpose per original brief: a master templates table storing at least:
- template name
- config-path (the config file driving document generation)
- template master docx path
- plus likely is_active/created_at/updated_at to mirror the clients app

Expected to follow the `clients` pattern: plan doc first in `docs/`, then DRF model + serializer + viewset + router + soft delete + loguru events.

## 2. Document generation core
The actual point of the project: generate .word documents from a config file + user inputs, using the template_master docx paths. No code exists for this yet.

## 3. Auth / hardening pass
Both apps currently run with `AllowAny`. Plan noted auth as deferred work.

## 4. Unblock the test suite
See `mem:clients-app/environment` — needs `ALTER ROLE doc_user CREATEDB;`.