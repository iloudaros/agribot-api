from typing import List, Annotated
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import execute_values, RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import MissionCreate, RobotState, AgriEvent, Mission
from app.security import get_current_active_user, UserInDB

router = APIRouter()

@router.post("/", summary="Create a new mission summary", response_model=Mission, status_code=201)
def create_mission(
    mission: MissionCreate,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        mission_data = (
            mission.robot_id, mission.field_id, current_user.id, mission.mission_type,
            mission.start_time, mission.end_time, mission.travelled_distance_m,
            mission.covered_area_m2, mission.sprayed_fluid_l, mission.target_fluid_density_lpha,
            mission.setpoint_pressure_bar, mission.cultivation_method, mission.inference_model,
            mission.context_crop_id, mission.target_id, mission.min_latitude,
            mission.max_latitude, mission.min_longitude, mission.max_longitude,
            mission.crop_weed_correlation, mission.weed_liquid_correlation
        )
        cur.execute(
            """
            INSERT INTO missions (
                robot_id, field_id, user_id, mission_type, start_time, end_time, travelled_distance_m,
                covered_area_m2, sprayed_fluid_l, target_fluid_density_lpha, setpoint_pressure_bar,
                cultivation_method, inference_model, context_crop_id, target_id, min_latitude,
                max_latitude, min_longitude, max_longitude, crop_weed_correlation, weed_liquid_correlation
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *;
            """,
            mission_data
        )
        new_mission = cur.fetchone()
        conn.commit()
    return new_mission


@router.get("/", summary="Get a list of all missions", response_model=List[Mission])
def get_missions(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM missions ORDER BY start_time DESC;")
        missions = cur.fetchall()
    return missions


@router.get("/{mission_id}", summary="Get a single mission by ID", response_model=Mission)
def get_mission(
    mission_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM missions WHERE id = %s;", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.post("/{mission_id}/robot_state", summary="Add a batch of robot state data")
def add_robot_state_batch(
    mission_id: int,
    states: List[RobotState],
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor() as cur:
        data_to_insert = [
            (
                mission_id, s.timestamp, s.system_state, s.latitude_rad, s.longitude_rad, s.pose_x_m, s.pose_y_m,
                s.pose_theta_rad, s.speed_x_mps, s.speed_y_mps, s.speed_omega_radps, s.unit0_fluid_l,
                s.unit1_fluid_l, s.unit2_fluid_l, s.target_coverage_percent, s.avoid_coverage_percent
            ) for s in states
        ]
        execute_values(
            cur,
            """
            INSERT INTO robot_state_timeseries (
                mission_id, timestamp, system_state, latitude_rad, longitude_rad, pose_x_m, pose_y_m,
                pose_theta_rad, speed_x_mps, speed_y_mps, speed_omega_radps, unit0_fluid_l,
                unit1_fluid_l, unit2_fluid_l, target_coverage_percent, avoid_coverage_percent
            ) VALUES %s
            """,
            data_to_insert
        )
        conn.commit()
    return {"message": f"{len(states)} robot states added to mission {mission_id}"}


@router.get("/{mission_id}/robot_state", summary="Get all robot state data for a mission", response_model=List[RobotState])
def get_robot_state_for_mission(
    mission_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM robot_state_timeseries WHERE mission_id = %s ORDER BY timestamp ASC;", (mission_id,))
        states = cur.fetchall()
    return states


@router.post("/{mission_id}/agri_events", summary="Add a batch of general agri-events")
def add_agri_events_batch(
    mission_id: int,
    events: List[AgriEvent],
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor() as cur:
        data_to_insert = [
            (
                mission_id, e.timestamp, e.latitude, e.longitude, e.altitude, e.event_type, e.event_value
            ) for e in events
        ]
        execute_values(
            cur,
            "INSERT INTO agri_events (mission_id, timestamp, latitude, longitude, altitude, event_type, event_value) VALUES %s",
            data_to_insert
        )
        conn.commit()
    return {"message": f"{len(events)} agri-events added to mission {mission_id}"}


@router.get("/{mission_id}/agri_events", summary="Get all agri-events for a mission", response_model=List[AgriEvent])
def get_agri_events_for_mission(
    mission_id: int,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    conn=Depends(get_db_conn)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM agri_events WHERE mission_id = %s ORDER BY timestamp ASC;", (mission_id,))
        events = cur.fetchall()
    return events
