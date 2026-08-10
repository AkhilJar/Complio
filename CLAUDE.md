# Complio

RAG-based legal compliance assistant. Notifies small businesses
when new bill changes affect their compliance documents.

## Stack

- Backend: FastAPI (Python 3.12)
- Database: PostgreSQL 16 (Docker container)
- ORM: SQLAlchemy + Alembic migrations
- Vector DB: Pinecone (future, hosted — not containerized)
- Frontend: React + Vite (future)

## Commands

- Run full stack: `docker compose up`
- Stop: `docker compose down` (add `-v` to also wipe the database)
- Never run bare `python3` — always through compose
- Test: `docker compose run --rm api pytest`

## Migrations (Alembic, always via compose)

- Generate after model change: `docker compose run --rm api alembic revision --autogenerate -m "message"`
- Apply: `docker compose run --rm api alembic upgrade head`
- Always review the generated migration file before applying

## Tests

- Run everything: `docker compose run --rm api pytest` (add `-v` for per-test output)
- A single file: `docker compose run --rm api pytest tests/test_bill_chunks.py`
- Tests use their own `complio_test` database on the same Postgres server, created
  automatically on first run — the dev database and its ~1000 real bills are never touched
- Schema comes from running the real migrations, not `create_all`, so the tests
  exercise what actually ships (extension, vector column, HNSW index)
- Each test runs inside a transaction that is rolled back, so tests cannot pollute
  each other and nothing survives the run
- CI runs the same suite against a `pgvector/pgvector:pg16-trixie` service container;
  any failing test fails the build

## Database

- Runs in the `db` compose service, data persists in the `pgdata` volume
- Image is `pgvector/pgvector:pg16-trixie` — postgres 16 plus pgvector. The tag must
  stay identical in `docker-compose.yml` and `.github/workflows/ci.yml`; the default
  `pg16` tag is a Debian release behind and its older glibc triggers a collation
  version mismatch against data created under the newer one. CI asserts the two match.
- `bill_chunks` holds the text slices for retrieval, with an `embedding vector(1536)`
  column and an HNSW cosine index. Embeddings are **null for now** — chunking and
  embedding generation are separate, later tasks
- Inside compose, reach it at host `db:5432`; from the Mac (TablePlus), `127.0.0.1:5432`
- Credentials live in `.env` at repo root, injected by compose as environment variables
- `config.py` reads them from the environment, not from a file inside the container
- `.env` is gitignored; `.env.example` is the template

## Conventions

- Raw SQL avoided — models in `database/models.py`, schema flows from them via Alembic
- `api/` imports from `database/`, never the reverse
- Every architectural decision gets a short comment explaining _why_
- Commit format: `feat:` / `fix:` / `chore:`
- Never commit `.env`

## Git workflow

- Trunk-based: branch off `main`, PR, CI must pass, merge, delete branch
- No direct pushes to `main` (branch protection)
- Descriptive branches: `feat/bill-notifications`, `fix/cors`

## Structure

backend/
├── main.py # app factory, router registration
├── config.py # settings from env
├── database/ # session, models
├── api/routes/ # endpoints
└── alembic/ # migrations
