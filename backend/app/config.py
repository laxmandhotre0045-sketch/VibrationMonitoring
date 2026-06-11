from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str = "change-in-production"
    upload_dir: str = "uploads"
    max_image_size_mb: int = 10

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    initial_admin_email: str = ""
    initial_admin_password: str = ""
    initial_admin_name: str = "Platform Administrator"

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.secret_key

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
