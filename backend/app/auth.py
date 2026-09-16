import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, HTTPException, Response, status
from passlib.context import CryptContext

from .database import db_connection
from .time_utils import to_canonical, utc_now

SESSION_COOKIE_NAME = "opptrail_session"
SESSION_DAYS = 7
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    hashed: str = pwd_context.hash(password)
    return hashed


def verify_password(password: str, password_hash: str) -> bool:
    is_valid: bool = pwd_context.verify(password, password_hash)
    return is_valid


def create_session(response: Response, user_id: int) -> None:
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DAYS)

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_id, utc_now(), to_canonical(expires_at)),
        )
        connection.commit()

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
    )


def clear_session(response: Response, session_id: str | None) -> None:
    if session_id:
        with db_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            connection.commit()

    response.delete_cookie(key=SESSION_COOKIE_NAME, httponly=True, samesite="lax")


def get_current_user(
    session_id: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> sqlite3.Row:
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    now = utc_now()
    with db_connection() as connection:
        user: sqlite3.Row | None = connection.execute(
            """
            SELECT users.id, users.email, users.name, users.created_at
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.id = ? AND sessions.expires_at > ?
            """,
            (session_id, now),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return user
