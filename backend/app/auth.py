import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Cookie, HTTPException, Response, status

from .database import db_connection
from .security import CSRF_COOKIE_NAME, cookies_are_secure, new_csrf_token
from .time_utils import to_canonical, utc_now

SESSION_COOKIE_NAME = "opptrail_session"
SESSION_DAYS = 7


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_session(response: Response, user_id: int, previous_session_id: str | None) -> None:
    """Issue a new session, destroying the one the caller arrived with.

    Rotation is the point of `previous_session_id`: without it a token planted
    before authentication would stay valid alongside the new one, which is the
    session-fixation case brief §4.5 asks to close. The CSRF token is rotated
    with it for the same reason.
    """
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=SESSION_DAYS)

    with db_connection() as connection:
        # There is no background worker to sweep expired rows (ADR 0011), so
        # every new login clears out what has lapsed since the last one.
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (utc_now(),))
        if previous_session_id:
            connection.execute("DELETE FROM sessions WHERE id = ?", (previous_session_id,))
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
        secure=cookies_are_secure(),
        max_age=SESSION_DAYS * 24 * 60 * 60,
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=new_csrf_token(),
        httponly=False,
        samesite="lax",
        secure=cookies_are_secure(),
        max_age=SESSION_DAYS * 24 * 60 * 60,
    )


def delete_user_sessions(connection: sqlite3.Connection, user_id: int) -> None:
    """Every session of one user, used when a password changes. `sessions` is
    ephemeral authentication state, not user content, so this really is a row
    deletion (see CLAUDE.md's Soft deletes section).
    """
    connection.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def clear_session(response: Response, session_id: str | None) -> None:
    if session_id:
        with db_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            connection.commit()

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=cookies_are_secure(),
    )


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
