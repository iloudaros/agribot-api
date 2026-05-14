from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import PC5Payload
from app.security import UserInDB, get_current_active_user
from app.api.forward.pc5 import push_pc5_data

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

def _process_pc5_payload(mission_id: int, payload: PC5Payload, record_type: str, background_tasks: BackgroundTasks, conn, user: UserInDB):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Verify Mission and Access
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        field_id = mission["field_id"]
        _ensure_field_access(cur, field_id, user)
        
        for tree in payload.trees:
            meta = tree.tree_metadata
            grid = tree.location.grid if tree.location and tree.location.grid else None
            geo = tree.location.geolocation if tree.location and tree.location.geolocation else None

            # 1. Upsert the Tree Record (keeps orchards synced across multiple missions)
            cur.execute("""
                INSERT INTO pc5_trees (field_id, tree_identifier, variety, rootstock, planting_date, grid_row, grid_col, elevation, location)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s::float IS NOT NULL THEN ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326) ELSE NULL END)
                ON CONFLICT (field_id, tree_identifier) DO UPDATE SET
                    variety = EXCLUDED.variety,
                    rootstock = EXCLUDED.rootstock,
                    planting_date = EXCLUDED.planting_date,
                    grid_row = EXCLUDED.grid_row,
                    grid_col = EXCLUDED.grid_col,
                    elevation = EXCLUDED.elevation,
                    location = EXCLUDED.location
                RETURNING id
            """, (
                field_id, meta.TreeID, meta.Variety, meta.Rootstock, meta.PlantingDate, 
                grid.row if grid else None, grid.col if grid else None, geo.elevation if geo else None, 
                geo.lon if geo else None, geo.lon if geo else None, geo.lat if geo else None
            ))
            tree_db_id = cur.fetchone()["id"]

            # 2. Insert the Harvest Event
            cur.execute("""
                INSERT INTO pc5_harvests (mission_id, tree_id, record_type, fruit_count)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (mission_id, tree_db_id, record_type, tree.harvest_data.FruitCount))
            harvest_id = cur.fetchone()["id"]

            # 3. Batch Insert all Apple Detections
            if tree.harvest_data.apples:
                apples_tuples = [
                    (
                        harvest_id, apple.AppleID, apple.SizeClass, apple.OvercolorClass,
                        apple.yolo_detection.picture_id, apple.yolo_detection.class_id,
                        apple.yolo_detection.x, apple.yolo_detection.y,
                        apple.yolo_detection.width, apple.yolo_detection.height,
                        apple.yolo_detection.confidence
                    )
                    for apple in tree.harvest_data.apples
                ]
                
                execute_values(cur, """
                    INSERT INTO pc5_apples (
                        harvest_id, apple_id, size_class, overcolor_class, 
                        picture_id, class_id, bbox_x, bbox_y, bbox_width, bbox_height, confidence
                    ) VALUES %s
                """, apples_tuples)
        
        conn.commit()

    # Dispatch to Webhook exactly as received (using Pydantic's alias dump)
    dict_payload = payload.model_dump(by_alias=True)
    background_tasks.add_task(push_pc5_data, mission_id, field_id, dict_payload, record_type)

    return {"status": "success", "message": f"Processed {len(payload.trees)} trees for {record_type}"}

@router.post("/missions/{mission_id}/inspection")
def submit_pc5_inspection(
    mission_id: int,
    payload: PC5Payload,
    background_tasks: BackgroundTasks,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    return _process_pc5_payload(mission_id, payload, "inspection", background_tasks, conn, user)

@router.post("/missions/{mission_id}/application")
def submit_pc5_application(
    mission_id: int,
    payload: PC5Payload,
    background_tasks: BackgroundTasks,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    return _process_pc5_payload(mission_id, payload, "application", background_tasks, conn, user)