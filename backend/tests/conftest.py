import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import settings

#a database of its own, so a test run can never see — let alone delete —
#the thousand real bills sitting in the dev database
TEST_DB_NAME = "complio_test"

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _server_url(database: str) -> str:
    """Same postgres server as the app, pointed at a different database."""
    base, _, _ = settings.database_url.rpartition("/")
    return f"{base}/{database}"


def test_database_url() -> str:
    return settings.test_database_url or _server_url(TEST_DB_NAME)


@pytest.fixture(scope="session")
def engine():
    url = test_database_url()

    #CREATE DATABASE cannot run inside a transaction, hence autocommit, and
    #it has to be issued from a different database — 'postgres' always exists
    admin = create_engine(_server_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        ).scalar()
        if not exists:
            #identifier cannot be parameterised; the name is a constant above
            connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()

    #build the schema by running the real migrations rather than
    #Base.metadata.create_all — that way the tests exercise what actually
    #ships, including the extension and the hnsw index
    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    #env.py reads the url from the environment, so this is how it is aimed
    #at the test database
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    test_engine = create_engine(url)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine):
    """A session whose writes are always rolled back.

    Every test gets a clean database without the cost of re-migrating: the
    outer transaction is never committed, so nothing a test writes survives
    it or leaks into the next one.
    """
    connection = engine.connect()
    transaction = connection.begin()
    #create_savepoint keeps an explicit rollback inside a test (after an
    #expected IntegrityError, say) from tearing down the outer transaction
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
