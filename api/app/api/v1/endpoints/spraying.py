import json
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
        SELECT 1
        FROM fields fld
        JOIN farm_ownerships fo
          ON fo.farm_id = fld.farm_id
        WHERE fld.id = %s
          AND fo.user_id = %s
        """,
        (field_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this field",
        )


@router.post("/missions", response_model=SprayingMission, status_code=status.HTTP_201_CREATED)
def create_spraying_mission(
    mission: SprayingMissionCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if mission.mission_type != "pc2_spraying":
        if mission.pc2_properties is not None or mission.pc2_metadata is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="pc2_properties and pc2_metadata are only valid for pc2_spraying missions",
            )

    mission_id = mission.id or str(uuid.uuid4())
    mission_date = mission.mission_date or mission.start_time

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, mission.field_id, user)

        cur.execute(
            """
            INSERT INTO missions
                (id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING
                id,
                commander_id,
                field_id,
                mission_type,
                status,
                start_time,
                end_time,
                mission_date
            """,
            (
                mission_id,
                user.id,
                mission.field_id,
                mission.mission_type,
                mission.status,
                mission.start_time,
                mission.end_time,
                mission_date,
            ),
        )
        new_mission = cur.fetchone()

        if mission.mission_type == "pc2_spraying":
            cur.execute(
                """
                INSERT INTO pc2_spraying_mission (id, properties)
                VALUES (%s, %s::jsonb)
                RETURNING properties AS pc2_properties
                """,
                (mission_id, json.dumps(mission.pc2_properties or {})),
            )
            new_mission["pc2_properties"] = cur.fetchone()["pc2_properties"]

            if mission.pc2_metadata is not None:
                cur.execute(
                    """
                    INSERT INTO pc2_spraying_metadata
                    (
                        id,
                        max_lat,
                        min_lat,
                        max_long,
                        min_long,
                        area_analyzed,
                        average_density,
                        crop_weed_correlation,
                        weed_liquid_correlation
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING
                        max_lat,
                        min_lat,
                        max_long,
                        min_long,
                        area_analyzed,
                        average_density,
                        crop_weed_correlation,
                        weed_liquid_correlation
                    """,
                    (
                        mission_id,
                        mission.pc2_metadata.max_lat,
                        mission.pc2_metadata.min_lat,
                        mission.pc2_metadata.max_long,
                        mission.pc2_metadata.min_long,
                        mission.pc2_metadata.area_analyzed,
                        mission.pc2_metadata.average_density,
                        mission.pc2_metadata.crop_weed_correlation,
                        mission.pc2_metadata.weed_liquid_correlation,
                    ),
                )
                new_mission["pc2_metadata"] = cur.fetchone()
            else:
                new_mission["pc2_metadata"] = None
        else:
            new_mission["pc2_properties"] = None
            new_mission["pc2_metadata"] = None

        conn.commit()

    return new_mission


@router.get("/missions", response_model=List[SprayingMission])
def list_spraying_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                m.id,
                m.commander_id,
                m.field_id,
                m.mission_type,
                m.status,
                m.start_time,
                m.end_time,
                m.mission_date,
                psm.properties AS pc2_properties,
                CASE
                    WHEN pmd.id IS NULL THEN NULL
                    ELSE json_build_object(
                        'max_lat', pmd.max_lat,
                        'min_lat', pmd.min_lat,
                        'max_long', pmd.max_long,
                        'min_long', pmd.min_long,
                        'area_analyzed', pmd.area_analyzed,
                        'average_density', pmd.average_density,
                        'crop_weed_correlation', pmd.crop_weed_correlation,
                        'weed_liquid_correlation', pmd.weed_liquid_correlation
                    )
                END AS pc2_metadata
            FROM missions m
            LEFT JOIN fields fld
                ON fld.id = m.field_id
            LEFT JOIN pc2_spraying_mission psm
                ON psm.id = m.id
            LEFT JOIN pc2_spraying_metadata pmd
                ON pmd.id = m.id
            WHERE m.mission_type IN ('pc1_inspection', 'pc1_spraying', 'pc2_spraying')
              AND (
                    %s = 'admin'
                    OR EXISTS (
                        SELECT 1
                        FROM farm_ownerships own
                        WHERE own.farm_id = fld.farm_id
                          AND own.user_id = %s
                    )
                  )
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="latitude and longitude must either both be provided or both be omitted",
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, field_id, mission_type
            FROM missions
            WHERE id = %s
            """,
            (weed.inspection_id,),
        )
        inspection = cur.fetchone()

        if inspection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection mission not found",
            )

        if inspection["mission_type"] != "pc1_inspection":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Weeds can only be attached to pc1_inspection missions",
            )

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            INSERT INTO pc1_weed
                (inspection_id, name, image, confidence, weed_loc, is_sprayed, spray_time)
            VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    CASE
                        WHEN %s IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    END,
                    %s,
                    %s
                )
            RETURNING
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                is_sprayed,
                spray_time
            """,
            (
                weed.inspection_id,
                weed.name,
                weed.image,
                weed.confidence,
                weed.latitude,
                weed.longitude,
                weed.latitude,
                weed.is_sprayed,
                weed.spray_time,
            ),
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
        cur.execute(
            """
            SELECT id, field_id, mission_type
            FROM missions
            WHERE id = %s
            """,
            (inspection_id,),
        )
        inspection = cur.fetchone()

        if inspection is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection mission not found",
            )

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            SELECT
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                is_sprayed,
                spray_time
            FROM pc1_weed
            WHERE inspection_id = %s
            ORDER BY id
            """,
            (inspection_id,),
        )
        return cur.fetchall()


@router.post("/telemetry", include_in_schema=False)
def telemetry_removed():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="The telemetry batch endpoint was removed because the new schema no longer contains uc1_uc2_telemetry. Store raw PC2 payloads in pc2_spraying_mission.properties.",
    )
