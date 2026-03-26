import json
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import Mission
from app.security import UserInDB, get_current_active_user

router = APIRouter()

def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return
    
    # Simple, direct check against the new table structure (No JOIN needed)
    cur.execute(
        """
        SELECT 1 FROM field_ownerships
        WHERE field_id = %s AND user_id = %s
        """,
        (field_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You do not have access to this field"
        )

# @router.post("/missions", response_model=SprayingMission, status_code=status.HTTP_201_CREATED)
# def create_pc2_mission(
#     mission: SprayingMissionCreate,
#     conn=Depends(get_db_conn),
#     user: UserInDB = Depends(get_current_active_user),
# ):
#     if mission.mission_type != "pc2_spraying":
#         raise HTTPException(status_code=400, detail="Endpoint only accepts pc2_spraying mission types")

#     mission_id = mission.id or str(uuid.uuid4())
#     mission_date = mission.mission_date or mission.start_time

#     with conn.cursor(cursor_factory=RealDictCursor) as cur:
#         _ensure_field_access(cur, mission.field_id, user)

#         # Core Mission
#         cur.execute(
#             """
#             INSERT INTO missions (id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date)
#             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#             RETURNING id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date
#             """,
#             (mission_id, user.id, mission.field_id, mission.mission_type, mission.status, mission.start_time, mission.end_time, mission_date),
#         )
#         new_mission = cur.fetchone()

#         # PC2 Properties
#         cur.execute(
#             """
#             INSERT INTO pc2_spraying_mission (id, properties) VALUES (%s, %s::jsonb)
#             RETURNING properties AS pc2_properties
#             """,
#             (mission_id, json.dumps(mission.pc2_properties or {})),
#         )
#         new_mission["pc2_properties"] = cur.fetchone()["pc2_properties"]

#         # PC2 Metadata
#         if mission.pc2_metadata is not None:
#             cur.execute(
#                 """
#                 INSERT INTO pc2_spraying_metadata 
#                 (id, max_lat, min_lat, max_long, min_long, area_analyzed, average_density, crop_weed_correlation, weed_liquid_correlation)
#                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
#                 RETURNING max_lat, min_lat, max_long, min_long, area_analyzed, average_density, crop_weed_correlation, weed_liquid_correlation
#                 """,
#                 (mission_id, mission.pc2_metadata.max_lat, mission.pc2_metadata.min_lat, mission.pc2_metadata.max_long, 
#                  mission.pc2_metadata.min_long, mission.pc2_metadata.area_analyzed, mission.pc2_metadata.average_density, 
#                  mission.pc2_metadata.crop_weed_correlation, mission.pc2_metadata.weed_liquid_correlation),
#             )
#             new_mission["pc2_metadata"] = cur.fetchone()
#         else:
#             new_mission["pc2_metadata"] = None

#         conn.commit()

#     return new_mission


@router.get("/missions", response_model=List[Mission])
def list_pc2_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user.role == "admin":
            cur.execute(
                """
                SELECT id, commander_id, field_id, mission_type, status, start_time, end_time
                FROM missions
                WHERE mission_type = 'pc2_spraying'
                ORDER BY start_time DESC
                """
            )
        else:
            cur.execute(
                """
                SELECT m.id, m.commander_id, m.field_id, m.mission_type, m.status, m.start_time, m.end_time
                FROM missions m
                JOIN field_ownerships fo ON m.field_id = fo.field_id
                WHERE m.mission_type = 'pc2_spraying' AND fo.user_id = %s
                ORDER BY m.start_time DESC
                """,
                (user.id,)
            )
        missions = cur.fetchall()


@router.post("/telemetry", include_in_schema=False)
def telemetry_removed():
    raise HTTPException(status_code=410, detail="The telemetry batch endpoint was removed.")
