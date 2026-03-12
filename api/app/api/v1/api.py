from fastapi import APIRouter

from app.api.v1.endpoints import token, core, spraying, monitoring, orchards

api_router = APIRouter()

# Authentication
api_router.include_router(
    token.router,
    prefix="/token",
    tags=["Authentication"],
)

# Core Infrastructure
api_router.include_router(
    core.router,
    prefix="/core",
    tags=["Core Infrastructure"],
)

# Use Case Groups
api_router.include_router(
    spraying.router,
    prefix="/spraying",
    tags=["UC1/2: Spraying"],
)

api_router.include_router(
    monitoring.router,
    prefix="/monitoring",
    tags=["UC3/4: Monitoring"],
)

api_router.include_router(
    orchards.router,
    prefix="/orchards",
    tags=["UC5/6: Orchards"],
)
