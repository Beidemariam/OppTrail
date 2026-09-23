import sqlite3

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from .auth import (
    SESSION_COOKIE_NAME,
    clear_session,
    create_session,
    delete_user_sessions,
    get_current_user,
    hash_password,
    normalize_email,
    verify_password,
)
from .database import db_connection
from .rate_limit import auth_rate_limiter, client_key
from .schemas import AuthResponse, LoginRequest, PasswordChangeRequest, SignupRequest, UserPublic
from .settings import settings
from .time_utils import utc_now

router = APIRouter(prefix="/api/v2/auth", tags=["auth"])


def public_user(row: sqlite3.Row) -> UserPublic:
    return UserPublic(
        id=row["id"],
        email=row["email"],
        name=row["name"],
        created_at=row["created_at"],
    )


def enforce_auth_rate_limit(request: Request, scope: str) -> None:
    """Applied before any password work, so a flood costs the server a dict
    lookup rather than a bcrypt verification.
    """
    auth_rate_limiter.check(
        client_key(request, scope),
        settings.auth_rate_limit_attempts,
        settings.auth_rate_limit_window_seconds,
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthResponse:
    enforce_auth_rate_limit(request, "signup")
    email = normalize_email(payload.email)
    with db_connection() as connection:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (email, hash_password(payload.password), payload.name, utc_now()),
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

    create_session(response, int(user["id"]), session_id)
    return AuthResponse(user=public_user(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> AuthResponse:
    enforce_auth_rate_limit(request, "login")
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

    create_session(response, int(user["id"]), session_id)
    return AuthResponse(user=public_user(user))


@router.post("/password", response_model=AuthResponse)
def change_password(
    payload: PasswordChangeRequest,
    response: Response,
    user: sqlite3.Row = Depends(get_current_user),
) -> AuthResponse:
    """Changing the password invalidates every existing session, including the
    caller's, and issues a fresh one — so a stolen cookie stops working the
    moment the theft is responded to (brief §4.5).
    """
    with db_connection() as connection:
        stored = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()

        if not verify_password(payload.current_password, stored["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(payload.new_password), user["id"]),
        )
        delete_user_sessions(connection, int(user["id"]))
        connection.commit()

    create_session(response, int(user["id"]), None)
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
