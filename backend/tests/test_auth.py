"""Authentication.

The first five tests here are `scripts/test_auth_phase1.py`, which this module
replaces. That script was a sequence of `assert`s against a module-level
`TestClient`, run by hand and printing as it went: it needed a developer to
remember it existed, it seeded the shared development database, and a failure
halfway through left the earlier steps' rows behind. The same five assertions
now run on every `pytest`, against a transaction that is rolled back.

The rest are the cases it did not cover — the ones where getting it wrong is
quiet rather than loud. A refresh token that still works after logout, or a
token that a changed secret still validates, is not a visible failure.
"""
from __future__ import annotations

import pytest

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, login

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# The converted smoke path
# ---------------------------------------------------------------------------


def test_login_returns_a_token_pair(client, admin_user):
    tokens = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["expires_in"] > 0
    assert tokens.get("token_type", "bearer").lower() == "bearer"


def test_me_returns_the_signed_in_user_and_roles(client, admin_headers):
    response = client.get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == ADMIN_EMAIL
    assert "super_admin" in body["roles"]


def test_refresh_exchanges_a_refresh_token_for_a_new_pair(client, admin_tokens):
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": admin_tokens["refresh_token"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_logout_succeeds(client, admin_tokens):
    refreshed = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": admin_tokens["refresh_token"]}
    ).json()
    response = client.post(
        "/api/v1/auth/logout", json={"refresh_token": refreshed["refresh_token"]}
    )
    assert response.status_code == 204


def test_me_without_a_token_is_rejected(client):
    assert client.get("/api/v1/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# What the script never checked
# ---------------------------------------------------------------------------


def test_logout_actually_revokes_the_refresh_token(client, admin_tokens):
    """The half of logout that matters.

    The script asserted logout answered 204 and stopped there — which it would
    also do if it revoked nothing at all. A refresh token that still works
    after logout is a session that never really ended.
    """
    refresh_token = admin_tokens["refresh_token"]
    assert client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token}).status_code == 204

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401, "a revoked refresh token was accepted"


def test_wrong_password_is_rejected(client, admin_user):
    response = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "not-the-password"}
    )
    assert response.status_code == 401


def test_unknown_email_is_rejected(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 401


def test_login_does_not_say_which_half_was_wrong(client, admin_user):
    """Same answer for a bad password and an unknown account.

    A login that distinguishes the two turns the endpoint into a way to find
    out who has an account here.
    """
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"}
    )
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "x"}
    )
    assert unknown.status_code == wrong_password.status_code
    assert unknown.json().get("detail") == wrong_password.json().get("detail")


def test_email_is_matched_case_insensitively(client, admin_user):
    """Users type their address however they like; accounts are stored lowercase."""
    tokens = login(client, ADMIN_EMAIL.upper(), ADMIN_PASSWORD)
    assert tokens["access_token"]


def test_a_garbage_token_is_rejected(client):
    response = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_a_token_signed_with_another_secret_is_rejected(client, admin_user):
    """Someone else's signing key is not ours.

    Cheap to get wrong — a decode that skips verification, or a fallback
    secret — and completely silent when it is.
    """
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    forged = jwt.encode(
        {
            "sub": str(admin_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "a-different-secret-entirely",
        algorithm="HS256",
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_an_expired_token_is_rejected(client, admin_user):
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.config import settings

    expired = jwt.encode(
        {
            "sub": str(admin_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret or settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_an_access_token_is_not_a_refresh_token(client, admin_tokens):
    """The two are not interchangeable.

    An access token accepted at the refresh endpoint would let a leaked
    short-lived token be traded up for a long-lived session.
    """
    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": admin_tokens["access_token"]}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Password hashing — no database needed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("password", ["Admin@2024", "a", "ünïcødé-pass", "x" * 60])
def test_password_round_trip(password):
    from app.services.auth_service import hash_password, verify_password

    hashed = hash_password(password)
    assert hashed != password, "the password was stored in the clear"
    assert verify_password(password, hashed)
    assert not verify_password(password + "x", hashed)


def test_bcrypt_ignores_everything_past_72_bytes():
    """Recorded because it is surprising, and because the schema disagrees.

    bcrypt hashes at most 72 bytes. `UserCreate.password` allows 128
    characters, so a user who sets a 100-character password can sign in with
    just its first 72 — the rest never reaches the hash and nothing says so.

    Not a break (an attacker still needs those 72 bytes), but it quietly caps
    the strength of long passwords. The usual fix is to SHA-256 the password
    before handing it to bcrypt, so the whole thing contributes. Until then
    this test states the behaviour rather than letting the next person
    rediscover it.
    """
    from app.services.auth_service import hash_password, verify_password

    seventy_two = "x" * 72
    hashed = hash_password(seventy_two)
    assert verify_password(seventy_two + "ignored-entirely", hashed)

    # Within the limit it behaves as you would expect.
    assert not verify_password("x" * 71, hashed)


def test_the_same_password_hashes_differently_each_time():
    """A per-password salt, so equal hashes never reveal equal passwords."""
    from app.services.auth_service import hash_password, verify_password

    first, second = hash_password("Admin@2024"), hash_password("Admin@2024")
    assert first != second
    assert verify_password("Admin@2024", first)
    assert verify_password("Admin@2024", second)
