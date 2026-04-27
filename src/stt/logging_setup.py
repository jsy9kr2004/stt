"""loguru 기반 로깅 설정."""

from __future__ import annotations

import sys

from loguru import logger

from stt.config import settings

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


def setup_logging() -> None:
    """기본 로거 설정. 콘솔 출력, 레벨은 settings에서."""
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, format=_FORMAT)
