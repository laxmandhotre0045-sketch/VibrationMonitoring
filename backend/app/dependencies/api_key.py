"""Authenticate a device by API key.

Devices posting measurements have no interactive login, so they present
`X-API-Key` instead of a bearer token. The key is looked up by digest; unknown,
revoked and expired keys are indistinguishable to the caller.
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.crud import integration as crud
from app.database import get_db
from app.models.integration import ApiKey

API_KEY_HEADER = "X-API-Key"


def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> ApiKey:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing {API_KEY_HEADER} header",
        )

    key = crud.resolve_api_key(db, x_api_key.strip())
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, revoked or expired API key",
        )

    crud.touch_api_key(db, key)
    return key
