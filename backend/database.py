import psycopg2
import psycopg2.extras  # gives us dict-like rows instead of plain tuples
import os
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """
    Opens and returns a new PostgreSQL connection.

    WHY not one global connection?
    Database connections can time out or go stale.
    Opening a connection per request and closing it after is safer.
    For higher traffic we would use a connection pool (psycopg2.pool).
    That is a Sprint 3 optimization — not needed for one user.
    """
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def query(sql, params=None, fetch="all"):
    """
    Run any SQL query and return results.

    Args:
        sql:    The SQL string. Use %s for parameters, never f-strings.
                WHY? f-strings allow SQL injection. %s uses parameterized
                queries — psycopg2 sanitizes the values before sending to DB.

                Example of SQL injection risk:
                  BAD:  f"SELECT * FROM users WHERE id = {user_id}"
                        A user could pass: "1; DROP TABLE users; --"
                        That f-string would execute the DROP.
                  GOOD: "SELECT * FROM users WHERE id = %s", (user_id,)
                        psycopg2 escapes the value so it is always treated
                        as data, never as SQL code.

        params: Tuple of values to substitute for %s placeholders.
                Must be a tuple even for one value: (value,) not (value).
        fetch:  "all" returns all rows, "one" returns one row, None for writes.

    Returns rows as dictionaries so you can do row["name"] not row[0].
    """
    conn = get_connection()
    try:
        # RealDictCursor returns rows as dicts instead of plain tuples.
        # row["name"] instead of row[0] — much more readable.
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)

            if fetch == "all":
                result = cur.fetchall()
            elif fetch == "one":
                result = cur.fetchone()
            else:
                # fetch=None means this is a write (INSERT/UPDATE/DELETE).
                # No rows to return.
                result = None

            # commit() saves INSERT/UPDATE/DELETE changes permanently.
            # Without commit(), changes are rolled back when connection closes.
            # SELECT queries do not need commit but it does not hurt.
            conn.commit()
            return result
    finally:
        # Always close the connection even if an exception occurs.
        # The finally block runs whether or not an exception was raised.
        conn.close()


def insert_returning(sql, params):
    """
    Run an INSERT ... RETURNING statement and return the new row.

    Used when we need the generated UUID or timestamp back after insert.
    PostgreSQL's RETURNING clause lets us get the inserted row in one
    round trip instead of inserting then immediately querying.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            result = cur.fetchone()
            conn.commit()
            return result
    finally:
        conn.close()
