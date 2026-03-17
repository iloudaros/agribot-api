from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg2.extras import RealDictCursor, execute_values

from app.core.db import get_db_conn
from app.models.schemas import Farm, FarmCreate, FarmBatchCreate, Field, FieldCreate, MissionType, UserCreate, UserResponse
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

    # 2. Hash passwords and prepare the tuple list for bulk insertion
    data_tuples = [
        (
            u.username,
            get_password_hash(u.password),
            u.name,
            u.surname,
            u.role,
            u.is_active
        )
        for u in users_in
    ]

    # 3. Perform Bulk Insert
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Using ON CONFLICT DO NOTHING ensures the query doesn't crash 
        # if a username already exists in the database.
        query = """
            INSERT INTO users (username, password_hash, name, surname, role, is_active)
            VALUES %s
            ON CONFLICT (username) DO NOTHING
            RETURNING id, username, name, surname, role, is_active
        """
        
        try:
            # fetch=True is required to get the RETURNING clause results back
            inserted_users = execute_values(cur, query, data_tuples, fetch=True)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail=f"Database error during bulk upload: {str(e)}"
            )

    # Note: If a user was skipped due to a duplicate username, they won't 
    # appear in this returned list.
    return inserted_users

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


@router.post("/farms/batch", response_model=List[Farm], status_code=status.HTTP_201_CREATED)
def create_farms_batch(
    farms_in: List[FarmBatchCreate],
    conn=Depends(get_db_conn),
    current_user: UserInDB = Depends(get_current_active_user),
):
    if current_user.role not in ["service_provider", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    if not farms_in:
        return []

    # PostGIS ST_MakePoint expects (Longitude, Latitude)
    farm_tuples = [(f.name, f.center_lon, f.center_lat) for f in farms_in]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1. Insert the farms
        query = """
            INSERT INTO farms (name, location_center)
            VALUES %s
            RETURNING id, name, ST_Y(location_center) AS center_lat, ST_X(location_center) AS center_lon
        """
        # The template applies the PostGIS function to the variables provided in the tuple
        template = "(%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))"
        
        try:
            inserted_farms = execute_values(cur, query, farm_tuples, template=template, fetch=True)
            
            # 2. Insert the ownerships
            # execute_values preserves order, so the returned IDs map 1:1 with farms_in
            ownership_tuples = [
                (inserted_farms[i]["id"], farms_in[i].owner_id, farms_in[i].ownership_percentage)
                for i in range(len(farms_in))
            ]
            
            own_query = """
                INSERT INTO farm_ownerships (farm_id, user_id, ownership_percentage)
                VALUES %s
                ON CONFLICT (farm_id, user_id) DO NOTHING
            """
            execute_values(cur, own_query, ownership_tuples)
            conn.commit()

        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Format the response to match the Pydantic Farm model
    result = []
    for i, farm in enumerate(inserted_farms):
        farm_dict = dict(farm)
        farm_dict["owners"] = [{
            "user_id": farms_in[i].owner_id,
            "ownership_percentage": farms_in[i].ownership_percentage
        }]
        result.append(farm_dict)
        
    return result


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

@router.post("/fields/batch", response_model=List[Field], status_code=status.HTTP_201_CREATED)
def create_fields_batch(
    fields_in: List[FieldCreate],
    conn=Depends(get_db_conn),
    current_user: UserInDB = Depends(get_current_active_user),
):
    if current_user.role not in ["service_provider", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions.")

    if not fields_in:
        return []

    # Note: We pass boundary_wkt twice so we can use it in the CASE WHEN template condition
    field_tuples = [
        (f.farm_id, f.name, f.crop_name, f.boundary_wkt, f.boundary_wkt)
        for f in fields_in
    ]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        query = """
            INSERT INTO fields (farm_id, name, crop_name, boundary)
            VALUES %s
            RETURNING id, farm_id, name, crop_name, ST_AsText(boundary) AS boundary_wkt
        """
        
        # Template gracefully handles both missing boundaries (NULL) and valid WKT strings
        template = "(%s, %s, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE ST_GeomFromText(%s::text, 4326) END)"
        
        try:
            inserted_fields = execute_values(cur, query, field_tuples, template=template, fetch=True)
            conn.commit()
        except Exception as e:
            conn.rollback()
            # If a farm_id doesn't exist, Postgres will throw a foreign key violation here
            raise HTTPException(status_code=400, detail=f"Upload failed. Ensure all farm_ids exist. Error: {str(e)}")

    return inserted_fields


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
