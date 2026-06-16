import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.crud import user as user_crud
from app.services.auth_service import hash_password

logger = logging.getLogger("uvicorn")


def seed_super_admin(db: Session) -> None:
    """Create initial super_admin from env if none exists."""
    if user_crud.super_admin_exists(db):
        logger.info("Super admin already exists — skipping seed")
        return

    email = settings.initial_admin_email
    password = settings.initial_admin_password
    if not email or not password:
        logger.warning(
            "No super admin found. Set INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD in .env to seed one."
        )
        return

    user_crud.create_user(
        db=db,
        email=email,
        password_hash=hash_password(password),
        full_name=settings.initial_admin_name,
        role_names=["super_admin"],
        must_change_password=False,
    )
    logger.info("Seeded super admin user: %s", email)
