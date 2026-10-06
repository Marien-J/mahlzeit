# Mahlzeit: working notes

Private meal planning, shopping, food and training log for couples. Read `docs/brief.md` first;
its principles override convenience. Open decisions go into `docs/decisions.md`, one line each.
Ask before changing the stack, a core entity or a milestone's scope.

## Layout

```
backend/   FastAPI app + worker (Python 3.13, uv); seed/ = BLS selection, scripts/build_bls_seed.py
  src/mahlzeit/domain     pure rules, no I/O (tests first)
  src/mahlzeit/services   the only layer that writes: transactions, permissions, change records
  src/mahlzeit/api        REST adapter (thin)          jobs/  worker adapter (thin)
  src/mahlzeit/tools      tool registry (thin)         connector/  MCP server at /mcp/<token>
  src/mahlzeit/models     SQLAlchemy tables            migrations/  Alembic
frontend/  React PWA (Vite, TypeScript 5.9, TanStack Query, i18next)
deploy/    Caddy image (serves the built PWA) and backup image
scripts/   backup, restore, restore drill, e2e (+ OFF stub), checks, client generation, env setup
compose.yaml   the one stack: caddy, app, worker, db (+ backup "ops", devdb "dev", offstub "e2e" profiles)
```

## Commands

`scripts/check.sh` runs every check a commit must pass (backend and frontend, API client freshness).

Development database (Postgres on localhost:5433, in memory):

```
docker compose --profile dev up -d devdb
```

Backend (from `backend/`):

```
uv sync                                    # install
uv run pytest                              # all tests (needs devdb; creates mahlzeit_test)
uv run ruff check src tests migrations     # lint
uv run ruff format src tests migrations    # format
uv run mypy                                # strict type check of src
DATABASE_URL=postgresql+psycopg://mahlzeit:mahlzeit@localhost:5433/mahlzeit uv run mahlzeit migrate
uv run alembic revision --autogenerate -m "..."   # new migration (same DATABASE_URL), then review it
uv run alembic check                       # models and migrations agree
ENV=development DATABASE_URL=... ENCRYPTION_KEY=... uv run uvicorn mahlzeit.main:app --reload
```

Frontend (from `frontend/`):

```
npm ci
npm run dev          # Vite on :5173, proxies /api to :8000; set EXTRA_ORIGINS=http://localhost:5173 on the API
npm test             # Vitest
npm run lint         # ESLint (no hard-coded UI strings) + Prettier check
npm run typecheck
npm run gen:api      # or scripts/gen-client.sh from the root: regenerate API types after API changes
```

Whole stack (from the root):

```
scripts/init-env.sh             # once: .env with generated secrets
docker compose up -d --build    # http://localhost
docker compose exec -T -e MAHLZEIT_PASSWORD app mahlzeit create-admin --email you@example.org --name You
docker compose exec app mahlzeit --help    # invite-household, reset-password, list-users, ...
scripts/e2e.sh                  # Playwright on a phone viewport; restarts the stack with the OFF stub
scripts/backup.sh               # encrypted backup into ./backups
scripts/restore.sh <file> <age key>
scripts/restore-drill.sh        # full backup/wipe/restore check in a separate Compose project
```

In this cloud sandbox only: Docker Hub rate-limits, so dockerd uses `mirror.gcr.io`; builds need
`--network host`, the proxy build args and `--secret id=build_ca,src=/root/.ccr/ca-bundle.crt`;
Playwright needs `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium`.

## Conventions

- **Layers.** Business rules live in `domain` (pure) and `services`. API routes, jobs, and later the
  tool registry and assistant only translate and call services. No client gets a private path.
- **Services** take `(db, actor, ...)`, check permissions, write a change record
  (`services.audit.record`) for every domain write, and commit before returning.
- **Household isolation.** Rows of another household raise `NotFound`, never `Forbidden`.
  `tests/api/test_security_matrix.py` walks every OpenAPI operation: new endpoints must be listed as
  public or pass the 401/CSRF checks, and every path parameter needs a cross-household case.
- **Errors** are `DomainError` subclasses with a stable snake_case code. The API returns
  `{"code", "detail"}`; the UI translates `errors.<code>`. A backend test fails if a code has no
  translation in de, en and nl.
- **Strings.** No literal UI text (ESLint `i18next/no-literal-string`). Keys must match across
  `frontend/src/i18n/locales/{de,en,nl}.json` (tested). Server strings (emails, push) live in
  `backend/src/mahlzeit/i18n/messages.py`. German and Dutch drafts are reviewed by Jonas.
- **Time.** Read it through `mahlzeit.clock.now()`; tests move it with the `clock` fixture.
- **Ids** are UUIDv7 from `mahlzeit.ids.uuid7`, generated in the app.
- **Tests first** for domain logic. Service and API tests run against real Postgres, one rolled
  back transaction per test (`tests/conftest.py`). Use `tests/factories.py` to build households.
- **Secrets** come only from the environment; never log them or put them in change records.
  `.env` is never committed; `.env.example` lists every variable.
- **Tools** are registered with `@tool` in `src/mahlzeit/tools/`; every tool needs a case in
  `tests/tools/test_registry.py` (and a cross-household case if it takes ids). The MCP connector
  serves the registry as is.
- **Live updates** come for free: `audit.record` also sends a Postgres NOTIFY, and the app turns
  it into a server-sent event at `/api/events`. When a new entity appears, map its name to the
  query keys to refetch in `frontend/src/features/live/live.ts`.
- **Shopping list writes** are operations with client-made ids (`services.shopping.apply`); the
  UI queues them in an outbox (`features/list/sync.ts`) and never calls the API for list
  writes directly.
- **Open Food Facts** is reached only through `off_client` behind `services.items` (rate limit,
  cache); tests use `tests/fakes.FakeOff`, end-to-end tests `scripts/offstub.py`.
- **Definition of done** for a feature: UI path, registered tools (from M1), tests for both,
  strings in de, en and nl, a line in `docs/decisions.md` for anything the brief left open.
- **Commits** are small and green: run backend lint, mypy, tests and frontend lint, typecheck,
  tests before each commit. Regenerate the API client when the API changes.
