import os
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
RULES_DIR = BASE_DIR / "rules"


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "Data Intelligence Portal")
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/data-intelligence-portal.sqlite")
        self.sqlite_journal_mode: str = os.getenv("SQLITE_JOURNAL_MODE", "DELETE")
        self.sqlite_persistent_copy_path: str = os.getenv("SQLITE_PERSISTENT_COPY_PATH", "")
        self.seed_reference_data: bool = env_bool("SEED_REFERENCE_DATA", "true")
        self.seed_demo_data: bool = env_bool("SEED_DEMO_DATA", "false")
        self.kra_llm_provider: str = os.getenv("KRA_LLM_PROVIDER", "disabled")
        self.kra_api_key: str = os.getenv("KRA_API_KEY", "")
        self.kra_model: str = os.getenv("KRA_MODEL", "")
        self.kra_mcp_mode: str = os.getenv("KRA_MCP_MODE", "local_registry")
        self.entra_auth_enabled: bool = env_bool("ENTRA_AUTH_ENABLED", "false")
        self.entra_admin_group_id: str = os.getenv("ENTRA_ADMIN_GROUP_ID", "")
        self.entra_standard_group_id: str = os.getenv("ENTRA_STANDARD_GROUP_ID", "")
        self.entra_admin_group_name: str = os.getenv("ENTRA_ADMIN_GROUP_NAME", "Data Intelligence Portal Admin Users")
        self.entra_standard_group_name: str = os.getenv("ENTRA_STANDARD_GROUP_NAME", "Data Intelligence Portal Standard Users")
        self.outbox_dir: str = os.getenv("DIP_OUTBOX_DIR", str(ROOT_DIR / ".outbox"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
