from typing import List
from fastapi import APIRouter, Depends
from psycopg2.extras import RealDictCursor, execute_values
from app.core.db import get_db_conn
from app.models.schemas import SprayingMissionCreate, TelemetryPoint
from app.security import get_current_active_user, UserInDB
import json

router = APIRouter()

@router.post("/missions", status_code=201)
def create_spraying_mission(
    mission: SprayingMissionCreate, 
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            INSERT INTO uc1_uc2_missions 
            (robot_id, field_id, mission_type, start_time, end_time, travelled_distance_m, 
             covered_area_m2, sprayed_fluid_l, target_fluid_density_lpha, cultivation_method)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
        """, (
            mission.robot_id, mission.field_id, mission.mission_type, 
            mission.start_time, mission.end_time, mission.travelled_distance_m,
            mission.covered_area_m2, mission.sprayed_fluid_l, 
            mission.target_fluid_density_lpha, mission.cultivation_method
        ))
        new_mission = cur.fetchone()
        conn.commit()
    return new_mission

@router.post("/telemetry")
def upload_telemetry_batch(
    points: List[TelemetryPoint], 
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    if not points:
        return {"message": "No points to insert"}

    # Prepare data for bulk insertion
    data_tuples = [
        (
            p.mission_id, p.timestamp, p.latitude, p.longitude, 
            p.speed_mps, p.spray_pressure_bar, p.flow_rate_lpm, 
            json.dumps(p.raw_status_json) if p.raw_status_json else None
        )
        for p in points
    ]

    with conn.cursor() as cur:
        query = """
            INSERT INTO uc1_uc2_telemetry 
            (mission_id, timestamp, latitude, longitude, speed_mps, spray_pressure_bar, flow_rate_lpm, raw_status_json)
            VALUES %s
        """
        execute_values(cur, query, data_tuples)
        conn.commit()
        
    return {"message": f"Inserted {len(points)} telemetry points"}
