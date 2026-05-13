import uuid
from datetime import timedelta, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import (
    Mission,
    PC2EcoGeoJSONUploadRequest,
    PC2EcoGeoTIFFUploadRequest,
    PC2EcoConfirmGeoJSON,
    PC2EcoConfirmGeoTIFF,
    PC2EcorobotixMission,
    PC2DTIPhotoUploadRequest,
    PC2DTIPhotoConfirm,
    PC2DTIPhotoResponse,
    PC2DTILatestPhotoResponse
)
from app.security import UserInDB, get_current_active_user
from app.api.forward.pc2 import push_pc2_spraying_data

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
            detail="You do not have access to this field"
        )

def _parse_minio_uri(uri: str) -> tuple[str, str]:
    if not uri or not uri.startswith("minio://"):
        raise HTTPException(status_code=400, detail="Invalid MinIO URI")
    parts = uri.replace("minio://", "", 1).split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=500, detail="Malformed URI in database")
    return parts[0], parts[1]


@router.get("/missions", response_model=List[Mission])
def list_pc2_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user.role == "admin":
            cur.execute("""
                SELECT * FROM missions 
                WHERE mission_type LIKE 'pc2_%' 
                ORDER BY start_time DESC
            """)
        else:
            cur.execute("""
                SELECT m.* FROM missions m
                JOIN field_ownerships fo ON m.field_id = fo.field_id
                WHERE m.mission_type LIKE 'pc2_%' AND fo.user_id = %s
                ORDER BY m.start_time DESC
            """, (user.id,))
        return cur.fetchall()


# ==========================================
# Ecorobotix Endpoints
# ==========================================

@router.post("/ecorobotix/geojson/presigned-url")
def get_pc2_eco_geojson_upload_url(
    req: PC2EcoGeoJSONUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s AND mission_type = 'pc2_spraying'", (req.mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Ecorobotix mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images"
    object_name = f"pc2_ecorobotix/mission_{req.mission_id}/{uuid.uuid4()}.geojson"

    upload_url = minio_public_client.get_presigned_url("PUT", bucket_name, object_name, expires=timedelta(minutes=10))

    return {
        "upload_url": upload_url,
        "bucket": bucket_name,
        "object_key": object_name,
        "geojson_uri": f"minio://{bucket_name}/{object_name}",
    }

@router.post("/ecorobotix/missions/{mission_id}/geojson/confirm", response_model=PC2EcorobotixMission)
def confirm_pc2_eco_geojson(
    mission_id: int, payload: PC2EcoConfirmGeoJSON, background_tasks: BackgroundTasks,
    request: Request, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, start_time FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission: raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute("""
            INSERT INTO pc2_ecorobotix (mission_id, geojson_uri) VALUES (%s, %s)
            ON CONFLICT (mission_id) DO UPDATE SET geojson_uri = EXCLUDED.geojson_uri
            RETURNING mission_id, geojson_uri, geotiff_uri
        """, (mission_id, payload.geojson_uri))
        saved_record = cur.fetchone()
        conn.commit()

    base_url = str(request.base_url).rstrip("/")
    agroapps_payload = {
        "parcel_id": mission["field_id"],
        "date": mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else ""
    }
    if saved_record.get("geojson_uri"): agroapps_payload["geojson_path"] = f"{base_url}/api/v1/pc2/ecorobotix/missions/{mission_id}/geojson"
    if saved_record.get("geotiff_uri"): agroapps_payload["geotiff_path"] = f"{base_url}/api/v1/pc2/ecorobotix/missions/{mission_id}/geotiff"
    background_tasks.add_task(push_pc2_spraying_data, agroapps_payload)

    return saved_record

@router.get("/ecorobotix/missions/{mission_id}/geojson")
def download_pc2_eco_geojson(mission_id: int, request: Request, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT p.geojson_uri, m.field_id FROM pc2_ecorobotix p JOIN missions m ON m.id = p.mission_id WHERE p.mission_id = %s", (mission_id,))
        row = cur.fetchone()
        if not row or not row["geojson_uri"]: raise HTTPException(status_code=404, detail="GeoJSON not found")
        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["geojson_uri"])
    minio_internal_client = request.app.state.minio_internal_client

    try:
        minio_response = minio_internal_client.get_object(bucket_name, object_key)
        def iterfile():
            try:
                for chunk in minio_response.stream(32 * 1024): yield chunk
            finally:
                minio_response.close(); minio_response.release_conn()
        return StreamingResponse(iterfile(), media_type="application/geo+json", headers={"Content-Disposition": f'attachment; filename="mission_{mission_id}.geojson"'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

@router.post("/ecorobotix/geotiff/presigned-url")
def get_pc2_eco_geotiff_upload_url(req: PC2EcoGeoTIFFUploadRequest, request: Request, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (req.mission_id,))
        mission = cur.fetchone()
        if not mission: raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images"
    object_name = f"pc2_ecorobotix/mission_{req.mission_id}/{uuid.uuid4()}.tif"

    upload_url = minio_public_client.get_presigned_url("PUT", bucket_name, object_name, expires=timedelta(minutes=10))
    return { "upload_url": upload_url, "bucket": bucket_name, "object_key": object_name, "geotiff_uri": f"minio://{bucket_name}/{object_name}" }

@router.post("/ecorobotix/missions/{mission_id}/geotiff/confirm", response_model=PC2EcorobotixMission)
def confirm_pc2_eco_geotiff(mission_id: int, payload: PC2EcoConfirmGeoTIFF, background_tasks: BackgroundTasks, request: Request, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, start_time FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission: raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute("""
            INSERT INTO pc2_ecorobotix (mission_id, geotiff_uri) VALUES (%s, %s)
            ON CONFLICT (mission_id) DO UPDATE SET geotiff_uri = EXCLUDED.geotiff_uri
            RETURNING mission_id, geojson_uri, geotiff_uri
        """, (mission_id, payload.geotiff_uri))
        saved_record = cur.fetchone()
        conn.commit()

    base_url = str(request.base_url).rstrip("/")
    agroapps_payload = { "parcel_id": mission["field_id"], "date": mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else "" }
    if saved_record.get("geojson_uri"): agroapps_payload["geojson_path"] = f"{base_url}/api/v1/pc2/ecorobotix/missions/{mission_id}/geojson"
    if saved_record.get("geotiff_uri"): agroapps_payload["geotiff_path"] = f"{base_url}/api/v1/pc2/ecorobotix/missions/{mission_id}/geotiff"
    background_tasks.add_task(push_pc2_spraying_data, agroapps_payload)

    return saved_record

@router.get("/ecorobotix/missions/{mission_id}/geotiff")
def download_pc2_eco_geotiff(mission_id: int, request: Request, conn=Depends(get_db_conn), user: UserInDB = Depends(get_current_active_user)):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT p.geotiff_uri, m.field_id FROM pc2_ecorobotix p JOIN missions m ON m.id = p.mission_id WHERE p.mission_id = %s", (mission_id,))
        row = cur.fetchone()
        if not row or not row["geotiff_uri"]: raise HTTPException(status_code=404, detail="GeoTIFF not found")
        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["geotiff_uri"])
    minio_internal_client = request.app.state.minio_internal_client

    try:
        minio_response = minio_internal_client.get_object(bucket_name, object_key)
        def iterfile():
            try:
                for chunk in minio_response.stream(32 * 1024): yield chunk
            finally:
                minio_response.close(); minio_response.release_conn()
        return StreamingResponse(iterfile(), media_type="image/tiff", headers={"Content-Disposition": f'attachment; filename="mission_{mission_id}_map.tif"'})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")


# ==========================================
# DTI Drones Endpoints
# ==========================================

@router.post("/dti/photo/presigned-url")
def get_pc2_dti_upload_url(
    req: PC2DTIPhotoUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """Generate a presigned PUT URL for a DTI drone photo upload."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (req.mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images"
    file_ext = req.filename.split(".")[-1] if "." in req.filename else "jpg"
    object_name = f"pc2_dti/mission_{req.mission_id}/{uuid.uuid4()}.{file_ext}"

    upload_url = minio_public_client.get_presigned_url("PUT", bucket_name, object_name, expires=timedelta(minutes=10))

    return {
        "upload_url": upload_url,
        "bucket": bucket_name,
        "object_key": object_name,
        "photo_uri": f"minio://{bucket_name}/{object_name}",
    }


@router.post("/dti/missions/{mission_id}/photo/confirm", response_model=PC2DTIPhotoResponse)
def confirm_pc2_dti_photo(
    mission_id: int,
    payload: PC2DTIPhotoConfirm,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """Confirm DTI drone photo upload and save creation timestamp."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute("""
            INSERT INTO pc2_dti (mission_id, photo_uri, created_at) 
            VALUES (%s, %s, %s)
            ON CONFLICT (mission_id) DO UPDATE 
            SET photo_uri = EXCLUDED.photo_uri, created_at = EXCLUDED.created_at
            RETURNING mission_id, photo_uri, created_at
        """, (mission_id, payload.photo_uri, datetime.now()))
        saved_record = cur.fetchone()
        conn.commit()

    return saved_record


@router.get("/dti/fields/{field_id}/latest-photo", response_model=PC2DTILatestPhotoResponse)
def get_latest_dti_photo(
    field_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """Retrieve metadata and a SECURE download link for the latest DTI drone photo for a specific field."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_field_access(cur, field_id, user)
        
        cur.execute("""
            SELECT d.mission_id, d.photo_uri, d.created_at
            FROM pc2_dti d
            JOIN missions m ON m.id = d.mission_id
            WHERE m.field_id = %s
            ORDER BY d.created_at DESC
            LIMIT 1
        """, (field_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="No DTI photos found for this field")

    # Instead of exposing MinIO directly, point to our secure streaming endpoint
    base_url = str(request.base_url).rstrip("/")
    secure_url = f"{base_url}/api/v1/pc2/dti/missions/{row['mission_id']}/photo"

    return {
        "mission_id": row["mission_id"],
        "field_id": field_id,
        "photo_url": secure_url,
        "created_at": row["created_at"]
    }


@router.get("/dti/missions/{mission_id}/photo")
def download_pc2_dti_photo(
    mission_id: int, 
    request: Request, 
    conn=Depends(get_db_conn), 
    user: UserInDB = Depends(get_current_active_user)
):
    """
    Securely stream the DTI drone photo from MinIO through the API.
    Requires a valid JWT token and field access permissions.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT d.photo_uri, m.field_id 
            FROM pc2_dti d 
            JOIN missions m ON m.id = d.mission_id 
            WHERE d.mission_id = %s
        """, (mission_id,))
        row = cur.fetchone()
        
        if not row or not row["photo_uri"]:
            raise HTTPException(status_code=404, detail="Photo not found for this mission")
            
        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["photo_uri"])
    minio_internal_client = request.app.state.minio_internal_client

    # Determine media type from extension
    ext = object_key.split(".")[-1].lower() if "." in object_key else "jpeg"
    media_type = "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"

    try:
        minio_response = minio_internal_client.get_object(bucket_name, object_key)
        def iterfile():
            try:
                for chunk in minio_response.stream(32 * 1024): yield chunk
            finally:
                minio_response.close()
                minio_response.release_conn()
                
        return StreamingResponse(
            iterfile(), 
            media_type=media_type, 
            headers={"Content-Disposition": f'inline; filename="mission_{mission_id}_photo.{ext}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")
