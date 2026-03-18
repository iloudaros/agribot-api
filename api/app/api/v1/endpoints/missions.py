import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import Mission, MissionCreate, MissionUpdate
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You do not have access to this field"
        )


@router.post("", response_model=Mission, status_code=status.HTTP_201_CREATED)
def create_mission(
    mission: MissionCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    mission_id = mission.id or str(uuid.uuid4())
    mission_date = mission.mission_date or mission.start_time

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, mission.field_id, user)

        cur.execute(
            """
            INSERT INTO missions
                (id, commander_id, field_id, mission_type, status, start_time, mission_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date
            """,
            (
                mission_id, user.id, mission.field_id, mission.mission_type, 
                mission.status, mission.start_time, mission_date
            ),
        )
        new_mission = cur.fetchone()
        conn.commit()

    return new_mission


@router.get("", response_model=List[Mission])
def list_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT m.*
            FROM missions m
            JOIN fields fld ON fld.id = m.field_id
            WHERE %s = 'admin' OR EXISTS (
                SELECT 1 FROM farm_ownerships own
                WHERE own.farm_id = fld.farm_id AND own.user_id = %s
            )
            ORDER BY m.start_time DESC NULLS LAST
            """,
            (user.role or "", user.id),
        )
        return cur.fetchall()


@router.patch("/{mission_id}", response_model=Mission)
def update_mission(
    mission_id: str,
    update_data: MissionUpdate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    # Filter out None values so we only update what was actually provided
    update_fields = {k: v for k, v in update_data.dict(exclude_unset=True).items() if v is not None}
    
    if not update_fields:
        raise HTTPException(status_code=400, detail="No valid fields provided for update")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Verify existence and ownership
        cur.execute(
            """
            SELECT m.field_id 
            FROM missions m
            WHERE m.id = %s
            """, 
            (mission_id,)
        )
        mission_row = cur.fetchone()
        
        if not mission_row:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission_row["field_id"], user)

        # 2. Build the dynamic update query
        set_clauses = []
        values = []
        for key, value in update_fields.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
            
        values.append(mission_id) # For the WHERE clause
        set_query = ", ".join(set_clauses)

        cur.execute(
            f"""
            UPDATE missions
            SET {set_query}
            WHERE id = %s
            RETURNING id, commander_id, field_id, mission_type, status, start_time, end_time, mission_date
            """,
            tuple(values),
        )
        updated_mission = cur.fetchone()
        conn.commit()

    return updated_mission
