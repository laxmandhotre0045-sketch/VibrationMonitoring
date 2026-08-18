"""API key and webhook persistence.

The plaintext of an API key exists only in the response to the create call. What
lands here is a SHA-256 digest, which is what every later lookup compares
against — so a database leak cannot be replayed as a valid key.
"""
import hashlib
import secrets
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session, selectinload

from app.models.integration import ApiKey, Webhook, WebhookDelivery

KEY_PREFIX = "svk_"
_PREFIX_DISPLAY_LENGTH = 12


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key() -> Tuple[str, str, str]:
    """Return (plaintext, display_prefix, digest)."""
    plaintext = KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, plaintext[:_PREFIX_DISPLAY_LENGTH], hash_key(plaintext)


# ── API keys ────────────────────────────────────────────────────────────────

def list_api_keys(db: Session) -> List[ApiKey]:
    return db.query(ApiKey).order_by(ApiKey.created_at.desc()).all()


def get_api_key(db: Session, key_id: UUID) -> Optional[ApiKey]:
    return db.query(ApiKey).filter(ApiKey.id == key_id).first()


def create_api_key(
    db: Session,
    name: str,
    created_by_id: Optional[UUID],
    expires_at: Optional[datetime],
) -> Tuple[ApiKey, str]:
    plaintext, prefix, digest = generate_key()
    record = ApiKey(
        name=name,
        key_prefix=prefix,
        key_hash=digest,
        created_by_id=created_by_id,
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record, plaintext


def revoke_api_key(db: Session, key: ApiKey) -> ApiKey:
    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        db.commit()
        db.refresh(key)
    return key


def delete_api_key(db: Session, key: ApiKey) -> None:
    db.delete(key)
    db.commit()


def resolve_api_key(db: Session, plaintext: str) -> Optional[ApiKey]:
    """Look a key up by digest. Returns None for unknown, revoked or expired."""
    record = db.query(ApiKey).filter(ApiKey.key_hash == hash_key(plaintext)).first()
    if record is None or not record.is_active:
        return None
    return record


def touch_api_key(db: Session, key: ApiKey) -> None:
    key.last_used_at = datetime.utcnow()
    db.commit()


# ── Webhooks ────────────────────────────────────────────────────────────────

def list_webhooks(db: Session) -> List[Webhook]:
    return db.query(Webhook).order_by(Webhook.created_at.desc()).all()


def get_webhook(db: Session, webhook_id: UUID) -> Optional[Webhook]:
    return (
        db.query(Webhook)
        .options(selectinload(Webhook.deliveries))
        .filter(Webhook.id == webhook_id)
        .first()
    )


def create_webhook(db: Session, **fields) -> Webhook:
    webhook = Webhook(**fields)
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return webhook


def update_webhook(db: Session, webhook: Webhook, data: dict) -> Webhook:
    for field, value in data.items():
        setattr(webhook, field, value)
    # Re-enabling a webhook clears the failure count, otherwise a hook that hit
    # the failure limit would stay silently muted after being fixed.
    if data.get("is_active") is True:
        webhook.consecutive_failures = 0
    db.commit()
    db.refresh(webhook)
    return webhook


def delete_webhook(db: Session, webhook: Webhook) -> None:
    db.delete(webhook)
    db.commit()


def list_deliveries(db: Session, webhook_id: UUID, limit: int = 20) -> List[WebhookDelivery]:
    return (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
        .all()
    )
