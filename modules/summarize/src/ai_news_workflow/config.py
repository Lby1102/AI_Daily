from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    max_input_chars: int
    max_retries: int

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(dotenv_path=env_file)
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise ValueError("缺少 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 后填写。")

        return cls(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip(),
            max_input_chars=int(os.getenv("DEEPSEEK_MAX_INPUT_CHARS", "300000")),
            max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "8")),
        )
