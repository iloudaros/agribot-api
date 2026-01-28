from fastapi import APIRouter
from .endpoints import missions, images, token

api_router = APIRouter()

api_router.include_router(token.router, prefix="/token", tags=["Authentication"])
api_router.include_router(missions.router, prefix="/missions", tags=["Missions"])
api_router.include_router(images.router, tags=["Images & Predictions"])
