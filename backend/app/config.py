from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str = "change-in-production"
    upload_dir: str = "uploads"
    measurement_upload_dir: str = "uploads/measurements"
    max_image_size_mb: int = 10
    max_pdf_size_mb: int = 50

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    initial_admin_email: str = ""
    initial_admin_password: str = ""
    initial_admin_name: str = "Platform Administrator"

    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_admin_name: str = "Plant Administrator"

    seed_user_email: str = ""
    seed_user_password: str = ""
    seed_user_name: str = "Read Only User"

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.secret_key

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
