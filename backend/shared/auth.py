"""
Tenancy. Foundation Rule 1: business_id comes from the verified session and
nowhere else.

The rule survived the move off Cognito unchanged -- only where the verified
identity arrives from has changed. It used to be claims placed on the event by
an API Gateway authorizer; from Phase 3 it is a JWT this application signs and
verifies itself. Either way a service is handed a Principal and never reads a
tenant out of a request body.
"""
import re
import secrets
import time
import uuid
from dataclasses import dataclass

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

from shared import config
from shared.errors import ApiError, AuthError
from shared.log import logger
from shared.store import get_store

_hasher = PasswordHasher()

# Fields a client is never allowed to influence. Checked on every request so a
# future handler cannot quietly start trusting the body.
FORBIDDEN_CLIENT_FIELDS = ("business_id", "businessId", "user_id", "userId")


@dataclass(frozen=True)
class Principal:
    """Who is calling, resolved from a verified token. Never built from input."""

    user_id: str
    business_id: str
    email: str | None = None


def principal_from_claims(claims: dict) -> Principal:
    """Turn verified token claims into a Principal.

    Raises 401 when the claims carry no subject, and 403 when a real user has
    no business linked -- which means their sign-up did not finish.
    """
    sub = (claims or {}).get("sub")
    if not sub:
        raise AuthError()

    store = get_store()
    user = store.get_user(sub)
    if user and user.get("business_id"):
        return Principal(user_id=sub, business_id=user["business_id"],
                         email=user.get("email") or claims.get("email"))

    if not config.DEV_MODE:
        raise ApiError(403, "This account is not linked to a business yet.")

    business_id = new_business_id(claims.get("email") or sub)
    store.put_user(sub, business_id, claims.get("email"))
    logger.info("Provisioned a business for a new user", user_id=sub, business_id=business_id)
    return Principal(user_id=sub, business_id=business_id, email=claims.get("email"))


def new_business_id(seed: str) -> str:
    """Readable but unique -- two bakeries called Amba must not collide."""
    slug = re.sub(r"[^a-z0-9]+", "-", (seed or "").split("@")[0].lower()).strip("-")[:24]
    return f"biz-{slug}-{uuid.uuid4().hex[:6]}" if slug else f"biz-{uuid.uuid4().hex[:12]}"


def reject_client_tenancy(payload) -> None:
    """Refuse any request that tries to name its own tenant.

    Rule 1 says business_id is never accepted from the client. Ignoring such a
    field silently would work, but failing loudly means a bug that starts
    sending one gets caught in development rather than in production.
    """
    if not isinstance(payload, dict):
        return
    for forbidden in FORBIDDEN_CLIENT_FIELDS:
        if forbidden in payload:
            raise ApiError(400, "That field is set from your sign-in, not the request.")


# --- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    """argon2id, with the library's current defaults for salt and cost.

    Never write a hashing scheme by hand, and never store what the user typed.
    """
    return _hasher.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        return _hasher.verify(stored_hash, password)
    except (Argon2Error, ValueError):
        # A wrong password raises VerifyMismatchError (an Argon2Error); a
        # corrupt stored hash raises InvalidHash (a ValueError). The name of
        # that second one has changed across argon2-cffi releases, so catch the
        # base classes rather than pin to a version's spelling.
        return False


# --- tokens ------------------------------------------------------------------

def _secret() -> str:
    """The signing key. A deployment must pin it.

    Left unset in development we generate one per process, which signs
    everyone out on restart -- annoying, and much safer than shipping a
    default secret that ends up in production.
    """
    global _generated_secret
    if config.JWT_SECRET:
        return config.JWT_SECRET
    if not config.DEV_MODE:
        raise ApiError(500, "This server is missing its signing key.")
    if not _generated_secret:
        _generated_secret = secrets.token_urlsafe(32)
        logger.warn("PLUTUS_JWT_SECRET is not set; generated a throwaway key for this process")
    return _generated_secret


_generated_secret = ""


def issue_token(principal: Principal) -> str:
    """A signed session.

    business_id is deliberately NOT a claim. The token says who you are; which
    business that means is looked up server-side on every request, so a tenant
    can never be carried in something a client holds (Foundation Rule 1), and
    a claim nobody trusts is a claim nobody can accidentally start trusting.
    """
    now = int(time.time())
    return jwt.encode(
        {
            "sub": principal.user_id,
            "email": principal.email,
            "iat": now,
            "exp": now + config.JWT_TTL_MINUTES * 60,
        },
        _secret(),
        algorithm=config.JWT_ALGORITHM,
    )


def principal_from_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise AuthError("That sign-in is not valid.")
    return principal_from_claims(claims)
