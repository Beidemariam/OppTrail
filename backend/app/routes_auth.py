import sqlite3

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from .auth import (
    SESSION_COOKIE_NAME,
    clear_session,
    create_session,
    get_current_user,
    hash_password,
    normalize_email,
    verify_password,
)
from .database import db_connection
from .schemas import AuthResponse, LoginRequest, SignupRequest, UserPublic

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(row: sqlite3.Row) -> UserPublic:
    return UserPublic(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        created_at=row["created_at"],
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response) -> AuthResponse:
    email = normalize_email(payload.email)
    with db_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, name)
                VALUES (?, ?, ?)
                """,
                (email, hash_password(payload.password), payload.name),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            ) from exc

        user = connection.execute(
            "SELECT id, email, name, created_at FROM users WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    create_session(response, int(user["id"]))
    return AuthResponse(user=public_user(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response) -> AuthResponse:
    with db_connection() as connection:
        user = connection.execute(
            "SELECT id, email, name, password_hash, created_at FROM users WHERE email = ?",
            (normalize_email(payload.email),),
        ).fetchone()

    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    create_session(response, int(user["id"]))
    return AuthResponse(user=public_user(user))


@router.post("/logout")
def logout(
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, bool]:
    clear_session(response, session_id)
    return {"ok": True}


@router.get("/me", response_model=AuthResponse)
def me(user: sqlite3.Row = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=public_user(user))
