from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "supersecretpassword"
    POSTGRES_SERVER: str = "agribot-postgres-postgresql.agribot-dev.svc.cluster.local"
    POSTGRES_DB: str = "postgres"
    MINIO_SERVER: str = "agribot-minio.agribot-dev.svc.cluster.local:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "minio123"

    class Config:
        env_file = ".env"

settings = Settings()
