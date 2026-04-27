"""스모크 테스트: 패키지 import 및 설정 기본값 검증."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "stt",
        "stt.config",
        "stt.logging_setup",
        "stt.collectors",
        "stt.features",
        "stt.labels",
        "stt.models",
        "stt.backtest",
        "stt.api",
        "stt.notifier",
    ],
)
def test_import(module: str) -> None:
    importlib.import_module(module)


def test_settings_defaults() -> None:
    from stt.config import settings

    assert settings.data_dir is not None
    assert settings.kis_env in {"paper", "live"}
    assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def test_setup_logging_runs() -> None:
    from stt.logging_setup import setup_logging

    setup_logging()
