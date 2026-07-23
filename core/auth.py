import secrets
import hashlib
from typing import Optional
from core.models import Client


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthError(Exception):
    pass


async def validate_token(token: str, db) -> Client:
    client = await db.get_client_by_token(hash_token(token))
    if not client:
        raise AuthError("Invalid token")
    if not client.is_active:
        raise AuthError("Client is inactive")
    return client