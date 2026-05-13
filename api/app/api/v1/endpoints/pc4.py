from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import PC4MonitoringPayload, PC4ChannelData
from app.security import UserInDB, get_current_active_user

router = APIRouter()

def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return
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
            detail="You do not have access to this field",
        )


@router.post("/missions/{mission_id}/monitor", status_code=status.HTTP_201_CREATED)
def upload_pc4_monitoring_data(
    mission_id: int,
    payload: PC4MonitoringPayload,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Upload PC4 channel monitoring data (Biomass, Fruit Quality, Growth Insight).
    """
    if not payload.channels:
        return {"message": "No channel data provided"}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Verify Mission and Access
        cur.execute("SELECT field_id, mission_type FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        if mission["mission_type"] != "pc4_monitoring":
            raise HTTPException(status_code=400, detail="Data can only be attached to a pc4_monitor mission")
            
        # Optional validation: ensure the JSON parcel_id matches the DB field_id
        if payload.parcel_id and payload.parcel_id != mission["field_id"]:
            raise HTTPException(status_code=400, detail=f"Payload parcel_id ({payload.parcel_id}) does not match mission field_id ({mission['field_id']})")

        _ensure_field_access(cur, mission["field_id"], user)

        # 2. Prepare Bulk Insert
        query = """
            INSERT INTO pc4_monitoring (
                mission_id, channel_name, biomass, fruit_quality, growth_insight
            ) VALUES %s
        """
        
        data_tuples = [
            (
                mission_id,
                channel.channelName,
                channel.biomass,
                channel.fruitQuality,
                channel.growthInsight
            )
            for channel in payload.channels
        ]

        # 3. Execute
        execute_values(cur, query, data_tuples)
        conn.commit()

    return {"message": f"Successfully inserted {len(payload.channels)} channel records."}


@router.get("/missions/{mission_id}/monitor")
def get_pc4_monitoring_data(
    mission_id: int,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Retrieve all monitoring channel data for a specific PC4 mission.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute(
            """
            SELECT 
                id, mission_id, channel_name, biomass, fruit_quality, growth_insight
            FROM pc4_monitoring 
            WHERE mission_id = %s
            ORDER BY id
            """,
            (mission_id,)
        )
        return cur.fetchall()
