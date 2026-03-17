from fastapi import APIRouter

from app.api.v1.endpoints import auth, core, pc1, pc2, pc3,# pc4, pc5, pc6

api_router = APIRouter()

# Authentication
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"],
)

# Core Infrastructure (Stays unchanged)
api_router.include_router(
    core.router,
    prefix="/core",
    tags=["Core Infrastructure"],
)

# Pilot Cases
api_router.include_router(
    pc1.router,
    prefix="/pc1",
    tags=["PC1: Weed Identification & Spot Spraying"],
)

api_router.include_router(
    pc2.router,
    prefix="/pc2",
    tags=["PC2: Robotic Spraying"],
)

api_router.include_router(
    pc3.router,
    prefix="/pc3",
    tags=["PC3: Open Field Monitoring"],
)

# api_router.include_router(
#     pc4.router,
#     prefix="/pc4",
#     tags=["PC4: ..."],
# )


# api_router.include_router(
#     pc5.router,
#     prefix="/pc5",
#     tags=["PC5: Orchards"],
# )

# api_router.include_router(
#     pc6.router,
#     prefix="/pc6",
#     tags=["PC6: Orchards"],
# )
