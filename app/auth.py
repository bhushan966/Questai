import os
from fastapi import Header, HTTPException
from jose import jwt, JWTError
import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL")  # e.g. https://dhfdhjschccpvejbxxmm.supabase.co
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

_jwks_cache = None


def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        response = httpx.get(JWKS_URL)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache


def get_current_user(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")

    try:
        jwks = get_jwks()
        unverified_header = jwt.get_unverified_header(token)
        key = next((k for k in jwks["keys"] if k["kid"] == unverified_header["kid"]), None)
        if not key:
            raise JWTError("Matching key not found in JWKS")

        payload = jwt.decode(token, key, algorithms=[unverified_header["alg"]], audience="authenticated")
    except JWTError as e:
        print(f"JWT decode failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return payload["sub"]