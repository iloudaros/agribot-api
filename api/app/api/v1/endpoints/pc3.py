from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import PC3InspectionItem, PC3InspectionBatch
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


@router.post("/inspections/batch", status_code=status.HTTP_201_CREATED)
def create_pc3_inspections_batch(
    batch: PC3InspectionBatch,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if not batch.data:
        return {"message": "No data provided"}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Verify Mission and Access
        cur.execute("SELECT field_id, mission_type FROM missions WHERE id = %s", (batch.mission_id,))
        mission = cur.fetchone()
        
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        if mission["mission_type"] != "pc3_inspection":
            raise HTTPException(status_code=400, detail="Data can only be attached to a pc3_inspection mission")
            
        _ensure_field_access(cur, mission["field_id"], user)

        # 2. Prepare Bulk Insert
        query = """
            INSERT INTO pc3_inspections (
                mission_id, timestamp_unix, location, biomass, altitude_m, avg_dim_x_cm, 
                avg_dim_y_cm, avg_dim_z_cm, avg_volume_cm3, avg_fol_area_cm2, 
                avg_ndvi, avg_biomass, avg_fertilization
            ) VALUES %s
        """
        
        # ST_MakePoint takes (longitude, latitude)
        template = "(%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        
        data_tuples = [
            (
                batch.mission_id,
                item.timestamp_unix,
                item.longitude, item.latitude, 
                item.biomass, item.altitude_m, item.avg_dim_x_cm,
                item.avg_dim_y_cm, item.avg_dim_z_cm, item.avg_volume_cm3,
                item.avg_fol_area_cm2, item.avg_ndvi, item.avg_biomass, item.avg_fertilization
            )
            for item in batch.data
        ]

        # 3. Execute
        execute_values(cur, query, data_tuples, template=template)
        conn.commit()

    return {"message": f"Successfully inserted {len(batch.data)} inspection records."}


@router.get("/inspections/{mission_id}")
def get_pc3_inspections(
    mission_id: int,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute(
            """
            SELECT 
                id, mission_id, 
                ST_Y(location) AS latitude, ST_X(location) AS longitude,
                biomass, altitude_m, avg_dim_x_cm, avg_dim_y_cm, avg_dim_z_cm, 
                avg_volume_cm3, avg_fol_area_cm2, avg_ndvi, avg_biomass, avg_fertilization
            FROM pc3_inspections 
            WHERE mission_id = %s
            ORDER BY id
            """,
            (mission_id,)
        )
        return cur.fetchall()
