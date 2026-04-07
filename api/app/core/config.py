from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # PostgreSQL configuration
    # ------------------------------------------------------------------
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "supersecretpassword"
    POSTGRES_SERVER: str = "agribot-postgres-postgresql.agribot-dev.svc.cluster.local"
    POSTGRES_DB: str = "postgres"

    # ------------------------------------------------------------------
    # MinIO configuration
    #
    # We keep two different endpoints:
    #
    # 1. MINIO_INTERNAL_SERVER
    #    Used by the API pod itself to communicate with MinIO from inside
    #    the Kubernetes cluster. This is the service DNS name.
    #
    # 2. MINIO_PUBLIC_SERVER
    #    Used only for generating presigned URLs that will be consumed by
    #    clients running outside the cluster, such as:
    #    * local connector scripts
    #    * browsers / frontend apps
    #
    # In local development, this is typically 127.0.0.1:9000 because we
    # port-forward the MinIO API service to localhost.
    # ------------------------------------------------------------------
    MINIO_INTERNAL_SERVER: str = "agribot-minio.agribot-dev.svc.cluster.local:9000"
    MINIO_PUBLIC_SERVER: str = "127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123"

    class Config:
        env_file = ".env"


settings = Settings()
