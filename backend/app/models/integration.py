"""Device API keys and alert webhooks.

An API key's plaintext is shown exactly once, at creation. Only the SHA-256
digest is stored, plus a short non-secret prefix so a key can be recognised in
a list without being recoverable from the database.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base

# Severities an alert webhook can subscribe to, weakest first.
SEVERITY_ORDER = ["warning", "critical"]


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    # Non-secret: the leading characters of the key, for display only.
    key_prefix = Column(String(16), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    created_by = relationship("User")

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at < datetime.utcnow():
            return False
        return True


class Webhook(Base):
    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    url = Column(String(1000), nullable=False)
    # Shared secret for the HMAC-SHA256 signature sent as X-SensoVibe-Signature.
    secret = Column(String(64), nullable=False)
    # Lowest severity that triggers delivery: "warning" fires for both.
    min_severity = Column(String(20), nullable=False, default="warning")
    is_active = Column(Boolean, nullable=False, default=True)
    headers = Column(JSONB, nullable=False, default=dict)

    last_status_code = Column(Integer, nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    deliveries = relationship(
        "WebhookDelivery",
        back_populates="webhook",
        cascade="all, delete-orphan",
        order_by="WebhookDelivery.created_at.desc()",
    )


class WebhookDelivery(Base):
    """One delivery attempt. Kept so a failing endpoint can be diagnosed."""

    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event = Column(String(60), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    status_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    webhook = relationship("Webhook", back_populates="deliveries")

    @property
    def succeeded(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300
