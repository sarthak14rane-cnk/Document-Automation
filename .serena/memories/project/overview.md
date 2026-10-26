# Document-Generator — project overview

Django 6.1.2 + Python 3.12 project for generating Word documents from config files and user input.

## Layout (repo root = C:/Users/sarth/PycharmProjects/Document-Generator)
- `src/document_generator/` — Django project root (run all `manage.py` commands from here)
  - `backend/` — settings/urls/wsgi + `middleware.py` + `logging_setup.py`
  - `clients/` — first app: full CRUD API (done)
  - `template_master/` — second app: skeleton only, no models/views yet (NEXT TASK)
- `docs/plan-*.md` — planning documents (planner writes here; executors update To-Do Matrix)
- Dependency manager: **uv** (not pip). `uv add <pkg>`, `uv run python manage.py ...`

## Apps
1. `clients` — implemented (see `mem:clients-app/api-contract`)
2. `template_master` — created by `startapp`, still empty. Planned purpose: master templates table storing template name, config-path, template master docx path.

## Confirmed conventions
- Plans live in `docs/`, named `plan-<task>.md`, with fixed sections 1-8 and a To-Do Matrix that executors must update.
- JSON API only this iteration — no frontend/HTML templates for clients.
- No authentication yet; `AllowAny` is explicit on viewsets by design.