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
    
    
@router.post("", response_model=Mission, status_code=status.HTTP_201_CREATED)
def create_mission(mission: MissionCreate, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    mission_date = mission.mission_date or mission.start_time
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, mission.field_id, user)
        
        # Because the DB and Pydantic match perfectly, we just use the real names and RETURNING *
        cur.execute(
            """
            INSERT INTO missions (commander_id, field_id, mission_type, status, start_time, mission_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user.id, mission.field_id, mission.mission_type, mission.status, mission.start_time, mission_date),
        )
        new_mission = cur.fetchone()
        conn.commit()
    return new_mission

@router.get("", response_model=List[Mission])
def list_missions(conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT m.*
            FROM missions m
            WHERE %s = 'admin' OR EXISTS (
                SELECT 1 FROM field_ownerships own WHERE own.field_id = m.field_id AND own.user_id = %s
            ) ORDER BY start_time DESC NULLS LAST
            """, (user.role or "", user.id),
        )
        return cur.fetchall()

@router.patch("/{mission_id}", response_model=Mission)
def update_mission(mission_id: int, update_data: MissionUpdate, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    update_fields = {k: v for k, v in update_data.dict(exclude_unset=True).items() if v is not None}
    if not update_fields: raise HTTPException(status_code=400, detail="No fields provided")
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission_row = cur.fetchone()
        if not mission_row: raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission_row["field_id"], user)

        set_clauses = [f"{k} = %s" for k in update_fields.keys()]
        values = list(update_fields.values()) + [mission_id]
        
        cur.execute(
            f"""
            UPDATE missions SET {", ".join(set_clauses)} WHERE id = %s
            RETURNING *
            """, tuple(values)
        )
        updated_mission = cur.fetchone()
        conn.commit()
    return updated_mission
