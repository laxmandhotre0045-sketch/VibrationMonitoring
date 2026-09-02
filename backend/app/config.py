from pydantic_settings import BaseSettings

#: Origins always allowed, matching the Vite dev server and preview ports.
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:4173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:4173",
    "http://127.0.0.1:3000",
]


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

    #: Extra browser origins allowed to call the API, comma-separated.
    #: Needed whenever the UI is opened on anything other than localhost —
    #: e.g. CORS_ORIGINS=http://192.168.1.51:4173
    cors_origins: str = ""

    #: When true, GET /api/v1/acquisition/config requires an X-API-Key.
    #:
    #: Default false so an MQTT edge device can fetch its own settings with a
    #: bare HTTP GET and no credential handling. The response carries device
    #: IDs and the MQTT broker/topic, so set this to true for any deployment
    #: where the API is reachable beyond a trusted plant network:
    #:   ACQUISITION_CONFIG_REQUIRE_KEY=true
    #: Writes (PUT) always require an authenticated operator regardless.
    acquisition_config_require_key: bool = False

    @property
    def effective_jwt_secret(self) -> str:
        return self.jwt_secret or self.secret_key

    @property
    def allowed_origins(self) -> list[str]:
        """Local dev origins plus anything configured via CORS_ORIGINS."""
        origins = list(DEFAULT_CORS_ORIGINS)
        for origin in self.cors_origins.split(","):
            cleaned = origin.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
        return origins

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
