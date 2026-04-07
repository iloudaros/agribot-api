from fastapi import FastAPI, Request
from psycopg2.pool import SimpleConnectionPool
from minio import Minio

from .config import settings


def connect_to_db(app: FastAPI):
    """
    Create the PostgreSQL connection pool and store it in app.state.

    This pool is shared by all incoming requests.
    """
    app.state.db_pool = SimpleConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=(
            f"postgresql://{settings.POSTGRES_USER}:"
            f"{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_SERVER}/"
            f"{settings.POSTGRES_DB}"
        ),
    )


def close_db_connection(app: FastAPI):
    """
    Close all pooled PostgreSQL connections during application shutdown.
    """
    if hasattr(app.state, 'db_pool'):
        app.state.db_pool.closeall()


def get_db_conn(request: Request):
    """
    FastAPI dependency that retrieves a database connection from the pool
    and always returns it afterwards.
    """
    conn = request.app.state.db_pool.getconn()
    try:
        yield conn
    finally:
        request.app.state.db_pool.putconn(conn)


def connect_to_minio(app: FastAPI):
    """
    Create two MinIO clients and store them in app.state.

    Why two clients?

    * minio_internal_client:
        Used by the API backend for real server-side MinIO operations such as:
        - bucket_exists
        - make_bucket
        - object metadata checks

        This must point to the INTERNAL Kubernetes service DNS.

    * minio_public_client:
        Used only for generating presigned URLs that are returned to external
        clients (connector, browser, frontend). These URLs must contain a host
        that the external client can actually reach.

        In local development this is typically 127.0.0.1:9000.
    """
    app.state.minio_internal_client = Minio(
        settings.MINIO_INTERNAL_SERVER,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
    )

    app.state.minio_public_client = Minio(
        settings.MINIO_PUBLIC_SERVER,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=False,
        region="us-east-1",
    )


def ensure_minio_bucket(app: FastAPI, bucket_name: str = "agribot-mission-images"):
    """
    Ensure the required MinIO bucket exists.

    This runs once at startup using the INTERNAL MinIO client.
    """
    minio_internal_client = app.state.minio_internal_client

    try:
        if not minio_internal_client.bucket_exists(bucket_name):
            minio_internal_client.make_bucket(bucket_name)
    except Exception as e:
        print(f"Warning: could not ensure MinIO bucket '{bucket_name}': {e}")
