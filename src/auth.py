"""Verifies the short-lived service token the Next.js frontend mints after a
successful Google sign-in (see frontend/app/api/backend-token/route.ts).

Why a separate token instead of trusting NextAuth's own session cookie
directly: that cookie is scoped to the frontend's origin and signed with a
secret (AUTH_SECRET) that has nothing to do with this backend, so this
service could never verify it. Instead, once the frontend's own server has
already verified the user (via next-auth's server-side session check), it
mints a small HS256 JWT - {sub, email, name}, ~10 min expiry - signed with
BACKEND_JWT_SECRET, a plain shared secret set on both Railway services. This
backend verifies that JWT the normal way (signature + exp), no network call
out, no dependency on NextAuth's internals.

`sub` is Google's stable per-account id - the owner key for threads/history
going forward, replacing the old anonymous device_id (which any caller could
set to any value; a verified user id closes that hole too).
"""
import os

import jwt
from fastapi import Header, HTTPException

_SECRET = os.environ["BACKEND_JWT_SECRET"]
_ALGO = "HS256"


class CurrentUser:
    __slots__ = ("id", "email", "name")

    def __init__(self, sub: str, email: str | None, name: str | None):
        self.id = sub
        self.email = email
        self.name = name


def get_current_user(authorization: str = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired, please refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid session")
    return CurrentUser(sub=sub, email=payload.get("email"), name=payload.get("name"))
