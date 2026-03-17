import uuid
from datetime import timedelta, datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg2.extras import RealDictCursor, execute_values
from app.core.db import get_db_conn
from app.models.schemas import TreeCreate, ImageUploadRequest, ImageDetection
from app.security import get_current_active_user, UserInDB

router = APIRouter()

@router.post("/trees", status_code=201)
def register_tree(
    tree: TreeCreate, 
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            INSERT INTO uc5_uc6_trees (field_id, tree_identifier, variety, planting_date, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, tree_identifier;
        """, (
            tree.field_id, tree.tree_identifier, tree.variety, 
            tree.planting_date, tree.latitude, tree.longitude
        ))
        new_tree = cur.fetchone()
        conn.commit()
    return new_tree

# --- MinIO Integration ---

@router.post("/images/presigned-url")
def get_upload_url(
    req: ImageUploadRequest, 
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """
    Generates a secure, temporary URL to upload directly to MinIO.
    """
    minio_client = request.app.state.minio_client
    bucket_name = "agribot-mission-images"
    
    # Ensure bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    # Generate hierarchical path: trees/{tree_id}/{uuid}.jpg
    file_ext = req.filename.split('.')[-1]
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    object_name = f"trees/{req.tree_id}/{unique_name}"

    try:
        url = minio_client.get_presigned_url(
            "PUT",
            bucket_name,
            object_name,
            expires=timedelta(minutes=10),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    return {
        "upload_url": url,
        "bucket": bucket_name,
        "object_key": object_name
    }

@router.post("/images/confirm", status_code=201)
def confirm_upload(
    tree_id: int,
    bucket: str,
    object_key: str,
    camera_type: str = "rgb",
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """
    Save metadata to Postgres after successful MinIO upload.
    Returns the new image_id needed for attaching detections.
    """
    image_url = f"minio://{bucket}/{object_key}"
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO uc5_uc6_images (tree_id, timestamp, image_url, camera_type)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (tree_id, datetime.now(), image_url, camera_type))
        image_id = cur.fetchone()[0]
        conn.commit()
    
    return {"image_id": image_id, "status": "confirmed"}

# --- Computer Vision Results ---

@router.post("/images/{image_id}/detections")
def upload_detections(
    image_id: int,
    detections: List[ImageDetection],
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    if not detections:
        return {"message": "No detections"}

    data_tuples = [
        (
            image_id, str(uuid.uuid4()), d.class_name, d.confidence,
            d.x, d.y, d.width, d.height
        )
        for d in detections
    ]

    with conn.cursor() as cur:
        query = """
            INSERT INTO uc5_uc6_detections 
            (image_id, detection_uuid, class_name, confidence, bbox_x, bbox_y, bbox_w, bbox_h)
            VALUES %s
        """
        execute_values(cur, query, data_tuples)
        conn.commit()

    return {"message": f"Saved {len(detections)} detections for image {image_id}"}
