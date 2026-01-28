from fastapi import FastAPI, Request
from psycopg2.pool import SimpleConnectionPool
from minio import Minio
from .config import settings

def connect_to_db(app: FastAPI):
    """Create a connection pool and store it in the app state."""
    app.state.db_pool = SimpleConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@{settings.POSTGRES_SERVER}/{settings.POSTGRES_DB}"
    )

def close_db_connection(app: FastAPI):
    """Close all connections in the pool."""
    if hasattr(app.state, 'db_pool'):
        app.state.db_pool.closeall()

def get_db_conn(request: Request):
    """
    FastAPI dependency to get a connection from the pool and
    ensure it is returned, even if an error occurs.
    """
    conn = request.app.state.db_pool.getconn()
    try:
        yield conn
    finally:
        request.app.state.db_pool.putconn(conn)

def connect_to_minio(app: FastAPI):
    """Create a Minio client and store it in the app state."""
    app.state.minio_client = Minio(
        settings.MINIO_SERVER,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False
    )
