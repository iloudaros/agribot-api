from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import PC6Payload
from app.security import UserInDB, get_current_active_user
from app.api.forward.pc6 import push_pc6_data

router = APIRouter()

def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return
    cur.execute(
        "SELECT 1 FROM field_ownerships WHERE field_id = %s AND user_id = %s",
        (field_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this field",
        )

def _process_pc6_payload(mission_id: int, payload: PC6Payload, operation_type: str, record_type: str, background_tasks: BackgroundTasks, conn, user: UserInDB):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
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

            # 1. Upsert the Tree Record (Shared with PC5)
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

            # Extract the correct operation data block
            op_data = tree.thinning_data if operation_type == "thinning" else tree.pruning_data
            if not op_data:
                continue

            # 2. Insert the Operation Record
            cur.execute("""
                INSERT INTO pc6_operations (mission_id, tree_id, operation_type, record_type, branches_to_cut_count, branches_cut_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (mission_id, tree_db_id, operation_type, record_type, op_data.BranchesToCutCount, op_data.BranchesCutCount))
            operation_id = cur.fetchone()["id"]

            # 3. Batch Insert Branches
            if op_data.branches:
                branch_tuples = [
                    (
                        operation_id, b.BranchID, b.Age_years, b.Length_m, b.Diameter_cm,
                        b.yolo_detection.picture_id, b.yolo_detection.class_id,
                        b.yolo_detection.x, b.yolo_detection.y,
                        b.yolo_detection.width, b.yolo_detection.height,
                        b.yolo_detection.confidence
                    )
                    for b in op_data.branches
                ]
                
                execute_values(cur, """
                    INSERT INTO pc6_branches (
                        operation_id, branch_id, age_years, length_m, diameter_cm, 
                        picture_id, class_id, bbox_x, bbox_y, bbox_width, bbox_height, confidence
                    ) VALUES %s
                """, branch_tuples)
        
        conn.commit()

    dict_payload = payload.model_dump(by_alias=True)
    background_tasks.add_task(push_pc6_data, mission_id, dict_payload, operation_type, record_type)

    return {"status": "success", "message": f"Processed {len(payload.trees)} trees for {operation_type} {record_type}"}

# --- Thinning Endpoints ---
@router.post("/missions/{mission_id}/thinning/inspection")
def submit_thinning_inspection(mission_id: int, payload: PC6Payload, bg: BackgroundTasks, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    return _process_pc6_payload(mission_id, payload, "thinning", "inspection", bg, conn, user)

@router.post("/missions/{mission_id}/thinning/application")
def submit_thinning_application(mission_id: int, payload: PC6Payload, bg: BackgroundTasks, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    return _process_pc6_payload(mission_id, payload, "thinning", "application", bg, conn, user)

# --- Pruning Endpoints ---
@router.post("/missions/{mission_id}/pruning/inspection")
def submit_pruning_inspection(mission_id: int, payload: PC6Payload, bg: BackgroundTasks, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    return _process_pc6_payload(mission_id, payload, "pruning", "inspection", bg, conn, user)

@router.post("/missions/{mission_id}/pruning/application")
def submit_pruning_application(mission_id: int, payload: PC6Payload, bg: BackgroundTasks, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    return _process_pc6_payload(mission_id, payload, "pruning", "application", bg, conn, user)