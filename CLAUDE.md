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
- Test: `docker compose run --rm api pytest`
- Never run bare `python3` — always through compose

## Migrations (Alembic, always via compose)

- Generate after model change: `docker compose run --rm api alembic revision --autogenerate -m "message"`
- Apply: `docker compose run --rm api alembic upgrade head`
- Always review the generated migration file before applying

## Database

- Runs in the `db` compose service, data persists in the `pgdata` volume
- Inside compose, reach it at host `db:5432`; from the Mac (TablePlus), `127.0.0.1:5432`
- Credentials in `.env` (gitignored); `.env.example` is the template

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
