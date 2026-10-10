from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _origins(value: str | None) -> tuple[str, ...]:
    if not value:
        return ("http://localhost:3000", "http://127.0.0.1:3000")
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    enable_web_search: bool
    ecos_api_key: str
    firebase_service_account_json: str
    firebase_service_account_path: str
    allowed_origins: tuple[str, ...]
    use_local_db: bool
    auto_sync: bool
    seed_csv: Path

    @property
    def firebase_credentials(self) -> dict | None:
        if self.firebase_service_account_json:
            try:
                return json.loads(self.firebase_service_account_json)
            except json.JSONDecodeError as exc:
                raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc
        if self.firebase_service_account_path:
            path = Path(self.firebase_service_account_path).expanduser()
            if not path.exists():
                raise RuntimeError(f"Firebase service account file not found: {path}")
            return json.loads(path.read_text(encoding="utf-8"))
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        enable_web_search=_as_bool(os.getenv("ENABLE_WEB_SEARCH"), False),
        ecos_api_key=os.getenv("ECOS_API_KEY", "").strip(),
        firebase_service_account_json=os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_JSON", ""
        ).strip(),
        firebase_service_account_path=os.getenv(
            "FIREBASE_SERVICE_ACCOUNT_PATH", ""
        ).strip(),
        allowed_origins=_origins(os.getenv("ALLOWED_ORIGINS")),
        use_local_db=_as_bool(os.getenv("USE_LOCAL_DB"), False),
        auto_sync=_as_bool(os.getenv("AUTO_SYNC"), True),
        seed_csv=BACKEND_DIR / "data" / "economic_indicators_monthly.csv",
    )

