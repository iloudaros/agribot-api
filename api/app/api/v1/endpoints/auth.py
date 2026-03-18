from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

from typing import Optional

from app.core.db import get_db_conn
from app.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    verify_password,
)

router = APIRouter()


class Token(BaseModel):
    access_token: str
    token_type: str


@router.post("/token", response_model=Token, summary="Login and get JWT access token")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(get_db_conn),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, username, password_hash, role, is_active
            FROM users
            WHERE username = %s
            """,
            (form_data.username,)
        )
        user = cur.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


class FrontendLoginRequest(BaseModel):
    username: str
    password: str

class UserProfile(BaseModel):
    id: int
    username: str
    name: Optional[str] = None
    surname: Optional[str] = None
    role: str

class FrontendLoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserProfile

@router.post("/farmer-login", response_model=FrontendLoginResponse, summary="Frontend login for Farmers (JSON)")
def frontend_farmer_login(
    credentials: FrontendLoginRequest,
    conn=Depends(get_db_conn),
):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, username, password_hash, name, surname, role, is_active
            FROM users
            WHERE username = %s
            """,
            (credentials.username,)
        )
        user = cur.fetchone()

    # 1. Check if user exists and password is correct
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    # 2. Check if user is active
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # 3. Restrict access to Farmers (and maybe Admins)
    if user["role"] not in ["farmer", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This portal is restricted to farmers.",
        )

    # 4. Generate Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"]},
        expires_delta=access_token_expires,
    )

    # 5. Return Token AND User Profile
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "surname": user["surname"],
            "role": user["role"]
        }
    }
