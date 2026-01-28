from fastapi import FastAPI
from app.api.v1.api import api_router
from app.core.db import connect_to_db, close_db_connection, connect_to_minio

app = FastAPI(
    title="AgriBot Data Lake API",
    description="API for ingesting agricultural mission and sensor data into the data lake.",
    version="1.0.0"
)

# Event handlers manage the lifecycle of the DB pool and Minio client
app.add_event_handler("startup", lambda: connect_to_db(app))
app.add_event_handler("startup", lambda: connect_to_minio(app))
app.add_event_handler("shutdown", lambda: close_db_connection(app))

# Include the main API router
app.include_router(api_router, prefix="/api/v1")

@app.get("/", summary="API Root", include_in_schema=False)
def read_root():
    return {"message": "Welcome to the AgriBot Data Lake API"}

