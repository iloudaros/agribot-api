import os
import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, Form, UploadFile, File, Request
from psycopg2.extras import execute_values

from app.core.db import get_db_conn
from app.models.schemas import ImagePrediction

router = APIRouter()

@router.post("/missions/{mission_id}/images", summary="Upload an image and its metadata", status_code=201)
def upload_mission_image(
    request: Request,
    mission_id: int,
    timestamp: datetime = Form(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    camera_id: int = Form(None),
    image: UploadFile = File(...),
    conn=Depends(get_db_conn)
):
    minio_client = request.app.state.minio_client
    image_bucket = "agribot-images"

    if not minio_client.bucket_exists(image_bucket):
        minio_client.make_bucket(image_bucket)

    file_extension = os.path.splitext(image.filename)[1]
    object_name = f"{mission_id}/{uuid.uuid4()}{file_extension}"

    minio_client.put_object(
        bucket_name=image_bucket,
        object_name=object_name,
        data=image.file,
        length=-1,
        part_size=10*1024*1024,
        content_type=image.content_type
    )

    image_url = f"minio://{image_bucket}/{object_name}"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mission_images (mission_id, timestamp, image_url, latitude, longitude, camera_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (mission_id, timestamp, image_url, latitude, longitude, camera_id)
        )
        image_id = cur.fetchone()[0]
        conn.commit()

    return {"image_id": image_id, "image_url": image_url}


@router.post("/images/{image_id}/predictions", summary="Add a batch of predictions for an image")
def add_predictions_batch(image_id: int, predictions: List[ImagePrediction], conn=Depends(get_db_conn)):
    with conn.cursor() as cur:
        data_to_insert = [
            (
                p.detection_id, image_id, p.class_name, p.confidence,
                p.x, p.y, p.width, p.height
            ) for p in predictions
        ]
        execute_values(
            cur,
            'INSERT INTO image_predictions (detection_id, image_id, class_name, confidence, x, y, width, height) VALUES %s',
            data_to_insert
        )
        conn.commit()
    return {"message": f"{len(predictions)} predictions added to image {image_id}"}
