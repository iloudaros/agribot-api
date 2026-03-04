from typing import List
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import Robot, RobotCreate, FarmCreate, FieldCreate
from app.security import get_current_active_user, UserInDB

router = APIRouter()

@router.post("/robots", response_model=Robot, status_code=201)
def register_robot(robot: RobotCreate, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO robots (name, serial_number, type, firmware_version) VALUES (%s, %s, %s, %s) RETURNING *",
            (robot.name, robot.serial_number, robot.type, robot.firmware_version)
        )
        new_robot = cur.fetchone()
        conn.commit()
    return new_robot

@router.get("/robots", response_model=List[Robot])
def list_robots(conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM robots")
        return cur.fetchall()

@router.post("/farms", status_code=201)
def create_farm(farm: FarmCreate, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Construct PostGIS Point geometry from lat/lon
        cur.execute("""
            INSERT INTO farms (name, owner_name, location_center) 
            VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) 
            RETURNING id, name
        """, (farm.name, farm.owner_name, farm.center_lon, farm.center_lat))
        new_farm = cur.fetchone()
        conn.commit()
    return new_farm

@router.post("/fields", status_code=201)
def create_field(field: FieldCreate, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Assuming boundary_wkt is something like 'POLYGON((...))'
        cur.execute("""
            INSERT INTO fields (farm_id, name, crop_name, boundary) 
            VALUES (%s, %s, %s, ST_GeomFromText(%s, 4326)) 
            RETURNING id, name
        """, (field.farm_id, field.name, field.crop_name, field.boundary_wkt))
        new_field = cur.fetchone()
        conn.commit()
    return new_field
