"""Device API keys and alert webhooks.

Both are administrator-only: a key grants device ingest access, and a webhook
URL receives alert contents, so neither should be manageable by ordinary users.

Two values are shown exactly once, at creation, and are unrecoverable afterwards:
the API key plaintext and the webhook signing secret. Rotation is the only way
back — which is why both resources expose a rotate endpoint.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import integration as crud
from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.integration import Webhook
from app.models.user import User
from app.schemas.integration import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    WebhookCreate,
    WebhookCreated,
    WebhookDeliveryOut,
    WebhookOut,
    WebhookSecretOut,
    WebhookTestResult,
    WebhookUpdate,
)
from app.services import webhook_service

router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["Integrations"],
    dependencies=[Depends(require_admin)],
)


def _key_out(key) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        is_active=key.is_active,
        last_used_at=key.last_used_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        created_at=key.created_at,
    )


def _webhook_out(hook: Webhook) -> WebhookOut:
    return WebhookOut(
        id=hook.id,
        name=hook.name,
        url=hook.url,
        min_severity=hook.min_severity,
        is_active=hook.is_active,
        headers=hook.headers or {},
        last_status_code=hook.last_status_code,
        last_triggered_at=hook.last_triggered_at,
        consecutive_failures=hook.consecutive_failures or 0,
        created_at=hook.created_at,
    )


# ── API keys ────────────────────────────────────────────────────────────────

@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db)):
    return [_key_out(k) for k in crud.list_api_keys(db)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Create a key. The `key` field in the response is never retrievable again."""
    key, plaintext = crud.create_api_key(db, data.name, actor.id, data.expires_at)
    return ApiKeyCreated(**_key_out(key).model_dump(), key=plaintext)


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(key_id: UUID, db: Session = Depends(get_db)):
    key = crud.get_api_key(db, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return _key_out(crud.revoke_api_key(db, key))


@router.delete("/api-keys/{key_id}", status_code=204)
def delete_api_key(key_id: UUID, db: Session = Depends(get_db)):
    key = crud.get_api_key(db, key_id)
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    crud.delete_api_key(db, key)


# ── Webhooks ────────────────────────────────────────────────────────────────

@router.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(db: Session = Depends(get_db)):
    return [_webhook_out(w) for w in crud.list_webhooks(db)]


@router.post("/webhooks", response_model=WebhookCreated, status_code=201)
def create_webhook(data: WebhookCreate, db: Session = Depends(get_db)):
    secret = webhook_service.generate_secret()
    hook = crud.create_webhook(
        db,
        name=data.name,
        url=data.url,
        secret=secret,
        min_severity=data.min_severity,
        is_active=data.is_active,
        headers=data.headers,
    )
    return WebhookCreated(**_webhook_out(hook).model_dump(), secret=secret)


@router.get("/webhooks/{webhook_id}", response_model=WebhookOut)
def get_webhook(webhook_id: UUID, db: Session = Depends(get_db)):
    hook = crud.get_webhook(db, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _webhook_out(hook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookOut)
def update_webhook(webhook_id: UUID, data: WebhookUpdate, db: Session = Depends(get_db)):
    hook = crud.get_webhook(db, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _webhook_out(crud.update_webhook(db, hook, data.model_dump(exclude_unset=True)))


@router.delete("/webhooks/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: UUID, db: Session = Depends(get_db)):
    hook = crud.get_webhook(db, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    crud.delete_webhook(db, hook)


@router.post("/webhooks/{webhook_id}/rotate-secret", response_model=WebhookSecretOut)
def rotate_webhook_secret(webhook_id: UUID, db: Session = Depends(get_db)):
    hook = crud.get_webhook(db, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    secret = webhook_service.generate_secret()
    crud.update_webhook(db, hook, {"secret": secret})
    return WebhookSecretOut(secret=secret)


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResult)
def test_webhook(webhook_id: UUID, db: Session = Depends(get_db)):
    """Send a signed sample payload synchronously and report what came back."""
    hook = crud.get_webhook(db, webhook_id)
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    delivery = webhook_service.deliver_now(
        db,
        hook,
        webhook_service.EVENT_TEST,
        {
            "event": webhook_service.EVENT_TEST,
            "message": "Test delivery from SensoVibe. If you can verify the "
                       "signature on this request, your endpoint is configured correctly.",
            "webhook_id": str(hook.id),
        },
    )
    return WebhookTestResult(
        delivered=delivery.succeeded,
        status_code=delivery.status_code,
        error=delivery.error,
        duration_ms=delivery.duration_ms,
    )


@router.get("/webhooks/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    webhook_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if not crud.get_webhook(db, webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    return [
        WebhookDeliveryOut(
            id=d.id,
            event=d.event,
            status_code=d.status_code,
            error=d.error,
            duration_ms=d.duration_ms,
            succeeded=d.succeeded,
            created_at=d.created_at,
        )
        for d in crud.list_deliveries(db, webhook_id, limit)
    ]
