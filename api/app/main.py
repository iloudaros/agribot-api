from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.db import connect_to_db, close_db_connection, connect_to_minio, ensure_minio_bucket

# 1. Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    connect_to_db(app)
    connect_to_minio(app)
    ensure_minio_bucket(app)
    yield
    # Shutdown logic
    close_db_connection(app)

# 2. Pass the lifespan to the FastAPI constructor
app = FastAPI(
    title="AgriBot Data Lake API",
    description="API for ingesting agricultural mission data into the data lake.",
    version="1.0.0",
    lifespan=lifespan
)

# 3. Include the main API router
app.include_router(api_router, prefix="/api/v1")

@app.get("/", summary="API Root", include_in_schema=False)
def read_root():
    return {"message": "Welcome to the AgriBot Data Lake API"}
