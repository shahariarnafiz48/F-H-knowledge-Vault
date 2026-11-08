from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from . import config
_pool = None
def pool():
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)
    return _pool
def get_db():
    """FastAPI dependency: one transaction per request, committed on success, rolled back on error."""
    with pool().connection() as cx:
        yield cx
