# Agents Guide

## Project Summary
- File storage system for image/video storage, browsing, and editing.
- Interactive image cropping and labeling pipeline; use `labelplus` for secondary/missed labels.
- Web backend (Django) + web frontend (Next.js) + desktop GUI entrypoint.

## Tech Stack
- Backend: Django (Python), uses `uv` for dependency management and running commands.
- Frontend: Next.js app (create-next-app baseline).
- Imaging: PIL; object detection via Ultralytics YOLO.

## Repo Layout
- `backend/`: Django app, API, utilities, management commands.
- `frontend/`: Next.js web UI.
- `README.md`: primary setup/run/test instructions.

## Setup (From README)
- Run `setup.py`.
- Install `uv` and all dependencies in `pyproject.toml`.
- Backend:
  - `cd backend`
  - `setup.py`
  - `manage.py setup`
- Frontend:
  - `cd frontend`
  - `npm install`
  - Patch Next.js: edit `next/dist/server/lib/router-utils/proxy-request.js`, line 36, add `secure: false` to `HttpProxy`.

## Run Commands
- Backend (web): `cd backend` then `uv run manage.py rs`
- Tests (backend): `cd backend` then `uv run -m coverage run manage.py test api`
- Desktop GUI: `cd backend` then `uv run manage.py tkservice`
- Django shell: `cd backend` then `uv run manage.py shell_plus`
- Frontend: `cd frontend` then `npm run dev -- -p 3001`

## Testing Notes
- Main backend test target: `manage.py test api`
- Coverage is run via `uv run -m coverage`.

## Editing Guidelines
- Follow existing patterns in `backend/api` and `backend/api/utils`.
- Keep tests deterministic; avoid network access in tests.
- When touching image processing, keep grayscale handling in mind.
- Do not touch the SQLite database at `data/database.sqlite3`.
- Ignore media storage paths; do not modify or rely on them.

## Known Quirks / Local Patches
- Next.js requires a manual patch to `HttpProxy` (`secure: false`) for local dev.

## Environment Notes
- `setup.py` creates a required environment variable with placeholder values to fill in.
- Database is SQLite at `data/database.sqlite3`; agents must not touch it.
- Python linting uses `ruff` via `uv`; `ty` will be added soon.
