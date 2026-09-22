"""
Registration and sign-in.

This is what replaced Cognito. It is deliberately small: an email, an argon2
hash, and a signed token. What it does not do -- email verification, password
reset, MFA, lockout after repeated failures -- is listed in the README rather
than half-built here, because a half-built account recovery flow is worse than
an absent one.
"""
import re
import uuid

from shared.auth import (
    Principal,
    hash_password,
    issue_token,
    new_business_id,
    verify_password,
)
from shared.errors import ApiError, AuthError
from shared.log import logger
from shared.store import get_store

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 10


def register(email: str, password: str, business_name: str | None = None) -> dict:
    email = _clean_email(email)
    if len(password or "") < MIN_PASSWORD:
        raise ApiError(400, f"Choose a password of at least {MIN_PASSWORD} characters.")

    store = get_store()
    if store.get_user_by_email(email):
        # This does tell an attacker the address is registered. The alternative
        # is telling a real person their sign-up silently did nothing, which is
        # the worse failure for a product people have to actually use.
        raise ApiError(409, "That email already has an account. Sign in instead.")

    user_id = uuid.uuid4().hex
    business_id = new_business_id(business_name or email)
    store.put_user(user_id, business_id, email, hash_password(password))
    if business_name:
        meta = store.get_business_meta(business_id)
        store.put_business_meta(business_id, {**meta, "business_name": business_name})

    principal = Principal(user_id=user_id, business_id=business_id, email=email)
    logger.info("Registered a business", business_id=business_id)
    return _session(principal)


def login(email: str, password: str) -> dict:
    store = get_store()
    user = store.get_user_by_email(_clean_email(email))

    # One message for both "no such account" and "wrong password", so the
    # response cannot be used to find out which addresses are registered.
    if not user or not verify_password(password or "", user.get("password_hash")):
        raise AuthError("Email or password is incorrect.")

    principal = Principal(user_id=user["user_id"], business_id=user["business_id"],
                          email=user.get("email"))
    return _session(principal)


def _session(principal: Principal) -> dict:
    # The name goes back with the session so the interface never has to show a
    # business_id to a human -- it is an identifier, not a name.
    meta = get_store().get_business_meta(principal.business_id)
    return {
        "token": issue_token(principal),
        "user": {
            "email": principal.email,
            "business_id": principal.business_id,
            "business_name": meta.get("business_name"),
        },
    }


def _clean_email(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not EMAIL.match(cleaned):
        raise ApiError(400, "That does not look like an email address.")
    return cleaned
