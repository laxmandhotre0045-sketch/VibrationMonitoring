"""Alert webhook signing and delivery.

Delivery uses stdlib urllib rather than an HTTP client library, so integrations
add no new runtime dependency. Dispatch happens on a daemon thread with its own
session: a slow or dead customer endpoint must never delay measurement ingestion,
and must never poison the caller's transaction.

Every request carries:
  X-SensoVibe-Event      the event name
  X-SensoVibe-Timestamp  unix seconds, included in the signed material
  X-SensoVibe-Signature  sha256=<hex HMAC of "<timestamp>.<body>" using the secret>
Receivers should recompute the HMAC and reject a timestamp that is far from now,
which is what makes a captured request non-replayable.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.integration import SEVERITY_ORDER, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
# Past this many consecutive failures a webhook stops being attempted, so one
# dead endpoint cannot make every ingest slow.
FAILURE_LIMIT = 20

EVENT_ALERT = "alert.triggered"
EVENT_TEST = "webhook.test"


def generate_secret() -> str:
    return secrets.token_hex(32)


def sign_payload(secret: str, timestamp: int, body: bytes) -> str:
    material = f"{timestamp}.".encode("utf-8") + body
    digest = hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _severity_at_least(severity: str, minimum: str) -> bool:
    try:
        return SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index(minimum)
    except ValueError:
        return False


def deliver_now(db: Session, webhook: Webhook, event: str, payload: dict) -> WebhookDelivery:
    """Send synchronously and record the attempt. Never raises for transport errors."""
    body = json.dumps(payload, default=str).encode("utf-8")
    timestamp = int(time.time())

    request = urllib.request.Request(webhook.url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "SensoVibe-Webhook/1.0")
    request.add_header("X-SensoVibe-Event", event)
    request.add_header("X-SensoVibe-Timestamp", str(timestamp))
    request.add_header("X-SensoVibe-Signature", sign_payload(webhook.secret, timestamp, body))
    for key, value in (webhook.headers or {}).items():
        request.add_header(str(key), str(value))

    status_code: Optional[int] = None
    error: Optional[str] = None
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.status
            response.read(2048)  # drain, but never store the endpoint's response body
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        error = f"HTTP {exc.code}"
    except Exception as exc:  # timeouts, DNS, refused connections, bad URLs
        error = f"{type(exc).__name__}: {exc}"[:500]
    duration_ms = int((time.monotonic() - started) * 1000)

    succeeded = status_code is not None and 200 <= status_code < 300
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event=event,
        payload=payload,
        status_code=status_code,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(delivery)

    webhook.last_status_code = status_code
    webhook.last_triggered_at = datetime.utcnow()
    webhook.consecutive_failures = 0 if succeeded else (webhook.consecutive_failures or 0) + 1
    db.commit()
    db.refresh(delivery)
    return delivery


def _dispatch_in_background(webhook_ids: list[UUID], event: str, payload: dict) -> None:
    # Imported here so importing this module never pulls in the engine.
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for webhook_id in webhook_ids:
            hook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
            if hook is None:
                continue
            try:
                deliver_now(db, hook, event, payload)
            except Exception:
                logger.exception("Webhook delivery failed for %s", webhook_id)
                db.rollback()
    finally:
        db.close()


def dispatch_alert(db: Session, severity: str, payload: dict) -> int:
    """Queue delivery to every active webhook subscribed at or below `severity`.

    Returns the number of webhooks queued. Returns immediately — the caller's
    session is only used to pick recipients, never to send.
    """
    if severity not in SEVERITY_ORDER:
        return 0

    candidates = (
        db.query(Webhook)
        .filter(Webhook.is_active.is_(True), Webhook.consecutive_failures < FAILURE_LIMIT)
        .all()
    )
    targets = [w.id for w in candidates if _severity_at_least(severity, w.min_severity)]
    if not targets:
        return 0

    body = {"event": EVENT_ALERT, "severity": severity, **payload}
    thread = threading.Thread(
        target=_dispatch_in_background,
        args=(targets, EVENT_ALERT, body),
        daemon=True,
        name="webhook-dispatch",
    )
    thread.start()
    return len(targets)


def build_alert_payload(
    *,
    sensor_id: Any,
    upload_id: Any,
    equipment: Optional[dict],
    triggered: list[dict],
) -> dict:
    return {
        "sensor_id": str(sensor_id),
        "upload_id": str(upload_id),
        "equipment": equipment or {},
        "triggered_at": datetime.utcnow().isoformat() + "Z",
        "feature_count": len(triggered),
        "features": triggered,
    }
