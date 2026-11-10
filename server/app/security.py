"""Inicio de sesión local: contraseña con PBKDF2, bloqueo por intentos fallidos y token firmado (JWT)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.config import settings
from app.db import SessionLocal, User, utcnow

_ITERATIONS = 240_000
MAX_FAILED = 5
LOCK_MINUTES = 5


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def issue_token(user: User) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user.id, "iat": now, "exp": now + timedelta(hours=settings.session_hours)}
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def login(username: str, password: str) -> tuple[User, str]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username.strip().lower()).one_or_none()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos.")
        if user.locked_until and user.locked_until > utcnow():
            raise HTTPException(status.HTTP_423_LOCKED, "Cuenta bloqueada unos minutos por intentos fallidos.")
        if not verify_password(password, user.password_hash):
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED:
                user.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES)
                user.failed_logins = 0
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos.")
        user.failed_logins, user.locked_until = 0, None
        db.commit()
        return user, issue_token(user)


def _token_from(request: Request) -> str | None:
    # Solo por cabecera: un token en la URL quedaría en los registros del servidor.
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else None


def current_user(request: Request) -> User:
    token = _token_from(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar.")
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión expiró; vuelve a iniciar sesión.") from exc
    with SessionLocal() as db:
        user = db.get(User, claims["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión ya no es válida.")
    return user


CurrentUser = Depends(current_user)
