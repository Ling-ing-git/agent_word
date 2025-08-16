from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Resolve project root (ai_girlfriend directory)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Load .env from project root if present
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Settings:
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    project_root: Path = PROJECT_ROOT
    static_dir: Path = project_root / "static"
    personas_dir: Path = project_root / "personas"
    data_dir: Path = project_root / "data"


settings = Settings()

# Ensure directories exist at import time for simple DX
settings.static_dir.mkdir(parents=True, exist_ok=True)
settings.personas_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "sessions").mkdir(parents=True, exist_ok=True)