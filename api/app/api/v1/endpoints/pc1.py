import uuid

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request
from psycopg2.extras import RealDictCursor, execute_values
from datetime import timedelta


from app.core.db import get_db_conn
from app.models.schemas import Mission, Weed, WeedCreate, WeedUpdate, WeedBatchUpdateItem, PC1MissionState, PC1ImageUploadRequest
from app.security import UserInDB, get_current_active_user
from app.api.forward.pc1 import push_pc1_inspection_data, push_pc1_sprayed_weeds_data
router = APIRouter()

def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return
    
    # Simple, direct check against the new table structure (No JOIN needed)
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

# ==========================================
# PC1 Mission State Endpoints
# ==========================================

@router.get("/missions", response_model=List[Mission])
def list_pc1_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user.role == "admin":
            cur.execute("SELECT * FROM missions WHERE mission_type LIKE 'pc1_%' ORDER BY start_time DESC")
        else:
            cur.execute("""
                SELECT m.* 
                FROM missions m
                JOIN field_ownerships fo ON fo.field_id = m.field_id
                WHERE m.mission_type LIKE 'pc1_%' AND fo.user_id = %s
                ORDER BY m.start_time DESC
            """, (user.id,))
        return cur.fetchall()

@router.put("/missions/{mission_id}/state", response_model=PC1MissionState)
def update_pc1_mission_state(
    mission_id: str,
    state: PC1MissionState,
    background_tasks: BackgroundTasks, 
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, start_time FROM missions WHERE id = %s", (mission_id,))
        mission = cur.fetchone()
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        
        _ensure_field_access(cur, mission["field_id"], user)

        # 1. Upsert the PC1 specific status
        cur.execute(
            """
            INSERT INTO pc1_missions (mission_id, status)
            VALUES (%s, %s)
            ON CONFLICT (mission_id) 
            DO UPDATE SET status = EXCLUDED.status
            RETURNING mission_id, status
            """,
            (mission_id, state.status)
        )
        updated_state = cur.fetchone()
        conn.commit()

        # 2. TRIGGER AGROAPPS WEBHOOKS BASED ON STATUS
        if state.status == "inspection_complete":
            # Fetch all weeds for this inspection
            cur.execute("""
                SELECT id, name, image, confidence, ST_Y(weed_loc) AS lat, ST_X(weed_loc) AS lon 
                FROM pc1_weed 
                WHERE inspection_id = %s
            """, (mission_id,))
            weeds_data = cur.fetchall()

            # --- MinIO Presigned URL Generation for Webhook ---
            minio_client = request.app.state.minio_client
            weeds_payload = []
            
            for w in weeds_data:
                external_image_url = w["image"]
                
                # Convert 'minio://' URI to an actual HTTP URL
                if external_image_url and external_image_url.startswith("minio://"):
                    try:
                        bucket, obj_key = external_image_url.replace("minio://", "").split("/", 1)
                        # Generate a URL valid for 7 days for the external server
                        external_image_url = minio_client.get_presigned_url(
                            "GET", 
                            bucket, 
                            obj_key, 
                            expires=timedelta(days=7)
                        )
                    except Exception as e:
                        print(f"Warning: Could not generate URL for webhook: {e}")

                weeds_payload.append({
                    "id": str(w["id"]),
                    "name": w["name"],
                    "image": external_image_url, # Now a valid HTTP URL
                    "confidence": int((w["confidence"] or 0) * 100),
                    "weed_loc": {
                        "lat": w["lat"],
                        "lon": w["lon"]
                    } if w["lat"] is not None else None
                })

            # Build AgroApps Payload
            payload = {
                "inspection_id": mission_id,
                "parcel_id": mission["field_id"],
                "date": mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else "",
                "weeds": weeds_payload
            }
            # Add to background queue
            background_tasks.add_task(push_pc1_inspection_data, payload)

        elif state.status == "spraying_complete":
            # Fetch only sprayed weeds
            cur.execute("""
                SELECT id, spray_time 
                FROM pc1_weed 
                WHERE inspection_id = %s AND is_sprayed = true
            """, (mission_id,))
            sprayed_data = cur.fetchall()

            payload = {
                "inspection_id": mission_id,
                "sprayed_weeds": [
                    {
                        "id": w["id"],
                        "timestamp": w["spray_time"].strftime("%Y%m%d%H%M%S") if w["spray_time"] else ""
                    } for w in sprayed_data
                ]
            }
            # Add to background queue
            background_tasks.add_task(push_pc1_sprayed_weeds_data, payload)

    return updated_state




# ==========================================
# PC1 Weed Endpoints
# ==========================================

# Create a batch of new weeds from an inspection mission.
@router.post("/weeds/batch", response_model=List[Weed], status_code=status.HTTP_201_CREATED)
def create_pc1_weeds_batch(
    weeds_in: List[WeedCreate],
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if not weeds_in:
        return []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        mission_ids = list(set(w.inspection_id for w in weeds_in))
        cur.execute("SELECT id, field_id, mission_type FROM missions WHERE id = ANY(%s)", (mission_ids,))
        missions = {m["id"]: m for m in cur.fetchall()}

        for m_id in mission_ids:
            if m_id not in missions:
                raise HTTPException(status_code=404, detail=f"Mission {m_id} not found")
            _ensure_field_access(cur, missions[m_id]["field_id"], user)

        query = """
            INSERT INTO pc1_weed (id, inspection_id, name, image, confidence, weed_loc, needs_verification, verified, is_sprayed, spray_time)
            VALUES %s
            RETURNING id, inspection_id, name, image, confidence, 
                      ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, 
                      is_sprayed, spray_time
        """

        template = "(%s, %s, %s, %s, %s, CASE WHEN %s::float IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326) END, %s, %s, %s, %s)"
        
        data_tuples = [
            (
                w.id, w.inspection_id, w.name, w.image, w.confidence, 
                w.longitude, w.longitude, w.latitude, 
                w.needs_verification, w.verified,
                w.is_sprayed, w.spray_time
            )
            for w in weeds_in
        ]

        inserted_weeds = execute_values(cur, query, data_tuples, template=template, fetch=True)
        conn.commit()

    return inserted_weeds

# Create a single weed (legacy support, not recommended if you can batch)
@router.post("/weeds", response_model=Weed, status_code=status.HTTP_201_CREATED)
def create_pc1_weed(
    weed: WeedCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    # Ensure client provided an ID
    if not weed.id:
        raise HTTPException(status_code=400, detail="Weed id (string) is required")

    if (weed.latitude is None) != (weed.longitude is None):
        raise HTTPException(status_code=400, detail="latitude and longitude must either both be provided or omitted")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, field_id, mission_type FROM missions WHERE id = %s", (weed.inspection_id,))
        inspection = cur.fetchone()

        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection mission not found")
        if inspection["mission_type"] != "pc1_inspection":
            raise HTTPException(status_code=400, detail="Weeds can only be attached to pc1_inspection missions")

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            INSERT INTO pc1_weed (id, inspection_id, name, image, confidence, weed_loc, is_sprayed, spray_time)
            VALUES (%s, %s, %s, %s, %s, CASE WHEN %s::float IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326) END, %s, %s)
            RETURNING id, inspection_id, name, image, confidence, ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, needs_verification, verified, is_sprayed, spray_time
            """,
            (
                weed.id, weed.inspection_id, weed.name, weed.image, weed.confidence, 
                weed.longitude, weed.longitude, weed.latitude,  
                weed.needs_verification, weed.verified,
                weed.is_sprayed, weed.spray_time
            ),
        )
        new_weed = cur.fetchone()
        conn.commit()

    return new_weed

# Update the sprayed status of a list of weeds in batch.
@router.patch("/weeds/batch", response_model=List[Weed])
def update_pc1_weeds_batch(
    updates: List[WeedBatchUpdateItem],
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    if not updates:
        return []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        mission_ids = list(set(u.inspection_id for u in updates))
        cur.execute("SELECT id, field_id FROM missions WHERE id = ANY(%s)", (mission_ids,))
        fields = cur.fetchall()
            
        for f in fields:
            _ensure_field_access(cur, f["field_id"], user)

        # Match on BOTH id and inspection_id due to the composite primary key
        query = """
            UPDATE pc1_weed AS w
            SET verified = data.verified::boolean,
                is_sprayed = data.is_sprayed::boolean,
                spray_time = data.spray_time::timestamptz
            FROM (VALUES %s) AS data(id, inspection_id, verified, is_sprayed, spray_time)
            WHERE w.id = data.id::int AND w.inspection_id = data.inspection_id::int
            RETURNING w.id, w.inspection_id, w.name, w.image, w.confidence, 
                      ST_Y(w.weed_loc) AS latitude, ST_X(w.weed_loc) AS longitude, 
                      w.is_sprayed, w.spray_time
        """
        data_tuples = [(u.id, u.inspection_id, u.verified, u.is_sprayed, u.spray_time) for u in updates]
        
        updated_weeds = execute_values(cur, query, data_tuples, fetch=True)
        conn.commit()

    return updated_weeds

# Update a single weed's sprayed status (legacy support, not recommended if you can batch)
@router.patch("/weeds/{weed_id}", response_model=Weed)
def update_pc1_weed(
    weed_id: str, 
    weed_update: WeedUpdate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Look up the weed to get the inspection_id (required for composite PK)
        cur.execute("""
            SELECT w.id, w.inspection_id, m.field_id 
            FROM pc1_weed w
            JOIN missions m ON m.id = w.inspection_id
            WHERE w.id = %s
        """, (weed_id,))
        weed_row = cur.fetchone()

        if not weed_row:
            raise HTTPException(status_code=404, detail="Weed not found")

        # 2. Check access
        _ensure_field_access(cur, weed_row["field_id"], user)

        # 3. Perform the update using BOTH parts of the composite primary key
        cur.execute(
            """
            UPDATE pc1_weed
            SET verified = %s, is_sprayed = %s, spray_time = %s
            WHERE id = %s AND inspection_id = %s
            RETURNING 
                id, inspection_id, name, image, confidence, 
                ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, 
                verified, is_sprayed, spray_time
            """,
            (
                weed_update.verified,
                weed_update.is_sprayed, 
                weed_update.spray_time, 
                weed_id, 
                weed_row["inspection_id"] # Extracted from the SELECT above
            ),
        )
        updated_weed = cur.fetchone()
        conn.commit()

    return updated_weed


# List all weeds for a given inspection mission.
@router.get("/weeds/{inspection_id}", response_model=List[Weed])
def list_pc1_weeds(
    inspection_id: str,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, field_id FROM missions WHERE id = %s", (inspection_id,))
        inspection = cur.fetchone()
        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")

        _ensure_field_access(cur, inspection["field_id"], user)

        cur.execute(
            """
            SELECT id, inspection_id, name, image, confidence, ST_Y(weed_loc) AS latitude, ST_X(weed_loc) AS longitude, needs_verification, verified, is_sprayed, spray_time
            FROM pc1_weed WHERE inspection_id = %s ORDER BY id
            """,
            (inspection_id,),
        )
        return cur.fetchall()



# ==========================================
# PC1 MinIO Image Endpoints
# ==========================================

@router.post("/images/presigned-url")
def get_pc1_upload_url(
    req: PC1ImageUploadRequest, 
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """
    Generates a secure, temporary URL to upload a weed image directly to MinIO.
    """
    # 1. Verify access to the mission/field before granting upload rights
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT field_id, mission_type FROM missions WHERE id = %s", (req.inspection_id,))
        mission = cur.fetchone()
        
        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")
        if mission["mission_type"] != "pc1_inspection_and_spraying" and mission["mission_type"] != "pc1_inspection":
            raise HTTPException(status_code=400, detail="Invalid mission type for PC1 images")
            
        _ensure_field_access(cur, mission["field_id"], user)

    minio_client = request.app.state.minio_client
    bucket_name = "agribot-mission-images"
    
    # Ensure bucket exists
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    # Generate hierarchical path: pc1/{inspection_id}/{uuid}.jpg
    file_ext = req.filename.split('.')[-1]
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    object_name = f"pc1/mission_{req.inspection_id}/{unique_name}"

    try:
        url = minio_client.get_presigned_url(
            "PUT",
            bucket_name,
            object_name,
            expires=timedelta(minutes=10),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    # Return the URL for PUTting the file, and the image_uri to save in the DB later
    return {
        "upload_url": url,
        "bucket": bucket_name,
        "object_key": object_name,
        "image_uri": f"minio://{bucket_name}/{object_name}"
    }



@router.get("/weeds/{inspection_id}/{weed_id}/image-url")
def get_pc1_weed_image_url(
    inspection_id: int,
    weed_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user)
):
    """
    Generates a secure, temporary GET URL for the frontend to display a weed image.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Fetch the weed and mission data
        cur.execute("""
            SELECT w.image, m.field_id 
            FROM pc1_weed w
            JOIN missions m ON m.id = w.inspection_id
            WHERE w.id = %s AND w.inspection_id = %s
        """, (weed_id, inspection_id))
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Weed not found")
        
        if not row["image"] or not row["image"].startswith("minio://"):
            raise HTTPException(status_code=400, detail="No valid MinIO image associated with this weed")

        # 2. Verify authorization
        _ensure_field_access(cur, row["field_id"], user)

    # 3. Parse the URI (Format: minio://<bucket>/<object_key>)
    # Example: minio://agribot-mission-images/pc1/mission_1/1234.jpg
    uri_parts = row["image"].replace("minio://", "").split("/", 1)
    if len(uri_parts) != 2:
        raise HTTPException(status_code=500, detail="Malformed image URI in database")
        
    bucket_name = uri_parts[0]
    object_key = uri_parts[1]

    # 4. Generate the presigned GET URL
    minio_client = request.app.state.minio_client
    
    try:
        url = minio_client.get_presigned_url(
            "GET",
            bucket_name,
            object_key,
            expires=timedelta(hours=1), # URL valid for 1 hour
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    return {"image_url": url}
