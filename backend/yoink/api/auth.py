"""Supabase JWT verification via JWKS (ES256/RS256) or HS256 secret.

Follows: https://supabase.com/docs/guides/auth/jwts#verifying-jwts
JWKS endpoint: GET {SUPABASE_URL}/auth/v1/.well-known/jwks.json
"""

import json
import logging
import os
import time
from typing import Optional

import httpx
import jwt as pyjwt
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from fastapi import Request

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""

# In-memory JWKS cache (refreshed every 5 min, matching Supabase Edge 10-min cache)
_jwks_cache: dict | None = None
_jwks_cache_ts: float = 0.0
_JWKS_TTL = 300


def _fetch_jwks() -> Optional[dict]:
    """Fetch JWKS from the documented Supabase endpoint, with caching."""
    global _jwks_cache, _jwks_cache_ts

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_ts) < _JWKS_TTL:
        return _jwks_cache

    if not JWKS_URL:
        logger.warning("SUPABASE_URL not set; cannot fetch JWKS")
        return None

    try:
        resp = httpx.get(JWKS_URL, timeout=5.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_ts = now
        return _jwks_cache
    except Exception as exc:
        logger.warning("JWKS fetch from %s failed: %s", JWKS_URL, exc)
        return None


def _signing_key_from_jwks(header: dict) -> Optional[object]:
    """Resolve the public signing key for the given JWT header from JWKS."""
    jwks = _fetch_jwks()
    if not jwks:
        return None

    kid = header.get("kid")
    alg = header.get("alg")
    jwk = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not jwk:
        logger.warning("No JWKS key found for kid=%s", kid)
        return None

    jwk_json = json.dumps(jwk)
    if alg == "ES256":
        return ECAlgorithm.from_jwk(jwk_json)
    if alg == "RS256":
        return RSAAlgorithm.from_jwk(jwk_json)
    logger.warning("Unsupported asymmetric alg in JWKS: %s", alg)
    return None


async def get_optional_user(request: Request) -> Optional[str]:
    """Extract and verify Supabase JWT from the Authorization header.

    Verification strategy (per Supabase docs):
      - ES256 / RS256: verify locally using JWKS public key.
      - HS256 (legacy): verify using SUPABASE_JWT_SECRET.

    Returns:
        user_id (UUID string) if token is valid, None for guests.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        header = pyjwt.get_unverified_header(token)
    except Exception as exc:
        logger.warning("JWT header unreadable: %s", exc)
        return None

    alg = header.get("alg", "HS256")

    try:
        if alg in {"ES256", "RS256"}:
            key = _signing_key_from_jwks(header)
            if not key:
                return None
            payload = pyjwt.decode(token, key, algorithms=[alg], audience="authenticated")
        else:
            if not SUPABASE_JWT_SECRET:
                logger.warning("SUPABASE_JWT_SECRET not set for HS256 token")
                return None
            payload = pyjwt.decode(
                token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated"
            )

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("JWT missing 'sub' claim")
            return None
        return user_id
    except pyjwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        return None
    except pyjwt.InvalidTokenError as e:
        logger.warning("JWT invalid: %s", e)
        return None
