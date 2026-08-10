# Complio

RAG-based legal compliance assistant. Notifies small businesses when new bill changes affect their compliance documents.

The current build covers the data foundation: ingesting Texas bill text into Postgres and standing up object storage. Retrieval, embeddings, and notifications come later.

## Stack

| Layer | Choice | Notes |
| --- | --- | --- |
| API | FastAPI (Python 3.12) | `/health` only so far |
| Database | PostgreSQL 16 | runs in the `db` compose service |
| ORM / migrations | SQLAlchemy 2 + Alembic | schema flows from models, no raw DDL |
| Object storage | MinIO | S3-compatible, driven with boto3 |
| Bill ingestion | ftplib + BeautifulSoup | Texas Legislature anonymous FTP |
| Tests | pytest | run inside the container |
| Vector DB | Pinecone | future, hosted — not containerized |
| Frontend | React + Vite | future |

MinIO is S3-compatible and accessed through boto3, so the same client code runs against real S3 or Cloudflare R2 at deploy time by changing the endpoint and credentials — no code change.

## Getting started

```bash
cp .env.example .env      # then fill in real values
docker compose up
```

`.env` is gitignored and never committed. `config.py` reads these from the environment, not from a file inside the container.

| Service | URL | Purpose |
| --- | --- | --- |
| api | http://localhost:8000 | FastAPI (`/health`, `/docs`) |
| db | `127.0.0.1:5432` | Postgres — connect from TablePlus here |
| minio | http://localhost:9000 | S3 API |
| minio console | http://localhost:9001 | browser UI, log in with the root credentials |

Inside the compose network, services reach each other by name (`db:5432`, `http://minio:9000`) — not `localhost`.

## Commands

```bash
docker compose up                      # run the full stack
docker compose down                    # stop (add -v to also wipe volumes)
docker compose run --rm api pytest     # run tests
```

Never run bare `python3` — everything goes through compose so it picks up the right environment and can reach `db` and `minio`.

## Structure

```
backend/
├── main.py              # app factory, router registration
├── config.py            # settings from env
├── conftest.py          # puts /app on sys.path for tests
├── database/            # session, models
├── api/routes/          # endpoints
├── ingest/tx/           # texas legislature ftp ingestion
├── storage/             # boto3 / minio client
├── tests/
└── alembic/             # migrations
```

Dependency direction is one-way: `api/` and `ingest/` import from `database/`, never the reverse.

## Data model

Two tables, joined by a foreign key.

**`bills`** — one row per bill seen on the FTP site.

| Column | Type | Notes |
| --- | --- | --- |
| `bill_id` | TEXT PK | natural key, e.g. `89R_HB1` |
| `session` | TEXT | e.g. `89r` |
| `bill_type` | TEXT | `house_bills` / `senate_bills` |
| `bill_number` | TEXT | `HB1` |
| `title` | TEXT | bill caption, nullable — not always present |
| `fetched_at` | TIMESTAMPTZ | |

**`bill_texts`** — the bill's text, verbatim and extracted.

| Column | Type | Notes |
| --- | --- | --- |
| `text_id` | UUID PK | |
| `bill_id` | TEXT FK → `bills.bill_id` | unique, so one text per bill |
| `raw_html` | TEXT | kept as-is, so re-extraction never needs a re-fetch |
| `extracted_text` | TEXT | plain text pulled from the HTML |
| `text_hash` | TEXT | sha256 of `raw_html`, to detect change |
| `fetched_at` | TIMESTAMPTZ | |

The natural key exists because the legislature already assigns every bill a stable identifier — a surrogate id would add indirection without value. `text_hash` is taken over the HTML rather than the extracted text so a change is still caught if the extraction logic changes.

v1 keeps **one text row per bill**: a re-fetch overwrites in place rather than appending a version. The unique constraint on `bill_texts.bill_id` gives the upsert its conflict target, which makes the ingest safe to re-run.

## Bill ingestion

Source is the Texas Legislature anonymous FTP site (`ftp.legis.state.tx.us`) — not a JSON API, and deliberately not the website. Their acceptable-use file states the TLC *"requires that legislative data services companies stop data mining the www.legis.state.tx.us site"*; the FTP exists so consumers don't have to scrape. No API key, anonymous login.

Path layout:

```
/bills/<session>/billtext/html/<bill type>/<grouping of 100>/<file>.htm
/bills/89r/billtext/html/house_bills/HB00001_HB00099/HB00002I.htm
```

The trailing letter is the version: `I`=Introduced, `H`/`S`=Committee Report, `E`=Engrossed, `F`=Enrolled. **The ingest takes Introduced only** — every filed bill has one, while later stages exist only for bills that advanced.

```bash
docker compose run --rm api python -m ingest.tx.fetch --limit 10
docker compose run --rm api python -m ingest.tx.fetch --limit 100 --bill-type senate_bills
```

Behavior worth knowing:

- **Nothing touches the host filesystem.** Downloads stream through memory into Postgres; the database is the only store.
- **Polite by default** — a delay between FTP requests (`tx_ftp_delay`), and retries that reconnect, since control connections drop on long runs.
- **PDF-only bills are skipped.** Some bills ship an HTML placeholder reading "An HTML version of this bill is not available"; storing that boilerplate would be worse than storing nothing. Skips don't count toward `--limit`.
- **Commits per bill**, so an interrupted run keeps what it fetched and re-running resumes without duplicates.

## Object storage

MinIO runs as a compose service with its objects in the `miniodata` volume. `backend/storage/client.py` is a thin boto3 wrapper — create bucket, upload, download — with no document- or bill-specific logic yet.

Path-style addressing is set explicitly because the bucket-as-subdomain form doesn't resolve for a compose service name. The MinIO root credentials double as the S3 access key and secret key.

## Database migrations (Alembic)

Schema changes are versioned with Alembic and run inside the container, so they always connect to Postgres at `db:5432` with no local setup.

**After changing a model** in `backend/database/models.py`:

```bash
# 1. generate a migration from the model changes
docker compose run --rm api alembic revision --autogenerate -m "describe the change"

# 2. review the generated file in backend/alembic/versions/ before applying

# 3. apply it to the database
docker compose run --rm api alembic upgrade head
```

**Other commands:**

```bash
docker compose run --rm api alembic downgrade -1   # roll back the most recent migration
docker compose run --rm api alembic current        # see current migration state
docker compose run --rm api alembic history        # view migration history
```

Always review autogenerated migrations before applying — Alembic can miss renames or propose unintended drops. Never edit a migration that's already been applied and committed; create a new one instead.

## Conventions

- Raw SQL avoided — models live in `database/models.py` and the schema flows from them via Alembic.
- Every architectural decision gets a short comment explaining *why*.
- Commit format: `feat:` / `fix:` / `chore:`.
- Never commit `.env`.

## Git workflow

Trunk-based: branch off `main`, open a PR, CI must pass, merge, delete the branch. No direct pushes to `main` (branch protection). Branch names describe the work: `feat/tx-bill-ingest`, `fix/cors`.
