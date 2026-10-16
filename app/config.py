"""RydeResolve settings. Read from environment variables (or .env), with safe defaults."""
from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field

# 项目根目录（app/config.py 的上两级）
BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = BASE_DIR / "fixtures"
STATIC_DIR = BASE_DIR / "static"
# 自动加载项目根目录 .env（若存在且装了 python-dotenv），方便本地直接放 key
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BASE_DIR / ".env")
except Exception:  # noqa: BLE001
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_first(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n, "").strip()
        if v:
            return v
    return default


@dataclass
class Settings:
    # --- LLM ---
    # "llm" = call an OpenAI-compatible model (needs LLM_API_KEY); "deterministic" = scripted fallback, no key needed.
    # Legacy HUNYUAN_* variable names are still accepted as aliases.
    # an empty value (e.g. a blank variable on a hosting dashboard) counts as unset: Offline demo
    llm_mode: str = field(default_factory=lambda: (os.environ.get("LLM_MODE") or "deterministic").strip().lower())
    llm_api_key: str = field(default_factory=lambda: _env_first("LLM_API_KEY", "GEMINI_API_KEY", "HUNYUAN_API_KEY"))
    llm_base_url: str = field(default_factory=lambda: _env_first(
        "LLM_BASE_URL", "HUNYUAN_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta/openai/"))
    llm_model: str = field(default_factory=lambda: _env_first(
        "LLM_MODEL", "HUNYUAN_MODEL", default="gemini-3.5-flash-lite"))
    llm_max_iterations: int = field(default_factory=lambda: int(os.environ.get("LLM_MAX_ITERATIONS", "14")))
    llm_temperature: float = field(default_factory=lambda: float(os.environ.get("LLM_TEMPERATURE", "0.2")))
    # 置信度低于该阈值则升级人工
    strict_escalation: bool = field(default_factory=lambda: os.environ.get("STRICT_ESCALATION", "false").lower() in ("1", "true", "yes"))
    escalation_threshold: float = field(default_factory=lambda: float(os.environ.get("ESCALATION_THRESHOLD", "0.6")))

    # --- demo login: signs the session cookie. Unset -> a random key per process (sessions end on restart).
    secret_key: str = field(default_factory=lambda: os.environ.get("SECRET_KEY", "").strip())

    # --- 服务 ---
    host: str = field(default_factory=lambda: os.environ.get("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("PORT") or "8000"))   # Render sets PORT; 8000 locally

    # backwards-compatible aliases
    @property
    def hunyuan_api_key(self) -> str: return self.llm_api_key
    @property
    def hunyuan_base_url(self) -> str: return self.llm_base_url
    @property
    def hunyuan_model(self) -> str: return self.llm_model

    @property
    def llm_provider(self) -> str:
        u = (self.llm_base_url or "").lower()
        if "generativelanguage" in u: return "Gemini"
        if "hunyuan" in u or "lkeap" in u: return "Tencent Hunyuan"
        if "openai.com" in u: return "OpenAI"
        return "OpenAI-compatible"

    @property
    def has_api_key(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def effective_mode(self) -> str:
        """If llm is requested but there is no key, downgrade to deterministic."""
        if self.llm_mode == "llm" and not self.has_api_key:
            return "deterministic"
        return self.llm_mode


settings = Settings()
