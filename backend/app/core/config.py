"""Application configuration loaded from environment variables via Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_DEFAULT_CORS = (
    "http://localhost:5173,"
    "http://localhost:3000,"
    "http://127.0.0.1:5173,"
    "http://127.0.0.1:3000"
)


def _parse_cors_value(value: object) -> List[str]:
    """Parse CORS origins from comma-separated string, JSON list, or list."""
    if value is None:
        return [p.strip() for p in _DEFAULT_CORS.split(",") if p.strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return [p.strip() for p in _DEFAULT_CORS.split(",") if p.strip()]
        if text.startswith("["):
            import json

            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in text.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


class Settings(BaseSettings):
    """Central application settings sourced from `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="APCOTEX Sales Insights API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    debug: bool = Field(default=True, alias="DEBUG")
    # Stored as str so pydantic-settings does not JSON-decode List fields.
    # Set CORS_ORIGINS in .env (comma-separated). Do not hardcode UAT IPs here.
    # Property cors_origins: split, strip, drop empties.
    cors_origins_raw: str = Field(default=_DEFAULT_CORS, alias="CORS_ORIGINS")

    # Database
    database_host: str = Field(default="localhost", alias="DATABASE_HOST")
    database_port: int = Field(default=5432, alias="DATABASE_PORT")
    database_name: str = Field(default="apcotex_salesinsights", alias="DATABASE_NAME")
    database_user: str = Field(default="postgres", alias="DATABASE_USER")
    database_password: str = Field(default="root", alias="DATABASE_PASSWORD")
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:root@localhost:5432/apcotex_salesinsights",
        alias="DATABASE_URL",
    )
    db_echo: bool = Field(default=False, alias="DB_ECHO")
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_pre_ping: bool = Field(default=True, alias="DB_POOL_PRE_PING")

    # Microsoft Graph
    graph_tenant_id: str = Field(default="", alias="GRAPH_TENANT_ID")
    graph_client_id: str = Field(default="", alias="GRAPH_CLIENT_ID")
    graph_client_secret: str = Field(default="", alias="GRAPH_CLIENT_SECRET")
    graph_mailbox: str = Field(default="", alias="GRAPH_MAILBOX")
    graph_authority_base: str = Field(
        default="https://login.microsoftonline.com",
        alias="GRAPH_AUTHORITY_BASE",
    )
    graph_scope: str = Field(
        default="https://graph.microsoft.com/.default",
        alias="GRAPH_SCOPE",
    )
    graph_base_url: str = Field(
        default="https://graph.microsoft.com/v1.0",
        alias="GRAPH_BASE_URL",
    )
    graph_excel_extensions: List[str] = Field(
        default_factory=lambda: [".xlsx", ".xlsm", ".xls"],
        alias="GRAPH_EXCEL_EXTENSIONS",
    )

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default=str(BASE_DIR / "logs"), alias="LOG_DIR")
    log_rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    log_retention: str = Field(default="30 days", alias="LOG_RETENTION")

    # Paths
    upload_dir: str = Field(default=str(BASE_DIR / "uploads"), alias="UPLOAD_DIR")
    download_dir: str = Field(default=str(BASE_DIR / "downloads"), alias="DOWNLOAD_DIR")
    template_dir: str = Field(default=str(BASE_DIR / "templates"), alias="TEMPLATE_DIR")

    # Master data soft-delete retention (hard-delete older history; 0 = disabled)
    master_history_retention_days: int = Field(
        default=180,
        alias="MASTER_HISTORY_RETENTION_DAYS",
        ge=0,
    )

    # Template generation (warn / soft-cap for extremely large dropdown lists)
    template_list_warn_threshold: int = Field(
        default=5000,
        alias="TEMPLATE_LIST_WARN_THRESHOLD",
        ge=100,
    )

    # Authentication mode:
    #   headers          – Phase 1 header RBAC (default; fine for local/dev)
    #   trusted_headers  – require X-Internal-Auth == AUTH_TRUSTED_SECRET (corp gateway)
    #   jwt              – Bearer JWT validated with AUTH_JWT_SECRET
    auth_mode: str = Field(default="headers", alias="AUTH_MODE")
    auth_trusted_secret: str = Field(default="", alias="AUTH_TRUSTED_SECRET")
    auth_trusted_header: str = Field(default="X-Internal-Auth", alias="AUTH_TRUSTED_HEADER")
    auth_jwt_secret: str = Field(default="", alias="AUTH_JWT_SECRET")
    auth_jwt_algorithm: str = Field(default="HS256", alias="AUTH_JWT_ALGORITHM")
    auth_jwt_audience: str = Field(default="", alias="AUTH_JWT_AUDIENCE")

    # RBAC header keys (Phase 1 – role passed via headers for enforcement hooks)
    rbac_role_header: str = Field(default="X-User-Role", alias="RBAC_ROLE_HEADER")
    rbac_user_header: str = Field(default="X-User-Name", alias="RBAC_USER_HEADER")
    rbac_user_id_header: str = Field(default="X-User-Id", alias="RBAC_USER_ID_HEADER")

    # Super Admin — permanent system identity; credentials live only in .env (never DB)
    super_admin_username: str = Field(default="superadmin", alias="SUPER_ADMIN_USERNAME")
    super_admin_password: str = Field(default="", alias="SUPER_ADMIN_PASSWORD")
    password_min_length: int = Field(default=8, alias="PASSWORD_MIN_LENGTH", ge=6)

    # OpenAI — ERP LLM header resolver fallback (mapping only; never extracts rows)
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=30.0, alias="OPENAI_TIMEOUT_SECONDS", gt=0)

    # ERP Excel quantity unit in the workbook (converted to MT on parse/import)
    # Typical distributor ERP exports are KG. Set ERP_EXCEL_QUANTITY_UNIT=MT if already tonnes.
    erp_excel_quantity_unit: str = Field(default="KG", alias="ERP_EXCEL_QUANTITY_UNIT")

    @property
    def cors_origins(self) -> List[str]:
        """Browser origins allowed by CORS (from CORS_ORIGINS env)."""
        return _parse_cors_value(self.cors_origins_raw)

    @field_validator("graph_excel_extensions", mode="before")
    @classmethod
    def parse_graph_extensions(cls, value: object) -> object:
        """Allow comma-separated excel extensions from environment."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                return json.loads(text)
            return [item.strip() for item in text.split(",") if item.strip()]
        return value

    @property
    def is_development(self) -> bool:
        """Return True when running in development mode."""
        return self.app_env.lower() in {"development", "dev", "local"}

    @property
    def is_production(self) -> bool:
        """Return True when running in production mode."""
        return self.app_env.lower() in {"production", "prod"}

    @property
    def graph_authority(self) -> str:
        """Full MSAL authority URL for the configured tenant."""
        return f"{self.graph_authority_base}/{self.graph_tenant_id}"

    def ensure_directories(self) -> None:
        """Create required filesystem directories if they do not exist."""
        for path in (
            self.log_dir,
            self.upload_dir,
            self.download_dir,
            self.template_dir,
            str(Path(self.upload_dir) / "master"),
            str(Path(self.upload_dir) / "reports"),
            str(Path(self.upload_dir) / "attachments"),
        ):
            Path(path).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()
