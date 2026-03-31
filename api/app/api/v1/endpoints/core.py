from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import (
    Field,
    FieldBatchCreate,
    FieldCreate,
    FieldOwnershipBatchCreate,
    MissionType,
    UserCreate,
    UserResponse,
)
from app.security import UserInDB, get_current_active_user, get_password_hash

router = APIRouter()


@router.post("/users/batch", response_model=List[UserResponse], status_code=status.HTTP_201_CREATED)
def create_users_batch(
    users_in: List[UserCreate],
    conn=Depends(get_db_conn),
    current_user: UserInDB = Depends(get_current_active_user),
):
    # 1. Authorization Check
    # Only service_providers (like FIRMP) or admins should be able to batch upload users
    if current_user.role not in ["service_provider", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Only service_providers or admins can upload users."
        )

    if not users_in:
        return []

    data_tuples = [
        (
            u.id,
            u.email,
            get_password_hash(u.password),
            u.name,
            u.role,
            u.is_active
        )
        for u in users_in
    ]

    # 3. Perform Bulk Insert
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
            INSERT INTO users (id, email, password_hash, name, role, is_active)
            VALUES %s
            RETURNING id, email, name, role, is_active
        """

        try:
            inserted_users = execute_values(cur, query, data_tuples, fetch=True)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error during bulk upload: {str(e)}"
            )

    return inserted_users


def _ensure_field_access(cur, field_id: int, user: UserInDB) -> None:
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


@router.post("/fields", response_model=Field, status_code=status.HTTP_201_CREATED)
def create_field(
    field: FieldCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    shape_json = field.shape.model_dump_json() if field.shape is not None else None

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO fields (name, crop_name, boundary)
            VALUES (
                %s,
                %s,
                CASE
                    WHEN %s IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                END
            )
            RETURNING
                id,
                name,
                crop_name,
                CASE
                    WHEN boundary IS NULL THEN NULL
                    ELSE ST_AsGeoJSON(boundary)::json
                END AS shape
            """,
            (
                field.name,
                field.crop_name,
                shape_json,
                shape_json,
            ),
        )
        new_field = cur.fetchone()

        cur.execute(
            """
            INSERT INTO field_ownerships (field_id, user_id, ownership_percentage)
            VALUES (%s, %s, %s)
            """,
            (new_field["id"], user.id, 100.0),
        )

        conn.commit()

    new_field["owners"] = [
        {
            "user_id": user.id,
            "ownership_percentage": 100.0,
        }
    ]
    return new_field




@router.post("/fields/batch", response_model=List[Field], status_code=status.HTTP_201_CREATED)
def create_fields_batch(
    fields_in: List[FieldBatchCreate],
    conn=Depends(get_db_conn),
    current_user: UserInDB = Depends(get_current_active_user),
):
    if current_user.role not in ["service_provider", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions."
        )

    if not fields_in:
        return []

    field_tuples = [
        (
            f.name,
            f.crop_name,
            f.shape.model_dump_json() if f.shape is not None else None,
            f.shape.model_dump_json() if f.shape is not None else None,
        )
        for f in fields_in
    ]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
            INSERT INTO fields (name, crop_name, boundary)
            VALUES %s
            RETURNING
                id,
                name,
                crop_name,
                CASE
                    WHEN boundary IS NULL THEN NULL
                    ELSE ST_AsGeoJSON(boundary)::json
                END AS shape
        """

        template = """
            (
                %s,
                %s,
                CASE
                    WHEN %s::text IS NULL THEN NULL
                    ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s::text), 4326)
                END
            )
        """

        try:
            inserted_fields = execute_values(cur, query, field_tuples, template=template, fetch=True)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"Upload failed. Error: {str(e)}")

    for field in inserted_fields:
        field["owners"] = []

    return inserted_fields




@router.post("/field-ownerships/batch", status_code=status.HTTP_201_CREATED)
def create_field_ownerships_batch(
    payload: FieldOwnershipBatchCreate,
    conn=Depends(get_db_conn),
    current_user: UserInDB = Depends(get_current_active_user),
):
    if current_user.role not in ["service_provider", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions."
        )

    if not payload.items:
        return {"message": "No ownerships provided."}

    ownership_tuples = [
        (item.field_id, item.user_id, item.ownership_percentage)
        for item in payload.items
    ]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
            INSERT INTO field_ownerships (field_id, user_id, ownership_percentage)
            VALUES %s
            ON CONFLICT (field_id, user_id)
            DO UPDATE SET ownership_percentage = EXCLUDED.ownership_percentage
        """

        try:
            execute_values(cur, query, ownership_tuples)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"Ownership upload failed. Error: {str(e)}")

    return {"message": f"Successfully upserted {len(payload.items)} field ownership records."}


@router.get("/fields", response_model=List[Field])
def list_fields(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                f.id,
                f.name,
                f.crop_name,
                CASE
                    WHEN f.boundary IS NULL THEN NULL
                    ELSE ST_AsGeoJSON(f.boundary)::json
                END AS shape,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'user_id', fo.user_id,
                            'ownership_percentage', fo.ownership_percentage
                        )
                        ORDER BY fo.user_id
                    ) FILTER (WHERE fo.user_id IS NOT NULL),
                    '[]'::json
                ) AS owners
            FROM fields f
            LEFT JOIN field_ownerships fo
                ON fo.field_id = f.id
            WHERE %s = 'admin'
               OR EXISTS (
                    SELECT 1
                    FROM field_ownerships own
                    WHERE own.field_id = f.id
                      AND own.user_id = %s
               )
            GROUP BY f.id
            ORDER BY f.id
            """,
            (user.role or "", user.id),
        )
        return cur.fetchall()




@router.get("/mission-types", response_model=List[MissionType])
def list_mission_types(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, pilot_case, partner, description
            FROM mission_types
            ORDER BY id
            """
        )
        return cur.fetchall()
