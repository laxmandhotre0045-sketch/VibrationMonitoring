import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.crud import user as user_crud
from app.services.auth_service import hash_password

logger = logging.getLogger("uvicorn")


def seed_super_admin(db: Session) -> None:
    """Create initial super_admin from env if none exists."""
    if user_crud.super_admin_exists(db):
        email = settings.initial_admin_email
        if email:
            user = user_crud.get_user_by_email(db, email)
            if user and user.must_change_password:
                user.must_change_password = False
                db.commit()
                logger.info(
                    "Cleared must_change_password for seeded admin (legacy flag): %s", email
                )
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


def _seed_user_if_missing(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role_names: list[str],
) -> None:
    if not email or not password:
        return
    if user_crud.get_user_by_email(db, email):
        return
    user_crud.create_user(
        db=db,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role_names=role_names,
        must_change_password=False,
    )
    logger.info("Seeded %s user: %s", role_names[0], email)


def seed_role_users(db: Session) -> None:
    """Seed admin and read-only user accounts from .env for RBAC testing."""
    _seed_user_if_missing(
        db,
        email=settings.seed_admin_email,
        password=settings.seed_admin_password,
        full_name=settings.seed_admin_name,
        role_names=["admin"],
    )
    _seed_user_if_missing(
        db,
        email=settings.seed_user_email,
        password=settings.seed_user_password,
        full_name=settings.seed_user_name,
        role_names=["user"],
    )
