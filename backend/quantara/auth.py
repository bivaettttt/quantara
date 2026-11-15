from hashlib import sha256
from secrets import token_urlsafe
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from quantara.db import audit, engine, row, sql

passwords = PasswordHasher()
dummy = passwords.hash(token_urlsafe(16))
scheme = HTTPBearer(auto_error=False)
FIN = ("ADMIN", "FINANCIAL_ANALYST", "DATA_ANALYST")
DATA = ("ADMIN", "DATA_ANALYST", "DATA_ENGINEER", "DATA_STEWARD")
ENGINEERING = ("ADMIN", "DATA_ENGINEER", "DATA_STEWARD")


def token_hash(token):
    return sha256(token.encode()).hexdigest()


def signin(payload, request):
    with engine.begin() as conn:
        found = row(conn, "SELECT * FROM users WHERE login=:login", login=payload.login)
        try:
            valid = passwords.verify(
                found["password"] if found else dummy, payload.password
            )
        except VerifyMismatchError:
            valid = False
        if not found or not valid:
            raise HTTPException(401, "INVALID_CREDENTIALS")
        token = token_urlsafe(32)
        sql(
            conn,
            "INSERT INTO sessions VALUES (:key,:login,now()+interval '8 hours')",
            key=token_hash(token),
            login=payload.login,
        )
        audit(conn, payload.login, request, "SIGN_IN", payload.login)
        return {k: found[k] for k in ("login", "name", "role")} | {"token": token}


def identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(scheme)],
):
    if credentials:
        key = token_hash(credentials.credentials)
        with engine.connect() as conn:
            found = row(
                conn,
                """SELECT u.login,u.name,u.role FROM users u JOIN sessions s ON s.login=u.login
                WHERE s.token_digest=:d AND s.expires>now()""",
                d=key,
            )
        if found:
            return found | {"session": key}
    raise HTTPException(401, "AUTH_REQUIRED")


Actor = Annotated[dict, Depends(identity)]


def allow(actor, *roles):
    if actor["role"] not in roles:
        raise HTTPException(403, "ROLE_FORBIDDEN")
