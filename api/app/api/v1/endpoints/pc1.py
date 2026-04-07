import uuid
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import (
    Mission,
    Weed,
    WeedCreate,
    WeedUpdate,
    WeedBatchUpdateItem,
    PC1MissionState,
    PC1ImageUploadRequest,
)
from app.security import UserInDB, get_current_active_user
from app.api.forward.pc1 import push_pc1_inspection_data, push_pc1_sprayed_weeds_data

router = APIRouter()


def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
    """
    Ensure that the current user has access to the given field.

    Admins automatically have access to everything.
    Non-admin users must have a corresponding record in field_ownerships.
    """
    if user.role == "admin":
        return

    cur.execute(
        """
        SELECT 1
        FROM field_ownerships
        WHERE field_id = %s
          AND user_id = %s
        """,
        (field_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this field",
        )


def _parse_minio_uri(image_uri: str) -> tuple[str, str]:
    """
    Convert a stored MinIO URI of the form:

        minio://bucket-name/path/to/object.jpg

    into:

        (bucket_name, object_key)

    This is useful when we want to generate a temporary GET URL
    for the frontend or for forwarding data to external systems.
    """
    if not image_uri or not image_uri.startswith("minio://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid MinIO image URI",
        )

    uri_parts = image_uri.replace("minio://", "", 1).split("/", 1)
    if len(uri_parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Malformed image URI in database",
        )

    return uri_parts[0], uri_parts[1]


# ==========================================
# PC1 Mission State Endpoints
# ==========================================

@router.get("/missions", response_model=List[Mission])
def list_pc1_missions(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Return all PC1-related missions visible to the current user.

    Admins can see all PC1 missions.
    Farmers and other non-admins can only see missions for fields they own.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user.role == "admin":
            cur.execute(
                """
                SELECT *
                FROM missions
                WHERE mission_type LIKE 'pc1_%'
                ORDER BY start_time DESC
                """
            )
        else:
            cur.execute(
                """
                SELECT m.*
                FROM missions m
                JOIN field_ownerships fo
                  ON fo.field_id = m.field_id
                WHERE m.mission_type LIKE 'pc1_%'
                  AND fo.user_id = %s
                ORDER BY m.start_time DESC
                """,
                (user.id,),
            )
        return cur.fetchall()


@router.put("/missions/{mission_id}/state", response_model=PC1MissionState)
def update_pc1_mission_state(
    mission_id: int,
    state: PC1MissionState,
    background_tasks: BackgroundTasks,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Update the PC1-specific mission state.

    This state machine is separate from the generic mission.status field.
    It is used to model the PC1 workflow:

    * ongoing
    * inspection_complete
    * spraying_complete
    * aborted

    State transitions may also trigger background forwarding to AgroApps.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate that the mission exists and the user has access to it
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT field_id, start_time
            FROM missions
            WHERE id = %s
            """,
            (mission_id,),
        )
        mission = cur.fetchone()

        if not mission:
            raise HTTPException(status_code=404, detail="Mission not found")

        _ensure_field_access(cur, mission["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Upsert the PC1-specific mission state
        # ------------------------------------------------------------------
        cur.execute(
            """
            INSERT INTO pc1_missions (mission_id, status)
            VALUES (%s, %s)
            ON CONFLICT (mission_id)
            DO UPDATE SET status = EXCLUDED.status
            RETURNING mission_id, status
            """,
            (mission_id, state.status),
        )
        updated_state = cur.fetchone()

        # Commit here so the state is stored even if a later forwarding step fails.
        conn.commit()

        # ------------------------------------------------------------------
        # 3. Trigger forwarding to AgroApps when inspection is completed
        # ------------------------------------------------------------------
        if state.status == "inspection_complete":
            cur.execute(
                """
                SELECT
                    id,
                    name,
                    image,
                    confidence,
                    ST_Y(weed_loc) AS lat,
                    ST_X(weed_loc) AS lon
                FROM pc1_weed
                WHERE inspection_id = %s
                """,
                (mission_id,),
            )
            weeds_data = cur.fetchall()

            minio_public_client = request.app.state.minio_public_client
            weeds_payload = []

            for w in weeds_data:
                external_image_url = w["image"]

                # If the image is stored as a MinIO URI, convert it to a
                # temporary public GET URL so AgroApps can access it.
                if external_image_url and external_image_url.startswith("minio://"):
                    try:
                        bucket_name, object_key = _parse_minio_uri(external_image_url)
                        external_image_url = minio_public_client.get_presigned_url(
                            "GET",
                            bucket_name,
                            object_key,
                            expires=timedelta(days=7),
                        )
                    except Exception:
                        # If URL generation fails, keep the original value.
                        # We do not want the whole request to fail because of a single image URL.
                        pass

                weeds_payload.append(
                    {
                        "id": w["id"],
                        "name": w["name"],
                        "image": external_image_url,
                        "confidence": int((w["confidence"] or 0) * 100),
                        "weed_loc": {
                            "lat": w["lat"],
                            "lon": w["lon"],
                        } if w["lat"] is not None else None,
                    }
                )

            payload = {
                "inspection_id": mission_id,
                "parcel_id": mission["field_id"],
                "date": mission["start_time"].strftime("%Y-%m-%d") if mission["start_time"] else "",
                "weeds": weeds_payload,
            }

            background_tasks.add_task(push_pc1_inspection_data, payload)

        # ------------------------------------------------------------------
        # 4. Trigger forwarding to AgroApps when spraying is completed
        # ------------------------------------------------------------------
        elif state.status == "spraying_complete":
            cur.execute(
                """
                SELECT id, spray_time
                FROM pc1_weed
                WHERE inspection_id = %s
                  AND is_sprayed = true
                """,
                (mission_id,),
            )
            sprayed_data = cur.fetchall()

            payload = {
                "inspection_id": mission_id,
                "sprayed_weeds": [
                    {
                        "id": w["id"],
                        "timestamp": w["spray_time"].strftime("%Y%m%d%H%M%S") if w["spray_time"] else "",
                    }
                    for w in sprayed_data
                ],
            }

            background_tasks.add_task(push_pc1_sprayed_weeds_data, payload)

    return updated_state


# ==========================================
# PC1 MinIO Image Endpoints
# ==========================================

@router.post("/images/presigned-url")
def get_pc1_upload_url(
    req: PC1ImageUploadRequest,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Generate a temporary presigned PUT URL so a connector can upload an image
    directly to MinIO without sending the binary through FastAPI.

    Important:
    * Bucket checks / creation use the INTERNAL MinIO client because they happen
      inside the Kubernetes cluster.
    * The presigned URL itself uses the PUBLIC MinIO client so that the caller
      running outside the cluster can actually reach the generated URL.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate mission and field access
        # ------------------------------------------------------------------
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

        if mission["mission_type"] not in ["pc1_inspection_and_spraying", "pc1_inspection"]:
            raise HTTPException(status_code=400, detail="Invalid mission type for PC1 images")

        _ensure_field_access(cur, mission["field_id"], user)

    minio_internal_client = request.app.state.minio_internal_client
    minio_public_client = request.app.state.minio_public_client
    bucket_name = "agribot-mission-images"

    # ----------------------------------------------------------------------
    # 2. Ensure the bucket exists using the INTERNAL MinIO endpoint
    # ----------------------------------------------------------------------
    try:
        if not minio_internal_client.bucket_exists(bucket_name):
            minio_internal_client.make_bucket(bucket_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    # ----------------------------------------------------------------------
    # 3. Generate a unique object key inside the mission folder
    # ----------------------------------------------------------------------
    file_ext = req.filename.split(".")[-1] if "." in req.filename else "bin"
    unique_name = f"{uuid.uuid4()}.{file_ext}"
    object_name = f"pc1/mission_{req.inspection_id}/{unique_name}"

    # ----------------------------------------------------------------------
    # 4. Generate the public presigned PUT URL using the PUBLIC MinIO client
    # ----------------------------------------------------------------------
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


@router.get("/weeds/{inspection_id}/{weed_id}/image-url")
def get_pc1_weed_image_url(
    inspection_id: int,
    weed_id: int,
    request: Request,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Generate a temporary presigned GET URL so the frontend can display
    a weed image stored in MinIO.

    The database stores the image as a MinIO URI:
        minio://bucket/object-key

    This endpoint converts it to a temporary HTTP URL.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Load the weed and make sure the user can access its field
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT w.image, m.field_id
            FROM pc1_weed w
            JOIN missions m
              ON m.id = w.inspection_id
            WHERE w.id = %s
              AND w.inspection_id = %s
            """,
            (weed_id, inspection_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Weed not found")

        if not row["image"] or not row["image"].startswith("minio://"):
            raise HTTPException(
                status_code=400,
                detail="No valid MinIO image associated with this weed",
            )

        _ensure_field_access(cur, row["field_id"], user)

    bucket_name, object_key = _parse_minio_uri(row["image"])
    minio_public_client = request.app.state.minio_public_client

    # ----------------------------------------------------------------------
    # 2. Generate a temporary GET URL that the frontend can use directly
    # ----------------------------------------------------------------------
    try:
        url = minio_public_client.get_presigned_url(
            "GET",
            bucket_name,
            object_key,
            expires=timedelta(hours=1),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO Error: {str(e)}")

    return {"image_url": url}


# ==========================================
# PC1 Weed Endpoints
# ==========================================

@router.post("/weeds/batch", response_model=List[Weed], status_code=status.HTTP_201_CREATED)
def create_pc1_weeds_batch(
    weeds_in: List[WeedCreate],
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Create multiple weeds in a single request.

    Each weed belongs to one inspection mission and may optionally reference
    an image stored in MinIO via a minio:// URI.
    """
    if not weeds_in:
        return []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate all referenced missions and access permissions
        # ------------------------------------------------------------------
        mission_ids = list(set(w.inspection_id for w in weeds_in))
        cur.execute(
            """
            SELECT id, field_id, mission_type
            FROM missions
            WHERE id = ANY(%s)
            """,
            (mission_ids,),
        )
        missions = {m["id"]: m for m in cur.fetchall()}

        for mission_id in mission_ids:
            if mission_id not in missions:
                raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")

            _ensure_field_access(cur, missions[mission_id]["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Bulk insert weeds
        # ------------------------------------------------------------------
        query = """
            INSERT INTO pc1_weed (
                id,
                inspection_id,
                name,
                image,
                confidence,
                weed_loc,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
            )
            VALUES %s
            RETURNING
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
        """

        template = """
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                CASE
                    WHEN %s::float IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326)
                END,
                %s,
                %s,
                %s,
                %s
            )
        """

        data_tuples = [
            (
                w.id,
                w.inspection_id,
                w.name,
                w.image,
                w.confidence,
                w.longitude,
                w.longitude,
                w.latitude,
                w.needs_verification,
                w.verified,
                w.is_sprayed,
                w.spray_time,
            )
            for w in weeds_in
        ]

        inserted_weeds = execute_values(cur, query, data_tuples, template=template, fetch=True)
        conn.commit()

    return inserted_weeds


@router.post("/weeds", response_model=Weed, status_code=status.HTTP_201_CREATED)
def create_pc1_weed(
    weed: WeedCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Legacy single-item weed creation endpoint.

    Prefer /weeds/batch for real connector integrations.
    """
    if not weed.id:
        raise HTTPException(status_code=400, detail="Weed id is required")

    if (weed.latitude is None) != (weed.longitude is None):
        raise HTTPException(
            status_code=400,
            detail="latitude and longitude must either both be provided or omitted",
        )

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate mission and access
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT id, field_id, mission_type
            FROM missions
            WHERE id = %s
            """,
            (weed.inspection_id,),
        )
        inspection = cur.fetchone()

        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection mission not found")

        if inspection["mission_type"] not in ["pc1_inspection", "pc1_inspection_and_spraying"]:
            raise HTTPException(
                status_code=400,
                detail="Weeds can only be attached to PC1 inspection missions",
            )

        _ensure_field_access(cur, inspection["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Insert weed
        # ------------------------------------------------------------------
        cur.execute(
            """
            INSERT INTO pc1_weed (
                id,
                inspection_id,
                name,
                image,
                confidence,
                weed_loc,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                CASE
                    WHEN %s::float IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_MakePoint(%s::float, %s::float), 4326)
                END,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
            """,
            (
                weed.id,
                weed.inspection_id,
                weed.name,
                weed.image,
                weed.confidence,
                weed.longitude,
                weed.longitude,
                weed.latitude,
                weed.needs_verification,
                weed.verified,
                weed.is_sprayed,
                weed.spray_time,
            ),
        )
        new_weed = cur.fetchone()
        conn.commit()

    return new_weed


@router.patch("/weeds/batch", response_model=List[Weed])
def update_pc1_weeds_batch(
    updates: List[WeedBatchUpdateItem],
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Batch update weed verification / sprayed status.

    Matching uses the composite key:
    * id
    * inspection_id
    """
    if not updates:
        return []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate access for all involved missions
        # ------------------------------------------------------------------
        mission_ids = list(set(u.inspection_id for u in updates))
        cur.execute(
            """
            SELECT id, field_id
            FROM missions
            WHERE id = ANY(%s)
            """,
            (mission_ids,),
        )
        missions = cur.fetchall()

        for mission in missions:
            _ensure_field_access(cur, mission["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Bulk update by composite key
        # ------------------------------------------------------------------
        query = """
            UPDATE pc1_weed AS w
            SET verified = data.verified::boolean,
                is_sprayed = data.is_sprayed::boolean,
                spray_time = data.spray_time::timestamptz
            FROM (VALUES %s) AS data(id, inspection_id, verified, is_sprayed, spray_time)
            WHERE w.id = data.id::int
              AND w.inspection_id = data.inspection_id::int
            RETURNING
                w.id,
                w.inspection_id,
                w.name,
                w.image,
                w.confidence,
                ST_Y(w.weed_loc) AS latitude,
                ST_X(w.weed_loc) AS longitude,
                w.needs_verification,
                w.verified,
                w.is_sprayed,
                w.spray_time
        """

        data_tuples = [
            (u.id, u.inspection_id, u.verified, u.is_sprayed, u.spray_time)
            for u in updates
        ]

        updated_weeds = execute_values(cur, query, data_tuples, fetch=True)
        conn.commit()

    return updated_weeds


@router.patch("/weeds/{weed_id}", response_model=Weed)
def update_pc1_weed(
    weed_id: int,
    weed_update: WeedUpdate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    Legacy single-item weed update endpoint.

    Prefer /weeds/batch for real connector integrations.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Load weed and validate access
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT w.id, w.inspection_id, m.field_id
            FROM pc1_weed w
            JOIN missions m
              ON m.id = w.inspection_id
            WHERE w.id = %s
            """,
            (weed_id,),
        )
        weed_row = cur.fetchone()

        if not weed_row:
            raise HTTPException(status_code=404, detail="Weed not found")

        _ensure_field_access(cur, weed_row["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Update using the composite key
        # ------------------------------------------------------------------
        cur.execute(
            """
            UPDATE pc1_weed
            SET verified = %s,
                is_sprayed = %s,
                spray_time = %s
            WHERE id = %s
              AND inspection_id = %s
            RETURNING
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
            """,
            (
                weed_update.verified,
                weed_update.is_sprayed,
                weed_update.spray_time,
                weed_id,
                weed_row["inspection_id"],
            ),
        )
        updated_weed = cur.fetchone()
        conn.commit()

    return updated_weed


@router.get("/weeds/{inspection_id}", response_model=List[Weed])
def list_pc1_weeds(
    inspection_id: int,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    """
    List all weeds belonging to a single inspection mission.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # ------------------------------------------------------------------
        # 1. Validate mission and access
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT id, field_id
            FROM missions
            WHERE id = %s
            """,
            (inspection_id,),
        )
        inspection = cur.fetchone()

        if not inspection:
            raise HTTPException(status_code=404, detail="Inspection not found")

        _ensure_field_access(cur, inspection["field_id"], user)

        # ------------------------------------------------------------------
        # 2. Return weeds
        # ------------------------------------------------------------------
        cur.execute(
            """
            SELECT
                id,
                inspection_id,
                name,
                image,
                confidence,
                ST_Y(weed_loc) AS latitude,
                ST_X(weed_loc) AS longitude,
                needs_verification,
                verified,
                is_sprayed,
                spray_time
            FROM pc1_weed
            WHERE inspection_id = %s
            ORDER BY id
            """,
            (inspection_id,),
        )
        return cur.fetchall()
