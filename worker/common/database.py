"""One function: open a connection to the Postgres database."""
from common.settings import load_settings


def connect():
    """Open a connection. Changes are saved immediately (autocommit)."""
    import psycopg
    from pgvector.psycopg import register_vector

    connection = psycopg.connect(load_settings().database_url, autocommit=True)
    register_vector(connection)  # lets us send and receive vectors
    return connection
