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
    """FastAPI dependency: one transaction per request, committed on success, rolled back on error.
    Serverless (Vercel): open one short connection per request instead of a pool, because instances are frozen between
    requests and a pooled connection would be dead on wake-up. prepare_threshold=None keeps it compatible with a pooled
    database endpoint (Neon's '-pooler' host)."""
    if config.SERVERLESS:
        with psycopg.connect(config.DATABASE_URL, row_factory=dict_row, prepare_threshold=None, connect_timeout=15) as cx:
            yield cx
        return
    with pool().connection() as cx:
        yield cx
