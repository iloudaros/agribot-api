from fastapi import APIRouter, Depends
from psycopg2.extras import RealDictCursor
from app.core.db import get_db_conn
from app.models.schemas import MonitoringObservationCreate
from app.security import get_current_active_user, UserInDB
import json

router = APIRouter()

@router.post("/observations", status_code=201)
def create_observation(
    obs: MonitoringObservationCreate, 
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            INSERT INTO uc3_uc4_observations 
            (robot_id, field_id, timestamp, latitude, longitude, altitude_m, 
             avg_foliage_area_cm2, avg_ndvi, avg_volume_cm3, raw_data_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            obs.robot_id, obs.field_id, obs.timestamp, obs.latitude, obs.longitude,
            obs.altitude_m, obs.avg_foliage_area_cm2, obs.avg_ndvi, obs.avg_volume_cm3,
            json.dumps(obs.raw_data_json) if obs.raw_data_json else None
        ))
        new_id = cur.fetchone()['id']
        conn.commit()
    return {"id": new_id, "message": "Observation recorded"}
