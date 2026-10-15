import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import PC6Payload, PC6ImageUploadRequest
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

def _parse_minio_uri(image_uri: str) -> tuple[str, str]:
    """
    Parse a MinIO URI of the form:

        minio://bucket-name/path/to/object.jpg

    and return:

        (bucket_name, object_key)
    """
    if not image_uri or not image_uri.startswith("minio://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MinIO image URI"
        )

    uri_parts = image_uri.replace("minio://", "", 1).split("/", 1)
    if len(uri_parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Malformed image URI in database"
        )

    return uri_parts[0], uri_parts[1]

def _process_pc6_payload(mission_id: int, payload: PC6Payload, operation_type: str, record_type: str, background_tasks: BackgroundTasks, conn, user: UserInDB):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, start_time FROM missions WHERE id = %s", (mission_id,))
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
                        b.yolo_detection.confidence,b.selected, b.image
                    )
                    for b in op_data.branches
                ]

                execute_values(cur, """
                    INSERT INTO pc6_branches (
                        operation_id, branch_id, age_years, length_m, diameter_cm,
                        picture_id, class_id, bbox_x, bbox_y, bbox_width, bbox_height, confidence, selected, image
                    ) VALUES %s
                """, branch_tuples)

        conn.commit()

    dict_payload = payload.model_dump(by_alias=True)
    
    dict_payload["parcel_id"] = field_id
    dict_payload["date"] = mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else ""

    background_tasks.add_task(push_pc6_data, mission_id, dict_payload, operation_type, record_type)

    return {"status": "success", "message": f"Processed {len(payload.trees)} trees for {operation_type} {record_type}"}

# --- Image Upload Endpoints ---
@router.post("/images/presigned-url")
def get_pc6_upload_url(
    req: PC6ImageUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
    ):
    """
    Generate a presigned PUT URL so the connector can upload images directly
    to MinIO.

    The bucket is assumed to already exist.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT field_id, mission_type
            FROM missions
            WHERE id = %s
            """,
            (req.inspection_id,),
        )
        mission = cur.fetchone()

        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        if mission["mission_type"] not in ["pc6_thinning", "pc6_pruning",]:
            raise HTTPException(status_code=400, detail="Invalid mission type for PC6 images")

        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images"

    file_ext = req.filename.split(".")[-1] if "." in req.filename else "bin"
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    object_name = f"pc6/mission_{req.inspection_id}/{unique_name}"

    try:
        upload_url = minio_public_client.get_presigned_url(
            "PUT",
            bucket_name,
            object_name,
            expires=timedelta(minutes=10),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    return {
        "upload_url": upload_url,
        "bucket": bucket_name,
        "object_key": object_name,
        "image_uri": f"minio://{bucket_name}/{object_name}",
    }




@router.get("/trees/{tree_id}/{mission_id}/{branch_id}/image-url")
def get_pc6_branch_image_url(
    mission_id: int,
    tree_id: int,
    branch_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Generate a presigned GET URL so the frontend can display a branch image.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT b.image AS image, m.field_id
            FROM pc6_branches b
            JOIN pc6_operations o
              ON o.id = b.operation_id
            JOIN pc5_trees t
              ON t.id = o.tree_id
            JOIN missions m
              ON m.id = o.mission_id
            WHERE b.id = %s
              AND t.id = %s
              AND o.mission_id = %s
            """,
            (branch_id, tree_id, mission_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Branch not found")

        if not row["image"] or not row["image"].startswith("minio://"):
            raise HTTPException(
                status_code=400,
                detail="No valid MinIO image associated with this branch",
            )

        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["image"])
    minio_public_client = request.app.state.minio_public_client

    try:
        image_url = minio_public_client.get_presigned_url(
            "GET",
            bucket_name,
            object_key,
            expires=timedelta(hours=1),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {e}") from e

    return {"image_url": image_url}

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