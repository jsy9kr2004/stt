"""환경 변수 기반 설정 로더.

KIS API 키 등 민감정보는 `.env`에서 읽는다.
설정은 모듈 레벨 싱글턴 ``settings`` 로 노출.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 한국투자증권 KIS API
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_env: str = Field(default="paper", pattern="^(paper|live)$")

    # 로깅
    log_level: str = "INFO"

    # 데이터 경로
    data_dir: Path = Path("./data")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def features_dir(self) -> Path:
        return self.data_dir / "features"

    @property
    def labels_dir(self) -> Path:
        return self.data_dir / "labels"


settings = Settings()
