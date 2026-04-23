import uuid
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import (
    Mission,
    PC2GeoJSONUploadRequest,
    PC2MissionConfirm,
    PC2Mission
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
                WHERE mission_type = 'pc2_spraying' 
                ORDER BY start_time DESC
            """)
        else:
            cur.execute("""
                SELECT m.* FROM missions m
                JOIN field_ownerships fo ON m.field_id = fo.field_id
                WHERE m.mission_type = 'pc2_spraying' AND fo.user_id = %s
                ORDER BY m.start_time DESC
            """, (user.id,))
        return cur.fetchall()


@router.post("/geojson/presigned-url")
def get_pc2_geojson_upload_url(
    req: PC2GeoJSONUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Generate a presigned PUT URL so the connector can upload the GeoJSON directly to MinIO.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, mission_type FROM missions WHERE id = %s", (req.mission_id,))
        mission = cur.fetchone()

        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        if mission["mission_type"] != "pc2_spraying":
            raise HTTPException(status_code=400, detail="Invalid mission type for PC2")

        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images" # Reusing the same bucket for all mission files

    unique_name = f"{uuid.uuid4()}.geojson"
    object_name = f"pc2/mission_{req.mission_id}/{unique_name}"

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
        "geojson_uri": f"minio://{bucket_name}/{object_name}",
    }


@router.post("/missions/{mission_id}/geojson/confirm", response_model=PC2Mission)
def confirm_pc2_geojson(
    mission_id: int,
    payload: PC2MissionConfirm,
    background_tasks: BackgroundTasks,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Save the GeoJSON MinIO URI to the database after successful upload,
    and forward the link to AgroApps in the background.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Fetch start_time so we can extract the date for AgroApps
        cur.execute("SELECT field_id, start_time FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute(
            """
            INSERT INTO pc2_missions (mission_id, geojson_uri)
            VALUES (%s, %s)
            ON CONFLICT (mission_id) DO UPDATE SET geojson_uri = EXCLUDED.geojson_uri
            RETURNING mission_id, geojson_uri
            """,
            (mission_id, payload.geojson_uri)
        )
        saved_record = cur.fetchone()
        conn.commit()

    # --------------------------------------------------------------
    # Webhook Logic: Forward the Secure API Endpoint to AgroApps
    # --------------------------------------------------------------
    
    # Construct the base URL of your API (e.g., http://127.0.0.1:8080 or https://api.agribot.eu)
    base_url = str(request.base_url).rstrip("/")
    secure_download_url = f"{base_url}/api/v1/pc2/missions/{mission_id}/geojson"

    agroapps_payload = {
        "parcel_id": mission["field_id"],
        "date": mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else "",
        "file_path": secure_download_url
    }

    # Dispatch the task to the background queue
    background_tasks.add_task(push_pc2_spraying_data, agroapps_payload)

    return saved_record




@router.get("/missions/{mission_id}/geojson")
def download_pc2_geojson(
    mission_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Securely stream the GeoJSON file from MinIO through the API.
    Requires a valid JWT token and field access permissions.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT p.geojson_uri, m.field_id 
            FROM pc2_missions p
            JOIN missions m ON m.id = p.mission_id
            WHERE p.mission_id = %s
        """, (mission_id,))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="GeoJSON not found for this mission")

        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["geojson_uri"])
    minio_internal_client = request.app.state.minio_internal_client

    try:
        # Request the object from MinIO
        minio_response = minio_internal_client.get_object(bucket_name, object_key)
        
        # Create a generator to stream the data in 32KB chunks
        def iterfile():
            try:
                for chunk in minio_response.stream(32 * 1024):
                    yield chunk
            finally:
                minio_response.close()
                minio_response.release_conn()

        return StreamingResponse(
            iterfile(),
            media_type="application/geo+json",
            headers={"Content-Disposition": f'attachment; filename="mission_{mission_id}.geojson"'}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

# ==========================================
# PC2 GeoTIFF Image Endpoints
# ==========================================

@router.post("/geotiff/presigned-url")
def get_pc2_geotiff_upload_url(
    req: PC2GeoTIFFUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Generate a presigned PUT URL so the connector can upload the GeoTIFF directly to MinIO.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, mission_type FROM missions WHERE id = %s", (req.mission_id,))
        mission = cur.fetchone()

        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        if mission["mission_type"] != "pc2_spraying":
            raise HTTPException(status_code=400, detail="Invalid mission type for PC2")

        _ensure_field_access(cur, mission["field_id"], user)

    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images" 

    # Extract extension or default to tif
    file_ext = req.filename.split(".")[-1] if "." in req.filename else "tif"
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    object_name = f"pc2/mission_{req.mission_id}/{unique_name}"

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
        "geotiff_uri": f"minio://{bucket_name}/{object_name}",
    }


@router.post("/missions/{mission_id}/geotiff/confirm", response_model=PC2Mission)
def confirm_pc2_geotiff(
    mission_id: int,
    payload: PC2GeoTIFFConfirm,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Save the GeoTIFF MinIO URI to the database after successful upload.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission["field_id"], user)

        cur.execute(
            """
            INSERT INTO pc2_missions (mission_id, geotiff_uri)
            VALUES (%s, %s)
            ON CONFLICT (mission_id) DO UPDATE SET geotiff_uri = EXCLUDED.geotiff_uri
            RETURNING mission_id, geojson_uri, geotiff_uri
            """,
            (mission_id, payload.geotiff_uri)
        )
        saved_record = cur.fetchone()
        conn.commit()

    return saved_record


@router.get("/missions/{mission_id}/geotiff")
def download_pc2_geotiff(
    mission_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Securely stream the GeoTIFF file from MinIO through the API.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT p.geotiff_uri, m.field_id 
            FROM pc2_missions p
            JOIN missions m ON m.id = p.mission_id
            WHERE p.mission_id = %s
        """, (mission_id,))
        row = cur.fetchone()

        if not row or not row["geotiff_uri"]:
            raise HTTPException(status_code=404, detail="GeoTIFF not found for this mission")

        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["geotiff_uri"])
    minio_internal_client = request.app.state.minio_internal_client

    try:
        minio_response = minio_internal_client.get_object(bucket_name, object_key)
        
        def iterfile():
            try:
                for chunk in minio_response.stream(32 * 1024):
                    yield chunk
            finally:
                minio_response.close()
                minio_response.release_conn()

        return StreamingResponse(
            iterfile(),
            media_type="image/tiff",
            headers={"Content-Disposition": f'attachment; filename="mission_{mission_id}_map.tif"'}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")
