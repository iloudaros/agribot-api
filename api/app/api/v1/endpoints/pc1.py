import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import SprayingMission, SprayingMissionCreate, Weed, WeedCreate
from app.security import UserInDB, get_current_active_user

router = APIRouter()

def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return
    cur.execute(
        """
        SELECT 1 FROM fields fld
        JOIN farm_ownerships fo ON fo.farm_id = fld.farm_id
        WHERE fld.id = %s AND fo.user_id = %s
        """,
        (field_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this field")


@router.post("/missions", response_model=SprayingMission, status_code=status.HTTP_201_CREATED)
def create_pc1_mission(
    mission: SprayingMissionCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if mission.mission_type not in ["pc1_inspection", "pc1_spraying"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Endpoint only accepts pc1_inspection or pc1_spraying mission types",
        )

    mission_id = mission.id or str(uuid.uuid4())
    mission_date = mission.mission_date or mission.start_time

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, mission.field_id, user)

        cur.execute(
            """
            INSERT INTO missions
                (id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date
            """,
            (mission_id, user.id, mission.field_id, mission.mission_type, mission.status, mission.start_time, mission.end_time, mission_date),
        )
        new_mission = cur.fetchone()
        new_mission["pc2_properties"] = None
        new_mission["pc2_metadata"] = None
        conn.commit()

    return new_mission


@router.get("/missions", response_model=List[SprayingMission])
def list_pc1_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT m.*, NULL as pc2_properties, NULL as pc2_metadata
            FROM missions m
            JOIN fields fld ON fld.id = m.field_id
            WHERE m.mission_type IN ('pc1_inspection', 'pc1_spraying')
              AND (%s = 'admin' OR EXISTS (
                    SELECT 1 FROM farm_ownerships own
                    WHERE own.farm_id = fld.farm_id AND own.user_id = %s
                  ))
            ORDER BY m.start_time DESC NULLS LAST, m.id
            """,
            (user.role or "", user.id),
        )
        return cur.fetchall()


@router.post("/weeds", response_model=Weed, status_code=status.HTTP_201_CREATED)
def create_pc1_weed(
    weed: WeedCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if (weed.latitude is None) != (weed.longitude is None):
        raise HTTPException(status_code=400, detail="latitude and longitude must either both be provided or omitted")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, field_id, mission_type FROM missions WHERE id = %s", (weed.inspection_id,))
        inspection = cur.fetchone()

        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection mission not found")
        if inspection["mission_type"] != "pc1_inspection":
            raise HTTPException(status_code=400, detail="Weeds can only be attached to pc1_inspection missions")

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            INSERT INTO pc1_weed (inspection_id, name, image, confidence, weed_loc, is_sprayed, spray_time)
            VALUES (%s, %s, %s, %s, CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END, %s, %s)
            RETURNING id, inspection_id, name, image, confidence, ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, is_sprayed, spray_time
            """,
            (weed.inspection_id, weed.name, weed.image, weed.confidence, weed.latitude, weed.longitude, weed.latitude, weed.is_sprayed, weed.spray_time),
        )
        new_weed = cur.fetchone()
        conn.commit()

    return new_weed


@router.get("/weeds/{inspection_id}", response_model=List[Weed])
def list_pc1_weeds(
    inspection_id: str,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, field_id FROM missions WHERE id = %s", (inspection_id,))
        inspection = cur.fetchone()
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            SELECT id, inspection_id, name, image, confidence, ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, is_sprayed, spray_time
            FROM pc1_weed WHERE inspection_id = %s ORDER BY id
            """,
            (inspection_id,),
        )
        return cur.fetchall()
