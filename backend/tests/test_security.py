import uuid

import pytest

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_is_not_plaintext():
    hashed = hash_password("correct-horse-battery-staple")
    assert "correct-horse-battery-staple" not in hashed


def test_access_token_roundtrip():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    payload = decode_token(token, TokenType.ACCESS)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_refresh_token_rejected_as_access_token():
    user_id = uuid.uuid4()
    refresh = create_refresh_token(user_id)
    with pytest.raises(InvalidTokenError):
        decode_token(refresh, TokenType.ACCESS)


def test_garbage_token_rejected():
    with pytest.raises(InvalidTokenError):
        decode_token("not-a-real-token", TokenType.ACCESS)
