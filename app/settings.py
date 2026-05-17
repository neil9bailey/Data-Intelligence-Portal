from functools import lru_cache
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
RULES_DIR = BASE_DIR / "rules"


class Settings:
    app_name: str = os.getenv("APP_NAME", "Data Intelligence Portal")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/data-intelligence-portal.sqlite")
    seed_demo_data: bool = os.getenv("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes", "on"}
    kra_llm_provider: str = os.getenv("KRA_LLM_PROVIDER", "disabled")
    kra_api_key: str = os.getenv("KRA_API_KEY", "")
    kra_model: str = os.getenv("KRA_MODEL", "")
    kra_mcp_mode: str = os.getenv("KRA_MCP_MODE", "local_registry")


@lru_cache
def get_settings() -> Settings:
    return Settings()
