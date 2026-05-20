import os
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
RULES_DIR = BASE_DIR / "rules"


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "Contracted Opportunity Finder")
        self.environment_label: str = os.getenv("DIP_ENVIRONMENT_LABEL", "Live COF workspace")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/data-intelligence-portal.sqlite")
        self.database_auto_create_all: bool = env_bool("DATABASE_AUTO_CREATE_ALL", "false")
        self.sqlite_journal_mode: str = os.getenv("SQLITE_JOURNAL_MODE", "DELETE")
        self.sqlite_persistent_copy_path: str = os.getenv("SQLITE_PERSISTENT_COPY_PATH", "")
        self.seed_reference_data: bool = env_bool("SEED_REFERENCE_DATA", "true")
        self.seed_demo_data: bool = env_bool("SEED_DEMO_DATA", "false")
        self.auto_apply_customer_packs: bool = env_bool("AUTO_APPLY_CUSTOMER_PACKS", "false")
        self.kra_llm_provider: str = os.getenv("KRA_LLM_PROVIDER", "disabled")
        self.kra_api_key: str = os.getenv("KRA_API_KEY", "")
        self.kra_model: str = os.getenv("KRA_MODEL", "")
        self.kra_mcp_mode: str = os.getenv("KRA_MCP_MODE", "local_registry")
        self.notice_lookback_days: int = env_int("DIP_NOTICE_LOOKBACK_DAYS", "180")
        self.notice_page_limit: int = env_int("DIP_NOTICE_PAGE_LIMIT", "100")
        self.notice_max_pages: int = env_int("DIP_NOTICE_MAX_PAGES", "8")
        self.entra_auth_enabled: bool = env_bool("ENTRA_AUTH_ENABLED", "false")
        self.local_admin_mode: bool = env_bool("LOCAL_ADMIN_MODE", "true")
        self.entra_admin_group_id: str = os.getenv("ENTRA_ADMIN_GROUP_ID", "")
        self.entra_standard_group_id: str = os.getenv("ENTRA_STANDARD_GROUP_ID", "")
        self.entra_auditor_group_id: str = os.getenv("ENTRA_AUDITOR_GROUP_ID", "")
        self.entra_admin_group_name: str = os.getenv("ENTRA_ADMIN_GROUP_NAME", "Data Intelligence Portal Admin Users")
        self.entra_standard_group_name: str = os.getenv("ENTRA_STANDARD_GROUP_NAME", "Data Intelligence Portal Standard Users")
        self.entra_auditor_group_name: str = os.getenv("ENTRA_AUDITOR_GROUP_NAME", "Data Intelligence Portal Auditor Users")
        self.access_scopes_json: str = os.getenv("DIP_ACCESS_SCOPES_JSON", "")
        self.outbox_dir: str = os.getenv("DIP_OUTBOX_DIR", str(ROOT_DIR / ".outbox"))
        self.public_domain: str = os.getenv("DIP_PUBLIC_DOMAIN", "dip.vendorlogic.io")
        self.remote_health_url: str = os.getenv("DIP_REMOTE_HEALTH_URL", "https://dip.vendorlogic.io/healthz")
        self.deployment_label: str = os.getenv("DIP_DEPLOYMENT_LABEL", "local")
        self.email_delivery_mode: str = os.getenv("DIP_EMAIL_DELIVERY_MODE", "")
        self.email_sender_name: str = os.getenv("DIP_EMAIL_SENDER_NAME", "")
        self.email_sender: str = os.getenv("DIP_EMAIL_SENDER", "")
        self.email_default_recipients: str = os.getenv("DIP_EMAIL_DEFAULT_RECIPIENTS", "")
        self.smtp_host: str = os.getenv("DIP_SMTP_HOST", "")
        self.smtp_port: str = os.getenv("DIP_SMTP_PORT", "")
        self.smtp_username: str = os.getenv("DIP_SMTP_USERNAME", "")
        self.smtp_password_secret_name: str = os.getenv("DIP_SMTP_PASSWORD_SECRET_NAME", "")
        self.smtp_password: str = os.getenv("DIP_SMTP_PASSWORD", "")
        self.smtp_use_tls: bool = env_bool("DIP_SMTP_USE_TLS", "true")
        self.smtp_enabled: bool = env_bool("DIP_SMTP_ENABLED", "false")
        self.cof_client_name_mode: str = os.getenv("DIP_COF_CLIENT_NAME_MODE", "redacted")
        self.cof_client_name_map_json: str = os.getenv("DIP_COF_CLIENT_NAME_MAP_JSON", "")
        self.report_brand_name: str = os.getenv("DIP_REPORT_BRAND_NAME", "Contracted Opportunity Finder")
        self.report_prepared_for: str = os.getenv("DIP_REPORT_PREPARED_FOR", "Procter Street")
        self.report_footer: str = os.getenv(
            "DIP_REPORT_FOOTER",
            "Human review required. Not a bid, legal, procurement or compliance decision.",
        )
        self.cof_min_customers: int = env_int("DIP_COF_MIN_CUSTOMERS", "11")
        self.autopilot_kra_customer_limit: int = env_int("DIP_AUTOPILOT_KRA_CUSTOMER_LIMIT", "0")
        self.autopilot_kra_max_pages: int = env_int("DIP_AUTOPILOT_KRA_MAX_PAGES", "1")
        self.autopilot_kra_candidates_per_page: int = env_int("DIP_AUTOPILOT_KRA_CANDIDATES_PER_PAGE", "15")
        self.autopilot_market_sweep_enabled: bool = env_bool("DIP_AUTOPILOT_MARKET_SWEEP_ENABLED", "false")
        self.autopilot_market_sweep_limit: int = env_int("DIP_AUTOPILOT_MARKET_SWEEP_LIMIT", "10")
        self.autopilot_market_sweep_keywords: str = os.getenv(
            "DIP_AUTOPILOT_MARKET_SWEEP_KEYWORDS",
            "cyber security,IT services,traffic management,CCTV",
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
