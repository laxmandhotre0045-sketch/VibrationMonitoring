from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str = "change-in-production"
    upload_dir: str = "uploads"
    max_image_size_mb: int = 10
    measurement_upload_dir: str = "uploads/measurements"
    max_pdf_size_mb: int = 50

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
