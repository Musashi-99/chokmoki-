from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


from src.security.cors_policy import parse_cors_origins
from src.security.secrets_validation import collect_production_secret_errors


INSECURE_DEFAULTS = {
    "admin_password": "admin123",
    "jwt_secret": "chokmoki-jwt-secret-change-me",
}


class Settings(BaseSettings):
    # Environment
    environment: str = Field(default="development", env="ENVIRONMENT")

    # Mongo
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="lowkey_ecom", env="MONGODB_DB_NAME")

    # Auth
    admin_email: str = Field(default="admin@chokmoki.com", env="ADMIN_EMAIL")
    admin_password: str = Field(default="admin123", env="ADMIN_PASSWORD")
    admin_password_hash: Optional[str] = Field(default=None, env="ADMIN_PASSWORD_HASH")
    jwt_secret: str = Field(default="chokmoki-jwt-secret-change-me", env="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, env="JWT_EXPIRATION_HOURS")
    jwt_access_ttl_minutes: int = Field(default=60, env="JWT_ACCESS_TTL_MINUTES")
    jwt_refresh_ttl_days: int = Field(default=7, env="JWT_REFRESH_TTL_DAYS")
    jwt_secret_previous: Optional[str] = Field(default=None, env="JWT_SECRET_PREVIOUS")
    admin_mfa_secret: Optional[str] = Field(default=None, env="ADMIN_MFA_SECRET")
    csrf_enabled: bool = Field(default=True, env="CSRF_ENABLED")
    admin_cookie_samesite: str = Field(default="lax", env="ADMIN_COOKIE_SAMESITE")
    admin_cookie_domain: Optional[str] = Field(default=None, env="ADMIN_COOKIE_DOMAIN")
    # Separate from admin_cookie_domain on purpose: the CSRF cookie is the
    # only one JS ever needs to read (httponly=False, by design, so the SPA
    # can echo it back as X-CSRF-Token). If the admin frontend and API live
    # on different hostnames (e.g. www.chokmoki.com vs api.chokmoki.com),
    # this MUST be a shared parent domain (".chokmoki.com") or
    # document.cookie on the frontend can never see it — cookies are
    # readable by JS only on their own exact hostname, regardless of
    # SameSite/CORS. The access/refresh cookies stay host-only (narrower,
    # safer) since they're httponly and only ever sent back to the API.
    admin_csrf_cookie_domain: Optional[str] = Field(default=None, env="ADMIN_CSRF_COOKIE_DOMAIN")
    admin_cookie_secure: Optional[bool] = Field(default=None, env="ADMIN_COOKIE_SECURE")
    admin_legacy_bearer_enabled: bool = Field(
        default=False, env="ADMIN_LEGACY_BEARER_ENABLED"
    )

    # Infra
    redis_url: str = Field(..., env="REDIS_URL")

    # CORS — comma-separated origins, e.g. https://shop.example.com,http://localhost:5173
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
        env="CORS_ALLOWED_ORIGINS",
    )

    # Cron / internal
    cron_secret: Optional[str] = Field(default=None, env="CRON_SECRET")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    # Directory for on-disk log files (rotated), mounted as a Docker volume
    # so logs survive container restarts/rebuilds and can be pulled off the
    # server independently of `docker logs` (which is not persistent).
    log_dir: str = Field(default="/app/logs", env="LOG_DIR")

    # Razorpay
    razorpay_key_id: str = Field(..., env="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(..., env="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: Optional[str] = Field(default=None, env="RAZORPAY_WEBHOOK_SECRET")

    # Telegram
    telegram_enabled: bool = Field(default=False, env="TELEGRAM_ENABLED")
    telegram_bot_token: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")
    telegram_product_base_url: str = Field(
        default="https://lowkey-ui.vercel.app/product", env="TELEGRAM_PRODUCT_BASE_URL"
    )

    # Shiprocket
    shiprocket_enabled: bool = Field(default=False, env="SHIPROCKET_ENABLED")
    shiprocket_email: Optional[str] = Field(default=None, env="SHIPROCKET_EMAIL")
    shiprocket_password: Optional[str] = Field(default=None, env="SHIPROCKET_PASSWORD")
    # Must exactly match a pickup location name already configured in the
    # Shiprocket dashboard (Settings > Pickup Addresses) — required on every
    # order-create call.
    shiprocket_pickup_location: Optional[str] = Field(default=None, env="SHIPROCKET_PICKUP_LOCATION")
    # The pincode of that SAME pickup location — the order-create call takes
    # the location by name, but the courier-serviceability quote call needs
    # the actual pickup postcode, so both are required.
    shiprocket_pickup_pincode: Optional[str] = Field(default=None, env="SHIPROCKET_PICKUP_PINCODE")
    # Shared secret Shiprocket sends back as the `x-api-key` header on every
    # webhook call (configured in their dashboard under Settings > API >
    # Webhooks). Not an HMAC signature — a static token compare.
    shiprocket_webhook_token: Optional[str] = Field(default=None, env="SHIPROCKET_WEBHOOK_TOKEN")
    # Fallback package dimensions/weight when product data doesn't have them
    # (Product.weight_grams is frequently unset, and we don't collect
    # per-order package dimensions at checkout).
    shiprocket_default_weight_kg: float = Field(default=0.3, env="SHIPROCKET_DEFAULT_WEIGHT_KG")
    shiprocket_default_length_cm: float = Field(default=15.0, env="SHIPROCKET_DEFAULT_LENGTH_CM")
    shiprocket_default_breadth_cm: float = Field(default=10.0, env="SHIPROCKET_DEFAULT_BREADTH_CM")
    shiprocket_default_height_cm: float = Field(default=5.0, env="SHIPROCKET_DEFAULT_HEIGHT_CM")
    # Used only when the admin doesn't manually pick a courier on "Ready to Ship".
    shiprocket_default_courier_selection: str = Field(
        default="cheapest", env="SHIPROCKET_DEFAULT_COURIER_SELECTION"
    )

    # R2 / S3
    r2_account_id: str = Field(default="", env="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", env="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", env="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="chokmoki", env="R2_BUCKET")
    r2_key_prefix: str = Field(default="", env="R2_KEY_PREFIX")
    r2_public_base_url: str = Field(default="", env="R2_PUBLIC_BASE_URL")
    # Optional override for local/sandbox testing against an S3-compatible mock
    # (e.g. MinIO). Unset in production -> R2Service builds the real Cloudflare
    # R2 endpoint from r2_account_id as before.
    r2_endpoint_url: str = Field(default="", env="R2_ENDPOINT_URL")

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    rate_limit_normal_get: int = Field(default=400, env="RATE_LIMIT_NORMAL_GET")
    rate_limit_normal_post: int = Field(default=400, env="RATE_LIMIT_NORMAL_POST")
    rate_limit_normal_time: str = Field(default="3m", env="RATE_LIMIT_NORMAL_TIME")
    rate_limit_order_max: int = Field(default=5, env="RATE_LIMIT_ORDER_MAX")
    rate_limit_order_time: str = Field(default="1h", env="RATE_LIMIT_ORDER_TIME")
    rate_limit_contact_max: int = Field(default=3, env="RATE_LIMIT_CONTACT_MAX")
    rate_limit_contact_time: str = Field(default="1h", env="RATE_LIMIT_CONTACT_TIME")
    rate_limit_newsletter_max: int = Field(default=3, env="RATE_LIMIT_NEWSLETTER_MAX")
    rate_limit_newsletter_time: str = Field(default="24h", env="RATE_LIMIT_NEWSLETTER_TIME")
    rate_limit_fail_closed: bool = Field(default=False, env="RATE_LIMIT_FAIL_CLOSED")
    rate_limit_auth_fail_closed: bool = Field(
        default=True, env="RATE_LIMIT_AUTH_FAIL_CLOSED"
    )
    rate_limit_config_file: Optional[str] = Field(default=None, env="RATE_LIMIT_CONFIG_FILE")
    trusted_proxy_enabled: bool = Field(default=False, env="TRUSTED_PROXY_ENABLED")
    trust_x_forwarded_for: bool = Field(default=False, env="TRUST_X_FORWARDED_FOR")
    rate_limit_ip_header: Optional[str] = Field(default=None, env="RATE_LIMIT_IP_HEADER")
    log_client_ip_headers: bool = Field(default=False, env="LOG_CLIENT_IP_HEADERS")

    # Login lockout
    login_max_failed_attempts: int = Field(default=5, env="LOGIN_MAX_FAILED_ATTEMPTS")
    login_lockout_seconds: int = Field(default=1800, env="LOGIN_LOCKOUT_SECONDS")
    login_failure_window_seconds: int = Field(
        default=900, env="LOGIN_FAILURE_WINDOW_SECONDS"
    )

    # Orders
    order_min_quantity: int = Field(default=1, env="ORDER_MIN_QUANTITY")
    order_max_quantity: int = Field(default=99, env="ORDER_MAX_QUANTITY")

    # Inventory
    inventory_enabled: bool = Field(default=True, env="INVENTORY_ENABLED")
    inventory_reservation_ttl_seconds: int = Field(
        default=3600, env="INVENTORY_RESERVATION_TTL_SECONDS"
    )

    # Fraud Detection
    fraud_enabled: bool = Field(default=False, env="FRAUD_ENABLED")
    fraud_fail_closed: bool = Field(default=False, env="FRAUD_FAIL_CLOSED")
    fraud_rules_file: str = Field(
        default="config/fraud_rules.yaml", env="FRAUD_RULES_FILE"
    )
    fraud_audit_enabled: bool = Field(default=True, env="FRAUD_AUDIT_ENABLED")
    fraud_velocity_window_seconds: int = Field(
        default=3600, env="FRAUD_VELOCITY_WINDOW_SECONDS"
    )
    fraud_duplicate_window_seconds: int = Field(
        default=900, env="FRAUD_DUPLICATE_WINDOW_SECONDS"
    )
    fraud_velocity_email_threshold: int = Field(
        default=5, env="FRAUD_VELOCITY_EMAIL_THRESHOLD"
    )
    fraud_velocity_ip_threshold: int = Field(default=10, env="FRAUD_VELOCITY_IP_THRESHOLD")

    # Idempotency
    idempotency_enabled: bool = Field(default=True, env="IDEMPOTENCY_ENABLED")
    idempotency_ttl_seconds: int = Field(default=86400, env="IDEMPOTENCY_TTL_SECONDS")
    idempotency_required_in_production: bool = Field(
        default=True, env="IDEMPOTENCY_REQUIRED_IN_PRODUCTION"
    )

    # Metrics
    metrics_enabled: bool = Field(default=True, env="METRICS_ENABLED")
    metrics_token: Optional[str] = Field(default=None, env="METRICS_TOKEN")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return (value or "development").strip().lower()

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def admin_password_configured(self) -> bool:
        return bool(
            (self.admin_password_hash and self.admin_password_hash.strip())
            or (self.admin_password and self.admin_password.strip())
        )

    @property
    def admin_mfa_enabled(self) -> bool:
        return bool(self.admin_mfa_secret and self.admin_mfa_secret.strip())

    @property
    def cookie_secure(self) -> bool:
        if self.admin_cookie_secure is not None:
            return self.admin_cookie_secure
        return self.is_production

    @property
    def cookie_samesite(self) -> str:
        value = (self.admin_cookie_samesite or "lax").strip().lower()
        if value not in {"lax", "strict", "none"}:
            return "lax"
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        allow_wildcard = not self.is_production
        return parse_cors_origins(
            self.cors_allowed_origins or "",
            allow_wildcard=allow_wildcard,
        )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        try:
            origins = parse_cors_origins(
                self.cors_allowed_origins or "",
                allow_wildcard=not self.is_production,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if not self.is_production:
            return self

        errors: List[str] = collect_production_secret_errors(
            admin_password=self.admin_password,
            admin_password_hash=self.admin_password_hash,
            jwt_secret=self.jwt_secret,
            jwt_secret_previous=self.jwt_secret_previous,
            cron_secret=self.cron_secret,
            metrics_enabled=self.metrics_enabled,
            metrics_token=self.metrics_token,
            r2_access_key_id=self.r2_access_key_id,
            r2_secret_access_key=self.r2_secret_access_key,
            razorpay_webhook_secret=self.razorpay_webhook_secret,
        )

        if not origins:
            errors.append(
                "CORS_ALLOWED_ORIGINS must list explicit storefront origins in production"
            )

        if self.order_min_quantity < 1:
            errors.append("ORDER_MIN_QUANTITY must be >= 1")

        if self.order_max_quantity < self.order_min_quantity:
            errors.append("ORDER_MAX_QUANTITY must be >= ORDER_MIN_QUANTITY")

        if not self.rate_limit_auth_fail_closed:
            errors.append("RATE_LIMIT_AUTH_FAIL_CLOSED must be true in production")

        if self.trust_x_forwarded_for:
            errors.append("TRUST_X_FORWARDED_FOR must be false in production")

        if self.admin_legacy_bearer_enabled:
            errors.append("ADMIN_LEGACY_BEARER_ENABLED must be false in production")

        if not self.fraud_enabled:
            errors.append("FRAUD_ENABLED must be true in production")

        if not self.idempotency_enabled:
            errors.append("IDEMPOTENCY_ENABLED must be true in production")

        if errors:
            raise ValueError(
                "Insecure production configuration:\n- " + "\n- ".join(errors)
            )

        return self


def load_settings() -> Settings:
    """Load settings and fail fast on insecure production configuration."""
    return Settings()


settings = load_settings()
