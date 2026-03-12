import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import MonitoringInspection, MonitoringInspectionCreate
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


@router.post("/inspections", response_model=MonitoringInspection, status_code=status.HTTP_201_CREATED)
@router.post("/observations", response_model=MonitoringInspection, status_code=status.HTTP_201_CREATED, deprecated=True)
def create_inspection(
    inspection: MonitoringInspectionCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    inspection_id = inspection.id or str(uuid.uuid4())
    mission_date = inspection.mission_date or inspection.start_time

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, inspection.field_id, user)

        cur.execute(
            """
            INSERT INTO missions
                (id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date)
            VALUES
                (%s, %s, %s, 'pc3_inspection', %s, %s, %s, %s)
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
                inspection_id,
                user.id,
                inspection.field_id,
                inspection.status,
                inspection.start_time,
                inspection.end_time,
                mission_date,
            ),
        )
        mission_row = cur.fetchone()

        cur.execute(
            """
            INSERT INTO pc3_inspections (id, location, biomass, ndvi)
            VALUES (
                %s,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                %s,
                %s
            )
            RETURNING
                ST_Y(location) AS latitude,
                ST_X(location) AS longitude,
                biomass,
                ndvi
            """,
            (
                inspection_id,
                inspection.longitude,
                inspection.latitude,
                inspection.biomass,
                inspection.ndvi,
            ),
        )
        inspection_row = cur.fetchone()

        conn.commit()

    mission_row.update(inspection_row)
    return mission_row


@router.get("/inspections", response_model=List[MonitoringInspection])
def list_inspections(
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
                ST_Y(pc3.location) AS latitude,
                ST_X(pc3.location) AS longitude,
                pc3.biomass,
                pc3.ndvi
            FROM missions m
            JOIN pc3_inspections pc3
              ON pc3.id = m.id
            JOIN fields fld
              ON fld.id = m.field_id
            WHERE m.mission_type = 'pc3_inspection'
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
