from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor

from app.core.db import get_db_conn
from app.models.schemas import Farm, FarmCreate, Field, FieldCreate, MissionType
from app.security import UserInDB, get_current_active_user

router = APIRouter()


def _ensure_farm_access(cur, farm_id: int, user: UserInDB) -> None:
    if user.role == "admin":
        return

    cur.execute(
        """
        SELECT 1
        FROM farm_ownerships
        WHERE farm_id = %s
          AND user_id = %s
        """,
        (farm_id, user.id),
    )
    if cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this farm",
        )


@router.post("/farms", response_model=Farm, status_code=status.HTTP_201_CREATED)
def create_farm(
    farm: FarmCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO farms (name, location_center)
            VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            RETURNING
                id,
                name,
                ST_Y(location_center) AS center_lat,
                ST_X(location_center) AS center_lon
            """,
            (farm.name, farm.center_lon, farm.center_lat),
        )
        new_farm = cur.fetchone()

        cur.execute(
            """
            INSERT INTO farm_ownerships (farm_id, user_id, ownership_percentage)
            VALUES (%s, %s, %s)
            """,
            (new_farm["id"], user.id, farm.ownership_percentage),
        )

        conn.commit()

    new_farm["owners"] = [
        {
            "user_id": user.id,
            "ownership_percentage": farm.ownership_percentage,
        }
    ]
    return new_farm


@router.get("/farms", response_model=List[Farm])
def list_farms(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                f.id,
                f.name,
                ST_Y(f.location_center) AS center_lat,
                ST_X(f.location_center) AS center_lon,
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
            FROM farms f
            LEFT JOIN farm_ownerships fo
                ON fo.farm_id = f.id
            WHERE %s = 'admin'
               OR EXISTS (
                    SELECT 1
                    FROM farm_ownerships own
                    WHERE own.farm_id = f.id
                      AND own.user_id = %s
               )
            GROUP BY f.id
            ORDER BY f.id
            """,
            (user.role or "", user.id),
        )
        return cur.fetchall()


@router.post("/fields", response_model=Field, status_code=status.HTTP_201_CREATED)
def create_field(
    field: FieldCreate,
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        _ensure_farm_access(cur, field.farm_id, user)

        cur.execute(
            """
            INSERT INTO fields (farm_id, name, crop_name, boundary)
            VALUES (
                %s,
                %s,
                %s,
                CASE
                    WHEN %s IS NULL THEN NULL
                    ELSE ST_GeomFromText(%s, 4326)
                END
            )
            RETURNING
                id,
                farm_id,
                name,
                crop_name,
                ST_AsText(boundary) AS boundary_wkt
            """,
            (
                field.farm_id,
                field.name,
                field.crop_name,
                field.boundary_wkt,
                field.boundary_wkt,
            ),
        )
        new_field = cur.fetchone()
        conn.commit()

    return new_field


@router.get("/fields", response_model=List[Field])
def list_fields(
    conn=Depends(get_db_conn),
    user: UserInDB = Depends(get_current_active_user),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                fld.id,
                fld.farm_id,
                fld.name,
                fld.crop_name,
                ST_AsText(fld.boundary) AS boundary_wkt
            FROM fields fld
            WHERE %s = 'admin'
               OR EXISTS (
                    SELECT 1
                    FROM farm_ownerships own
                    WHERE own.farm_id = fld.farm_id
                      AND own.user_id = %s
               )
            ORDER BY fld.id
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
