"""Environment-backed settings for the independent job project."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    database_path: str = "./data/job_analysis.db"
    job_provider: str = "fixture"
    boss_cli_command: str = "./.tools/bin/boss"
    boss_cli_timeout_seconds: int = Field(default=30, gt=0, le=120)
    boss_login_timeout_seconds: int = Field(default=180, gt=30, le=600)
    boss_browser_source: str = "existing-browser"
    boss_cdp_url: str = "http://127.0.0.1:9222"
    boss_chrome_path: str = ""
    boss_chrome_profile_path: str = "~/.boss-agent/chrome-profile"
    boss_auto_start_chrome: bool = True
    boss_risk_cooldown_seconds: int = Field(default=900, gt=0, le=3600)
    job_pro_command: str = "./.tools/job-pro/node_modules/.bin/job-pro"
    job_pro_timeout_seconds: int = Field(default=45, gt=0, le=180)
    job_pro_companies: str = "tencent,bytedance,alibaba,meituan,xiaohongshu,jd,kuaishou,baidu,netease,didi,bilibili,pdd,huawei,weibo,mihoyo,pingan,trip,unitree,byd,antgroup,liauto,sf,oppo,xiaomi,nio,minimax,moonshot,zhipu,iqiyi,agibot,lilith,zerooneai,baichuan,sensetime,horizonrobotics,vivo,iflytek,megvii,deepseek,galaxyuniversal,stepfun,cambricon,geely,xpeng,weride,hoyoverse,hikvision,cicc,cainiao,webank"
    job_pro_scope: str = "intern"
    import_timeout_seconds: int = Field(default=15, gt=0, le=60)

    offer_xiansheng_api: str = ""
    offer_xiansheng_timeout_seconds: int = Field(default=20, gt=0, le=60)

    shixiseng_app_id: str = ""
    shixiseng_app_secret: str = ""

    litellm_provider: str = ""
    litellm_model: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_timeout_seconds: int = Field(default=60, gt=0, le=600)

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5175,http://localhost:5175"
    log_level: str = "INFO"

    @field_validator("litellm_provider")
    @classmethod
    def normalize_litellm_provider(cls, value: str) -> str:
        provider = value.strip().lower().rstrip("/")
        if provider and not re.fullmatch(r"[a-z][a-z0-9_-]*", provider):
            raise ValueError("LITELLM_PROVIDER must be a LiteLLM provider name, such as openai")
        return provider

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def database_path_absolute(self) -> Path:
        path = Path(self.database_path).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path_absolute.as_posix()}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
