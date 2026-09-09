# -*- coding: utf-8 -*-
"""统一工作流配置：唯一事实来源是代码根目录下的 .env / 环境变量。

命名约定（模块间 API 协议，见 docs/ARCHITECTURE.md）：
  DEEPSEEK_*         模块 2~4（summarize）上游配置
  LLM_LOCAL_*        本地 OpenAI 兼容推理服务（可选，零成本跑通）
  SUMMARIZE_*        模块 2~4 行为开关
  WECHAT_*           模块 6（wechat）推送配置
  CRAWL_*            模块 1（crawler）配置
  SCHEDULE_*         自动生成调度
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent          # AI-Daily-Workflow/
# 进程启动即自动加载代码根目录 .env（显式环境变量优先，不覆盖）
load_dotenv(ROOT / ".env")
MODULES = ROOT / "modules"
CRAWLER = MODULES / "crawler"
SUMMARIZE = MODULES / "summarize"
WECHAT = MODULES / "wechat"
DATA = ROOT / "data"
REVIEW = ROOT / "review"
LOGS = ROOT / "logs"


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    # ---- 路径 ----
    root: Path = ROOT
    modules: Path = MODULES
    crawler_dir: Path = CRAWLER
    summarize_dir: Path = SUMMARIZE
    wechat_dir: Path = WECHAT
    data_dir: Path = DATA
    review_dir: Path = REVIEW
    logs_dir: Path = LOGS

    # ---- 本地模型服务（供"自动拉起"使用）----
    # llm 目录默认取代码文件夹的平行目录（可 LLM_DIR 覆盖）
    llm_dir: Path = field(default_factory=lambda: Path(_get("LLM_DIR", str(ROOT.parent / "llm"))))
    llm_model_file: str = field(default_factory=lambda: _get("LLM_MODEL_FILE", "Qwen3.5-9B-Q4_K_M.gguf"))

    # ---- 模块 1：crawler ----
    crawl_edition: str = field(default_factory=lambda: _get("CRAWL_EDITION", "morning"))
    crawl_hours: int = field(default_factory=lambda: int(_get("CRAWL_HOURS", "24") or 24))
    crawl_min_score: int = field(default_factory=lambda: int(_get("CRAWL_MIN_SCORE", "35") or 35))
    crawl_extra_args: str = field(default_factory=lambda: _get("CRAWL_EXTRA_ARGS", ""))
    crawl_output_dir: Path = field(default_factory=lambda: Path(_get("CRAWL_OUTPUT_DIR", str(DATA / "crawl"))))

    # ---- 模块 2~4：summarize（LLM）----
    # provider: auto -> 有 DEEPSEEK_API_KEY 用 deepseek，否则用本地 LLM
    llm_provider: str = field(default_factory=lambda: _get("LLM_PROVIDER", "auto"))
    deepseek_api_key: str = field(default_factory=lambda: _get("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = field(default_factory=lambda: _get("DEEPSEEK_MODEL", "deepseek-chat"))
    local_base_url: str = field(default_factory=lambda: _get("LLM_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1"))
    local_model: str = field(default_factory=lambda: _get("LLM_LOCAL_MODEL", "qwen3.5-9b"))
    local_api_key: str = field(default_factory=lambda: _get("LLM_LOCAL_API_KEY", "local"))
    summarize_json_mode: str = field(default_factory=lambda: _get("SUMMARIZE_JSON_MODE", "auto"))
    summarize_thinking: str = field(default_factory=lambda: _get("SUMMARIZE_THINKING", "auto"))
    summarize_max_retries: int = field(default_factory=lambda: int(_get("SUMMARIZE_MAX_RETRIES", "8") or 8))
    summarize_max_input_chars: int = field(default_factory=lambda: int(_get("SUMMARIZE_MAX_INPUT_CHARS", "0") or 0))
    summarize_max_tokens: int = field(default_factory=lambda: int(_get("SUMMARIZE_MAX_TOKENS", "0") or 0))
    top_candidates: int = field(default_factory=lambda: int(_get("TOP_CANDIDATES", "60") or 60))

    # ---- 图片 / 附件 ----
    images_per_news: int = field(default_factory=lambda: int(_get("IMAGES_PER_NEWS", "3") or 3))
    fetch_images: str = field(default_factory=lambda: _get("FETCH_IMAGES", "true"))

    # ---- 模块 6：wechat（透传）----
    wechat_app_id: str = field(default_factory=lambda: _get("WECHAT_APP_ID", ""))
    wechat_app_secret: str = field(default_factory=lambda: _get("WECHAT_APP_SECRET", ""))
    article_title: str = field(default_factory=lambda: _get("ARTICLE_TITLE", ""))
    article_author: str = field(default_factory=lambda: _get("ARTICLE_AUTHOR", ""))
    article_digest: str = field(default_factory=lambda: _get("ARTICLE_DIGEST", ""))
    article_source_url: str = field(default_factory=lambda: _get("ARTICLE_SOURCE_URL", ""))

    # ---- 调度 ----
    schedule_time: str = field(default_factory=lambda: _get("SCHEDULE_TIME", "09:00"))
    auto_enabled: bool = field(default_factory=lambda: _get("AUTO_ENABLED", "false").lower() in ("1", "true", "yes", "on"))

    def effective_provider(self) -> str:
        p = self.llm_provider.lower()
        if p in ("deepseek", "local"):
            return p
        return "deepseek" if self.deepseek_api_key else "local"

    def validate_wechat(self) -> list[str]:
        errors = []
        if not self.wechat_app_id:
            errors.append("缺少 WECHAT_APP_ID")
        if not self.wechat_app_secret:
            errors.append("缺少 WECHAT_APP_SECRET")
        return errors

    def wechat_env(self, article_html: Path, cover_image: Path,
                   default_title: str = "") -> dict[str, str]:
        """生成推送给模块 6 子进程的完整环境（环境变量优先于模块内 .env）。

        default_title：自动推送用的简短标题（公众号草稿标题长度限制很严，
        不传时若也未配置 ARTICLE_TITLE，则不发该变量、由模块从 HTML 提取长标题）。
        """
        env = {
            "WECHAT_APP_ID": self.wechat_app_id,
            "WECHAT_APP_SECRET": self.wechat_app_secret,
            "ARTICLE_HTML": str(article_html),
            "COVER_IMAGE": str(cover_image),
        }
        title = self.article_title or default_title
        if title:
            env["ARTICLE_TITLE"] = title
        for key, value in (("ARTICLE_AUTHOR", self.article_author),
                           ("ARTICLE_DIGEST", self.article_digest),
                           ("ARTICLE_SOURCE_URL", self.article_source_url)):
            if value:
                env[key] = value
        return env

    def summarize_env(self, raw_txt: Path, output_html: Path, report_json: Path) -> dict[str, str]:
        """模块 2~4 子进程环境：路径 + LLM 配置 + 行为开关。"""
        provider = self.effective_provider()
        if provider == "deepseek":
            base, model, key = self.deepseek_base_url, self.deepseek_model, self.deepseek_api_key
        else:
            base, model, key = self.local_base_url, self.local_model, self.local_api_key
        json_mode = self.summarize_json_mode.lower()
        if json_mode == "auto":
            json_mode = "true"
        thinking = self.summarize_thinking.lower()
        if thinking == "auto":
            thinking = "true" if provider == "deepseek" else "false"
        # 本地小上下文模型用小分块 + 短输出，避免超上下文
        max_input = self.summarize_max_input_chars or (300000 if provider == "deepseek" else 6000)
        max_tokens = self.summarize_max_tokens or (12000 if provider == "deepseek" else 10000)
        env = {
            "DEEPSEEK_API_KEY": key,
            "DEEPSEEK_BASE_URL": base,
            "DEEPSEEK_MODEL": model,
            "DEEPSEEK_JSON_MODE": json_mode,
            "DEEPSEEK_SEND_THINKING": thinking,
            "DEEPSEEK_MAX_RETRIES": str(self.summarize_max_retries),
            "DEEPSEEK_MAX_INPUT_CHARS": str(max_input),
            "DEEPSEEK_MAX_TOKENS": str(max_tokens),
        }
        return env


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")   # 可选；显式环境变量优先
    return Settings()
