"""일봉 OHLCV 수집·저장 (Parquet, ticker별 파티셔닝).

설계
----
- 저장 레이아웃: ``{root}/{ticker}.parquet`` — ML 학습 시 종목별 시계열 read 효율 우선.
- 증분 갱신: 기존 Parquet 의 마지막 일자 다음 영업일부터 ``target_date`` 까지만 fetch.
- pykrx 호출은 ``fetch_daily_bars`` 한 곳에 격리.
- 머지·검증 로직은 순수 함수 → mock 없이 단위 테스트 가능.

데이터 컬럼
-----------
``date`` (datetime64[ns], naive, KST 일자), ``open``, ``high``, ``low``, ``close``,
``volume``, ``trading_value``, ``change`` (float, 등락률 %).

Note: 분봉(1m/5m/30m) 은 pykrx 미지원으로 Phase 2 의 KIS API 누적 수집으로 이연.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
from loguru import logger

from stt.config import settings

if TYPE_CHECKING:
    from collections.abc import Iterable


# ─── 컬럼 명세 ────────────────────────────────────────────────────────────────
COLUMNS: list[str] = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trading_value",
    "change",
]

_PYKRX_COL_MAP: dict[str, str] = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
    "거래대금": "trading_value",
    "등락률": "change",
}


# ─── 경로 ─────────────────────────────────────────────────────────────────────
def default_root() -> Path:
    """기본 일봉 저장 루트: ``settings.raw_dir / 'daily'``."""
    return settings.raw_dir / "daily"


def daily_parquet_path(ticker: str, root: Path | None = None) -> Path:
    return (root or default_root()) / f"{ticker}.parquet"


# ─── 날짜 유틸 ────────────────────────────────────────────────────────────────
def _to_yyyymmdd(d: date | datetime | str) -> str:
    if isinstance(d, datetime):
        return d.strftime("%Y%m%d")
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    if isinstance(d, str):
        s = d.replace("-", "")
        if len(s) != 8 or not s.isdigit():
            raise ValueError(f"date 문자열은 YYYYMMDD 또는 YYYY-MM-DD 형식이어야 함: {d!r}")
        return s
    raise TypeError(f"지원하지 않는 date 타입: {type(d).__name__}")


def _years_back(d: date, years: int) -> date:
    """``years`` 년 전 같은 일자. 윤년 2/29 는 2/28 로."""
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


# ─── pykrx I/O ────────────────────────────────────────────────────────────────
def fetch_daily_bars(ticker: str, from_yyyymmdd: str, to_yyyymmdd: str) -> pd.DataFrame:
    """pykrx 로 단일 종목의 일봉 수집.

    Returns:
        ``COLUMNS`` 순서의 DataFrame. 결과 없으면 빈 DataFrame.
    """
    from pykrx import stock

    raw = stock.get_market_ohlcv(from_yyyymmdd, to_yyyymmdd, ticker)
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=COLUMNS)
    return _normalize_pykrx_frame(raw)


def _normalize_pykrx_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """pykrx 한글 컬럼·DatetimeIndex 를 표준 스키마로 정규화."""
    df = raw.rename(columns=_PYKRX_COL_MAP).copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "date"
    df = df.reset_index()

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[COLUMNS]


# ─── Parquet I/O ──────────────────────────────────────────────────────────────
def load_existing(ticker: str, root: Path | None = None) -> pd.DataFrame:
    """기존 일봉 Parquet 로드. 없으면 빈 DataFrame 반환."""
    path = daily_parquet_path(ticker, root)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    return df.reset_index(drop=True)


def save_daily_bars(
    df: pd.DataFrame, ticker: str, root: Path | None = None
) -> Path:
    """일봉 DataFrame 을 Parquet 으로 저장. 디렉토리는 자동 생성."""
    path = daily_parquet_path(ticker, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


# ─── 머지·검증 (순수 함수) ────────────────────────────────────────────────────
def merge_bars(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """두 DataFrame 을 합치고 ``date`` 기준 중복 제거 + 정렬.

    중복 시 ``new`` 가 ``old`` 를 덮어쓴다 (재수집 신뢰).
    """
    if old.empty and new.empty:
        return pd.DataFrame(columns=COLUMNS)
    combined = pd.concat([old, new], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    return combined.sort_values("date").reset_index(drop=True)[COLUMNS]


def validate_bars(df: pd.DataFrame) -> list[str]:
    """일봉 정합성 검증. 위반 사항을 메시지 리스트로 반환 (빈 리스트 = 통과).

    검사 항목:
      - 컬럼·중복·정렬
      - high ≥ low, high ≥ open/close, low ≤ open/close
      - volume·trading_value ≥ 0
    """
    errors: list[str] = []
    if df.empty:
        return errors

    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        errors.append(f"missing columns: {missing}")
        return errors

    if df["date"].duplicated().any():
        errors.append("duplicate dates present")
    if not df["date"].is_monotonic_increasing:
        errors.append("date not monotonically increasing")

    if (df["high"] < df["low"]).any():
        errors.append("high < low")
    if (df["high"] < df["open"]).any() or (df["high"] < df["close"]).any():
        errors.append("high < open|close")
    if (df["low"] > df["open"]).any() or (df["low"] > df["close"]).any():
        errors.append("low > open|close")

    if (df["volume"] < 0).any():
        errors.append("negative volume")
    if (df["trading_value"] < 0).any():
        errors.append("negative trading_value")

    return errors


# ─── 증분 갱신 ────────────────────────────────────────────────────────────────
def _next_day_yyyymmdd(last_date: pd.Timestamp) -> str:
    return (last_date + timedelta(days=1)).strftime("%Y%m%d")


def update_daily_bars(
    ticker: str,
    *,
    target_date: date | datetime | str,
    history_years: int = 1,
    root: Path | None = None,
) -> pd.DataFrame:
    """단일 종목의 일봉 증분 갱신.

    동작:
      1. 기존 Parquet 로드.
      2. 비어있으면 ``target_date`` 기준 ``history_years`` 년치 수집.
         존재하면 마지막 일자 다음 날부터 ``target_date`` 까지만 수집.
      3. 머지 → 검증 → 저장.

    Returns:
        저장된 최종 DataFrame.

    Raises:
        ValueError: 검증 실패 시.
    """
    target_yyyymmdd = _to_yyyymmdd(target_date)
    target = datetime.strptime(target_yyyymmdd, "%Y%m%d").date()

    existing = load_existing(ticker, root)
    if existing.empty:
        from_yyyymmdd = _years_back(target, history_years).strftime("%Y%m%d")
    else:
        last_date = existing["date"].max()
        if last_date.date() >= target:
            logger.debug(f"{ticker}: 이미 {target} 까지 수집 완료, skip")
            return existing
        from_yyyymmdd = _next_day_yyyymmdd(last_date)

    logger.info(f"{ticker}: fetch {from_yyyymmdd} → {target_yyyymmdd}")
    new = fetch_daily_bars(ticker, from_yyyymmdd, target_yyyymmdd)

    merged = merge_bars(existing, new)
    errors = validate_bars(merged)
    if errors:
        raise ValueError(f"{ticker} 일봉 검증 실패: {errors}")

    save_daily_bars(merged, ticker, root)
    logger.info(
        f"{ticker}: 저장 {len(merged)} 행 ({merged['date'].min().date()} → "
        f"{merged['date'].max().date()})"
    )
    return merged


def update_many(
    tickers: Iterable[str],
    *,
    target_date: date | datetime | str,
    history_years: int = 1,
    root: Path | None = None,
    sleep_sec: float = 0.0,
) -> dict[str, int]:
    """다수 종목 일괄 갱신.

    Args:
        sleep_sec: 호출 간 sleep (pykrx 레이트리밋 보호).

    Returns:
        ``{ticker: row_count}`` (실패 종목은 -1).
    """
    summary: dict[str, int] = {}
    for ticker in tickers:
        try:
            df = update_daily_bars(
                ticker,
                target_date=target_date,
                history_years=history_years,
                root=root,
            )
            summary[ticker] = len(df)
        except Exception as e:
            logger.exception(f"{ticker}: 갱신 실패 — {e}")
            summary[ticker] = -1
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    ok = sum(1 for v in summary.values() if v >= 0)
    logger.info(f"update_many 완료: 성공 {ok}/{len(summary)}")
    return summary
